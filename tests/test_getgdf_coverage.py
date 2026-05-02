"""T4: fallback/edge-case coverage for ``restgdf.utils.getgdf``.

Focused on uncovered fallback branches:

* :func:`_extract_raw_spatial_reference` — ``None`` / plain-Mapping / unknown-type
  fallbacks around lines 360–392.
* :func:`_iter_pages_raw` — the ``finally:`` block (tasks cancelled, span ended)
  when the streaming body raises mid-iteration.

These tests assert behavioral guarantees only (return values, side effects on
the span and on scheduled tasks). They deliberately do NOT pin request-shape
details such as verb choice or ``max_record_count_factor``.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from geopandas import GeoDataFrame
from shapely.geometry import Point

from restgdf._models.responses import LayerMetadata
from restgdf.utils import getgdf as getgdf_mod
from restgdf.utils.getgdf import (
    _extract_raw_spatial_reference,
    _iter_pages_raw,
    chunk_generator,
)


# ---------------------------------------------------------------------------
# _extract_raw_spatial_reference fallback branches
# ---------------------------------------------------------------------------


def test_extract_raw_spatial_reference_returns_none_for_none_metadata():
    """When metadata is None, no lookup occurs and None is returned."""
    assert _extract_raw_spatial_reference(None) is None


def test_extract_raw_spatial_reference_returns_none_for_unknown_type():
    """Non-LayerMetadata, non-Mapping inputs fall through to ``return None``."""

    class _NotMetadata:
        extent = {"spatialReference": {"wkid": 4326}}

    # Lists / ints / custom objects are neither LayerMetadata nor Mapping.
    assert _extract_raw_spatial_reference(_NotMetadata()) is None
    assert _extract_raw_spatial_reference([1, 2, 3]) is None  # type: ignore[arg-type]
    assert _extract_raw_spatial_reference(42) is None  # type: ignore[arg-type]


def test_extract_raw_spatial_reference_plain_mapping_extent_wins():
    """A plain dict with extent.spatialReference is read via the Mapping branch."""
    raw = {"wkid": 4326, "latestWkid": 4326}
    metadata: Mapping[str, Any] = {"extent": {"spatialReference": raw}}

    result = _extract_raw_spatial_reference(metadata)

    assert result == raw


def test_extract_raw_spatial_reference_plain_mapping_top_level_fallback():
    """When extent is missing, the top-level ``spatialReference`` key is used."""
    raw = {"wkid": 2263}
    metadata: Mapping[str, Any] = {"spatialReference": raw}

    result = _extract_raw_spatial_reference(metadata)

    assert result == raw


def test_extract_raw_spatial_reference_plain_mapping_without_sr_returns_none():
    """A Mapping with no SR in either location returns None without raising."""
    metadata: Mapping[str, Any] = {"name": "Layer", "extent": {"xmin": 0}}

    assert _extract_raw_spatial_reference(metadata) is None


def test_extract_raw_spatial_reference_plain_mapping_non_mapping_extent():
    """Non-Mapping extent value is ignored; fallback continues to top-level."""
    raw = {"wkid": 3857}
    metadata: Mapping[str, Any] = {
        "extent": "not-a-mapping",
        "spatialReference": raw,
    }

    assert _extract_raw_spatial_reference(metadata) == raw


# ---------------------------------------------------------------------------
# _iter_pages_raw: finally-block runs on mid-iteration failure
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_iter_pages_raw_finally_cancels_pending_tasks_and_ends_span():
    """An exception while resolving a page must still run the ``finally:``.

    Behavioral guarantees:
    * any asyncio Tasks scheduled for paging are cancelled when they are not
      already done, and
    * the parent INTERNAL span created for the stream is ended exactly once
      regardless of which page raised.
    """
    url = "https://example.test/FeatureServer/0"

    # Two batches — forcing the 2nd task to remain pending while the 1st
    # triggers a _resolve_page failure, so the ``finally`` has work to cancel.
    batches = [{"where": "1=1"}, {"where": "2=2"}]

    never_done = asyncio.Event()

    async def fake_fetch_page_dict(u, s, qd, **_kw):
        if qd.get("where") == "1=1":
            return {"features": [], "exceededTransferLimit": False}
        # 2nd batch stays pending until we cancel it in the finally block.
        await never_done.wait()
        return {"features": []}

    async def boom_resolve(*_a, **_kw):
        raise RuntimeError("resolve failed")
        # pragma: no cover - generator machinery never reaches here
        yield  # type: ignore[unreachable]

    fake_span = MagicMock()

    with (
        patch.object(
            getgdf_mod,
            "get_query_data_batches",
            AsyncMock(return_value=batches),
        ),
        patch.object(
            getgdf_mod,
            "_fetch_page_dict",
            side_effect=fake_fetch_page_dict,
        ),
        patch.object(getgdf_mod, "_resolve_page", side_effect=boom_resolve),
        patch.object(
            getgdf_mod,
            "start_feature_layer_stream_span",
            return_value=fake_span,
        ),
    ):
        agen = _iter_pages_raw(url, object(), order="request")
        with pytest.raises(RuntimeError, match="resolve failed"):
            async for _ in agen:
                pass

    # span.end() must have been called from the outer ``finally:`` even though
    # iteration aborted with an exception.
    fake_span.end.assert_called_once()


# ---------------------------------------------------------------------------
# chunk_generator: spatial-reference stamping on each yielded chunk
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_chunk_generator_stamps_spatial_reference_on_each_chunk():
    """Each yielded chunk carries ``attrs['spatial_reference']`` when metadata has SR."""
    url = "https://example.test/FeatureServer/0"
    raw_sr = {"wkid": 4326, "latestWkid": 4326}

    metadata = LayerMetadata.model_validate(
        {
            "name": "T",
            "type": "Feature Layer",
            "fields": [{"name": "OBJECTID", "type": "esriFieldTypeOID"}],
            "maxRecordCount": 2,
            "advancedQueryCapabilities": {"supportsPagination": True},
            "extent": {"spatialReference": raw_sr},
        },
    )

    def _sub(oid: int) -> GeoDataFrame:
        return GeoDataFrame(
            {"OBJECTID": [oid], "geometry": [Point(0, 0)]},
            crs="EPSG:4326",
        )

    async def fake_get_sub_gdf(u, s, query_data, **_kw):
        return _sub(int(query_data.get("resultOffset", 0)))

    with (
        patch.object(
            getgdf_mod,
            "get_query_data_batches",
            AsyncMock(
                return_value=[
                    {"resultOffset": 0, "resultRecordCount": 1},
                    {"resultOffset": 1, "resultRecordCount": 1},
                ],
            ),
        ),
        patch.object(getgdf_mod, "get_metadata", AsyncMock(return_value=metadata)),
        patch.object(getgdf_mod, "get_sub_gdf", side_effect=fake_get_sub_gdf),
    ):
        chunks = [chunk async for chunk in chunk_generator(url, object())]

    assert len(chunks) == 2
    for chunk in chunks:
        assert chunk.attrs.get("spatial_reference") == raw_sr


@pytest.mark.asyncio
async def test_chunk_generator_skips_stamping_when_metadata_has_no_sr():
    """Without SR in metadata, chunk_generator yields chunks without the attr."""
    url = "https://example.test/FeatureServer/0"

    metadata = LayerMetadata.model_validate(
        {
            "name": "T",
            "type": "Feature Layer",
            "fields": [{"name": "OBJECTID", "type": "esriFieldTypeOID"}],
            "maxRecordCount": 2,
            "advancedQueryCapabilities": {"supportsPagination": True},
        },
    )

    def _sub() -> GeoDataFrame:
        return GeoDataFrame(
            {"OBJECTID": [1], "geometry": [Point(0, 0)]},
            crs="EPSG:4326",
        )

    async def fake_get_sub_gdf(u, s, query_data, **_kw):
        return _sub()

    with (
        patch.object(
            getgdf_mod,
            "get_query_data_batches",
            AsyncMock(return_value=[{"resultOffset": 0, "resultRecordCount": 1}]),
        ),
        patch.object(getgdf_mod, "get_metadata", AsyncMock(return_value=metadata)),
        patch.object(getgdf_mod, "get_sub_gdf", side_effect=fake_get_sub_gdf),
    ):
        chunks = [chunk async for chunk in chunk_generator(url, object())]

    assert len(chunks) == 1
    assert "spatial_reference" not in chunks[0].attrs


@pytest.mark.asyncio
async def test_apply_spatial_reference_attr_passes_token_and_stamps_raw_sr():
    url = "https://example.test/FeatureServer/0"
    raw_sr = {"wkid": 4326, "latestWkid": 4326}
    session = object()
    gdf = GeoDataFrame({"OBJECTID": [1], "geometry": [Point(0, 0)]}, crs="EPSG:4326")

    with patch.object(
        getgdf_mod,
        "get_metadata",
        AsyncMock(return_value={"extent": {"spatialReference": raw_sr}}),
    ) as get_metadata:
        await getgdf_mod._apply_spatial_reference_attr(
            gdf,
            url,
            session,
            data={"token": "secret", "where": "1=1"},
        )

    get_metadata.assert_awaited_once_with(url, session, token="secret")
    assert gdf.attrs["spatial_reference"] == raw_sr


@pytest.mark.asyncio
async def test_apply_spatial_reference_attr_ignores_metadata_errors():
    url = "https://example.test/FeatureServer/0"
    gdf = GeoDataFrame({"OBJECTID": [1], "geometry": [Point(0, 0)]}, crs="EPSG:4326")

    with patch.object(
        getgdf_mod,
        "get_metadata",
        AsyncMock(side_effect=RuntimeError("metadata unavailable")),
    ):
        await getgdf_mod._apply_spatial_reference_attr(
            gdf,
            url,
            object(),
            data={"token": "secret"},
        )

    assert "spatial_reference" not in gdf.attrs


@pytest.mark.asyncio
async def test_iter_pages_raw_finally_ends_span_when_batches_fail_early():
    """If ``get_query_data_batches`` raises, no tasks exist but span still ends."""
    url = "https://example.test/FeatureServer/0"
    fake_span = MagicMock()

    with (
        patch.object(
            getgdf_mod,
            "get_query_data_batches",
            AsyncMock(side_effect=RuntimeError("batch planning failed")),
        ),
        patch.object(
            getgdf_mod,
            "start_feature_layer_stream_span",
            return_value=fake_span,
        ),
    ):
        agen = _iter_pages_raw(url, object())
        with pytest.raises(RuntimeError, match="batch planning failed"):
            async for _ in agen:
                pass

    fake_span.end.assert_called_once()
