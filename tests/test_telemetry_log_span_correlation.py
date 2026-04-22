"""Pin _SpanContextFilter auto-attach: trace_id/span_id on LogRecords."""

from __future__ import annotations

import logging

import pytest

from restgdf import reset_config_cache
from restgdf._logging import build_log_extra
from restgdf.telemetry import feature_layer_stream_span
from restgdf.telemetry._correlation import span_context_fields


@pytest.mark.asyncio
async def test_restgdf_log_record_auto_carries_trace_id(
    memory_exporter,
    monkeypatch,
    caplog,
):
    """_SpanContextFilter stamps trace_id/span_id onto LogRecords automatically."""
    monkeypatch.setenv("RESTGDF_TELEMETRY_ENABLED", "1")
    reset_config_cache()

    async with feature_layer_stream_span(
        layer_url="https://example.com/arcgis/rest/services/Svc/FeatureServer/0",
        order="request",
    ) as span:
        active_trace_id = format(span.get_span_context().trace_id, "032x")
        active_span_id = format(span.get_span_context().span_id, "016x")

        with caplog.at_level(logging.INFO, logger="restgdf.transport"):
            logging.getLogger("restgdf.transport").info(
                "test record",
                extra=build_log_extra(service_root="https://example.com"),
            )
        record = next(r for r in caplog.records if r.message == "test record")
        assert getattr(record, "trace_id") == active_trace_id
        assert getattr(record, "span_id") == active_span_id


@pytest.mark.asyncio
async def test_span_context_fields_still_works_for_user_loggers(
    memory_exporter,
    monkeypatch,
):
    """The helper remains public for non-restgdf.* logger consumers."""
    monkeypatch.setenv("RESTGDF_TELEMETRY_ENABLED", "1")
    reset_config_cache()

    async with feature_layer_stream_span(
        layer_url="https://example.com/arcgis/rest/services/Svc/FeatureServer/0",
        order="request",
    ) as span:
        active_trace_id = format(span.get_span_context().trace_id, "032x")
        fields = span_context_fields()
        assert fields.get("trace_id") == active_trace_id


def test_restgdf_log_record_outside_span_has_no_trace_id(caplog):
    """Outside an active span, the filter stamps nothing (no-op)."""
    reset_config_cache()
    with caplog.at_level(logging.INFO, logger="restgdf.transport"):
        logging.getLogger("restgdf.transport").info("no-span record")
    record = next(r for r in caplog.records if r.message == "no-span record")
    assert not hasattr(record, "trace_id")
    assert not hasattr(record, "span_id")


def test_span_context_fields_empty_outside_span():
    """Outside any active span → empty dict."""
    reset_config_cache()
    assert span_context_fields() == {}
