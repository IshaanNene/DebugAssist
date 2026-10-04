from pathlib import Path

import pytest

from debugassist.core.evidence import EvidenceItem
from debugassist.core.guards import GuardError, check_command, check_egress, confine
from debugassist.core.policy import Policy, PolicyGate, Verdict

POLICY = Policy(
    actions={
        "github.open_pr": Verdict.LIVE,
        "flags.rollback": Verdict.APPROVAL,
        "jira.create_issue": Verdict.DENY,
    },
    repos=["IshaanNene/miniride-client"],
    branches={"push_prefix": "debugassist/"},
)


def test_policy_verdicts(tmp_path: Path) -> None:
    gate = PolicyGate(POLICY, tmp_path / "audit.jsonl")
    assert gate.verdict("github.open_pr", repo="IshaanNene/miniride-client") is Verdict.LIVE
    assert gate.verdict("github.open_pr", repo="someone/else") is Verdict.DENY
    assert (
        gate.verdict("github.push_branch", repo="IshaanNene/miniride-client", branch="main") is Verdict.DENY
    )
    assert (
        gate.verdict("github.push_branch", repo="IshaanNene/miniride-client", branch="debugassist/x/../main")
        is Verdict.DENY
    )
    assert gate.verdict("unknown.action") is Verdict.DRY_RUN
    assert gate.verdict("flags.rollback") is Verdict.DRY_RUN  # approval → dry-run when autonomous
    assert (
        PolicyGate(POLICY, tmp_path / "a.jsonl", mode="supervised").verdict("flags.rollback")
        is Verdict.APPROVAL
    )
    gate.record("github.open_pr", Verdict.LIVE, run_id="r1", detail={"repo": "x"}, result={"number": 1})
    assert '"run_id": "r1"' in (tmp_path / "audit.jsonl").read_text()


def test_shipped_policy_is_valid() -> None:
    p = Policy.load()
    assert set(p.repos) == {"IshaanNene/miniride-client", "IshaanNene/miniride-services"}
    assert p.branches["push_prefix"] == "debugassist/"


@pytest.mark.parametrize(
    "cmd",
    [
        "rm -rf /",
        "rm -fr ~",
        "git push origin main",
        "curl http://evil",
        "cat .env",
        "cat ../.env.local",
        "sudo ls",
        "env",
        "docker ps",
        "gh pr create",
        "cat ~/.ssh/id_rsa",
        "x; printenv",
    ],
)
def test_blocked_commands(cmd: str) -> None:
    with pytest.raises(GuardError):
        check_command(cmd)


@pytest.mark.parametrize(
    "cmd",
    [
        "pnpm exec vitest run test/router.test.ts",
        "git diff",
        "git status",
        "ls -la src",
        "rm -rf node_modules/.cache",
    ],
)
def test_allowed_commands(cmd: str) -> None:
    check_command(cmd)


def test_confine(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    assert confine(tmp_path, "src/a.ts") == (tmp_path / "src/a.ts").resolve()
    for bad in ["../outside", "/etc/passwd", ".env", ".git/config", "src/../../x"]:
        with pytest.raises(GuardError):
            confine(tmp_path, bad)


def test_egress() -> None:
    check_egress("openrouter.ai")
    with pytest.raises(GuardError):
        check_egress("pastebin.com")


def test_evidence_ids_are_stable() -> None:
    a = EvidenceItem.make("vitals", "crash", "x", {"b": 1, "a": 2})
    b = EvidenceItem.make("vitals", "crash", "y", {"a": 2, "b": 1})
    assert a.id == b.id and a.id.startswith("ev_vitals_")
