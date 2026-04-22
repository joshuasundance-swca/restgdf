"""Pin R-58: RestgdfInstrumentor is an AioHttpClientInstrumentor subclass."""

from __future__ import annotations

from opentelemetry.instrumentation.aiohttp_client import AioHttpClientInstrumentor

from restgdf.telemetry import RestgdfInstrumentor


def test_instrumentor_is_aiohttp_client_subclass():
    inst = RestgdfInstrumentor()
    assert isinstance(inst, AioHttpClientInstrumentor), (
        f"RestgdfInstrumentor must be an AioHttpClientInstrumentor subclass (R-58); "
        f"got {type(inst).__mro__}"
    )
