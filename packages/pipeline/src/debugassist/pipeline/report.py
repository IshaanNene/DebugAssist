"""`debugassist report <run_id>`: one self-contained HTML page documenting a run end to end.

Everything on the page comes from the run's own artifacts (state.json, the decision ledger, the audit
log) plus, when Jira is live, the ticket as Jira holds it at report time. Nothing is computed for show.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from html import escape
from pathlib import Path
from typing import Annotated, Any

import httpx
import typer

from debugassist.core.policy import ROOT
from debugassist.core.settings import Integration, Mode, get_settings
from debugassist.integrations.jira import JiraCloud

RUNS = ROOT / ".data" / "runs"
J = dict[str, Any]
NODE_LABELS = {
    "ingest": "Ingest",
    "auto_triage": "Triage",
    "context_collector": "Context",
    "classify_rca": "Root cause",
    "mitigate": "Mitigate",
    "fix": "Reproduce + fix",
    "validate": "Validate",
    "ship_gate": "Ship gate",
    "pr_and_notify": "PR + notify",
}


def _e(v: Any) -> str:
    return escape("" if v is None else str(v))


def _decisions(run_id: str) -> list[dict[str, Any]]:
    db = ROOT / ".data" / "debugassist.db"
    if not db.is_file():
        return []
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "select decision_id, backend, model, mode, chosen, confidence, band, action, latency_ms, "
        "input_tokens, cost_usd, created_at from decision_ledger where run_id = ? order by created_at",
        (run_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def _audit(run_id: str) -> list[dict[str, Any]]:
    path = ROOT / ".data" / "audit.jsonl"
    if not path.is_file():
        return []
    out: list[dict[str, Any]] = []
    for line in path.read_text().splitlines():
        rec = json.loads(line)
        if rec.get("run_id") == run_id:
            out.append(rec)
    return out


def _jira(key: str | None) -> dict[str, Any] | None:
    s = get_settings()
    if not key or s.mode(Integration.JIRA) is not Mode.LIVE:
        return None
    assert s.jira_base_url and s.jira_email and s.jira_api_key
    try:
        return JiraCloud(s.jira_base_url, s.jira_email, s.jira_api_key.get_secret_value(), "").snapshot(key)
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}


def _ci(pr_url: str | None) -> list[dict[str, Any]] | None:
    """GitHub check runs on the PR head, as GitHub reports them at report time."""
    s = get_settings()
    if not pr_url or not pr_url.startswith("https://github.com/") or s.github_token is None:
        return None
    repo, number = pr_url.removeprefix("https://github.com/").split("/pull/")
    h = {
        "Authorization": f"Bearer {s.github_token.get_secret_value()}",
        "Accept": "application/vnd.github+json",
    }
    try:
        with httpx.Client(base_url="https://api.github.com", headers=h, timeout=20) as gh:
            sha = gh.get(f"/repos/{repo}/pulls/{number}").raise_for_status().json()["head"]["sha"]
            runs = gh.get(f"/repos/{repo}/commits/{sha}/check-runs").raise_for_status().json()["check_runs"]
    except httpx.HTTPError:
        return None
    return [
        {"name": r["name"], "status": r["status"], "conclusion": r["conclusion"], "url": r["html_url"]}
        for r in runs
    ]


def _diff_html(diff: str) -> str:
    rows: list[str] = []
    for line in diff.splitlines():
        cls = (
            "meta"
            if line.startswith(("diff --git", "index ", "--- ", "+++ ", "new file"))
            else "hunk"
            if line.startswith("@@")
            else "add"
            if line.startswith("+")
            else "del"
            if line.startswith("-")
            else ""
        )
        rows.append(f'<span class="{cls}">{_e(line) or " "}</span>')
    return '<pre class="diff">' + "".join(rows) + "</pre>"


def _pill(text: str, kind: str = "") -> str:
    return f'<span class="pill {kind}">{_e(text)}</span>'


def _llm_rows(state: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    rows: list[tuple[str, J]] = []
    rca: J = state.get("rca") or {}
    if rca.get("llm"):
        rows.append(("Root cause (RCA agent)", rca["llm"]))
    attempts: list[J] = state.get("fix_attempts", [])
    for fa in attempts:
        llm: dict[str, J] = fa.get("llm") or {}
        for k, v in llm.items():
            rows.append((f"{k.capitalize()} agent · attempt {fa['n']}", v))
    return rows


def render(run_id: str) -> str:
    state: J = json.loads((RUNS / run_id / "state.json").read_text())
    issue: J = state.get("issue") or {}
    triage: J = state.get("triage") or {}
    rca: J = state.get("rca") or {}
    out: J = rca.get("output") or {}
    mit: J = state.get("mitigation") or {}
    v: J = state.get("validation") or {}
    ship: J = state.get("ship") or {}
    pr: J = state.get("pr") or {}
    attempts: list[J] = state.get("fix_attempts") or [{}]
    fa: J = attempts[-1]
    evidence: dict[str, J] = {e["id"]: e for e in state.get("evidence", [])}
    decisions = _decisions(run_id)
    audit = _audit(run_id)
    jira = _jira(triage.get("jira_key"))
    llm = _llm_rows(state)
    total_s = sum(state.get("timings_ms", {}).values()) / 1000
    llm_cost = sum(state.get("costs", {}).values())
    clef_cost = sum(float(d["cost_usd"] or 0) for d in decisions)
    models = sorted({str(r.get("model")) for _, r in llm if r.get("model")})
    tokens = sum(int(r.get("input_tokens") or 0) + int(r.get("output_tokens") or 0) for _, r in llm)
    tool_calls = sum(len(r.get("tool_calls") or []) for _, r in llm)

    h: list[str] = []
    a = h.append

    # ---- header
    status_kind = "ok" if state.get("status") == "done" and v.get("passed") else "warn"
    a('<header class="hero">')
    a('<div class="brand">DebugAssist <span>run report</span></div>')
    a(f"<h1>{_e(issue.get('title'))}</h1>")
    a('<div class="meta">')
    a(_pill(issue.get("id", ""), "dark") + _pill(f"{issue.get('app')} {issue.get('version')}"))
    a(_pill(f"run {run_id}") + _pill(f"status: {state.get('status')}", status_kind))
    a(_pill(f"{state.get('mode')} · LLM {state.get('llm_mode')}"))
    a("</div></header>")

    # ---- outcome strip
    a('<section class="kpis">')
    for label, value, sub in [
        (
            "Outcome",
            (ship.get("outcome") or "-").replace("_", " "),
            f"PR #{pr.get('number')}" if pr else "no PR",
        ),
        ("Validation", "passed" if v.get("passed") else "not passed", "fails before · passes after · suite"),
        ("Wall clock", f"{total_s / 60:.1f} min", f"{len(state.get('timings_ms', {}))} pipeline steps"),
        ("LLM", f"{tokens / 1000:.0f}k tokens", f"{tool_calls} tool calls · ${llm_cost:.4f}"),
        ("Clef decisions", str(len(decisions)), f"${clef_cost:.5f} on Workers AI"),
    ]:
        a(
            f'<div class="kpi"><div class="k">{_e(label)}</div><div class="v">{_e(value)}</div><div class="s">{_e(sub)}</div></div>'
        )
    a("</section>")

    # ---- links
    a('<section class="links">')
    for label, url in [
        ("Crash in Vitals", issue.get("url")),
        (f"Jira {triage.get('jira_key')}", triage.get("jira_url")),
        (f"Pull request #{pr.get('number')}", pr.get("url")),
    ]:
        if url:
            a(f'<a href="{_e(url)}">{_e(label)} ↗</a>')
    a("</section>")

    # ---- timeline
    timings: dict[str, int] = state.get("timings_ms", {})
    longest = max(timings.values() or [1])
    a(
        '<section><h2>Pipeline</h2><p class="note">The plan is fixed in code; models reason and write code, '
        'Clef makes the decisions, deterministic code takes the actions.</p><div class="timeline">'
    )
    for node, ms in timings.items():
        if node not in NODE_LABELS:
            continue
        w = max(2, int(100 * ms / longest))
        a(
            f'<div class="step"><div class="name">{NODE_LABELS[node]}</div><div class="bar"><i style="width:{w}%"></i></div>'
            f'<div class="ms">{ms / 1000:.1f}s</div></div>'
        )
    a("</div></section>")

    # ---- triage + decisions
    a('<section class="grid2"><div class="card"><h2>Triage</h2><dl>')
    for k, val in [
        ("Priority", triage.get("priority")),
        ("Severity", triage.get("severity")),
        ("Owner", f"{triage.get('owner_team')} ({triage.get('owner_source')})"),
        ("On call", triage.get("oncall")),
        ("Customer impacting", f"{float(triage.get('customer_impacting') or 0):.0%}"),
        (
            "Events / versions",
            f"{issue.get('events')} · {issue.get('first_version')} → {issue.get('last_version')}",
        ),
        ("Ticket", f"{triage.get('jira_key')} ({triage.get('jira_mode')})"),
    ]:
        a(f"<dt>{_e(k)}</dt><dd>{_e(val)}</dd>")
    a("</dl></div>")
    a(
        '<div class="card"><h2>Decisions (Clef)</h2><table><tr><th>Point</th><th>Chosen</th><th>Conf.</th><th>Band</th><th>Action</th><th>Latency</th></tr>'
    )
    for d in decisions:
        chosen: J = json.loads(d["chosen"]) if d["chosen"] else {}
        brief = ", ".join(
            f"{k}={round(x, 2) if isinstance(x, float) else x}" for k, x in list(chosen.items())[:3]
        )
        band = str(d["band"])
        a(
            f"<tr><td><b>{_e(d['decision_id'])}</b><br><small>{_e(d['backend'])}/{_e(d['model'])} · {_e(d['mode'])}</small></td>"
            f"<td><small>{_e(brief)}</small></td><td>{float(d['confidence'] or 0):.2f}</td>"
            f"<td>{_pill(band, {'act': 'ok', 'escalate': 'warn'}.get(band, ''))}</td><td>{_e(d['action'])}</td><td>{_e(d['latency_ms'])} ms</td></tr>"
        )
    a("</table></div></section>")

    # ---- RCA
    a('<section class="card"><h2>Root cause</h2>')
    a(f'<p class="lead">{_e(out.get("summary"))}</p>')
    loc: J = out.get("location") or {}
    a('<div class="meta">' + _pill(f"category: {out.get('category')}", "dark"))
    if loc:
        a(_pill(f"{loc.get('file')} → {loc.get('function') or ''}"))
    if out.get("suspect_commit"):
        a(_pill(f"suspect commit {str(out['suspect_commit'])[:12]}"))
    if out.get("implicated_flag"):
        a(_pill(f"flag {out['implicated_flag']}"))
    a("</div>")
    a(f"<h3>Mechanism</h3><p>{_e(out.get('root_cause'))}</p>")
    a('<h3>Claims, each backed by collected evidence</h3><ol class="claims">')
    for c in out.get("claims", []):
        refs = " ".join(
            f'<span class="ev" title="{_e(evidence[i]["summary"]) if i in evidence else "unknown"}">{_e(i)}</span>'
            for i in c.get("evidence_ids", [])
        )
        a(f"<li>{_e(c.get('text'))} {refs}</li>")
    a("</ol>")
    if out.get("timeline"):
        a('<h3>Timeline</h3><ul class="tl">')
        for t in out["timeline"]:
            a(f"<li><b>{_e(t.get('when'))}</b> {_e(t.get('event'))}</li>")
        a("</ul>")
    a("</section>")

    # ---- evidence
    a(
        '<section class="card"><h2>Evidence collected</h2><table><tr><th>ID</th><th>Source</th><th>Kind</th><th>Summary</th></tr>'
    )
    for e in evidence.values():
        a(
            f"<tr><td><code>{_e(e['id'])}</code></td><td>{_e(e['source'])}</td><td>{_e(e['kind'])}</td><td>{_e(e['summary'])}</td></tr>"
        )
    a("</table></section>")

    # ---- mitigation
    if mit:
        corr: J = mit.get("correlation") or {}
        ex: J = corr.get("exposed") or {}
        un: J = corr.get("unexposed") or {}
        a('<section class="card"><h2>Mitigation</h2>')
        a(
            f"<p>Flag <code>{_e(mit.get('flag'))}</code>: crash rate <b>{float(ex.get('rate') or 0):.0%}</b> of exposed sessions "
            f"({ex.get('affected')}/{ex.get('sessions')}) vs <b>{float(un.get('rate') or 0):.0%}</b> unexposed "
            f"({un.get('affected')}/{un.get('sessions')}); z = {float(corr.get('z') or 0):.1f}, p = {float(corr.get('p_value') or 1):.1e}.</p>"
        )
        a(
            f"<p>{_pill(mit.get('action', ''), 'warn' if mit.get('action') == 'dry_run' else 'ok')} {_e(mit.get('detail'))}</p></section>"
        )

    # ---- fix + validation
    repro: J = fa.get("repro") or {}
    a('<section class="card"><h2>Reproduction and fix</h2>')
    a(
        f"<p><b>Reproduction test</b> <code>{_e(repro.get('test_file'))}</code>: {_e(repro.get('asserts'))}</p>"
    )
    a(f"<p><b>Fails on the release with</b> <code>{_e(repro.get('failure'))}</code></p>")
    if fa.get("diff"):
        a(_diff_html(str(fa["diff"])))
    a("</section>")
    a('<section class="card"><h2>Validation</h2><div class="checks">')
    for key, expect_fail in [
        ("failing_before", True),
        ("passing_after", False),
        ("suite", False),
        ("static", False),
    ]:
        t = v.get(key)
        if not t:
            continue
        ok = (t["exit_code"] != 0) if expect_fail else (t["exit_code"] == 0)
        a(
            f'<div class="check {"ok" if ok else "bad"}"><div class="mark">{"✓" if ok else "✗"}</div><div><b>{_e(t["label"])}</b><br>'
            f"<code>{_e(t['command'])}</code> → exit {t['exit_code']}</div></div>"
        )
    a("</div>")
    ci = _ci(pr.get("url"))
    if ci:
        a('<h3>The target repository\'s CI on the pull request (from GitHub)</h3><div class="meta">')
        for c in ci:
            kind = {"success": "ok", "failure": "bad"}.get(str(c["conclusion"]), "warn")
            label = f"{c['name']}: {c['conclusion'] or c['status']}"
            a(f'<a href="{_e(c["url"])}">{_pill(label, kind)}</a>')
        a("</div>")
    before: J = v.get("failing_before") or {}
    tail = before.get("output_tail")
    if tail:
        a(
            f"<details><summary>Failing-before output (release, without the fix)</summary><pre>{_e(tail[-2500:])}</pre></details>"
        )
    a("</section>")

    # ---- ship + writes
    dec: J = ship.get("decision") or {}
    a('<section class="grid2"><div class="card"><h2>Ship gate</h2>')
    a(
        f"<p>{_pill((ship.get('outcome') or '-').replace('_', ' '), 'dark')} risk {_e(ship.get('risk'))} · Clef p={_e(dec.get('p'))} "
        f"band {_e(dec.get('band'))}</p>"
    )
    if pr:
        a(
            f'<p>Pull request <a href="{_e(pr.get("url"))}">#{_e(pr.get("number"))}</a> '
            f"<code>{_e(pr.get('branch'))}</code> → <code>{_e(pr.get('base'))}</code>{' (draft)' if pr.get('draft') else ''}</p>"
        )
    a("</div>")
    a(
        '<div class="card"><h2>Write actions (policy-gated, audited)</h2><table><tr><th>Action</th><th>Verdict</th><th>Detail</th></tr>'
    )
    for r in audit:
        detail: J = r.get("detail") or {}
        brief = detail.get("key") or detail.get("branch") or detail.get("flag") or detail.get("repo") or ""
        verdict = str(r.get("verdict"))
        a(
            f"<tr><td><code>{_e(r.get('action'))}</code></td><td>{_pill(verdict, {'live': 'ok', 'dry_run': 'warn', 'deny': 'bad'}.get(verdict, ''))}</td>"
            f"<td><small>{_e(brief)}</small></td></tr>"
        )
    a("</table></div></section>")

    # ---- LLM usage
    a('<section class="card"><h2>LLM usage</h2>')
    a(
        f'<p class="note">Model{"s" if len(models) > 1 else ""}: {", ".join(f"<code>{_e(m)}</code>" for m in models)} via OpenRouter. '
        "Agents run with their own sandboxed tools (read, grep, edit, run tests in a network-less container) and MCP servers "
        "(crash analytics, code search, git history, feature flags).</p>"
    )
    a(
        "<table><tr><th>Agent</th><th>Status</th><th>Turns</th><th>Tool calls</th><th>Tokens in / out</th><th>Cost</th></tr>"
    )
    for name, r in llm:
        a(
            f"<tr><td>{_e(name)}</td><td>{_e(r.get('status'))}</td><td>{_e(r.get('turns'))}</td><td>{len(r.get('tool_calls') or [])}</td>"
            f"<td>{int(r.get('input_tokens') or 0):,} / {int(r.get('output_tokens') or 0):,}</td><td>${float(r.get('cost_usd') or 0):.4f}</td></tr>"
        )
    a("</table>")
    for name, r in llm:
        calls: list[J] = r.get("tool_calls") or []
        if not calls:
            continue
        a(f'<details><summary>{_e(name)}: {len(calls)} tool calls</summary><ol class="calls">')
        for c in calls:
            args = json.dumps(c.get("args"), ensure_ascii=False)
            a(
                f"<li><code>{_e(c.get('name'))}</code> <small>{_e(args[:160])}</small>"
                f"{' ' + _pill('evidence ' + str(c.get('evidence_id'))) if c.get('evidence_id') else ''}{'' if c.get('ok') else ' ' + _pill('error', 'bad')}</li>"
            )
        a("</ol></details>")
    a("</section>")

    # ---- Jira
    if jira:
        a('<section class="card"><h2>Jira ticket, as Jira holds it now</h2>')
        if jira.get("error"):
            a(f"<p>{_e(jira['error'])}</p>")
        else:
            a(
                f'<p><a href="{_e(jira["url"])}"><b>{_e(jira["key"])}</b></a> {_e(jira["summary"])}</p><div class="meta">'
            )
            a(_pill(f"status: {jira['status']}", "ok") + _pill(f"priority: {jira.get('priority')}"))
            a("".join(_pill(lb) for lb in jira.get("labels", [])))
            a("</div>")
            a(
                "<p><b>Linked:</b> "
                + ", ".join(
                    f'<a href="{_e(li["url"])}">{_e(li["title"])}</a>'
                    for li in {li["url"]: li for li in jira.get("links", [])}.values()
                )
                + "</p>"
            )
            last = [c for c in jira.get("comments", []) if "Root cause" in c["text"]][-1:]
            for c in last:
                a(
                    f'<h3>Latest DebugAssist comment · {_e(c["created"][:16].replace("T", " "))}</h3><pre class="comment">{_e(c["text"][:1800])}</pre>'
                )
        a("</section>")

    a(
        f"<footer>Generated {datetime.now(UTC):%Y-%m-%d %H:%M} UTC by <code>debugassist report {_e(run_id)}</code> from the run's "
        "artifacts (state.json, decision ledger, audit log) and the live Jira API. Open-source project; not affiliated with Uber or Cloudflare.</footer>"
    )
    body = "\n".join(h)
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>DebugAssist run {_e(run_id)}</title><style>{CSS}</style></head><body><main>{body}</main></body></html>"""


