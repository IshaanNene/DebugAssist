"""Agent tracing (SPEC §10): OpenTelemetry spans in OpenInference form, exported to Phoenix and/or Langfuse.

One trace per `debugassist run` invocation: a root AGENT span for the run, a span per graph node, the
LangChain instrumentor's spans for every LLM and tool call (MCP tools included), DECISION spans for Clef,
TOOL spans for sandbox commands and AGENT spans for subagents. Spans carry the run id as `session.id`, so
Phoenix groups every invocation of a run (including resumes) into one session.

DA_TRACING picks the backends: phoenix (default; "1" too) | langfuse | both | 0. A backend is used when it
answers: Phoenix at PHOENIX_URL (default http://localhost:6006); Langfuse at LANGFUSE_HOST (default
http://localhost:3200, `make langfuse`) with LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY, over its OTLP endpoint
(Langfuse maps OpenInference's session.id, input.value / output.value and llm.* attributes). With no backend
answering every helper is a no-op, so tests and keyless CI need nothing.
"""

from __future__ import annotations

import base64
import json
import os
from collections.abc import Generator
from contextlib import contextmanager, nullcontext
from typing import Any

import httpx
from opentelemetry import trace

PROJECT = os.environ.get("PHOENIX_PROJECT_NAME", "debugassist")
_provider: Any = None


_active: set[str] = set()


def phoenix_url() -> str:
    return os.environ.get("PHOENIX_URL", "http://localhost:6006").rstrip("/")


def langfuse_url() -> str:
    return os.environ.get("LANGFUSE_HOST", "http://localhost:3200").rstrip("/")


def langfuse_headers() -> dict[str, str] | None:
    """Basic auth from the project's key pair, plus v4 real-time ingestion; None without keys."""
    pk, sk = os.environ.get("LANGFUSE_PUBLIC_KEY"), os.environ.get("LANGFUSE_SECRET_KEY")
    if not pk or not sk:
        return None
    token = base64.b64encode(f"{pk}:{sk}".encode()).decode()
    return {"Authorization": f"Basic {token}", "x-langfuse-ingestion-version": "4"}


def backends() -> set[str]:
    """The backends DA_TRACING asks for (whether they answer is checked in setup)."""
    value = os.environ.get("DA_TRACING", "phoenix").strip().lower()
    choices = {"0": set[str](), "off": set[str](), "1": {"phoenix"}, "phoenix": {"phoenix"}}
    choices |= {"langfuse": {"langfuse"}, "both": {"phoenix", "langfuse"}}
    if value not in choices:
        raise ValueError(f"DA_TRACING must be phoenix, langfuse, both or 0 (got {value!r})")
    return choices[value]


def _answers(name: str) -> bool:
    try:
        if name == "phoenix":
            httpx.get(f"{phoenix_url()}/healthz", timeout=0.5).raise_for_status()
        else:
            if langfuse_headers() is None:
                return False
            httpx.get(f"{langfuse_url()}/api/public/health", timeout=1).raise_for_status()
    except httpx.HTTPError:
        return False
    return True


def langfuse_exporter() -> Any:
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

    return OTLPSpanExporter(
        endpoint=f"{langfuse_url()}/api/public/otel/v1/traces", headers=langfuse_headers()
    )


def enabled() -> bool:
    return _provider is not None


def active() -> set[str]:
    return set(_active)


def setup(project: str = PROJECT) -> bool:
    """Register the exporters that answer and instrument LangChain (idempotent). False when none does."""
    global _provider
    if _provider is not None:
        return True
    use = {b for b in backends() if _answers(b)}
    if not use:
        return False
    from openinference.instrumentation.langchain import LangChainInstrumentor
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    if "phoenix" in use:
        from phoenix.otel import register

        _provider = register(
            endpoint=f"{phoenix_url()}/v1/traces", project_name=project, batch=True, verbose=False
        )
    else:
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider

        _provider = TracerProvider(resource=Resource.create({"service.name": project}))
    if "langfuse" in use:
        processor = BatchSpanProcessor(langfuse_exporter())
        if "phoenix" in use:
            # Phoenix's provider drops its own exporter when another processor is added, unless told not to
            _provider.add_span_processor(processor, replace_default_processor=False)
        else:
            _provider.add_span_processor(processor)
    LangChainInstrumentor().instrument(tracer_provider=_provider)
    _active.clear()
    _active.update(use)
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


def langfuse_project_id() -> str | None:
    headers = langfuse_headers()
    if headers is None:
        return None
    try:
        rows = httpx.get(
            f"{langfuse_url()}/api/public/projects", headers=headers, timeout=2
        ).raise_for_status()
        data = rows.json().get("data", [])
    except (httpx.HTTPError, ValueError):
        return None
    return str(data[0]["id"]) if data else None


def langfuse_trace_url(trace_id: str) -> str | None:
    pid = langfuse_project_id()
    return f"{langfuse_url()}/project/{pid}/traces/{trace_id}" if pid else None
