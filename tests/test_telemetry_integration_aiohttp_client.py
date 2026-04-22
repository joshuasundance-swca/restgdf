"""Integration: RestgdfInstrumentor emits CLIENT spans for aiohttp traffic (R-58)."""

from __future__ import annotations

import pytest
from aioresponses import aioresponses
from opentelemetry.trace import SpanKind

from restgdf import reset_config_cache
from restgdf.telemetry import RestgdfInstrumentor


@pytest.mark.asyncio
async def test_instrumentor_emits_client_spans_for_real_restgdf_aiohttp_traffic(
    memory_exporter, monkeypatch
):
    """Exercise a real restgdf call path through aioresponses so
    AioHttpClientInstrumentor (via RestgdfInstrumentor) emits CLIENT spans."""
    monkeypatch.setenv("RESTGDF_TELEMETRY_ENABLED", "1")
    reset_config_cache()

    instrumentor = RestgdfInstrumentor()
    instrumentor.instrument()
    try:
        service_root = (
            "https://example.com/arcgis/rest/services/Svc/FeatureServer"
        )
        stub_payload = {
            "currentVersion": 10.9,
            "serviceDescription": "",
            "hasVersionedData": False,
            "supportsDisconnectedEditing": False,
            "layers": [],
            "tables": [],
        }
        with aioresponses() as m:
            m.get(f"{service_root}?f=json", payload=stub_payload)
            import aiohttp

            from restgdf import Rest

            async with aiohttp.ClientSession() as session:
                rest = await Rest.from_url(url=service_root, session=session)
                assert rest is not None

        finished = memory_exporter.get_finished_spans()
        client_spans = [s for s in finished if s.kind == SpanKind.CLIENT]
        assert len(client_spans) >= 1, (
            f"expected >=1 CLIENT span from AioHttpClientInstrumentor; "
            f"got {[(s.name, s.kind) for s in finished]}"
        )
        (client,) = client_spans[:1]
        attrs = dict(client.attributes or {})
        url_keys = [
            k for k in attrs if k.startswith(("http.", "url.", "server.", "net."))
        ]
        assert url_keys, (
            f"expected OTel http/url attrs on CLIENT span; got {list(attrs)}"
        )
    finally:
        instrumentor.uninstrument()
