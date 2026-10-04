"""Vitals SDK for Python services (stdlib only; vendored into services by `make sync-sdks`).

import vitals_sdk
vitals_sdk.init(endpoint="http://vitals:8100", app="dispatch", version="1.6.0")
vitals_sdk.install_asgi(app)            # report unhandled exceptions from FastAPI/Starlette
"""

from __future__ import annotations

import json
import logging
import queue
import threading
import time
import traceback
import urllib.request
import uuid
from collections import deque
from typing import Any

_cfg: dict[str, str] = {}
_logs: deque[dict[str, Any]] = deque(maxlen=50)
_q: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=1000)


class _RingHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        if record.name.startswith("vitals"):
            return
        _logs.append(
            {"ts": record.created, "level": record.levelname.lower(), "message": record.getMessage()[:500]}
        )


def _worker() -> None:
    while True:
        event = _q.get()
        body = json.dumps({"events": [event]}).encode()
        req = urllib.request.Request(
            _cfg["endpoint"] + "/v1/events",
            data=body,
            headers={"content-type": "application/json"},
            method="POST",
        )
        try:
            urllib.request.urlopen(req, timeout=5).close()
        except Exception:
            logging.getLogger("vitals").warning("could not deliver event")


def init(*, endpoint: str | None, app: str, version: str) -> None:
    if not endpoint or _cfg:
        return
    _cfg.update(endpoint=endpoint.rstrip("/"), app=app, version=version)
    logging.getLogger().addHandler(_RingHandler(level=logging.INFO))
    threading.Thread(target=_worker, name="vitals-sender", daemon=True).start()


def capture_exception(
    exc: BaseException,
    *,
    culprit: str | None = None,
    session_id: str | None = None,
    trace_id: str | None = None,
    tags: dict[str, str] | None = None,
) -> None:
    if not _cfg:
        return
    frames = [
        {
            "function": f.name,
            "file": f.filename.split("/site-packages/")[-1],
            "line": f.lineno,
            "in_app": "site-packages" not in f.filename and "/lib/python" not in f.filename,
        }
        for f in traceback.extract_tb(exc.__traceback__)
    ]
    event = {
        "event_id": str(uuid.uuid4()),
        "kind": "exception",
        "app": _cfg["app"],
        "platform": "python",
        "version": _cfg["version"],
        "ts": time.time(),
        "session_id": session_id,
        "culprit": culprit,
        "error": {"type": type(exc).__name__, "message": str(exc)[:1000], "frames": frames},
        "logs": list(_logs)[-30:],
        "tags": tags or {},
        "trace_id": trace_id,
    }
    try:
        _q.put_nowait(event)
    except queue.Full:
        pass


def install_asgi(app: Any) -> None:
    """Wrap an ASGI app (FastAPI/Starlette) so unhandled exceptions are reported, then re-raised."""
    inner = app.build_middleware_stack

    def build() -> Any:
        stack = inner()

        async def middleware(scope: dict[str, Any], receive: Any, send: Any) -> None:
            try:
                await stack(scope, receive, send)
            except Exception as exc:
                if scope.get("type") == "http":
                    headers = {k.decode(): v.decode() for k, v in scope.get("headers", [])}
                    route = scope.get("route")
                    path = getattr(route, "path", scope.get("path"))
                    tp = headers.get("traceparent", "")
                    capture_exception(
                        exc,
                        culprit=f"{scope.get('method')} {path}",
                        session_id=headers.get("x-session-id"),
                        trace_id=tp.split("-")[1] if tp.count("-") >= 3 else None,
                    )
                raise

        return middleware

    app.build_middleware_stack = build
