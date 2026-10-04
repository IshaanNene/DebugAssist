"""Build decision backends and engines from settings (live when keys exist, mock otherwise)."""

from __future__ import annotations

from typing import Literal

from debugassist.core.ledger import Ledger
from debugassist.core.settings import Integration, Mode, Settings
from debugassist.decisions.backends.base import DecisionBackend
from debugassist.decisions.backends.llm import LLMDecider
from debugassist.decisions.backends.local import LocalClef
from debugassist.decisions.backends.mock import MockDecider, Override
from debugassist.decisions.backends.workers_ai import WorkersAIClef
from debugassist.decisions.engine import DecisionEngine
from debugassist.decisions.resilience import FallbackBackend
from debugassist.decisions.schema import ClefModel

BackendName = Literal["auto", "clef", "llm", "local", "mock"]


def build_backend(
    settings: Settings,
    name: BackendName = "auto",
    *,
    mock_overrides: dict[str, Override] | None = None,
    local_model: ClefModel = "clef",
) -> DecisionBackend:
    clef_live = settings.mode(Integration.CLEF) is Mode.LIVE
    llm_live = settings.mode(Integration.LLM) is Mode.LIVE
    if name == "mock" or (name == "auto" and not clef_live):
        return MockDecider(mock_overrides)
    if name == "llm":
        return LLMDecider.from_settings(settings)
    if name == "local":
        return LocalClef(local_model)
    if settings.cloudflare_account_id is None or settings.cloudflare_api_key is None:
        raise ValueError("Clef backend needs CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_KEY")
    clef = WorkersAIClef(settings.cloudflare_account_id, settings.cloudflare_api_key.get_secret_value())
    # Circuit breaker falls back to the LLM baseline (PLAN A5), or to mock when no LLM key.
    fallback: DecisionBackend = (
        LLMDecider.from_settings(settings) if llm_live else MockDecider(mock_overrides)
    )
    return FallbackBackend(clef, fallback)


async def build_engine(
    settings: Settings,
    backend: BackendName = "auto",
    *,
    model_override: ClefModel | None = None,
    with_ledger: bool = True,
    second_opinion: bool = True,
    mock_overrides: dict[str, Override] | None = None,
) -> DecisionEngine:
    primary = build_backend(settings, backend, mock_overrides=mock_overrides)
    second: DecisionBackend | None = None
    if second_opinion and backend in ("auto", "clef") and settings.mode(Integration.LLM) is Mode.LIVE:
        second = LLMDecider.from_settings(settings)
    ledger = await Ledger.open(settings.database_url) if with_ledger else None
    return DecisionEngine(primary, ledger=ledger, second_opinion=second, model_override=model_override)
