"""Build decision backends and engines from settings (live when keys exist, mock otherwise)."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field

from debugassist.core.ledger import Ledger
from debugassist.core.policy import ROOT
from debugassist.core.settings import Integration, Mode, Settings
from debugassist.decisions.backends.base import DecisionBackend
from debugassist.decisions.backends.llm import LLMDecider
from debugassist.decisions.backends.local import LocalClef
from debugassist.decisions.backends.mock import MockDecider, Override, RulesDecider
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
    routes = deciders(settings, mock_overrides=mock_overrides) if backend in ("auto", "clef") else {}
    return DecisionEngine(
        primary, ledger=ledger, second_opinion=second, model_override=model_override, routes=routes
    )


DECIDERS = ROOT / "configs" / "deciders.yaml"


class DecidersConfig(BaseModel):
    templates: dict[str, Literal["rules", "llm", "mock"]] = Field(
        default_factory=dict[str, Literal["rules", "llm", "mock"]]
    )
    rules: dict[str, dict[str, float | int | str | dict[str, float]]] = Field(
        default_factory=dict[str, dict[str, float | int | str | dict[str, float]]]
    )


def deciders(
    settings: Settings, path: Path | None = None, *, mock_overrides: dict[str, Override] | None = None
) -> dict[str, DecisionBackend]:
    """Templates routed to another decider than the default, from `configs/deciders.yaml` (ROADMAP-100 037):
    `rules` (the fixed answers in the file's `rules:` section), `llm`, or `mock`. A route to `llm` without a live
    LLM falls back to the mock, as the default decider does."""
    f = path or DECIDERS
    cfg = (
        DecidersConfig.model_validate(yaml.safe_load(f.read_text()) or {})
        if f.is_file()
        else DecidersConfig()
    )
    routes: dict[str, DecisionBackend] = {}
    for template, name in cfg.templates.items():
        if name == "rules":
            routes[template] = RulesDecider(cfg.rules.get(template, {}))
        elif name == "llm" and settings.mode(Integration.LLM) is Mode.LIVE:
            routes[template] = LLMDecider.from_settings(settings)
        else:  # llm without a live key, or mock
            routes[template] = MockDecider(mock_overrides)
    return routes
