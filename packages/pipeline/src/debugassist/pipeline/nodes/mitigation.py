"""N4 mitigate: a feature-flag rollback when the evidence and the policy allow it."""

from __future__ import annotations

import re
from typing import Any

import httpx

from debugassist.core.policy import Verdict
from debugassist.decisions.engine import RunContext
from debugassist.decisions.state import CompactState
from debugassist.pipeline.deps import Deps
from debugassist.pipeline.state import (
    Mitigation,
    RunState,
)


def flag_names() -> list[str]:
    from debugassist.mcp_servers import feature_flags as ff

    try:
        return [str(f["name"]) for f in ff.list_flags()["flags"]]
    except Exception:  # flag service unreachable (mock runs): fall back to the leading identifier
        return []


def known_flag(raw: str, known: list[str]) -> str | None:
    """The flag `raw` names: an exact match, else the first known flag named in it as a whole word. Without a
    flag list, the leading identifier of `raw` ("notif_router_v2 (…)" → notif_router_v2)."""
    if raw in known:
        return raw
    if not known:
        m = re.match(r"\s*([A-Za-z0-9_.-]+)", raw)
        return m.group(1) if m and m.group(1).lower() not in ("none", "n/a") else None
    hits = [
        (m.start(), name) for name in known if (m := re.search(rf"(?<![\w-]){re.escape(name)}(?![\w-])", raw))
    ]
    return min(hits)[1] if hits else None


async def mitigate(state: RunState, deps: Deps) -> dict[str, Any]:
    from debugassist.mcp_servers import feature_flags as ff

    issue, rca = state.issue, state.rca
    assert issue and rca and rca.output
    corr_items = [e.data for e in state.evidence if e.kind == "flag_correlation"]
    raw = rca.output.implicated_flag or (corr_items[0]["flag"] if corr_items else None)
    # The RCA's flag is free text from the LLM ("notif_router_v2 (flag is off …)"): only a real flag acts.
    flag = known_flag(raw, flag_names()) if raw else None
    if not flag:
        return {"mitigation": Mitigation(detail="no feature flag implicated; nothing to roll back")}
    current = ff.get_flag(flag)
    cs = CompactState().add("flag", {"name": flag, "rollout_pct": current["rollout_pct"]}, priority=0)
    if issue.fingerprint:
        # A crash group: compare the crash rate of sessions exposed to the flag with the rest.
        corr = ff.flag_crash_correlation(issue.fingerprint, flag)
        signal = {
            k: corr[k]
            for k in ("exposed", "unexposed", "z", "p_value", "significant", "share_of_affected_exposed")
        }
        supported = bool(corr["significant"])
        cs.add("crash_rates", {k: v for k, v in signal.items() if k != "significant"}, priority=0)
    elif rca.output.category == "flag_config":
        # A rider report has no crash group to split by exposure, but the RCA found the flag's configuration to
        # be the defect itself. D11 weighs that against the flag's rollout and its recent changes.
        events = ff.rollout_history(flag, limit=5)["events"]
        signal = {"source": "rca: flag configuration is the defect", "recent_changes": events}
        supported = bool(events) and bool(current["rollout_pct"])
        cs.add("recent_changes", events, priority=0)
    elif issue.source == "bugdrop":
        # Rider reports instead of a crash group: do the reports come from sessions exposed to the flag far more
        # often than its rollout share would give? (ROADMAP-100 020; D11 was calibrated on crash rates only.)
        try:
            corr = ff.flag_report_correlation(issue.app, flag)
        except httpx.HTTPError:
            corr = None
        if not corr or not corr.get("reports"):
            return {
                "mitigation": Mitigation(flag=flag, detail=f"{flag}: no reports with flag data to compare")
            }
        signal = {
            k: corr[k]
            for k in ("reports", "exposed_reports", "rollout_pct", "share_exposed", "p_value", "significant")
        }
        supported = bool(corr["significant"])
        cs.add("report_exposure", {k: v for k, v in signal.items() if k != "significant"}, priority=0)
    else:
        return {
            "mitigation": Mitigation(
                flag=flag,
                detail=f"{flag}: no crash group to compare exposure against; rollback not considered",
            )
        }
    cs.add(
        "rca",
        {"category": rca.output.category, "summary": rca.output.summary, "root_cause": rca.output.root_cause},
        priority=1,
    )
    d11 = await deps.engine.decide("D11", cs, ctx=RunContext(run_id=state.run_id, issue_id=issue.id))
    m = Mitigation(
        flag=flag,
        correlation=signal,
        decision={"p": d11.p, "band": d11.band, "action": d11.action},
    )
    if d11.action == "rollback_flag" and supported and not current["rollout_pct"]:
        m.detail = f"{flag}: rollback warranted, but the flag is already at 0% — nothing to roll back"
    elif d11.action == "rollback_flag" and supported:
        verdict = deps.gate.verdict("flags.rollback")
        if verdict is Verdict.APPROVAL:
            from langgraph.types import interrupt

            approved = interrupt(
                {
                    "question": f"Roll back {flag} from {current['rollout_pct']}% to 0%?",
                    "flag": flag,
                    "correlation": m.correlation,
                }
            )
            verdict = Verdict.LIVE if approved else Verdict.DRY_RUN
        res = ff.apply_rollout(
            flag,
            0,
            reason=f"{issue.id}: {rca.output.summary[:200]}",
            authorized=verdict is Verdict.LIVE,
            gate=deps.gate,
            run_id=state.run_id,
        )
        m.action = "rolled_back" if res["applied"] else "dry_run"
        m.rolled_back_from = int(res["from_percent"])
        m.detail = f"{flag}: {res['from_percent']}% → 0% ({'applied' if res['applied'] else 'dry run — policy requires approval'})"
    else:
        m.detail = f"{flag}: no rollback (Clef band {d11.band}, evidence supports it: {supported})"
    return {"mitigation": m, "decisions": [*state.decisions, d11.ledger_id or ""]}
