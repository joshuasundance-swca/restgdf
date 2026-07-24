"""W4-1 (PAGINATION-01): the GeoDataFrame path must detect
``exceededTransferLimit`` and RAISE instead of silently returning a
truncated GeoDataFrame.

``get_sub_gdf`` (the only page primitive behind ``get_gdf`` and
``chunk_generator`` / ``stream_gdf_chunks``) previously read the page
straight into geopandas with no envelope inspection, so an ArcGIS response
carrying ``exceededTransferLimit=true`` (byte/geometry cap hit) yielded a
GeoDataFrame silently missing rows -- silent data loss on the flagship geo
call. These tests drive the REAL reader seam with both ESRIJSON and GeoJSON
driver shapes and assert a ``PaginationError`` (mirroring the raw-feature
engine ``_get_sub_features``).

Implementation hazard covered: pyogrio/``read_file`` discards the top-level
``exceededTransferLimit`` member, so the flag must be detected from the parsed
JSON dict -- ``test_..._detects_flag_before_read_file`` asserts the raise fires
without ``read_file`` ever being called.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, Mock, patch

import pytest

from restgdf.errors import PaginationError
from restgdf.utils.getgdf import chunk_generator, get_gdf, get_sub_gdf


_ESRIJSON_TRUNCATED = json.dumps(
    {
        "objectIdFieldName": "OBJECTID",
        "geometryType": "esriGeometryPoint",
        "spatialReference": {"wkid": 4326},
        "features": [
            {"attributes": {"OBJECTID": 101}, "geometry": {"x": -117.1, "y": 34.0}},
        ],
        "exceededTransferLimit": True,
    },
)

_GEOJSON_TRUNCATED = json.dumps(
    {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"OBJECTID": 101},
                "geometry": {"type": "Point", "coordinates": [-117.1, 34.0]},
            },
        ],
        "exceededTransferLimit": True,
    },
)

_GEOJSON_COMPLETE = json.dumps(
    {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"OBJECTID": 101},
                "geometry": {"type": "Point", "coordinates": [-117.1, 34.0]},
            },
        ],
        "exceededTransferLimit": False,
    },
)


class _TextSession:
    """ArcGIS session double: every request returns the same body text."""

    def __init__(self, response_text: str) -> None:
        self.response_text = response_text
        self.post_calls: list[tuple[str, dict]] = []
        self._closed = False

    @property
    def closed(self) -> bool:
        return self._closed

    async def close(self) -> None:
        self._closed = True

    async def post(self, url: str, **kwargs):
        self.post_calls.append((url, kwargs))

        class Response:
            def __init__(self, text_payload: str) -> None:
                self._text_payload = text_payload

            async def text(self) -> str:
                return self._text_payload

        return Response(self.response_text)

    async def get(self, url: str, **kwargs):
        if "params" in kwargs:
            kwargs.setdefault("data", kwargs.pop("params"))
        return await self.post(url, **kwargs)


@pytest.mark.asyncio
async def test_get_sub_gdf_raises_on_truncation_esrijson() -> None:
    """ESRIJSON driver shape: exceededTransferLimit=true must raise."""
    session = _TextSession(_ESRIJSON_TRUNCATED)

    with patch(
        "restgdf.utils.getgdf.supported_drivers",
        new={"ESRIJSON": "rw"},
    ), patch(
        # Patch the reader so the red failure is unambiguously "did not raise"
        # (a returned GeoDataFrame), not a pyogrio parse error on the string.
        "restgdf.utils.getgdf.read_file",
        new=Mock(name="read_file"),
    ):
        with pytest.raises(PaginationError, match="exceededTransferLimit") as exc_info:
            await get_sub_gdf(
                "https://example.com/layer/0",
                session,
                query_data={"where": "1=1", "resultRecordCount": 500},
            )

    # page_size context comes from the query batch's resultRecordCount.
    assert exc_info.value.page_size == 500


@pytest.mark.asyncio
async def test_get_sub_gdf_raises_on_truncation_geojson() -> None:
    """GeoJSON driver shape: the top-level flag pyogrio strips must raise."""
    session = _TextSession(_GEOJSON_TRUNCATED)

    with patch(
        "restgdf.utils.getgdf.supported_drivers",
        new={"GeoJSON": "rw"},
    ), patch(
        "restgdf.utils.getgdf.read_file",
        new=Mock(name="read_file"),
    ):
        with pytest.raises(PaginationError, match="exceededTransferLimit"):
            await get_sub_gdf(
                "https://example.com/layer/0",
                session,
                query_data={"where": "1=1"},
            )


@pytest.mark.asyncio
async def test_get_sub_gdf_detects_flag_before_read_file() -> None:
    """The flag is read from the parsed JSON, not from ``read_file`` output
    (pyogrio discards it). Assert the raise fires without ``read_file`` being
    called at all."""
    session = _TextSession(_GEOJSON_TRUNCATED)
    read_file_spy = Mock(name="read_file")

    with patch(
        "restgdf.utils.getgdf.supported_drivers",
        new={"GeoJSON": "rw"},
    ), patch(
        "restgdf.utils.getgdf.read_file",
        new=read_file_spy,
    ):
        with pytest.raises(PaginationError, match="exceededTransferLimit"):
            await get_sub_gdf(
                "https://example.com/layer/0",
                session,
                query_data={"where": "1=1"},
            )

    read_file_spy.assert_not_called()


@pytest.mark.asyncio
async def test_get_sub_gdf_allows_non_truncated_page(sample_feature_gdf) -> None:
    """A complete page (exceededTransferLimit=false) still returns a
    GeoDataFrame -- no false positive."""
    session = _TextSession(_GEOJSON_COMPLETE)

    with patch(
        "restgdf.utils.getgdf.supported_drivers",
        new={"GeoJSON": "rw"},
    ), patch(
        "restgdf.utils.getgdf.read_file",
        return_value=sample_feature_gdf,
    ) as mock_read_file:
        result = await get_sub_gdf(
            "https://example.com/layer/0",
            session,
            query_data={"where": "1=1"},
        )

    assert result.equals(sample_feature_gdf)
    mock_read_file.assert_called_once()


@pytest.mark.asyncio
async def test_get_gdf_raises_on_truncated_page(sample_feature_gdf) -> None:
    """End-to-end through the public ``get_gdf``: a truncated page propagates
    a PaginationError instead of a silently-short GeoDataFrame.

    ``read_file`` is stubbed to a valid GeoDataFrame so that in the RED state
    the failure is unambiguously "did not raise" (get_gdf returns a frame),
    not an incidental pyogrio parse error. In the GREEN state the raise fires
    inside ``get_sub_gdf`` before ``read_file`` is ever reached.
    """
    session = _TextSession(_GEOJSON_TRUNCATED)

    with patch(
        "restgdf.utils.getgdf.supported_drivers",
        new={"GeoJSON": "rw"},
    ), patch(
        "restgdf.utils.getgdf.read_file",
        return_value=sample_feature_gdf,
    ), patch(
        "restgdf.utils.getgdf.get_query_data_batches",
        new=AsyncMock(return_value=[{"where": "1=1"}]),
    ), patch(
        "restgdf.utils.getgdf.get_metadata",
        new=AsyncMock(return_value={}),
    ):
        with pytest.raises(PaginationError, match="exceededTransferLimit"):
            await get_gdf("https://example.com/layer/0", session=session)


@pytest.mark.asyncio
async def test_chunk_generator_raises_on_truncated_page(sample_feature_gdf) -> None:
    """Through ``chunk_generator`` (the impl behind ``stream_gdf_chunks``):
    a truncated chunk raises rather than yielding a short GeoDataFrame."""
    session = _TextSession(_GEOJSON_TRUNCATED)

    with patch(
        "restgdf.utils.getgdf.supported_drivers",
        new={"GeoJSON": "rw"},
    ), patch(
        "restgdf.utils.getgdf.read_file",
        return_value=sample_feature_gdf,
    ), patch(
        "restgdf.utils.getgdf.get_query_data_batches",
        new=AsyncMock(return_value=[{"where": "1=1"}]),
    ), patch(
        "restgdf.utils.getgdf.get_metadata",
        new=AsyncMock(return_value={}),
    ):
        with pytest.raises(PaginationError, match="exceededTransferLimit"):
            async for _chunk in chunk_generator(
                "https://example.com/layer/0",
                session,
            ):
                pass
