from __future__ import annotations

import base64

import pytest

from debugassist.core import tracing


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("phoenix", {"phoenix"}),
        ("1", {"phoenix"}),
        ("langfuse", {"langfuse"}),
        ("both", {"phoenix", "langfuse"}),
        ("0", set[str]()),
        ("off", set[str]()),
    ],
)
def test_backends(monkeypatch: pytest.MonkeyPatch, value: str, expected: set[str]) -> None:
    monkeypatch.setenv("DA_TRACING", value)
    assert tracing.backends() == expected


def test_default_is_phoenix_and_typos_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DA_TRACING", raising=False)
    assert tracing.backends() == {"phoenix"}
    monkeypatch.setenv("DA_TRACING", "langfsue")
    with pytest.raises(ValueError):
        tracing.backends()


def test_langfuse_headers_need_both_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-lf-test")
    assert tracing.langfuse_headers() is None
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-lf-test")
    h = tracing.langfuse_headers()
    assert h is not None
    assert h["Authorization"] == "Basic " + base64.b64encode(b"pk-lf-test:sk-lf-test").decode()
    assert h["x-langfuse-ingestion-version"] == "4"


def test_langfuse_without_keys_is_off(monkeypatch: pytest.MonkeyPatch) -> None:
    # no keys → never contacted, so keyless CI never reaches out
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    assert tracing._answers("langfuse") is False  # pyright: ignore[reportPrivateUsage]


def test_both_keeps_phoenix_next_to_langfuse(monkeypatch: pytest.MonkeyPatch) -> None:
    """Regression: adding the Langfuse processor silently removed Phoenix's exporter."""
    from openinference.instrumentation.langchain import LangChainInstrumentor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    langfuse = InMemorySpanExporter()
    monkeypatch.setenv("DA_TRACING", "both")

    def answers(_name: str) -> bool:
        return True

    def no_instrument(*_a: object, **_k: object) -> None:
        return None

    monkeypatch.setattr(tracing, "_answers", answers)
    monkeypatch.setattr(tracing, "langfuse_exporter", lambda: langfuse)
    monkeypatch.setattr(LangChainInstrumentor, "instrument", no_instrument)
    monkeypatch.setattr(tracing, "_provider", None)
    try:
        assert tracing.setup()
        assert tracing.active() == {"phoenix", "langfuse"}
        provider = tracing._provider  # pyright: ignore[reportPrivateUsage]
        assert provider._default_processor is not None  # Phoenix's exporter is still there
        with tracing.span("probe"):
            pass
        provider.force_flush()
        assert [s.name for s in langfuse.get_finished_spans()] == ["probe"]
    finally:
        provider = tracing._provider  # pyright: ignore[reportPrivateUsage]
        if provider is not None:
            provider.shutdown()
