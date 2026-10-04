"""Catalog integrity: regression applies, hidden test fails on it, reference fix makes everything pass.

Runs in throwaway git worktrees under .data/verify/, never in the target repos' working trees.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from debugassist.scenarios.catalog import ROOT, Bug
from debugassist.scenarios.targets import TargetRepo

WORK = ROOT / ".data" / "verify"


@dataclass
class Check:
    name: str
    ok: bool
    detail: str = ""


@dataclass
class Verification:
    bug: str
    checks: list[Check] = field(default_factory=list[Check])

    @property
    def ok(self) -> bool:
        return all(c.ok for c in self.checks)


def _sh(cmd: str, cwd: Path, timeout: int = 900) -> tuple[int, str]:
    p = subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    return p.returncode, (p.stdout + p.stderr)[-2000:]


def _component(dest: str) -> tuple[str, str]:
    """(component dir relative to repo, test path relative to that dir)."""
    for comp in ("gateway", "dispatch", "payments"):
        if dest.startswith(comp + "/"):
            return comp, dest[len(comp) + 1 :]
    return ".", dest


SETUP = {
    "gateway": "pnpm install --frozen-lockfile --silent",
    "dispatch": "uv sync -q",
    "payments": "go mod download",
    ".": "pnpm install --frozen-lockfile --silent",
}


def _test_cmd(comp: str, test: str | None) -> str:
    if comp == "dispatch":
        return f"uv run pytest -q {test or ''}"
    if comp == "payments":
        return "go test ./..."
    return f"pnpm exec vitest run {test or ''}"


def verify(bug: Bug) -> Verification:
    v = Verification(bug.id)
    if not bug.injection.repos:
        v.checks.append(Check("no code injection", True, "environment-only scenario"))
        return v
    for repo_name, patches in bug.injection.repos.items():
        repo = TargetRepo(repo_name)
        wt = WORK / f"{bug.id}-{repo_name}"
        if wt.exists():
            subprocess.run(["git", "worktree", "remove", "--force", str(wt)], cwd=repo.path, check=False)
            shutil.rmtree(wt, ignore_errors=True)
        repo.git("worktree", "add", "-q", "--detach", str(wt), bug.injection.base)
        try:
            for rel in patches:
                code, out = _sh(f"git am -q --3way {bug.path(rel)}", wt)
                v.checks.append(Check(f"{repo_name}: apply {Path(rel).name}", code == 0, out if code else ""))
                if code:
                    return v
            tests = [h for h in bug.ground_truth.hidden_tests if h.repo == repo_name]
            comps = {(_component(h.dest)[0]) for h in tests} or {"."}
            for comp in comps:
                code, out = _sh(SETUP[comp], wt / comp)
                if code:
                    v.checks.append(Check(f"{repo_name}/{comp}: setup", False, out))
                    return v
            for h in tests:
                shutil.copy(bug.path(h.src), wt / h.dest)
                comp, test = _component(h.dest)
                code, out = _sh(_test_cmd(comp, test), wt / comp)
                v.checks.append(
                    Check(f"{repo_name}: hidden test fails on the regression", code != 0, "" if code else out)
                )
            if bug.ground_truth.fix:
                fix = bug.path(bug.ground_truth.fix)
                code, out = _sh(f"git apply {fix} || git apply --3way {fix}", wt)
                v.checks.append(Check(f"{repo_name}: reference fix applies", code == 0, out if code else ""))
                if code:
                    return v
                for comp in comps:
                    code, out = _sh(_test_cmd(comp, None), wt / comp)
                    v.checks.append(
                        Check(
                            f"{repo_name}/{comp}: all tests pass with the fix",
                            code == 0,
                            "" if code == 0 else out,
                        )
                    )
        finally:
            subprocess.run(
                ["git", "worktree", "remove", "--force", str(wt)],
                cwd=repo.path,
                check=False,
                capture_output=True,
            )
    return v
