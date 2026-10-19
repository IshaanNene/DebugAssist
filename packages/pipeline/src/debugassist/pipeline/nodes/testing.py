"""Running tests in the run's sandbox: test commands, the reproduction contract, worktree hygiene."""

from __future__ import annotations

from typing import Any, cast

from langchain_core.tools import BaseTool, tool

from debugassist.core import hostgit
from debugassist.core.policy import ROOT
from debugassist.integrations.sandbox import CommandResult, Sandbox
from debugassist.llm.workspace_tools import is_test_path
from debugassist.pipeline import (
    e2e,
)
from debugassist.pipeline.nodes.common import pipeline_yaml, repro_problem, run_on_release, static_problem
from debugassist.pipeline.state import (
    Issue,
    Tier,
)


def apply_diff(sb: Sandbox) -> Any:
    def apply(diff: str) -> None:
        hostgit.run(sb.worktree, "apply", "--whitespace=nowarn", "-", input=diff, check=True)

    return apply


def worktree_status(sb: Sandbox) -> list[str]:
    """Paths `git status` reports, both sides of a rename included; NUL-separated, so quoted, escaped and
    renamed paths (`old -> new`) are not misread (audit P3-22)."""
    raw = hostgit.run(
        sb.worktree, "status", "--porcelain=v1", "-z", "--untracked-files=all", check=True
    ).stdout
    parts, out, i = raw.split("\0"), list[str](), 0
    while i < len(parts):
        entry, i = parts[i], i + 1
        if not entry:
            continue
        out.append(entry[3:])
        if "R" in entry[:2] or "C" in entry[:2]:  # the source path follows as its own field
            out.append(parts[i])
            i += 1
    return out


def revert_non_tests(sb: Sandbox) -> None:
    for path in worktree_status(sb):
        if is_test_path(path):
            continue
        if hostgit.run(sb.worktree, "cat-file", "-e", f"HEAD:{path}").returncode == 0:
            hostgit.run(sb.worktree, "checkout", "-q", "HEAD", "--", path, check=False)
        else:  # new in the worktree: drop it from the index (intent-to-add) and from disk
            hostgit.run(sb.worktree, "rm", "-q", "--cached", "--ignore-unmatch", "--", path, check=False)
            (sb.worktree / path).unlink(missing_ok=True)


def new_test_files(sb: Sandbox) -> list[str]:
    tests = [f for f in worktree_status(sb) if is_test_path(f) and (sb.worktree / f).is_file()]
    return sorted(set(tests), key=lambda f: (sb.worktree / f).stat().st_mtime)


def test_cmd(language: str, test_file: str, component: str, template: str | None = None) -> str:
    """The pipeline, not the agent, decides how the reproduction test is run: the repo's own `test_one` command
    from its .DebugAssist/pipeline.yaml when it declares one, else the language's default runner."""
    rel = test_file if component == "." else test_file.removeprefix(f"{component}/")
    if template:
        return template.format(file=rel)
    if language == "python":
        return f"uv run --offline pytest -q {rel}"
    if language == "go":
        pkg = "./" + rel.rsplit("/", 1)[0] if "/" in rel else "."
        return f"go test {pkg}"
    return f"pnpm exec vitest run {rel}"


def run_test(sb: Sandbox, issue: Issue, cmd: str) -> CommandResult:
    """Unit/integration tests run in the sandbox; E2E specs run against a build of the worktree."""
    if e2e.is_e2e_cmd(cmd):
        return e2e.run(sb, pipeline_yaml(sb.worktree, issue), issue.component, cmd)
    return sb.run(cmd, workdir=issue.component)


