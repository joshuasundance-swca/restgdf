"""R-61 red tests: :meth:`FeatureLayer.iter_pages` emits ONE INTERNAL parent span.

When telemetry is enabled, a single ``feature_layer.stream`` INTERNAL span
wraps the per-page loop (no per-page child spans emitted by restgdf).
When telemetry is disabled, no restgdf spans are emitted.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from opentelemetry.trace import SpanKind

from restgdf import reset_config_cache
from restgdf.featurelayer.featurelayer import FeatureLayer


class _JsonResp:
    def __init__(self, payload):
        self._payload = payload

    async def json(self, content_type=None):
        return self._payload


class _ScriptedSession:
    def __init__(self, payloads):
        self.payloads = list(payloads)
        self.post_calls: list[tuple[str, dict]] = []

    async def post(self, url: str, **kwargs):
        self.post_calls.append((url, kwargs))
        return _JsonResp(self.payloads.pop(0))


def _make_layer():
    layer = FeatureLayer(
        "https://example.com/arcgis/rest/services/Svc/FeatureServer/0",
        session=object(),
    )
    layer.fields = ("OBJECTID",)
    layer.object_id_field = "OBJECTID"
    return layer


@pytest.mark.asyncio
async def test_iter_pages_emits_exactly_one_internal_parent_span(
    memory_exporter,
    monkeypatch,
):
    monkeypatch.setenv("RESTGDF_TELEMETRY_ENABLED", "1")
    reset_config_cache()

    layer = _make_layer()
    layer.session = _ScriptedSession(
        [
            {"features": [{"attributes": {"OBJECTID": 1}}]},
            {"features": [{"attributes": {"OBJECTID": 2}}]},
            {"features": [{"attributes": {"OBJECTID": 3}}]},
        ],
    )

    with patch(
        "restgdf.utils.getgdf.get_query_data_batches",
        new=AsyncMock(return_value=[{"resultOffset": o} for o in (0, 1, 2)]),
    ):
        pages = [p async for p in layer.iter_pages(order="request")]
    assert len(pages) == 3

    finished = memory_exporter.get_finished_spans()
    parents = [s for s in finished if s.name == "feature_layer.stream"]
    assert (
        len(parents) == 1
    ), f"expected exactly 1 parent span, got {[s.name for s in finished]}"
    assert parents[0].kind == SpanKind.INTERNAL

    # R-21: no per-page restgdf-owned INTERNAL spans.
    per_page = [
        s
        for s in finished
        if s.name != "feature_layer.stream" and s.kind == SpanKind.INTERNAL
    ]
    assert per_page == [], f"unexpected per-page spans: {[s.name for s in per_page]}"


@pytest.mark.asyncio
async def test_iter_pages_early_break_still_closes_span(
    memory_exporter,
    monkeypatch,
    caplog,
):
    """rd-gate2 HIGH #1: span must close cleanly when consumer breaks early.

    The span lifetime must not rely on an asyncio context token that crosses
    ``yield`` boundaries; otherwise cancellation/early-break triggers OTel's
    "Failed to detach context" error.
    """
    monkeypatch.setenv("RESTGDF_TELEMETRY_ENABLED", "1")
    reset_config_cache()

    layer = _make_layer()
    layer.session = _ScriptedSession(
        [
            {"features": [{"attributes": {"OBJECTID": 1}}]},
            {"features": [{"attributes": {"OBJECTID": 2}}]},
            {"features": [{"attributes": {"OBJECTID": 3}}]},
        ],
    )

    caplog.set_level("ERROR", logger="opentelemetry.context")
    with patch(
        "restgdf.utils.getgdf.get_query_data_batches",
        new=AsyncMock(return_value=[{"resultOffset": o} for o in (0, 1, 2)]),
    ):
        gen = layer.iter_pages(order="request")
        async for _p in gen:
            break
        # Consumer ``break`` drops the loop-iterator reference, but the
        # async-generator object survives on the local ``gen``. Explicitly
        # ``aclose()`` to drive the ``finally`` block that ends the R-61
        # span. Pre-fix this path would raise "Failed to detach context".
        await gen.aclose()

    finished = memory_exporter.get_finished_spans()
    parents = [s for s in finished if s.name == "feature_layer.stream"]
    assert (
        len(parents) == 1
    ), f"expected exactly 1 finished parent span, got {len(parents)}"

    detach_errors = [
        rec for rec in caplog.records if "Failed to detach context" in rec.getMessage()
    ]
    assert detach_errors == [], (
        f"OTel detach-context errors leaked across yield boundary: "
        f"{[r.getMessage() for r in detach_errors]}"
    )


@pytest.mark.asyncio
async def test_iter_pages_aclose_closes_span(memory_exporter, monkeypatch, caplog):
    """rd-gate2 HIGH #1: explicit ``aclose()`` must end the span cleanly."""
    monkeypatch.setenv("RESTGDF_TELEMETRY_ENABLED", "1")
    reset_config_cache()

    layer = _make_layer()
    layer.session = _ScriptedSession(
        [
            {"features": [{"attributes": {"OBJECTID": 1}}]},
            {"features": [{"attributes": {"OBJECTID": 2}}]},
        ],
    )

    caplog.set_level("ERROR", logger="opentelemetry.context")
    with patch(
        "restgdf.utils.getgdf.get_query_data_batches",
        new=AsyncMock(return_value=[{"resultOffset": o} for o in (0, 1)]),
    ):
        gen = layer.iter_pages(order="request")
        await gen.__anext__()
        await gen.aclose()

    finished = memory_exporter.get_finished_spans()
    parents = [s for s in finished if s.name == "feature_layer.stream"]
    assert (
        len(parents) == 1
    ), f"expected exactly 1 finished parent span, got {len(parents)}"

    detach_errors = [
        rec for rec in caplog.records if "Failed to detach context" in rec.getMessage()
    ]
    assert detach_errors == [], (
        f"OTel detach-context errors leaked on aclose(): "
        f"{[r.getMessage() for r in detach_errors]}"
    )


@pytest.mark.asyncio
async def test_iter_pages_is_noop_when_telemetry_disabled(
    memory_exporter,
    monkeypatch,
):
    monkeypatch.delenv("RESTGDF_TELEMETRY_ENABLED", raising=False)
    reset_config_cache()

    layer = _make_layer()
    layer.session = _ScriptedSession(
        [{"features": [{"attributes": {"OBJECTID": 1}}]}],
    )

    with patch(
        "restgdf.utils.getgdf.get_query_data_batches",
        new=AsyncMock(return_value=[{"resultOffset": 0}]),
    ):
        pages = [p async for p in layer.iter_pages()]
    assert len(pages) == 1

    finished = memory_exporter.get_finished_spans()
    # With telemetry disabled, restgdf must not emit any spans.
    restgdf_spans = [s for s in finished if s.name == "feature_layer.stream"]
    assert restgdf_spans == []
