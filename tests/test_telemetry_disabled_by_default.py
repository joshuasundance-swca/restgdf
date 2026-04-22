"""Pin: TelemetryConfig.enabled=False by default → zero spans emitted."""

from __future__ import annotations

import pytest

from restgdf import reset_config_cache
from restgdf.telemetry import feature_layer_stream_span


@pytest.mark.asyncio
async def test_no_spans_when_telemetry_disabled(memory_exporter, monkeypatch):
    monkeypatch.delenv("RESTGDF_TELEMETRY_ENABLED", raising=False)
    reset_config_cache()

    async with feature_layer_stream_span(
        layer_url="https://example.com/arcgis/rest/services/Svc/FeatureServer/0",
        order="request",
    ) as span:
        assert span is None

    names = [s.name for s in memory_exporter.get_finished_spans()]
    assert "feature_layer.stream" not in names
    assert names == []
