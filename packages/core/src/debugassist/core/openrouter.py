"""OpenRouter model metadata (capabilities, pricing), so the LLM layer adapts to whichever model is set.

Fetched from the public /models endpoint and cached for a day under .data/.
"""

from __future__ import annotations

import json
import time
from functools import cache
from pathlib import Path

import httpx
from pydantic import BaseModel

from debugassist.core.policy import ROOT

CACHE = ROOT / ".data" / "openrouter_models.json"
MODELS_URL = "https://openrouter.ai/api/v1/models"


class ModelInfo(BaseModel):
    id: str
    supported_parameters: list[str] = []
    price_in_per_mtok: float = 0.0
    price_out_per_mtok: float = 0.0
    price_cache_read_per_mtok: float | None = None  # None: cached input is billed like other input
    context_length: int = 0

    @property
    def structured_outputs(self) -> bool:
        return (
            "structured_outputs" in self.supported_parameters
            or "response_format" in self.supported_parameters
        )

    @property
    def free(self) -> bool:
        return self.id.endswith(":free") or (self.price_in_per_mtok == 0 and self.price_out_per_mtok == 0)


def _catalog(path: Path = CACHE) -> list[dict[str, object]]:
    if path.is_file() and time.time() - path.stat().st_mtime < 86_400:
        return json.loads(path.read_text())
    try:
        data = httpx.get(MODELS_URL, timeout=20).raise_for_status().json()["data"]
    except httpx.HTTPError:
        return json.loads(path.read_text()) if path.is_file() else []
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))
    return data


@cache
def model_info(model: str) -> ModelInfo:
    for m in _catalog():
        if m.get("id") == model:
            pricing: dict[str, str] = m.get("pricing") or {}  # type: ignore[assignment]
            return ModelInfo(
                id=model,
                supported_parameters=list(m.get("supported_parameters") or []),  # type: ignore[arg-type]
                price_in_per_mtok=float(pricing.get("prompt", 0) or 0) * 1e6,
                price_out_per_mtok=float(pricing.get("completion", 0) or 0) * 1e6,
                price_cache_read_per_mtok=float(pricing["input_cache_read"]) * 1e6
                if pricing.get("input_cache_read")
                else None,
                context_length=int(m.get("context_length") or 0),  # type: ignore[arg-type]
            )
    # Unknown model (offline, renamed): assume the conservative capability set.
    return ModelInfo(id=model, supported_parameters=["tools", "max_tokens"])
