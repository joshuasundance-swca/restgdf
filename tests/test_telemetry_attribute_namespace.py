"""Pin R-22: custom attributes use ``restgdf.*`` namespace prefix."""

from __future__ import annotations

import pytest

from restgdf import reset_config_cache
from restgdf.telemetry import feature_layer_stream_span


@pytest.mark.asyncio
async def test_custom_attrs_use_restgdf_namespace(memory_exporter, monkeypatch):
    monkeypatch.setenv("RESTGDF_TELEMETRY_ENABLED", "1")
    reset_config_cache()

    url = "https://example.com/arcgis/rest/services/Svc/FeatureServer/0"
    async with feature_layer_stream_span(layer_url=url, order="completion") as span:
        span.set_attribute("restgdf.page.count", 7)

    (parent,) = [
        s
        for s in memory_exporter.get_finished_spans()
        if s.name == "feature_layer.stream"
    ]
    attrs = dict(parent.attributes or {})

    assert (
        attrs.get("restgdf.service_root")
        == "https://example.com/arcgis/rest/services/Svc/FeatureServer"
    )
    assert attrs.get("restgdf.order") == "completion"
    assert attrs.get("restgdf.page.count") == 7

    non_restgdf_custom = [
        k
        for k in attrs
        if not k.startswith("restgdf.")
        and not k.startswith(("http.", "net.", "server.", "url.", "network."))
    ]
    assert non_restgdf_custom == [], (
        f"R-22 violation: unprefixed custom attrs: {non_restgdf_custom}"
    )


@pytest.mark.asyncio
async def test_service_root_is_token_scrubbed_and_layer_id_stripped(
    memory_exporter, monkeypatch
):
    monkeypatch.setenv("RESTGDF_TELEMETRY_ENABLED", "1")
    reset_config_cache()

    async with feature_layer_stream_span(
        layer_url="https://example.com/arcgis/rest/services/Svc/FeatureServer/0?token=SECRET",
        order="request",
    ) as _:
        pass

    (parent,) = [
        s
        for s in memory_exporter.get_finished_spans()
        if s.name == "feature_layer.stream"
    ]
    scrubbed = (parent.attributes or {}).get("restgdf.service_root", "")
    assert "SECRET" not in scrubbed
    assert scrubbed.endswith("/FeatureServer"), (
        f"expected FeatureServer root, got {scrubbed!r}"
    )
    assert "/0" not in scrubbed.rsplit("/FeatureServer", 1)[-1]
