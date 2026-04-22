"""Pin R-21: 1 INTERNAL parent span ``feature_layer.stream``; zero per-page children."""

from __future__ import annotations

import pytest
from opentelemetry.trace import SpanKind

from restgdf import reset_config_cache
from restgdf.telemetry import feature_layer_stream_span


@pytest.mark.asyncio
async def test_feature_layer_stream_emits_internal_parent_span(
    memory_exporter,
    monkeypatch,
):
    monkeypatch.setenv("RESTGDF_TELEMETRY_ENABLED", "1")
    reset_config_cache()

    async with feature_layer_stream_span(
        layer_url="https://example.com/arcgis/rest/services/Svc/FeatureServer/0",
        order="request",
    ) as span:
        assert span is not None
        span.set_attribute("restgdf.page.count", 3)

    finished = memory_exporter.get_finished_spans()
    parents = [s for s in finished if s.name == "feature_layer.stream"]
    assert (
        len(parents) == 1
    ), f"expected 1 parent INTERNAL span, got {[s.name for s in finished]}"
    assert parents[0].kind == SpanKind.INTERNAL

    # R-21: no restgdf-owned per-page INTERNAL children.
    restgdf_children = [
        s
        for s in finished
        if s.name != "feature_layer.stream" and s.kind == SpanKind.INTERNAL
    ]
    assert restgdf_children == [], (
        f"restgdf must not emit per-page INTERNAL spans (R-21); "
        f"saw {[s.name for s in restgdf_children]}"
    )