def repro_cmd(issue: Issue, test_file: str) -> str:
    rel = test_file if issue.component == "." else test_file.removeprefix(f"{issue.component}/")
    if rel.startswith("e2e/"):
        return e2e.e2e_cmd(test_file, issue.component)
    # The same source as `test`, `lint` and `setup` (ROADMAP-100 014): the release's own config, read through the
    # target's main checkout (no agent writes there), not that checkout's working copy, which may have moved on.
    try:
        cfg: dict[str, Any] = pipeline_yaml(ROOT / "targets" / issue.repo, issue) or {}
    except (OSError, RuntimeError):  # no checkout or no config: the language's default runner
        cfg = {}
    comps = cast(dict[str, dict[str, Any]], cfg.get("components") or {})
    template = cast(str | None, (comps.get(issue.component) or {}).get("test_one"))
    return test_cmd(issue.language, test_file, issue.component, template)


def tier_problem(tier: Tier, issue: Issue, test_file: str) -> str | None:
    rel = test_file if issue.component == "." else test_file.removeprefix(f"{issue.component}/")
    if tier == "e2e_env" and not rel.startswith("e2e/"):
        return f"this step needs a Playwright spec under e2e/, not {test_file}."
    if tier != "e2e_env" and rel.startswith("e2e/"):
        return f"this step needs a {tier} test next to the existing tests, not a Playwright spec."
    return None


def e2e_tool(sb: Sandbox, issue: Issue) -> BaseTool:
    """Lets the agent check its spec: the pipeline builds the worktree and runs the spec in the isolated
    E2E runner (the agent's own sandbox has no network)."""

    @tool
    def run_e2e(test_file: str) -> str:
        """Build the app from the worktree and run one Playwright spec (e2e/….spec.ts) against the live
        backends. Slow (about a minute): use it to check your spec before submitting."""
        if tier_problem("e2e_env", issue, test_file) or not (sb.worktree / test_file).is_file():
            return f"{test_file} is not an existing spec under e2e/"
        res = e2e.run(
            sb, pipeline_yaml(sb.worktree, issue), issue.component, e2e.e2e_cmd(test_file, issue.component)
        )
        return f"exit code {res.exit_code}\n{res.output[-3500:]}"

    return run_e2e


def fix_contract_problem(
    sb: Sandbox, issue: Issue, comp: dict[str, Any], base: str, cmd: str, test_file: str
) -> str | None:
    """Why the worktree's change is not (yet) a proven fix; None when it is: the reproduction test still
    fails on the release with only the source change reverted, passes with it, and the suite and the
    repository's CI checks pass. A test weakened to pass is therefore rejected."""
    if not (sb.worktree / test_file).is_file():
        return f"the reproduction test {test_file} is missing; restore it"
    before = run_on_release(sb, base, lambda rsb: run_test(rsb, issue, cmd))
    if before is None:
        return "you have not changed any source file yet"
    if problem := repro_problem(cmd, before.exit_code, before.output, issue):
        return (
            f"with your source change reverted, the reproduction test no longer reproduces the bug: {problem}"
        )
    res = run_test(sb, issue, cmd)
    if res.exit_code != 0:
        return f"the reproduction test still fails with your change:\n{res.output[-1200:]}"
    suite = sb.run(str(comp["test"]), workdir=issue.component)
    if suite.exit_code != 0:
        return f"the component suite fails:\n{suite.output[-1200:]}"
    return static_problem(sb, comp, issue.component)


def reset_to(sb: Sandbox, base: str) -> None:
    # Every attempt (and a resumed run) starts from the release tag, not the branch head: after a PR
    # the bot branch holds the previous fix commit. Ignored dirs (node_modules…) survive.
    hostgit.run(sb.worktree, "reset", "-q", "--hard", base, check=True)
    hostgit.run(sb.worktree, "clean", "-qfd", check=False)


def file_at_release(sb: Sandbox, base: str, path: str) -> str | None:
    """The file as it is in the release, None if it is not there. (Not `git ls-files`: the runner's diff marks new
    files intent-to-add, which lists them as tracked.)"""
    out = hostgit.run(sb.worktree, "show", f"{base}:{path}")
    return out.stdout if out.returncode == 0 else None
