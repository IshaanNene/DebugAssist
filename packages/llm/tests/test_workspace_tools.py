from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from debugassist.integrations.sandbox import CommandResult
from debugassist.llm.workspace_tools import build_workspace_tools, changed_files, is_test_path


@dataclass
class FakeSandbox:
    worktree: Path
    commands: list[tuple[str, str]] = field(default_factory=list[tuple[str, str]])

    def run(self, command: str, *, workdir: str = ".", **_: Any) -> CommandResult:
        self.commands.append((command, workdir))
        return CommandResult(command=command, exit_code=0, output="ok")


def _tools(tmp_path: Path, **kw: Any) -> tuple[dict[str, Any], FakeSandbox]:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.ts").write_text("export const x = 1;\nexport const y = 2;\n")
    (tmp_path / "test").mkdir()
    sb = FakeSandbox(tmp_path)
    tools = build_workspace_tools(sb, **kw)  # pyright: ignore[reportArgumentType]
    return {t.name: t for t in tools}, sb


def test_read_only_tools_by_default(tmp_path: Path) -> None:
    tools, _ = _tools(tmp_path, allow_edits=False, allow_commands=False)
    assert set(tools) == {"list_dir", "read_file", "grep"}
    assert "1  export const x" in tools["read_file"].invoke({"path": "src/a.ts"})
    assert "src/a.ts:2:" in tools["grep"].invoke({"pattern": "y = 2"})


def test_paths_are_confined_to_the_worktree(tmp_path: Path) -> None:
    tools, _ = _tools(tmp_path, allow_edits=True, allow_commands=False)
    assert "blocked" in tools["read_file"].invoke({"path": "../../etc/passwd"}).lower()
    assert "blocked" in tools["write_file"].invoke({"path": "/tmp/x.ts", "content": "x"}).lower()
    assert "blocked" in tools["read_file"].invoke({"path": ".git/config"}).lower()


def test_editable_filter_limits_writes_to_tests(tmp_path: Path) -> None:
    tools, _ = _tools(tmp_path, allow_edits=True, allow_commands=False, editable=is_test_path)
    assert tools["write_file"].invoke({"path": "test/a.test.ts", "content": "it('x')"}).startswith("wrote")
    out = tools["edit_file"].invoke({"path": "src/a.ts", "old_text": "x = 1", "new_text": "x = 3"})
    assert out.startswith("blocked")
    assert "x = 1" in (tmp_path / "src" / "a.ts").read_text()


def test_edit_requires_exactly_one_match(tmp_path: Path) -> None:
    tools, _ = _tools(tmp_path, allow_edits=True, allow_commands=False)
    assert "matched 2 times" in tools["edit_file"].invoke(
        {"path": "src/a.ts", "old_text": "export const", "new_text": "const"}
    )
    assert (
        tools["edit_file"].invoke({"path": "src/a.ts", "old_text": "x = 1", "new_text": "x = 3"})
        == "edited src/a.ts"
    )


def test_commands_run_in_the_sandbox_from_the_component_dir(tmp_path: Path) -> None:
    tools, sb = _tools(tmp_path, allow_edits=False, allow_commands=True, workdir="gateway")
    assert tools["run_command"].invoke({"command": "pnpm test"}).startswith("exit code 0")
    assert sb.commands == [("pnpm test", "gateway")]


def test_changed_files_and_test_paths() -> None:
    diff = "+++ b/src/a.ts\n+++ b/test/a.test.ts\n--- a/src/a.ts\n"
    assert changed_files(diff) == ["src/a.ts", "test/a.test.ts"]
    assert is_test_path("test/router.test.ts") and is_test_path("dispatch/tests/test_x.py")
    assert not is_test_path("src/notifications/router.ts")


def test_edit_tolerates_wrong_indentation_and_reindents(tmp_path: Path) -> None:
    from debugassist.llm.workspace_tools import replace_ignoring_indent

    src = "export function f() {\n    if (x) {\n      return a;\n    }\n}\n"
    old = "      if (x) {\n        return a;\n      }"  # the agent guessed two more spaces
    new = "      if (x) {\n        return b;\n      }"
    assert (
        replace_ignoring_indent(src, old, new)
        == "export function f() {\n    if (x) {\n      return b;\n    }\n}\n"
    )
    assert replace_ignoring_indent(src + src, old, new) is None  # ambiguous: two matches


def test_failed_edit_shows_the_closest_lines(tmp_path: Path) -> None:
    tools, _ = _tools(tmp_path, allow_edits=True, allow_commands=False)
    out = tools["edit_file"].invoke({"path": "src/a.ts", "old_text": "export const y = 3;", "new_text": "z"})
    assert "matched 0 times" in out and "2  export const y = 2;" in out


def test_component_relative_paths_resolve_but_escapes_stay_blocked(tmp_path: Path) -> None:
    (tmp_path / "gateway" / "src").mkdir(parents=True)
    (tmp_path / "gateway" / "src" / "b.ts").write_text("const v = 1;\n")
    sb = FakeSandbox(tmp_path)
    built = build_workspace_tools(sb, allow_edits=True, allow_commands=False, workdir="gateway")  # pyright: ignore[reportArgumentType]
    tools = {t.name: t for t in built}
    assert "1  const v = 1;" in tools["read_file"].invoke({"path": "src/b.ts"})
    assert (
        tools["edit_file"]
        .invoke({"path": "./src/b.ts", "old_text": "v = 1", "new_text": "v = 2"})
        .startswith("edited gateway/src/b.ts")
    )
    assert "blocked" in tools["read_file"].invoke({"path": "../../etc/passwd"}).lower()
    assert "blocked" in tools["write_file"].invoke({"path": "/tmp/x.ts", "content": "x"}).lower()
