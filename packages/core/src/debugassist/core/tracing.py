"""Phoenix tracing (SPEC §10): OpenTelemetry spans in OpenInference form, exported to Phoenix.

One trace per `debugassist run` invocation: a root AGENT span for the run, a span per graph node, the
LangChain instrumentor's spans for every LLM and tool call (MCP tools included), DECISION spans for Clef,
TOOL spans for sandbox commands and AGENT spans for subagents. Spans carry the run id as `session.id`, so
Phoenix groups every invocation of a run (including resumes) into one session.

Tracing is on when Phoenix answers (PHOENIX_URL, default http://localhost:6006) and DA_TRACING is not "0";
otherwise every helper is a no-op, so tests and keyless CI need nothing.
"""

from __future__ import annotations

import json
import os
from collections.abc import Generator
from contextlib import contextmanager, nullcontext
from typing import Any

import httpx
from opentelemetry import trace

PROJECT = os.environ.get("PHOENIX_PROJECT_NAME", "debugassist")
_provider: Any = None


def phoenix_url() -> str:
    return os.environ.get("PHOENIX_URL", "http://localhost:6006").rstrip("/")


def enabled() -> bool:
    return _provider is not None


def setup(project: str = PROJECT) -> bool:
    """Register the Phoenix exporter and instrument LangChain (idempotent). False when Phoenix is off."""
    global _provider
    if _provider is not None:
        return True
    if os.environ.get("DA_TRACING", "1") == "0":
        return False
    try:
        httpx.get(f"{phoenix_url()}/healthz", timeout=0.5).raise_for_status()
    except httpx.HTTPError:
        return False
    from openinference.instrumentation.langchain import LangChainInstrumentor
    from phoenix.otel import register

    _provider = register(
        endpoint=f"{phoenix_url()}/v1/traces", project_name=project, batch=True, verbose=False
    )
    LangChainInstrumentor().instrument(tracer_provider=_provider)
    return True


def shutdown() -> None:
    if _provider is not None:
        _provider.force_flush()


def _tracer() -> Any:
    return _provider.get_tracer("debugassist") if _provider is not None else None


def _attr(value: Any) -> Any:
    if isinstance(value, str | bool | int | float):
        return value
    return json.dumps(value, default=str)[:8000]


@contextmanager
def span(name: str, kind: str = "chain", **attributes: Any) -> Generator[Any]:
    """A span (no-op when tracing is off). `kind`: chain | agent | llm | tool | decision | guardrail."""
    t = _tracer()
    if t is None:
        with nullcontext() as nothing:
            yield nothing
        return
    with t.start_as_current_span(name, openinference_span_kind=kind) as s:
        for k, v in attributes.items():
            if v is not None:
                s.set_attribute(k, _attr(v))
        yield s


def set_attributes(s: Any, **attributes: Any) -> None:
    if s is None:
        return
    for k, v in attributes.items():
        if v is not None:
            s.set_attribute(k, _attr(v))


def current_trace_id() -> str | None:
    ctx = trace.get_current_span().get_span_context()
    return format(ctx.trace_id, "032x") if ctx.is_valid else None


@contextmanager
def session(run_id: str, **metadata: Any) -> Generator[None]:
    """Tag every span inside (LangChain's included) with the run id as session.id."""
    if _provider is None:
        yield
        return
    from openinference.instrumentation import using_attributes

    with using_attributes(session_id=run_id, metadata=metadata):
        yield


def project_id(project: str = PROJECT) -> str | None:
    """Phoenix's id for the project (for deep links), or None."""
    try:
        rows = httpx.get(f"{phoenix_url()}/v1/projects", timeout=2).raise_for_status().json().get("data", [])
    except (httpx.HTTPError, ValueError):
        return None
    return next((str(p["id"]) for p in rows if p.get("name") == project), None)


def trace_url(trace_id: str, project: str = PROJECT) -> str | None:
    pid = project_id(project)
    return f"{phoenix_url()}/projects/{pid}/traces/{trace_id}" if pid else None
