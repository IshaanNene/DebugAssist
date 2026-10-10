from __future__ import annotations

import json

from debugassist.llm.concise import TOP_K, concise, concise_text


def _search(n: int) -> str:
    items = [{"repo": "svc", "path": f"src/f{i}.ts", "line": i, "snippet": "x" * 400} for i in range(n)]
    return json.dumps(
        {"evidence_id": "ev_code_0123456789", "kind": "search", "total": n, "items": items}, indent=2
    )


def test_json_is_compact_and_lists_are_top_k() -> None:
    full = _search(25)
    out = concise_text("search_code", full)
    data = json.loads(out)
    assert data["evidence_id"] == "ev_code_0123456789" and data["total"] == 25  # facts kept
    assert len(data["items"]) == TOP_K + 1 and data["items"][-1]["omitted"] == 25 - TOP_K
    assert data["items"][0]["snippet"].endswith("more chars]")  # long strings inside list items are clipped
    assert "\n" not in out and len(out) < len(full) / 3


def test_long_blobs_are_clipped_and_short_values_kept() -> None:
    commit = {"evidence_id": "ev_git_0123456789", "sha": "abc", "message": "fix: x", "patch": "+" * 5_000}
    data = json.loads(concise_text("commit_details", json.dumps(commit)))
    assert data["sha"] == "abc" and data["message"] == "fix: x"
    assert len(data["patch"]) < 1_600 and "more chars" in data["patch"]


def test_plain_text_keeps_the_first_lines() -> None:
    grep = "\n".join(f"src/a.ts:{i}: hit" for i in range(80))
    out = concise_text("grep", grep)
    assert out.count("\n") == 30 and "50 more lines" in out
    assert concise_text("grep", "no matches") == "no matches"


def test_reads_commands_and_skills_are_untouched() -> None:
    body = json.dumps({"content": "y" * 5_000}, indent=2)
    for name in ("read_file", "run_command", "load_skill"):
        assert concise_text(name, body) == body


def test_mcp_text_blocks() -> None:
    blocks = [{"type": "text", "text": _search(12)}]
    out: list[dict[str, str]] = concise("search_code", blocks)
    assert json.loads(out[0]["text"])["items"][-1]["omitted"] == 2
