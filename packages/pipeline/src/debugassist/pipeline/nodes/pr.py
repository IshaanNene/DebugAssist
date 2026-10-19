"""N8 pr_and_notify and N9 post_merge_watch: the PR, Jira, chat and the issue comment."""

from __future__ import annotations

import contextlib
from typing import Any

import httpx

from debugassist.core import hostgit
from debugassist.core.policy import Verdict
from debugassist.integrations.chat import ChatMessage
from debugassist.pipeline import (
    postmerge,
    pr_body,
    release,
)
from debugassist.pipeline.deps import Deps
from debugassist.pipeline.nodes.common import sandbox_for, source_label
from debugassist.pipeline.nodes.ship import commit_trailer, ready_pr_allowed
from debugassist.pipeline.notify import notify
from debugassist.pipeline.state import (
    PRInfo,
    RunState,
)


def app_comment(state: RunState, pr_url: str | None, outcome: str) -> str:
    """What the run says on the GitHub issue it was asked about (starts with the app's marker)."""
    issue, rca = state.issue, state.rca
    assert issue
    o = rca.output if rca else None
    lines = [f"<!-- debugassist:run {state.run_id} -->", "**DebugAssist** looked into this issue."]
    if o:
        lines += ["", o.summary, "", f"**Where:** `{o.location.file}` → `{o.location.function}`"]
        b = state.bisect or {}
        if b.get("result") == "found":
            lines.append(
                f"**Introduced by:** `{b['first_bad']}` {b.get('subject', '')} (bisected with the test)"
            )
        elif o.suspect_commit:
            lines.append(f"**Suspected cause:** `{o.suspect_commit}`")
    if pr_url:
        lines += ["", f"A fix with a reproduction test is ready for review: {pr_url}"]
    else:
        lines += [
            "",
            {
                "rca_only": "No fix proposed: the root cause is outside this repository's code.",
                "escalate": "No fix proposed: this needs a maintainer's decision.",
            }.get(outcome, f"No pull request ({outcome.replace('_', ' ')})."),
        ]
    lines += [
        "",
        f"<sub>Automated analysis, run `{state.run_id}`. Remove the label to stop; remove and re-add it to rerun.</sub>",
    ]
    return "\n".join(lines)


def comment_app_issue(
    deps: Deps, state: RunState, pr_info: PRInfo | None, outcome: str
) -> list[dict[str, Any]]:
    """GitHub App issues: the outcome as a comment on the issue, through the policy gate."""
    issue = state.issue
    if issue is None or issue.app_issue is None or deps.app is None:
        return []
    verdict = deps.gate.verdict("github.comment", repo=issue.gh_repo)
    result: Any = "dry_run"
    marker = f"<!-- debugassist:run {state.run_id} -->"
    if verdict is Verdict.LIVE:
        try:
            if any(c.lstrip().startswith(marker) for c in deps.app.comments(issue.gh_repo, issue.app_issue)):
                result = "already commented"  # a resumed run: this run's comment is there (ROADMAP-100 019)
            else:
                deps.app.comment(
                    issue.gh_repo,
                    issue.app_issue,
                    app_comment(state, pr_info.url if pr_info else None, outcome),
                )
                result = "commented"
        except (httpx.HTTPError, PermissionError, KeyError) as exc:
            result = f"failed: {type(exc).__name__}"
    deps.gate.record(
        "github.comment",
        verdict,
        run_id=state.run_id,
        detail={"repo": issue.gh_repo, "issue": issue.app_issue},
        result=result,
    )
    return [{"kind": "comment", "issue": f"{issue.gh_repo}#{issue.app_issue}", "result": result}]


