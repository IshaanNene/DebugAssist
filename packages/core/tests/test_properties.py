"""Property tests (ROADMAP-100 023, 024): redaction never lets a credential through and leaves diagnostics alone;
path confinement, host-side walks and the git-dir check never point outside the worktree, whatever the input."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

from debugassist.core import hostgit
from debugassist.core.guards import GuardError, confine, walk_files
from debugassist.core.redaction import redact_secrets, redact_text

BODY = st.text(
    alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789", min_size=20, max_size=40
)
PREFIX = st.sampled_from(
    ["ghp_", "gho_", "ghs_", "ghu_", "ghr_", "github_pat_", "gsk_", "sk-", "sk-or-v1-", "xoxb-"]
)
WORDS = st.sampled_from(
    ["error", "at", "line", "42", "File", "main.py", "TypeError:", "cannot", "read", "undefined", "(reading",
     "'x')", "->", "took", "1234", "ms", "v1.6.1", "retry", "3/3", "failed", "assert", "==", "None", "ok"]
)  # fmt: skip
TEXT = st.lists(WORDS, max_size=12).map(" ".join)


@given(PREFIX, BODY, TEXT, TEXT)
def test_a_prefixed_key_never_survives(prefix: str, body: str, before: str, after: str) -> None:
    secret = prefix + body
    raw = f"{before} {secret} {after}"
    for redacted in (redact_secrets(raw), redact_text(raw)):
        assert secret not in redacted and body not in redacted


@given(st.sampled_from(["OPEN_ROUTER_API_KEY", "CLOUDFLARE_API_KEY", "GITHUB_TOKEN", "GROQ_CLOUD_API",
                        "GITHUB_APP_WEBHOOK_SECRET", "DB_PASSWORD"]), BODY, st.sampled_from(["=", ": ", "='", '="']))  # fmt: skip
def test_a_value_assigned_to_a_credential_name_never_survives(name: str, body: str, sep: str) -> None:
    assert body not in redact_secrets(f"{name}{sep}{body}")


@given(TEXT)
def test_diagnostics_without_credentials_are_left_alone(text: str) -> None:
    assert redact_secrets(text) == text


@given(st.text(max_size=200))
def test_secret_redaction_is_idempotent(text: str) -> None:
    once = redact_secrets(text)
    assert redact_secrets(once) == once


SEGMENT = st.sampled_from(["a", "b", "..", ".", "src", "x.ts", ".git", ".env", "", "~", "/etc"])


@given(st.lists(SEGMENT, min_size=1, max_size=6).map("/".join))
def test_confine_returns_only_paths_inside_the_root(rel: str) -> None:
    with tempfile.TemporaryDirectory() as d:
        root = Path(d) / "wt"
        root.mkdir()
        try:
            p = confine(root, rel)
        except GuardError:
            return
        assert p == root.resolve() or root.resolve() in p.parents
        assert ".git" not in p.relative_to(root.resolve()).parts and p.name != ".env"


LINK_TARGETS = st.sampled_from(["../outside", "../../outside", "/", "inside", "sub", "sub/f", "../wt/sub"])


@settings(max_examples=60, deadline=None)
@given(st.lists(st.tuples(st.sampled_from(["l1", "l2", "sub/l3"]), LINK_TARGETS), max_size=4))
def test_walk_files_never_returns_a_link_or_a_file_outside(links: list[tuple[str, str]]) -> None:
    with tempfile.TemporaryDirectory() as d:
        base = Path(d)
        (base / "outside").mkdir()
        (base / "outside" / "secret").write_text("x")
        root = base / "wt"
        (root / "sub").mkdir(parents=True)
        (root / "sub" / "f").write_text("y")
        (root / "inside").write_text("z")
        for name, target in links:
            link = root / name
            if not link.exists() and not link.is_symlink():
                os.symlink(target, link)
        for f in walk_files(root):
            assert not f.is_symlink() and root.resolve() in f.resolve().parents


@settings(max_examples=60, deadline=None)
@given(st.sampled_from(["gitdir: {wt}/fake", "gitdir: ../../evil", "gitdir: {base}/repo/.git/worktrees/x",
                        "gitdir: {wt}", "gitdir:", "nonsense", "gitdir: /"]))  # fmt: skip
def test_a_planted_dot_git_file_never_yields_a_git_dir_inside_the_worktree(content: str) -> None:
    with tempfile.TemporaryDirectory() as d:
        base = Path(d).resolve()
        wt = base / "wt"
        (wt / "fake").mkdir(parents=True)
        (wt / "fake" / "gitdir").write_text(str(wt / ".git"))  # a forged back-pointer, inside the worktree
        (wt / ".git").write_text(content.format(wt=wt, base=base))
        got = hostgit.trusted_gitdir(wt)
        assert got is None or (wt not in got.parents and got != wt)
