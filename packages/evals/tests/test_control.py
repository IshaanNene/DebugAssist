"""The no-model localization control (evals.control)."""

from __future__ import annotations

from pathlib import Path

from debugassist.evals import control


def test_the_innermost_in_app_frame_wins() -> None:
    event = {
        "frames": [
            {"function": "<anonymous>", "file": "src/main.tsx", "in_app": True},
            {"function": "routeV2", "file": "src/notifications/router.ts", "in_app": True},
            {"function": "dispatch", "file": "node_modules/react/index.js", "in_app": False},
        ]
    }
    loc = control.frame_location(event)
    assert loc and (loc["file"], loc["function"]) == ("src/notifications/router.ts", "routeV2")
    assert control.frame_location({"frames": [{"function": "x", "file": "/app/src/dispatch/m.py"}]}) == {
        "file": "src/dispatch/m.py",
        "function": "x",
        "how": "top in-app frame",
    }
    assert control.frame_location({}) is None


def test_called_names_skip_what_the_report_defines_and_builtins() -> None:
    text = """
    class Example:
        def value(self, number):
            return number
    example = Example()
    print(Example.value(example, 3))
    print(list(ichunked(rows, 0)))
    """
    assert control.called_names(text) == ["ichunked"]


def test_the_definition_is_found_per_language_outside_tests(tmp_path: Path) -> None:
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "more.py").write_text("def ichunked(it, n):\n    pass\n")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_more.py").write_text("def ichunked():\n    pass\n")
    assert control.definition("ichunked", tmp_path, "python") == "pkg/more.py"
    (tmp_path / "math.go").write_text("func (d Decimal) Ln(precision int32) (Decimal, error) {\n}\n")
    assert control.definition("Ln", tmp_path, "go") == "math.go"
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "toggle.ts").write_text("export function toggle<T>(xs: T[]) {}\n")
    assert control.definition("toggle", tmp_path, "typescript") == "src/toggle.ts"
    loc = control.locate(
        {"title": "x", "report": {"body": "ichunked(rows, 0) raises"}, "language": "python"}, tmp_path
    )
    assert loc and loc["file"] == "pkg/more.py" and loc["function"] == "ichunked"
    assert control.locate({"title": "battery drain", "language": "python"}, tmp_path) is None