def link_source(
    deps: Deps, state: RunState, links: list[tuple[str, str | None, str | None]], outcome: str
) -> list[dict[str, Any]]:
    """Attach links to the Vitals issue / BugDrop report and move the report's status along."""
    issue = state.issue
    assert issue
    if issue.source == "bugdrop":
        base = f"{deps.bugdrop_url}/api/reports/{issue.id}"
    elif issue.source == "vitals":
        base = f"{deps.vitals_url}/api/issues/{issue.id}"
    else:
        return []
    notes: list[dict[str, Any]] = []
    verdict = deps.gate.verdict("source.link")
    for kind, url, title in links:
        if not url:
            continue
        result: Any = "dry_run"
        if verdict is Verdict.LIVE:
            try:
                httpx.post(
                    f"{base}/links", json={"kind": kind, "url": url, "title": title or ""}, timeout=10
                ).raise_for_status()
                result = "linked"
            except httpx.HTTPError as exc:
                result = f"failed: {type(exc).__name__}"
        deps.gate.record(
            "source.link", verdict, run_id=state.run_id, detail={"issue": issue.id, "url": url}, result=result
        )
        notes.append({"kind": "link", "issue": issue.id, "url": url, "result": result})
    if issue.source == "bugdrop" and verdict is Verdict.LIVE:
        status = "in_progress" if outcome in ("open_pr", "draft_pr") else "triaged"
        with contextlib.suppress(httpx.HTTPError):  # a convenience; the links above are what matter
            httpx.post(f"{base}/status", json={"status": status}, timeout=10).raise_for_status()
    return notes


