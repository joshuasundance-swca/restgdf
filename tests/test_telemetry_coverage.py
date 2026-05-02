"""Coverage-focused tests for ``restgdf.telemetry._correlation`` and
``restgdf.telemetry._spans``.

These tests pin contract-level behavior for two edge paths that aren't
exercised elsewhere:

* ``span_context_fields()`` and ``start_feature_layer_stream_span()`` must
  degrade cleanly when ``opentelemetry`` is not importable — the former
  returning ``{}``, the latter raising ``OptionalDependencyError``.
* The public ``feature_layer_stream_span`` context manager must propagate
  every optional descriptor (``layer_id``, ``out_fields``, ``where``,
  ``order``, ``extra_attrs``) onto the emitted span's attributes.
"""

from __future__ import annotations

import sys

import pytest

from restgdf import reset_config_cache
from restgdf.errors import OptionalDependencyError


def _block_opentelemetry(monkeypatch: pytest.MonkeyPatch) -> None:
    """Simulate ``opentelemetry`` being uninstalled for subsequent imports."""
    monkeypatch.setitem(sys.modules, "opentelemetry", None)
    monkeypatch.setitem(sys.modules, "opentelemetry.trace", None)
    for key in list(sys.modules):
        if key.startswith("restgdf.telemetry"):
            monkeypatch.delitem(sys.modules, key, raising=False)


def test_span_context_fields_returns_empty_when_opentelemetry_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without OTel installed, ``span_context_fields()`` yields ``{}``."""
    _block_opentelemetry(monkeypatch)

    from restgdf.telemetry._correlation import span_context_fields

    assert span_context_fields() == {}


def test_span_context_fields_returns_empty_without_active_span() -> None:
    """With OTel installed but no active span, ``span_context_fields()`` is ``{}``.

    This pins the non-ImportError "invalid context" branch so both halves of
    the function's contract are locked in.
    """
    from restgdf.telemetry._correlation import span_context_fields

    assert span_context_fields() == {}


@pytest.mark.asyncio
async def test_span_context_fields_returns_ids_inside_active_span(
    memory_exporter,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Inside an active span, ``span_context_fields()`` returns hex IDs."""
    monkeypatch.setenv("RESTGDF_TELEMETRY_ENABLED", "1")
    reset_config_cache()

    from restgdf.telemetry import feature_layer_stream_span
    from restgdf.telemetry._correlation import span_context_fields

    async with feature_layer_stream_span(
        layer_url="https://example.com/arcgis/rest/services/Svc/FeatureServer/0",
    ) as span:
        fields = span_context_fields()

    assert set(fields) == {"trace_id", "span_id"}
    assert fields["trace_id"] == format(span.get_span_context().trace_id, "032x")
    assert fields["span_id"] == format(span.get_span_context().span_id, "016x")
    assert len(fields["trace_id"]) == 32
    assert len(fields["span_id"]) == 16


def test_start_feature_layer_stream_span_raises_when_opentelemetry_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When telemetry is enabled but OTel is absent, starting a span raises."""
    monkeypatch.setenv("RESTGDF_TELEMETRY_ENABLED", "1")
    reset_config_cache()

    _block_opentelemetry(monkeypatch)

    from restgdf.telemetry._spans import start_feature_layer_stream_span

    with pytest.raises(OptionalDependencyError, match=r"restgdf\[telemetry\]"):
        start_feature_layer_stream_span(layer_url="https://example.com/0")


def test_start_feature_layer_stream_span_returns_none_when_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Disabled telemetry short-circuits before any OTel import."""
    monkeypatch.delenv("RESTGDF_TELEMETRY_ENABLED", raising=False)
    reset_config_cache()

    from restgdf.telemetry._spans import start_feature_layer_stream_span

    span = start_feature_layer_stream_span(layer_url="https://example.com/0")
    assert span is None


