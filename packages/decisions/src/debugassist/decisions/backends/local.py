"""Optional self-hosted Clef using Cloudflare's ``joint_schema_model.py`` from Hugging Face.

Needs a CUDA GPU and ``pip install 'debugassist-decisions[local]'``. Do not use the generic
Transformers/vLLM snippets from the HF "Use this model" panel: they load the backbone as a chat
model and skip the joint schema head (``joint_head.safetensors``).
"""

from __future__ import annotations

import asyncio
import importlib
import importlib.util
import sys
from pathlib import Path
from typing import Any

from debugassist.core.settings import Mode
from debugassist.decisions.schema import ClefRequest, ClefRequestError, ClefResponse, parse_response

HF_REPOS = {"clef": "Cloudflare/clef", "clef-flash": "Cloudflare/clef-flash"}


class LocalClef:
    name = "local"
    mode = Mode.LIVE

    def __init__(self, model: str = "clef", *, device: str = "cuda", path: Path | None = None) -> None:
        self.model = model
        self._device = device
        self._path = path
        self._loaded: tuple[Any, Any, Any] | None = None  # (module, model, processor)
        self._lock = asyncio.Lock()

    def _load(self) -> tuple[Any, Any, Any]:
        try:
            snapshot_download: Any = importlib.import_module("huggingface_hub").snapshot_download
        except ImportError as exc:
            raise ClefRequestError("LocalClef needs: pip install 'debugassist-decisions[local]'") from exc
        path = self._path or Path(snapshot_download(HF_REPOS[self.model]))
        spec = importlib.util.spec_from_file_location("joint_schema_model", path / "joint_schema_model.py")
        if spec is None or spec.loader is None:
            raise ClefRequestError(f"joint_schema_model.py not found in {path}")
        module = importlib.util.module_from_spec(spec)
        sys.modules["joint_schema_model"] = module
        spec.loader.exec_module(module)
        model, processor = module.load_release_model(str(path), device=self._device)
        return module, model, processor

    async def run(self, request: ClefRequest) -> ClefResponse:
        if request.model != self.model:
            raise ClefRequestError(f"LocalClef loaded {self.model}, request asks for {request.model}")
        async with self._lock:
            if self._loaded is None:
                self._loaded = await asyncio.to_thread(self._load)
            module, model, processor = self._loaded
            raw: dict[str, Any] = await asyncio.to_thread(module.systemone, model, processor, request.body())
        parsed = parse_response(raw)
        parsed.check_against(request)
        return parsed

    def cost_usd(self, response: ClefResponse) -> float:
        return 0.0

    async def aclose(self) -> None:
        self._loaded = None
