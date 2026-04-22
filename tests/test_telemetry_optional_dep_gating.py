"""Pin §10.6: OptionalDependencyError on missing telemetry extra."""

from __future__ import annotations

import sys

import pytest

from restgdf import reset_config_cache
from restgdf.errors import OptionalDependencyError


def test_instrumentor_without_telemetry_extra_raises_optional_dep(monkeypatch):
    """RestgdfInstrumentor() raises OptionalDependencyError when OTel is absent."""
    # Simulate missing opentelemetry by blocking the import.
    monkeypatch.setitem(sys.modules, "opentelemetry", None)
    monkeypatch.setitem(sys.modules, "opentelemetry.instrumentation", None)
    monkeypatch.setitem(
        sys.modules, "opentelemetry.instrumentation.aiohttp_client", None
    )

    # Force re-import of the instrumentor module to pick up the blocked import.
    for key in list(sys.modules):
        if key.startswith("restgdf.telemetry"):
            monkeypatch.delitem(sys.modules, key, raising=False)

    from restgdf.telemetry import RestgdfInstrumentor

    with pytest.raises(OptionalDependencyError, match=r"restgdf\[telemetry\]"):
        RestgdfInstrumentor().instrument()


@pytest.mark.asyncio
async def test_feature_layer_stream_span_raises_when_enabled_but_otel_missing(
    monkeypatch,
):
    """feature_layer_stream_span with enabled=True raises when OTel absent."""
    monkeypatch.setenv("RESTGDF_TELEMETRY_ENABLED", "1")
    reset_config_cache()

    monkeypatch.setitem(sys.modules, "opentelemetry", None)
    monkeypatch.setitem(sys.modules, "opentelemetry.trace", None)

    for key in list(sys.modules):
        if key.startswith("restgdf.telemetry"):
            monkeypatch.delitem(sys.modules, key, raising=False)

    from restgdf.telemetry import feature_layer_stream_span

    with pytest.raises(OptionalDependencyError, match=r"restgdf\[telemetry\]"):
        async with feature_layer_stream_span(layer_url="https://example.com/0"):
            pass  # pragma: no cover


def test_span_context_filter_stays_silent_on_missing_otel(monkeypatch, caplog):
    """With OTel absent, restgdf.* logging does NOT raise."""
    import logging

    monkeypatch.setitem(sys.modules, "opentelemetry", None)
    monkeypatch.setitem(sys.modules, "opentelemetry.trace", None)

    with caplog.at_level(logging.INFO, logger="restgdf.transport"):
        logging.getLogger("restgdf.transport").info("safe without otel")

    record = next(r for r in caplog.records if r.message == "safe without otel")
    assert not hasattr(record, "trace_id")
