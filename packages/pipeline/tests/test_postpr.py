# pyright: reportPrivateUsage=false, reportUnknownLambdaType=false, reportUnknownArgumentType=false
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from debugassist.core.policy import PolicyGate
from debugassist.decisions.policy import Band
from debugassist.integrations.chat import ChatMock
from debugassist.llm.spec import LLMResult
from debugassist.pipeline import feedback, postpr
from debugassist.pipeline.state import RunState

FIXTURE = Path(__file__).parent / "fixtures" / "run_state.json"


def run_state() -> RunState:
    return RunState.model_validate(json.loads(FIXTURE.read_text()))


def write_skill(root: Path, body: str = "Keep diffs small.") -> Path:
    p = root / "plugins" / "web-crash" / "skills" / "web-client-fixes" / "SKILL.md"
    p.parent.mkdir(parents=True)
    p.write_text(
        f"---\nname: web-client-fixes\ndescription: d\n---\n\n# Fixing\n\n{body}\n\n## Lessons from reviews\n"
    )
    return p


class FakeLedger:
    def __init__(self, rows: list[Any]) -> None:
        self.rows = rows
        self.labels: dict[str, Any] = {}

    async def list(self, *, run_id: str | None = None, decision_id: str | None = None) -> list[Any]:
        return self.rows

    async def label(self, row_id: str, outcome: Any, *, source: str) -> None:
        self.labels[row_id] = (outcome, source)


def d18(kind: str, action: str, p: float = 0.9) -> Any:
    class Engine:
        def __init__(self) -> None:
            self.ledger: Any = None

        async def decide(self, decision_id: str, cs: Any, **kw: Any) -> Any:
            assert decision_id == "D18"
            return SimpleNamespace(chosen={"kind": kind}, p=p, band=Band.ACT, action=action, ledger_id="d18")

    return Engine()


def deps(tmp_path: Path, engine: Any) -> Any:
    return SimpleNamespace(
        engine=engine,
        gate=PolicyGate(mode="autonomous", audit_path=tmp_path / "audit.jsonl"),
        chat=ChatMock(tmp_path / "inbox.jsonl"),
        agent_type={"skills": {"fix": ["web-client-fixes"]}},
    )


@pytest.fixture(autouse=True)
def data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(feedback, "DATA", tmp_path / "data")
    return tmp_path / "data"


async def test_a_thumbs_up_on_a_claim_labels_its_grounding_decision(tmp_path: Path) -> None:
    s = run_state()
    assert s.rca and s.rca.output
    claim = s.rca.output.claims[0].text
    s.rca.grounding = [{"claim": 0, "text": claim, "grounding": "supported", "p": 0.9}]
    rows = [
        SimpleNamespace(
            id="g1",
            decision_id="D09_grounding",
            questions={"supported.c1": {"instructions": f'Claim c1: "{claim}". Is it?'}},
        ),
        SimpleNamespace(
            id="g2",
            decision_id="D09_grounding",
            questions={"supported.c2": {"instructions": "Claim c2: other"}},
        ),
    ]
    engine = d18("praise", "label_store")
    engine.ledger = FakeLedger(rows)
    out = await feedback.route(s, deps(tmp_path, engine), {"target": "claim:0", "reaction": "up"})
    assert out == {"target": "claim:0", "reaction": "up", "labelled": ["g1"], "action": "label_store"}
    assert engine.ledger.labels["g1"] == ({"claim_true": True, "comment": "", "correct": True}, "review")


async def test_a_root_cause_correction_is_labelled_and_logged_for_prompts(
    tmp_path: Path, data_dir: Path
) -> None:
    out = await feedback.route(
        run_state(),
        deps(tmp_path, d18("root_cause", "label_store")),
        {"target": "rca", "reaction": "down", "comment": "it is the cache, not the router"},
    )
    assert out["kind"] == "root_cause" and out["action"] == "label_store"
    assert "classify_rca" in (data_dir / "prompt_log.jsonl").read_text()
    assert "the cache" in (data_dir / "labels.jsonl").read_text()


async def test_unclear_feedback_goes_to_a_human_in_chat(tmp_path: Path) -> None:
    d = deps(tmp_path, d18("other", "human", 0.4))
    out = await feedback.route(
        run_state(), d, {"target": "fix", "reaction": "down", "comment": "hmm, not sure about this"}
    )
    assert out["action"] == "human" and d.chat.inbox()[0]["title"].startswith("Review feedback on VIT-1001")


async def test_style_feedback_proposes_a_skill_update_on_a_local_branch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    skill = write_skill(repo / "marketplace")
    for args in (
        ["init", "-q"],
        ["add", "."],
        ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "init"],
    ):
        subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)
    monkeypatch.setattr(feedback, "ROOT", repo)
    monkeypatch.setattr(feedback, "DATA", repo / ".data")
    monkeypatch.setattr(feedback.skills, "find", lambda name, root=None: skill)
    d = deps(tmp_path, d18("style", "skill_update"))
    out = await feedback.route(
        run_state(),
        d,
        {"target": "fix", "reaction": "down", "comment": "Put new cases in the existing test file."},
    )
    prop = out["proposal"]
    assert prop["status"] == "proposed" and prop["branch"].startswith("debugassist/skill-web-client-fixes-")
    shown = subprocess.run(
        ["git", "show", f"{prop['branch']}:marketplace/plugins/web-crash/skills/web-client-fixes/SKILL.md"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert "_(style; review of VIT-1001," in shown
    assert "Put new cases in the existing test file." in shown
    record = json.loads((repo / prop["record"]).read_text())
    assert (
        record["pushed"] is False and record["repo"] == "IshaanNene/DebugAssist"
    )  # outside the write policy
    assert skill.read_text().count("Put new cases") == 0  # the working tree is untouched


class Scripted:
    def __init__(self, output: dict[str, Any] | None) -> None:
        self.output = output
        self.prompts: list[str] = []

    async def run(self, spec: Any, prompt: str, schema: Any, **kw: Any) -> LLMResult:
        self.prompts.append(prompt)
        return LLMResult(
            node=spec.node,
            output=self.output,
            status="ok",
            turns=1,
            tool_calls=[],
            model="m",
            mode="live",
            cost_usd=0.001,
        )


async def test_ask_cites_known_evidence_only_and_resumes_sessions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    s = run_state()
    known = s.evidence[0].id
    runner = Scripted(
        {
            "answer": f"Because of the race [{known}] and [ev_logs_ffffffffff].",
            "evidence_ids": [known, "ev_made_up_000"],
        }
    )

    class Ledgerless:
        ledger = None

    async def fake_deps(state: RunState) -> Any:
        return SimpleNamespace(engine=Ledgerless(), runner=lambda _a=None: runner)

    monkeypatch.setattr(postpr, "_load", lambda run_id: (s, tmp_path / "state.json"))
    monkeypatch.setattr(postpr, "_deps", fake_deps)
    monkeypatch.setattr(postpr, "chat_dir", lambda run_id: tmp_path / "chat")
    first = await postpr.ask("r", "why?")
    assert first["evidence_ids"] == [known] and first["unknown_citations"] == ["ev_logs_ffffffffff"]
    second = await postpr.ask("r", "and then?", first["session_id"])
    assert second["session_id"] == first["session_id"]
    assert "user: why?" in runner.prompts[1] and "assistant: Because of the race" in runner.prompts[1]
    assert len(postpr.session("r", first["session_id"])) == 4
