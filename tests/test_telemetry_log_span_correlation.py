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


def test_restgdf_log_record_outside_span_has_empty_trace_id_sentinel(caplog):
    """W5-12 (TELEMETRY-01): outside an active span, the filter stamps the

    empty-string sentinel rather than leaving the attribute unset --
    see ``test_formatter_with_trace_id_field_does_not_error_outside_span``
    below for why an unset attribute is the actual bug this replaces.
    """
    reset_config_cache()
    with caplog.at_level(logging.INFO, logger="restgdf.transport"):
        logging.getLogger("restgdf.transport").info("no-span record")
    record = next(r for r in caplog.records if r.message == "no-span record")
    assert record.trace_id == ""
    assert record.span_id == ""


def test_formatter_with_trace_id_field_does_not_error_outside_span(caplog):
    """W5-12 (TELEMETRY-01): the documented ``%(trace_id)s`` log-correlation

    recipe must render cleanly for a record emitted OUTSIDE any active
    span -- the common case (an ``auth.refresh.start`` DEBUG record, the
    pagination ``exceededTransferLimit`` warning, ...). Before the fix,
    ``_SpanContextFilter`` left ``trace_id``/``span_id`` unset outside a
    span, so formatting such a record raised ``KeyError: 'trace_id'``
    (which stdlib ``logging`` normally swallows into a stderr
    "--- Logging error ---" dump via ``Handler.handleError``) instead of
    rendering the empty-string sentinel.
    """
    reset_config_cache()
    with caplog.at_level(logging.INFO, logger="restgdf.transport"):
        logging.getLogger("restgdf.transport").info("outside-span record")
    record = next(r for r in caplog.records if r.message == "outside-span record")

    formatter = logging.Formatter("%(trace_id)s|%(span_id)s|%(message)s")
    formatted = formatter.format(record)  # must not raise KeyError

    assert formatted == "||outside-span record"


def test_span_context_fields_empty_outside_span():
    """Outside any active span → empty dict."""
    reset_config_cache()
    assert span_context_fields() == {}
