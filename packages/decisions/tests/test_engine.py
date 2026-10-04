from collections.abc import AsyncIterator
from typing import Any

import pytest

from debugassist.core.ledger import Ledger
from debugassist.core.settings import Mode
from debugassist.decisions.backends.mock import MockDecider
from debugassist.decisions.engine import DecisionEngine, RunContext
from debugassist.decisions.policy import Band
from debugassist.decisions.schema import ClefRequest, ClefResponse
from debugassist.decisions.state import CompactState


class Recording(MockDecider):
    def __init__(self, overrides: dict[str, Any] | None = None) -> None:
        super().__init__(overrides)
        self.requests: list[ClefRequest] = []

    async def run(self, request: ClefRequest) -> ClefResponse:
        self.requests.append(request)
        return await super().run(request)


@pytest.fixture
async def ledger() -> AsyncIterator[Ledger]:
    led = await Ledger.open("sqlite+aiosqlite:///:memory:")
    yield led
    await led.close()


TEAMS = {"rider-app": "React PWA", "dispatch": "matching + ETA", "payments": "fares"}
STATE = {"issue": "TypeError at routeDeepLink", "flag": "notif_router_v2 5%"}


async def test_decide_writes_ledger_and_bands(ledger: Ledger) -> None:
    backend = Recording({"worth_agent_run": 0.9})
    engine = DecisionEngine(backend, ledger=ledger)
    d = await engine.decide("D01", STATE, params={"teams": TEAMS}, ctx=RunContext(run_id="r1", issue_id="i1"))
    assert d.mode is Mode.MOCK and d.backend == "mock"
    assert (d.band, d.action) == (Band.ACT, "run_agent")
    assert d.chosen["owning_team"] in TEAMS
    assert set(d.probabilities["priority"]) == {"0", "1", "2", "3", "4"}
    rows = await ledger.list(run_id="r1")
    assert len(rows) == 1
    row = rows[0]
    assert row.decision_id == "D01_triage" and row.template_version == 1 and row.mode == "mock"
    assert row.state == STATE and len(row.state_hash) == 64
    assert row.action == "run_agent" and row.band == "act"
    assert backend.requests[0].model == "clef"
    await ledger.label(row.id, {"worth_agent_run": True}, source="catalog")
    labelled = await ledger.get(row.id)
    assert labelled is not None and labelled.outcome_label == {"worth_agent_run": True}


async def test_mock_is_deterministic() -> None:
    e = DecisionEngine(MockDecider())
    a = await e.decide("D05", STATE)
    b = await e.decide("D05", STATE)
    c = await e.decide("D05", {**STATE, "extra": 1})
    assert a.probabilities == b.probabilities
    assert a.probabilities != c.probabilities


async def test_model_override_and_template_default() -> None:
    backend = Recording()
    await DecisionEngine(backend).decide("D08", STATE)
    await DecisionEngine(backend, model_override="clef").decide("D08", STATE)
    await DecisionEngine(backend).decide("D08", STATE, model="clef")
    assert [r.model for r in backend.requests] == ["clef-flash", "clef", "clef"]


async def test_foreach_chunks_beyond_64_questions() -> None:
    backend = Recording()
    windows = [{"id": f"w{i}", "summary": f"log window {i}"} for i in range(150)]
    d = await DecisionEngine(backend).decide("D03_log_relevance", STATE, params={"windows": windows})
    assert [len(r.questions) for r in backend.requests] == [64, 64, 22]
    assert d.n_calls == 3 and len(d.items) == 150 and d.band is None
    assert {v.action for v in d.items.values()} <= {"keep", "keep_if_budget", "drop"}


async def test_two_stage_for_large_candidate_sets() -> None:
    backend = Recording({"is_location.c007": 0.99})
    cands = [{"id": f"c{i:03d}", "summary": f"src/mod{i}.ts:fn{i}"} for i in range(300)]
    d = await DecisionEngine(backend).decide("D12", STATE, params={"candidates": cands})
    stage1, stage2 = backend.requests[:-1], backend.requests[-1]
    assert sum(len(r.questions) for r in stage1) == 300 and len(stage1) == 5
    (q,) = stage2.questions.values()
    assert q.type == "choice"
    options = set(q.criteria)  # pyright: ignore[reportAttributeAccessIssue]
    assert len(options) == 13 and "none" in options and "c007" in options
    assert d.n_calls == 6


async def test_two_stage_direct_when_small() -> None:
    backend = Recording({"location": "c1"})
    cands = [{"id": f"c{i}", "summary": f"file{i}"} for i in range(5)]
    d = await DecisionEngine(backend).decide("D12", STATE, params={"candidates": cands})
    assert len(backend.requests) == 1
    assert d.chosen["location"] == "c1" and d.action == "focus_location"


async def test_choice_params_accept_item_lists() -> None:
    backend = Recording({"duplicate_of": "none"})
    cands = [{"id": "ISS-1", "description": "crash in router"}, {"id": "none", "description": "no match"}]
    d = await DecisionEngine(backend).decide("D02", STATE, params={"candidates": cands})
    assert d.action == "new_issue"


async def test_escalation_gets_llm_second_opinion(ledger: Ledger) -> None:
    first = MockDecider({"category": {"own_code": 0.5, "infra": 0.3, "network": 0.2}})
    second = MockDecider({"category": "own_code"})
    engine = DecisionEngine(first, ledger=ledger, second_opinion=second)
    d = await engine.decide("D05", STATE, ctx=RunContext(run_id="r2"))
    assert d.second_opinion is not None
    assert d.second_opinion.band is Band.ACT
    assert (d.band, d.action) == (Band.ACT, "investigate")
    rows = await ledger.list(run_id="r2")
    assert len(rows) == 2 and rows[1].parent_id == rows[0].id


async def test_compact_state_budget_is_enforced() -> None:
    backend = Recording()
    state = (
        CompactState().add("stack", "TypeError " * 50, priority=0).add("logs", "line\n" * 50_000, priority=90)
    )
    d = await DecisionEngine(backend).decide("D10", state)  # 3000-token budget
    sent = backend.requests[0].state
    assert isinstance(sent, dict) and str(sent["stack"]).startswith("TypeError")
    assert d.state_tokens_est <= 3000


async def test_images_are_prepared_and_sent() -> None:
    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (32, 32), "white").save(buf, format="PNG")
    backend = Recording()
    d = await DecisionEngine(backend).decide("D04", {"report": "my screen is blank"}, images=[buf.getvalue()])
    assert backend.requests[0].images and str(backend.requests[0].images[0]).startswith("data:image/png")
    assert d.action in {"flag_battery_evidence", "keep_for_rca", "none"}