CSS = """
:root{--bg:#f6f7f9;--card:#fff;--ink:#14181f;--mute:#5b6472;--line:#e3e6eb;--accent:#3b5bfd;--ok:#127a3a;--okbg:#e5f6ec;
--warn:#8a5a00;--warnbg:#fff3d6;--bad:#b42318;--badbg:#fde7e5;--code:#f1f3f6}
@media (prefers-color-scheme:dark){:root{--bg:#0e1116;--card:#161b22;--ink:#e6e9ef;--mute:#98a1b0;--line:#283039;--accent:#7c95ff;
--ok:#4ade80;--okbg:#0f2a1a;--warn:#fbbf24;--warnbg:#2a210b;--bad:#f87171;--badbg:#2c1313;--code:#1d232c}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.55 ui-sans-serif,system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
main{max-width:1180px;margin:0 auto;padding:28px 20px 60px}code,pre{font:12.5px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace}
code{background:var(--code);padding:1px 5px;border-radius:5px}a{color:var(--accent);text-decoration:none}a:hover{text-decoration:underline}
.hero{padding:8px 0 18px}.brand{font-weight:700;letter-spacing:.2px;color:var(--accent)}.brand span{color:var(--mute);font-weight:500}
h1{font-size:26px;margin:6px 0 12px;line-height:1.25}h2{font-size:16px;margin:0 0 12px}h3{font-size:13.5px;margin:18px 0 6px;color:var(--mute);text-transform:uppercase;letter-spacing:.5px}
.meta{display:flex;flex-wrap:wrap;gap:6px;margin:6px 0}.pill{display:inline-block;padding:2px 9px;border-radius:999px;background:var(--code);font-size:12.5px;color:var(--ink);border:1px solid var(--line)}
.pill.dark{background:var(--ink);color:var(--bg);border-color:var(--ink)}.pill.ok{background:var(--okbg);color:var(--ok);border-color:transparent}
.pill.warn{background:var(--warnbg);color:var(--warn);border-color:transparent}.pill.bad{background:var(--badbg);color:var(--bad);border-color:transparent}
.kpis{display:grid;grid-template-columns:repeat(5,1fr);gap:12px;margin:8px 0 14px}.kpi{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px}
.kpi .k{color:var(--mute);font-size:12px;text-transform:uppercase;letter-spacing:.5px}.kpi .v{font-size:22px;font-weight:700;margin:2px 0;text-transform:capitalize}.kpi .s{color:var(--mute);font-size:12.5px}
.links{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:18px}.links a{background:var(--card);border:1px solid var(--line);padding:7px 12px;border-radius:9px;font-weight:600}
section{margin:0 0 16px}.card,section>.timeline{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:18px}
section>h2+.note+.timeline{margin-top:4px}.grid2{display:grid;grid-template-columns:1fr 1.4fr;gap:16px}.note{color:var(--mute);margin:-6px 0 10px;font-size:13.5px}
.step{display:grid;grid-template-columns:130px 1fr 60px;gap:10px;align-items:center;padding:3px 0}.step .name{font-weight:600;font-size:13.5px}
.bar{height:10px;background:var(--code);border-radius:6px;overflow:hidden}.bar i{display:block;height:100%;background:var(--accent);border-radius:6px}.ms{text-align:right;color:var(--mute);font-size:12.5px}
dl{display:grid;grid-template-columns:auto 1fr;gap:6px 14px;margin:0}dt{color:var(--mute)}dd{margin:0;font-weight:500}
table{width:100%;border-collapse:collapse;font-size:13.5px}th{text-align:left;color:var(--mute);font-weight:600;font-size:12px;text-transform:uppercase;letter-spacing:.4px}
th,td{padding:7px 8px;border-bottom:1px solid var(--line);vertical-align:top}tr:last-child td{border-bottom:0}small{color:var(--mute)}
.lead{font-size:16.5px;font-weight:500}.claims li{margin:5px 0}.ev{font:11px ui-monospace,monospace;background:var(--okbg);color:var(--ok);padding:1px 6px;border-radius:5px;margin-left:3px;cursor:help}
.tl{padding-left:18px}.tl li{margin:4px 0}
pre{background:var(--code);border-radius:9px;padding:12px;overflow:auto;white-space:pre-wrap;word-break:break-word}
.diff span{display:block}.diff .add{background:var(--okbg);color:var(--ok)}.diff .del{background:var(--badbg);color:var(--bad)}.diff .hunk{color:var(--accent)}.diff .meta{color:var(--mute);font-weight:600}
.checks{display:grid;grid-template-columns:repeat(2,1fr);gap:10px}.check{display:flex;gap:12px;align-items:flex-start;border:1px solid var(--line);border-radius:10px;padding:12px}
.check .mark{width:28px;height:28px;border-radius:50%;display:grid;place-items:center;font-weight:800;flex:none}.check.ok .mark{background:var(--okbg);color:var(--ok)}.check.bad .mark{background:var(--badbg);color:var(--bad)}
details{margin-top:10px}summary{cursor:pointer;color:var(--accent);font-weight:600}.calls li{margin:3px 0}.comment{max-height:380px}
footer{color:var(--mute);font-size:12.5px;margin-top:26px}
@media (max-width:900px){.kpis{grid-template-columns:repeat(2,1fr)}.grid2,.checks{grid-template-columns:1fr}.step{grid-template-columns:100px 1fr 50px}}
"""


def report(
    run_id: Annotated[str | None, typer.Argument(help="run id (default: the latest run)")] = None,
    out: Annotated[
        Path | None, typer.Option(help="output file (default .data/runs/<run_id>/report.html)")
    ] = None,
) -> None:
    """Render one run as a self-contained HTML report."""
    if run_id is None:
        latest = sorted(RUNS.glob("*/state.json"), key=lambda p: p.stat().st_mtime)
        if not latest:
            raise typer.BadParameter("no runs yet")
        run_id = latest[-1].parent.name
    path = out or RUNS / run_id / "report.html"
    path.write_text(render(run_id))
    typer.echo(str(path))