async def pr_and_notify(state: RunState, deps: Deps) -> dict[str, Any]:
    issue, tr, rca, ship = state.issue, state.triage, state.rca, state.ship
    assert issue and rca and ship
    notes = list(state.notifications)
    out: dict[str, Any] = {}
    jira_blocks: list[tuple[str, str]] = []
    if rca.output:
        jira_blocks = [
            ("heading", "Root cause (DebugAssist)"),
            ("para", rca.output.summary),
            ("para", rca.output.root_cause),
            ("bullet", "\n".join(f"{c.text} [{', '.join(c.evidence_ids)}]" for c in rca.output.claims[:8])),
        ]
    if ship.outcome in ("open_pr", "draft_pr") and state.fix_attempts:
        sb = sandbox_for(state)
        fa = state.fix_attempts[-1]
        # What is shipped, classified again (a resumed run may carry an older validation): a protected change
        # makes the PR a draft with a warning, whatever the ship decision said.
        shipped = f"v{issue.last_version}"
        flagged = release.flagged(sb.worktree, shipped, release.classify_changes(sb.worktree, shipped))
        v = state.validation
        if v is not None and flagged != v.protected:
            v = v.model_copy(update={"protected": flagged})
            state = state.model_copy(update={"validation": v})
            out["validation"] = v
        loc = rca.output.location if rca.output else None
        scope = (loc.file.split("/")[-2] if loc and "/" in loc.file else issue.component.strip("./")) or "app"
        title = (
            fa.output.commit_title
            if fa.output and fa.output.commit_title.startswith(("fix", "perf", "refactor"))
            else f"fix({scope}): {issue.title[:70]}"
        )[:100]
        # A run resumed after this step committed has nothing left to commit: push what is there (ROADMAP-100 019).
        if hostgit.run(sb.worktree, "status", "--porcelain", check=True).stdout.strip():
            sb.commit(
                f"{title}\n\n{rca.output.root_cause if rca.output else ''}\n\n{commit_trailer(issue)}"
                + (f"\nJira: {tr.jira_key}" if tr and tr.jira_key else "")
            )
        branch = hostgit.run(sb.worktree, "branch", "--show-current", check=True).stdout.strip()
        base = issue.base_branch or f"release/{issue.last_version}"
        push_v = deps.gate.verdict("github.push_branch", repo=issue.gh_repo, branch=branch)
        pr_v = deps.gate.verdict("github.open_pr", repo=issue.gh_repo)
        if push_v is Verdict.LIVE and pr_v is Verdict.LIVE:
            if not deps.github.remote_branch_exists(issue.gh_repo, base):
                raise RuntimeError(
                    f"base branch {base} is not on GitHub; push it first (debugassist scenario inject --push)"
                )
            deps.github.push(sb.worktree, branch)
            # Enforced here too, not only in the ship gate: a resumed run may carry an older ship decision.
            draft = ship.outcome == "draft_pr" or not ready_pr_allowed(state, deps) or bool(flagged)
            pr = deps.github.open_pr(issue.gh_repo, branch, base, title, pr_body.pr_body(state), draft=draft)
            out["pr"] = PRInfo(
                url=pr.url, number=pr.number, branch=branch, base=base, draft=pr.draft, mode=pr.mode
            )
        deps.gate.record(
            "github.open_pr",
            pr_v,
            run_id=state.run_id,
            detail={"repo": issue.gh_repo, "branch": branch, "base": base},
            result=out["pr"].model_dump() if out.get("pr") else None,
        )
    pr_info: PRInfo | None = out.get("pr")
    if tr and tr.jira_key:
        key, gate = tr.jira_key, deps.gate
        if pr_info:
            jira_blocks.append(("para", f"Pull request: {pr_info.url}"))
            title = f"PR #{pr_info.number} (DebugAssist)"
            url = pr_info.url
            gate.gated(
                "jira.link", lambda: deps.jira.link(key, url, title), run_id=state.run_id, detail={"key": key}
            )
        blocks = jira_blocks or [("para", f"DebugAssist outcome: {ship.outcome}")]
        gate.gated(
            "jira.comment", lambda: deps.jira.comment(key, blocks), run_id=state.run_id, detail={"key": key}
        )
        to = "In Review" if pr_info else "In Progress"
        gate.gated(
            "jira.transition",
            lambda: deps.jira.transition(key, to),
            run_id=state.run_id,
            detail={"key": key, "to": to},
        )
    # Link the PR / ticket back to the user-facing issue (Vitals or BugDrop).
    links: list[tuple[str, str | None, str | None]] = (
        [("jira", tr.jira_url, tr.jira_key)] if tr and tr.jira_url and tr.jira_url.startswith("http") else []
    )
    if pr_info:
        links.append(("pr", pr_info.url, f"PR #{pr_info.number} (DebugAssist)"))
    notes += link_source(deps, state, links, ship.outcome)
    notes += comment_app_issue(deps, state, pr_info, ship.outcome)
    if tr:
        o = rca.output
        msg = ChatMessage(
            to=f"@{tr.oncall}",
            title=(
                f"Fix ready for review: {issue.title[:180]}"
                if pr_info
                else f"{ship.outcome.replace('_', ' ')}: {issue.title[:180]}"
            ),
            text=(o.summary if o else "No root cause produced.")[:1500],
            level="success" if pr_info and not pr_info.draft else "warning" if pr_info else "info",
            links={
                "PR": pr_info.url if pr_info else "",
                "Jira": tr.jira_url or "",
                source_label(issue): issue.url,
            },
            fields={
                "Outcome": ship.outcome,
                "Location": f"{o.location.file} → {o.location.function}" if o else "-",
                "Proof": (
                    f"{state.fix_attempts[-1].tier or '-'} test fails before, passes after"
                    if state.validation and state.validation.passed and state.fix_attempts
                    else "not validated"
                ),
            },
        )
        notes.append(notify(deps, state.run_id, msg))
    return {**out, "notifications": notes}


async def post_merge_watch(state: RunState, deps: Deps) -> dict[str, Any]:
    """Start watching the issue after a PR; `debugassist watch <run>` checks it after merge + deploy (D17)."""
    w = postmerge.start(state)
    if w is None:
        return {"status": "done"}
    return {
        "status": "watching",
        "watch": w,
        "notifications": [
            *state.notifications,
            {"kind": "watch", "detail": f"watching after merge + deploy: debugassist watch {state.run_id}"},
        ],
    }
