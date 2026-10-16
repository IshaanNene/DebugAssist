"""usages: how the code at fault is used elsewhere — docs and stubs first, the most specific names first."""

from __future__ import annotations

import subprocess
from pathlib import Path

from debugassist.pipeline import usages


def _repo(tmp_path: Path, files: dict[str, str]) -> Path:
    for rel, text in files.items():
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(text)
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    return tmp_path


def test_names_are_the_fault_then_the_reports_defined_identifiers_most_specific_first(tmp_path: Path) -> None:
    wt = _repo(
        tmp_path,
        {
            "pkg/core.py": "class Box:\n    def get(self):\n        pass\n\n\ndef memo(f):\n    return f\n",
            "pkg/other.py": "from pkg.core import Box\nBox()\nBox()\nBox()\n",
        },
    )
    report = "It fails:\n```python\nfrom pkg.core import Box, memo\nprint(memo(Box).get())\n```\n"
    assert usages.names_for(wt, "Box.get", report) == ["Box", "get", "memo"]


def test_collect_puts_docs_and_stubs_before_source_and_skips_excluded_files(tmp_path: Path) -> None:
    wt = _repo(
        tmp_path,
        {
            "src/lib.py": "def head(xs, n=1):\n    return xs[:n]\n",
            "src/use.py": "from lib import head\nhead([1])\n",
            "src/lib.pyi": "def head(xs: list[int], n: int = 1) -> list[int]: ...\n",
            "docs/index.rst": "Call ``head(xs, n=0)`` for nothing.\n",
            "CHANGELOG.rst": "head: fixed\n",
        },
    )
    out = usages.collect(wt, ["head"], exclude={"src/lib.py"})
    headers = [line for line in out.splitlines() if line.startswith("---")]
    assert [h.split()[1].split(":")[0] for h in headers] == ["docs/index.rst", "src/lib.pyi", "src/use.py"]
    assert "CHANGELOG" not in out and "return xs[:n]" not in out


def test_a_reports_prose_gives_no_names_only_its_code(tmp_path: Path) -> None:
    wt = _repo(tmp_path, {"pkg/core.py": "def call(x):\n    pass\n\n\ndef memo(f):\n    return f\n"})
    report = {"body": "Any call fails.\n\n```python\nmemo(1)\n```\n", "url": "https://example.test/1"}
    assert usages.report_text(report).count("\n") > 2  # real newlines, not JSON escapes
    assert usages.names_for(wt, None, usages.report_text(report)) == ["memo"]
