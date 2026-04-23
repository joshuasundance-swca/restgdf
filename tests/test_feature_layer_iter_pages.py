"""BL-24 red tests for :meth:`FeatureLayer.iter_pages`.

Covers:

* ``order="request"`` (default) yields pages in batch-plan order
* ``order="completion"`` yields pages in completion order
* ``max_concurrent_pages`` caps in-flight fetches
* ``on_truncation="raise"`` → :class:`RestgdfResponseError`
* ``on_truncation="ignore"`` → warning logged, iteration continues
* ``on_truncation="split"`` → bisects and resolves
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from restgdf.errors import RestgdfResponseError
from restgdf.featurelayer.featurelayer import FeatureLayer


class _JsonResp:
    def __init__(self, payload):
        self._payload = payload

    async def json(self, content_type=None):
        return self._payload


class _ScriptedSession:
    """Serves queued POST payloads in FIFO order."""

    def __init__(self, payloads):
        self.payloads = list(payloads)
        self.post_calls: list[tuple[str, dict]] = []

    async def post(self, url: str, **kwargs):
        self.post_calls.append((url, kwargs))
        return _JsonResp(self.payloads.pop(0))

    async def get(self, url, **kwargs):
        if "params" in kwargs and "data" not in kwargs:
            kwargs = {**kwargs, "data": kwargs["params"]}
        return await self.post(url, **kwargs)


class _DelayedSession:
    """Serves POST payloads with per-call delays (seconds)."""

    def __init__(self, pairs):
        # pairs = list of (delay_seconds, payload_dict)
        self.pairs = list(pairs)
        self.post_calls: list[tuple[str, dict]] = []
        self._idx = 0

    async def post(self, url, **kwargs):
        idx = self._idx
        self._idx += 1
        self.post_calls.append((url, kwargs))
        delay, payload = self.pairs[idx]
        await asyncio.sleep(delay)
        return _JsonResp(payload)

    async def get(self, url, **kwargs):
        if "params" in kwargs and "data" not in kwargs:
            kwargs = {**kwargs, "data": kwargs["params"]}
        return await self.post(url, **kwargs)


def _make_layer():
    layer = FeatureLayer(
        "https://example.com/arcgis/rest/services/Svc/FeatureServer/0",
        session=object(),  # overridden per test
    )
    # Populate attributes normally set by prep() so iter_pages can run
    # without issuing a real metadata call.
    layer.fields = ("OBJECTID", "CITY")
    layer.object_id_field = "OBJECTID"
    return layer


@pytest.mark.asyncio
async def test_iter_pages_request_order_preserves_batch_sequence():
    layer = _make_layer()
    layer.session = _ScriptedSession(
        [
            {"features": [{"attributes": {"OBJECTID": 1}}]},
            {"features": [{"attributes": {"OBJECTID": 2}}]},
            {"features": [{"attributes": {"OBJECTID": 3}}]},
        ],
    )
    batches = [{"resultOffset": o} for o in (0, 1, 2)]

    with patch(
        "restgdf.utils.getgdf.get_query_data_batches",
        new=AsyncMock(return_value=batches),
    ):
        pages = [page async for page in layer.iter_pages(order="request")]

    oids = [p["features"][0]["attributes"]["OBJECTID"] for p in pages]
    assert oids == [1, 2, 3]


@pytest.mark.asyncio
async def test_iter_pages_completion_order_yields_as_ready():
    layer = _make_layer()
    # First batch is slow, second is fast → completion order: [2, 1].
    layer.session = _DelayedSession(
        [
            (0.05, {"features": [{"attributes": {"OBJECTID": 1}}]}),
            (0.0, {"features": [{"attributes": {"OBJECTID": 2}}]}),
        ],
    )
    batches = [{"resultOffset": 0}, {"resultOffset": 1}]

    with patch(
        "restgdf.utils.getgdf.get_query_data_batches",
        new=AsyncMock(return_value=batches),
    ):
        pages = [page async for page in layer.iter_pages(order="completion")]

    oids = [p["features"][0]["attributes"]["OBJECTID"] for p in pages]
    assert oids == [2, 1]


@pytest.mark.asyncio
async def test_iter_pages_max_concurrent_pages_bounds_inflight():
    layer = _make_layer()
    inflight = 0
    peak = 0
    lock = asyncio.Lock()

    class _TrackedSession:
        def __init__(self):
            self.post_calls: list[tuple[str, dict]] = []

        async def post(self, url, **kwargs):
            nonlocal inflight, peak
            async with lock:
                inflight += 1
                peak = max(peak, inflight)
            await asyncio.sleep(0.02)
            async with lock:
                inflight -= 1
            self.post_calls.append((url, kwargs))
            return _JsonResp({"features": []})

        async def get(self, url, **kwargs):
            if "params" in kwargs and "data" not in kwargs:
                kwargs = {**kwargs, "data": kwargs["params"]}
            return await self.post(url, **kwargs)

    layer.session = _TrackedSession()
    batches = [{"resultOffset": i} for i in range(6)]

    with patch(
        "restgdf.utils.getgdf.get_query_data_batches",
        new=AsyncMock(return_value=batches),
    ):
        async for _ in layer.iter_pages(
            order="completion",
            max_concurrent_pages=2,
        ):
            pass

    assert peak <= 2, f"peak in-flight={peak}, expected <=2"


@pytest.mark.asyncio
async def test_iter_pages_on_truncation_raise_raises_responseerror():
    layer = _make_layer()
    layer.session = _ScriptedSession(
        [
            {"features": [{"attributes": {"OBJECTID": 1}}]},
            {
                "features": [{"attributes": {"OBJECTID": 2}}],
                "exceededTransferLimit": True,
            },
        ],
    )
    batches = [{"resultOffset": 0}, {"resultOffset": 1}]

    with patch(
        "restgdf.utils.getgdf.get_query_data_batches",
        new=AsyncMock(return_value=batches),
    ):
        with pytest.raises(RestgdfResponseError) as exc_info:
            async for _ in layer.iter_pages(on_truncation="raise"):
                pass

    assert exc_info.value.context == "exceededTransferLimit"


@pytest.mark.asyncio
async def test_iter_pages_on_truncation_ignore_continues_with_warning(caplog):
    layer = _make_layer()
    layer.session = _ScriptedSession(
        [
            {
                "features": [{"attributes": {"OBJECTID": 1}}],
                "exceededTransferLimit": True,
            },
            {"features": [{"attributes": {"OBJECTID": 2}}]},
        ],
    )
    batches = [{"resultOffset": 0}, {"resultOffset": 1}]

    with patch(
        "restgdf.utils.getgdf.get_query_data_batches",
        new=AsyncMock(return_value=batches),
    ):
        with caplog.at_level("WARNING", logger="restgdf.pagination"):
            pages = [
                page
                async for page in layer.iter_pages(
                    order="request",
                    on_truncation="ignore",
                )
            ]

    oids = [p["features"][0]["attributes"]["OBJECTID"] for p in pages]
    assert oids == [1, 2]
    assert any(
        "exceededTransferLimit" in record.message
        or "transfer" in record.message.lower()
        for record in caplog.records
    ), "expected a transfer-limit warning via restgdf.pagination"


@pytest.mark.asyncio
async def test_iter_pages_on_truncation_split_bisects_and_completes():
    """Split strategy: first page exceeds limit, bisection of OIDs resolves it.

    Simulated sequence:
    - initial page ⇒ exceededTransferLimit=true
    - returnIdsOnly (to get OIDs for current predicate) ⇒ [1, 2, 3, 4]
    - left-half query (OIDs 1,2) ⇒ clean page
    - right-half query (OIDs 3,4) ⇒ clean page
    """
    layer = _make_layer()
    layer.session = _ScriptedSession(
        [
            # initial page: exceedsTransferLimit
            {
                "features": [{"attributes": {"OBJECTID": 1}}],
                "exceededTransferLimit": True,
            },
            # returnIdsOnly response (for bisection)
            {"objectIdFieldName": "OBJECTID", "objectIds": [1, 2, 3, 4]},
            # left half
            {
                "features": [
                    {"attributes": {"OBJECTID": 1}},
                    {"attributes": {"OBJECTID": 2}},
                ],
            },
            # right half
            {
                "features": [
                    {"attributes": {"OBJECTID": 3}},
                    {"attributes": {"OBJECTID": 4}},
                ],
            },
        ],
    )
    batches = [{"where": "1=1"}]

    with patch(
        "restgdf.utils.getgdf.get_query_data_batches",
        new=AsyncMock(return_value=batches),
    ):
        pages = [
            page
            async for page in layer.iter_pages(
                order="request",
                on_truncation="split",
            )
        ]

    # Expect two resolved pages covering all four OIDs.
    all_oids = sorted(f["attributes"]["OBJECTID"] for p in pages for f in p["features"])
    assert all_oids == [1, 2, 3, 4]
