from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from restgdf.adapters import stream as stream_adapter
from restgdf.errors import OptionalDependencyError


class JsonResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    async def json(self, content_type=None):
        return self._payload


class QuerySession:
    def __init__(self, responses: list[dict]):
        self.responses = list(responses)
        self.post_calls: list[tuple[str, dict]] = []

    async def post(self, url: str, **kwargs):
        self.post_calls.append((url, kwargs))
        return JsonResponse(self.responses.pop(0))


@pytest.mark.asyncio
async def test_iter_feature_batches_delegates() -> None:
    session = QuerySession(
        [
            {"features": [{"attributes": {"A": 1}}]},
            {"features": [{"attributes": {"A": 2}}]},
        ],
    )

    with patch(
        "restgdf.utils.getgdf.get_query_data_batches",
        new=AsyncMock(return_value=[{"where": "1=1"}, {"where": "OBJECTID > 5"}]),
    ):
        batches = [
            batch
            async for batch in stream_adapter.iter_feature_batches(
                "https://example.com/layer/0",
                session,
            )
        ]

    # Two feature-batch envelopes; each batch is a list of raw features.
    assert len(batches) == 2
    flat = [f["attributes"]["A"] for batch in batches for f in batch]
    assert sorted(flat) == [1, 2]


@pytest.mark.asyncio
async def test_iter_rows_delegates() -> None:
    session = QuerySession(
        [
            {"features": [{"attributes": {"CITY": "DAYTONA"}}]},
            {"features": [{"attributes": {"CITY": "ORMOND"}}]},
        ],
    )

    with patch(
        "restgdf.utils.getgdf.get_query_data_batches",
        new=AsyncMock(return_value=[{"where": "1=1"}, {"where": "OBJECTID > 5"}]),
    ):
        rows = [
            row
            async for row in stream_adapter.iter_rows(
                "https://example.com/layer/0",
                session,
            )
        ]

    assert sorted(row["CITY"] for row in rows) == ["DAYTONA", "ORMOND"]


@pytest.mark.asyncio
async def test_iter_gdf_chunks_delegates() -> None:
    pytest.importorskip("pandas")
    pytest.importorskip("geopandas")
    pytest.importorskip("pyogrio")

    sentinel_chunks = [object(), object()]

    async def fake_chunk_generator(url, session, **kwargs):
        for chunk in sentinel_chunks:
            yield chunk

    with patch(
        "restgdf.adapters.stream.chunk_generator",
        side_effect=fake_chunk_generator,
    ):
        chunks = [
            chunk
            async for chunk in stream_adapter.iter_gdf_chunks(
                "https://example.com/layer/0",
                object(),
            )
        ]

    assert chunks == sentinel_chunks


@pytest.mark.asyncio
async def test_iter_gdf_chunks_requires_geo_stack(monkeypatch) -> None:
    # Force chunk_generator's internal require_geo_stack to fail.
    import importlib

    def _missing(module_name: str):
        exc = ModuleNotFoundError(f"No module named '{module_name}'")
        exc.name = module_name
        raise exc

    monkeypatch.setattr("restgdf.utils._optional.import_module", _missing)
    # Reload adapter to re-bind chunk_generator references — not strictly
    # required because chunk_generator calls require_geo_stack lazily.
    importlib.reload(stream_adapter)

    with pytest.raises(OptionalDependencyError):
        async for _ in stream_adapter.iter_gdf_chunks(
            "https://example.com/layer/0",
            object(),
        ):
            pass
