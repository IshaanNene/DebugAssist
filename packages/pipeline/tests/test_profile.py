"""profile.for_issue retargets prompts to a real repository by replacing exact MiniRide text. A reflowed prompt line
would silently tell a cachetools run that it is debugging MiniRide; these tests catch that."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from debugassist.core.policy import ROOT
from debugassist.pipeline import profile
from debugassist.pipeline.nodes import load_prompt
from debugassist.pipeline.rca import SUBAGENT_PROMPT
from debugassist.pipeline.state import Issue

FIXTURE = Path(__file__).parent / "fixtures" / "run_state.json"
ABOUT = "cachetools (a Python library of memoizing collections and decorators)"


def issue(about: str | None) -> Issue:
    data = json.loads(FIXTURE.read_text())["issue"]
    return Issue.model_validate({**data, "about": about})


def prompts() -> dict[str, str]:
    """Every prompt the pipeline passes through profile.for_issue."""
    out = {"rca_system.md": load_prompt("rca_system.md")}
    subagents = yaml.safe_load((ROOT / "configs" / "subagents.yaml").read_text())
    for sid, s in (subagents.get("subagents") or subagents).items():
        if isinstance(s, dict) and "description" in s:
            out[f"subagent {sid}"] = SUBAGENT_PROMPT.format(
                sid=sid,
                description=s["description"],  # pyright: ignore[reportUnknownArgumentType]
                focus=" ".join(str(s.get("focus", "")).split()),  # pyright: ignore[reportUnknownMemberType]
            )
    return out


def test_every_retargeted_prompt_names_the_real_repository_and_not_miniride() -> None:
    ps = prompts()
    assert len(ps) > 1  # the RCA prompt and at least one subagent
    for name, prompt in ps.items():
        assert profile.MINIRIDE in prompt, f"{name}: the MiniRide line was reflowed; update profile.MINIRIDE"
        out = profile.for_issue(prompt, issue(ABOUT))
        assert "MiniRide" not in out and "miniride" not in out, name
        assert ABOUT in out, name


def test_miniride_issues_keep_their_prompts_byte_for_byte() -> None:
    for prompt in prompts().values():
        assert profile.for_issue(prompt, issue(None)) == prompt
        assert profile.for_issue(prompt, None) == prompt