def test_start_feature_layer_stream_span_emits_span_when_enabled(
    memory_exporter,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With telemetry enabled + OTel present, the helper returns a live span.

    The caller owns the span lifetime and must call ``end()``. The emitted
    span ends up in the exporter with the expected attributes.
    """
    monkeypatch.setenv("RESTGDF_TELEMETRY_ENABLED", "1")
    reset_config_cache()

    from restgdf.telemetry._spans import start_feature_layer_stream_span

    url = "https://example.com/arcgis/rest/services/Svc/FeatureServer/7"
    span = start_feature_layer_stream_span(
        layer_url=url,
        layer_id=7,
        out_fields="*",
        where="1=1",
        order="completion",
        extra_attrs={"restgdf.page.count": 1},
    )
    assert span is not None
    try:
        assert span.is_recording()
    finally:
        span.end()

    (finished,) = (
        s
        for s in memory_exporter.get_finished_spans()
        if s.name == "feature_layer.stream"
    )
    attrs = dict(finished.attributes or {})
    assert attrs.get("restgdf.layer_id") == 7
    assert attrs.get("restgdf.out_fields") == "*"
    assert attrs.get("restgdf.where") == "1=1"
    assert attrs.get("restgdf.order") == "completion"
    assert attrs.get("restgdf.page.count") == 1


@pytest.mark.asyncio
async def test_feature_layer_stream_span_yields_none_when_disabled(
    memory_exporter,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Disabled telemetry makes the async context manager yield ``None``."""
    monkeypatch.delenv("RESTGDF_TELEMETRY_ENABLED", raising=False)
    reset_config_cache()

    from restgdf.telemetry import feature_layer_stream_span

    async with feature_layer_stream_span(
        layer_url="https://example.com/0",
    ) as span:
        assert span is None

    assert memory_exporter.get_finished_spans() == ()


@pytest.mark.asyncio
async def test_feature_layer_stream_span_sets_all_optional_attributes(
    memory_exporter,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every optional descriptor is surfaced as a ``restgdf.*`` span attribute."""
    monkeypatch.setenv("RESTGDF_TELEMETRY_ENABLED", "1")
    reset_config_cache()

    from restgdf.telemetry import feature_layer_stream_span

    url = "https://example.com/arcgis/rest/services/Svc/FeatureServer/3"
    async with feature_layer_stream_span(
        layer_url=url,
        layer_id=3,
        out_fields="OBJECTID,NAME",
        where="STATUS='OPEN'",
        order="request",
        extra_attrs={"restgdf.page.count": 2},
    ):
        pass

    (span,) = (
        s
        for s in memory_exporter.get_finished_spans()
        if s.name == "feature_layer.stream"
    )
    attrs = dict(span.attributes or {})

    assert attrs.get("restgdf.layer_id") == 3
    assert attrs.get("restgdf.out_fields") == "OBJECTID,NAME"
    assert attrs.get("restgdf.where") == "STATUS='OPEN'"
    assert attrs.get("restgdf.order") == "request"
    assert attrs.get("restgdf.page.count") == 2


@pytest.mark.asyncio
async def test_feature_layer_stream_span_omits_unset_optional_attributes(
    memory_exporter,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unset optional descriptors are absent from the emitted span attributes."""
    monkeypatch.setenv("RESTGDF_TELEMETRY_ENABLED", "1")
    reset_config_cache()

    from restgdf.telemetry import feature_layer_stream_span

    url = "https://example.com/arcgis/rest/services/Svc/FeatureServer/0"
    async with feature_layer_stream_span(layer_url=url):
        pass

    (span,) = (
        s
        for s in memory_exporter.get_finished_spans()
        if s.name == "feature_layer.stream"
    )
    attrs = dict(span.attributes or {})

    for key in (
        "restgdf.layer_id",
        "restgdf.out_fields",
        "restgdf.where",
        "restgdf.order",
    ):
        assert key not in attrs
    assert "restgdf.service_root" in attrs
