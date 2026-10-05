"""PR description rendered from the `pr-authoring` skill (marketplace/plugins/core/skills/pr-authoring).

The skill's ```template block fixes the section order; this module fills each `{{section}}` from the run
state. Empty sections are dropped together with their heading, so the template stays the single place to
change what every PR looks like.
"""

from __future__ import annotations

import re
from functools import cache
from pathlib import Path

from debugassist.pipeline.state import RunState


def _skill() -> Path:
    from debugassist.harness import marketplace

    path = marketplace.find("pr-authoring")
    if path is None:
        raise RuntimeError("the pr-authoring skill is missing from the marketplace")
    return path


GROUNDING_MARK = {"supported": "✓", "unverified": "? unverified", "unsupported": "✗"}


@cache
def template() -> str:
    skill = _skill()
    m = re.search(r"```template\n(.*?)```", skill.read_text(), re.S)
    if not m:
        raise RuntimeError(f"{skill} has no ```template block")
    return m.group(1)


def render(tpl: str, sections: dict[str, str]) -> str:
    """Fill `{{name}}`; a heading whose section is empty is dropped with it."""
    out: list[str] = []
    pending_heading: str | None = None
    for line in tpl.splitlines():
        m = re.fullmatch(r"\s*\{\{(\w+)\}\}\s*", line)
        if line.startswith("## "):
            pending_heading = line
            continue
        if m:
            body = sections.get(m.group(1), "").strip()
            if body:
                if pending_heading:
                    out.append(pending_heading)
                out.append(body)
            pending_heading = None
            continue
        if pending_heading and line.strip():
            out.append(pending_heading)
            pending_heading = None
        out.append(line)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip() + "\n"


def _cell(text: str) -> str:
    return text.replace("|", "/").replace("\n", " ")


def sections(state: RunState, dashboard_url: str | None = None) -> dict[str, str]:
    issue, tr, rca, m, v, plan = (
        state.issue,
        state.triage,
        state.rca,
        state.mitigation,
        state.validation,
        state.fix_plan,
    )
    assert issue and rca and rca.output
    o = rca.output
    fa = state.fix_attempts[-1] if state.fix_attempts else None
    source = "BugDrop report" if issue.source == "bugdrop" else "Vitals issue"
    what = f"{issue.events} events" if issue.source == "vitals" else "user report"

    links = [
        f"- {source} [{issue.id}]({issue.url}) — `{_cell(issue.title[:120])}` ({what}, {issue.app} {issue.last_version})"
    ]
    if tr and tr.jira_key and tr.jira_url and tr.jira_url.startswith("http"):
        links.append(f"- Jira [{tr.jira_key}]({tr.jira_url})")
    if dashboard_url:
        links.append(f"- Run [{state.run_id}]({dashboard_url})")

    cause = [o.root_cause, "", f"**Location:** `{o.location.file}` → `{o.location.function}`"
             + (f" (line {o.location.line})" if o.location.line else "")]  # fmt: skip
    window = plan.suspect_commits if plan else []
    if window:
        cause.append(
            "**Introduced by:** "
            + "; ".join(f"`{c['sha']}` {c['subject']} ({c['window']})" for c in window[:3])
        )
    elif o.suspect_commit:
        cause.append(f"**Introduced by:** `{o.suspect_commit}`")
    if o.implicated_flag:
        cause.append(f"**Behind flag:** `{o.implicated_flag}`")

    grounding = {g["text"]: g["grounding"] for g in rca.grounding}
    evidence = ["| Claim | Evidence | Check |", "|---|---|---|"]
    evidence += [
        f"| {_cell(c.text)} | {', '.join(f'`{e}`' for e in c.evidence_ids) or '—'} | "
        f"{GROUNDING_MARK.get(grounding.get(c.text, ''), '')} |"
        for c in o.claims
    ]
    if o.timeline:
        evidence += ["", "<details><summary>Timeline</summary>", ""]
        evidence += [f"- **{t.when}** — {t.event}" for t in o.timeline]
        evidence += ["", "</details>"]
    if rca.dropped_claims:
        evidence.append(f"\n_{len(rca.dropped_claims)} claim(s) dropped by the grounding check._")

    mitigation = ""
    if m and m.flag:
        c = m.correlation
        p = c.get("p_value")
        mitigation = (
            f"{m.detail}. Crash rate exposed {c.get('exposed', {}).get('rate')} vs unexposed "
            f"{c.get('unexposed', {}).get('rate')} (z={c.get('z')}, p={p:.2g})."
            if isinstance(p, float)
            else m.detail
        )

    fix = ""
    if fa and fa.output:
        fix = "\n".join(
            [
                fa.output.summary,
                "",
                f"*Why:* {fa.output.rationale}",
                f"*Strategy:* {fa.output.strategy} · *Files:* {', '.join(f'`{f}`' for f in fa.files)}",
            ]
        )

    proof: list[str] = []
    if v and fa:
        tier = {"unit": "unit test", "integration": "integration test", "e2e_env": "E2E test with the user's environment emulated"}.get(
            fa.tier or "", "test"
        )  # fmt: skip
        if fa.repro:
            proof.append(f"Reproduction: `{fa.repro.test_file}` ({tier}) — asserts {fa.repro.asserts}")
            proof.append("")
        rows = [
            ("❌ on the release (must fail)", v.failing_before, True),
            ("✅ with the fix", v.passing_after, False),
            ("full suite", v.suite, False),
            ("CI checks", v.static, False),
        ]
        proof += ["| Check | Command | Exit |", "|---|---|---|"]
        for label, run, expect_fail in rows:
            if run is None:
                continue
            ok = (run.exit_code != 0) if expect_fail else (run.exit_code == 0)
            proof.append(f"| {label} | `{_cell(run.command)}` | {run.exit_code} {'✓' if ok else '✗'} |")
        if not v.passed:
            proof.append("\n**Validation did not pass — this PR is a draft.**")
        if v.failing_before:
            proof += [
                "",
                "<details><summary>Failure on the release</summary>",
                "",
                "```",
                v.failing_before.output_tail[-1500:],
                "```",
                "</details>",
            ]

    risk = fa.output.risk if fa and fa.output else "unknown"
    ship_risk = state.ship.risk if state.ship and state.ship.risk is not None else None
    rollback = [
        f"Risk: **{risk}**"
        + (f" (Clef ship-gate risk {ship_risk:.1f}/4)" if ship_risk is not None else "")
        + f" · {len(fa.files) if fa else 0} file(s), {fa.diff.count(chr(10)) if fa else 0} diff lines.",
        "Rollback: revert this PR"
        + (f"; keep `{m.flag}` off until the fix is deployed" if m and m.flag else "")
        + ".",
        "After deploy: DebugAssist watches the issue's crash/report rate and resolves or reopens it.",
    ]

    cost = sum(state.costs.values())
    footer = (
        f"Opened by **DebugAssist** (automated) · run `{state.run_id}` · reasoning {rca.llm.get('model')} "
        f"({rca.llm.get('mode')}) · decisions by Clef · LLM cost ${cost:.4f}. Review before merging."
    )
    return {
        "summary": o.summary,
        "links": "\n".join(links),
        "root_cause": "\n".join(cause),
        "evidence": "\n".join(evidence),
        "mitigation": mitigation,
        "fix": fix,
        "test_proof": "\n".join(proof),
        "risk_rollback": "\n".join(rollback),
        "footer": footer,
    }


def pr_body(state: RunState, dashboard_url: str | None = None) -> str:
    return render(template(), sections(state, dashboard_url))
