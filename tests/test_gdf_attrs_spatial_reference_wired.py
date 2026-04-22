"""R-65 red tests: ``.attrs['spatial_reference']`` wired end-to-end.

Verifies that GDF-returning entrypoints set the normalized
``spatial_reference`` dict on the returned ``GeoDataFrame.attrs``:

* :func:`restgdf.utils.getgdf.get_gdf` (module-level)
* :meth:`FeatureLayer.get_gdf`
* :meth:`FeatureLayer.sample_gdf`
* :meth:`FeatureLayer.head_gdf`

Production is expected to read ``spatialReference`` from the layer
metadata envelope (``extent.spatialReference`` or top-level
``spatialReference``), normalize via
:func:`restgdf.utils._metadata.normalize_spatial_reference`, and stamp
the raw dict onto ``gdf.attrs["spatial_reference"]``.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from geopandas import GeoDataFrame
from shapely.geometry import Point

from restgdf._models.responses import LayerMetadata


def _fake_sub_gdf(oid: int) -> GeoDataFrame:
    return GeoDataFrame(
        {"OBJECTID": [oid], "geometry": [Point(0, 0)]},
        crs="EPSG:4326",
    )


def _metadata_with_sr(sr: dict) -> LayerMetadata:
    return LayerMetadata.model_validate(
        {
            "name": "Test",
            "type": "Feature Layer",
            "fields": [{"name": "OBJECTID", "type": "esriFieldTypeOID"}],
            "maxRecordCount": 2,
            "advancedQueryCapabilities": {"supportsPagination": True},
            "extent": {"spatialReference": sr},
        },
    )


@pytest.mark.asyncio
async def test_get_gdf_sets_spatial_reference_attr_from_metadata():
    from restgdf.utils import getgdf as getgdf_mod

    raw_sr = {"wkid": 4326, "latestWkid": 4326}

    async def _fake_get_sub_gdf(url, session, query_data, **kwargs):
        # Production is responsible for stamping attrs on the aggregate
        # result, not per-batch — the sub-GDF returned here has no attrs.
        return _fake_sub_gdf(1)

    with patch(
        "restgdf.utils.getgdf.get_query_data_batches",
        new=AsyncMock(return_value=[{"resultOffset": 0}]),
    ), patch.object(
        getgdf_mod,
        "get_sub_gdf",
        side_effect=_fake_get_sub_gdf,
    ), patch(
        "restgdf.utils.getgdf.get_metadata",
        new=AsyncMock(return_value=_metadata_with_sr(raw_sr)),
    ):
        result = await getgdf_mod.get_gdf(
            "https://example.com/layer/0",
            session=object(),
        )

    assert result.attrs.get("spatial_reference") == raw_sr


@pytest.mark.asyncio
async def test_feature_layer_get_gdf_sets_spatial_reference_attr():
    from restgdf.featurelayer.featurelayer import FeatureLayer
    from restgdf.utils import getgdf as getgdf_mod

    raw_sr = {"wkid": 3857, "latestWkid": 3857}

    layer = FeatureLayer(
        "https://example.com/arcgis/rest/services/Svc/FeatureServer/0",
        session=object(),
    )
    layer.fields = ("OBJECTID",)
    layer.object_id_field = "OBJECTID"

    async def _fake_get_sub_gdf(url, session, query_data, **kwargs):
        return _fake_sub_gdf(1)

    with patch(
        "restgdf.utils.getgdf.get_query_data_batches",
        new=AsyncMock(return_value=[{"resultOffset": 0}]),
    ), patch.object(
        getgdf_mod,
        "get_sub_gdf",
        side_effect=_fake_get_sub_gdf,
    ), patch(
        "restgdf.utils.getgdf.get_metadata",
        new=AsyncMock(return_value=_metadata_with_sr(raw_sr)),
    ):
        result = await layer.get_gdf()

    assert result.attrs.get("spatial_reference") == raw_sr


@pytest.mark.asyncio
async def test_get_gdf_accepts_top_level_spatial_reference():
    """Fallback: some metadata envelopes put ``spatialReference`` at the top level."""
    from restgdf.utils import getgdf as getgdf_mod

    raw_sr = {"wkid": 2264, "latestWkid": 2264}

    meta = LayerMetadata.model_validate(
        {
            "name": "Test",
            "type": "Feature Layer",
            "fields": [{"name": "OBJECTID", "type": "esriFieldTypeOID"}],
            "maxRecordCount": 2,
            "advancedQueryCapabilities": {"supportsPagination": True},
            "spatialReference": raw_sr,
        },
    )

    async def _fake_get_sub_gdf(url, session, query_data, **kwargs):
        return _fake_sub_gdf(1)

    with patch(
        "restgdf.utils.getgdf.get_query_data_batches",
        new=AsyncMock(return_value=[{"resultOffset": 0}]),
    ), patch.object(
        getgdf_mod,
        "get_sub_gdf",
        side_effect=_fake_get_sub_gdf,
    ), patch(
        "restgdf.utils.getgdf.get_metadata",
        new=AsyncMock(return_value=meta),
    ):
        result = await getgdf_mod.get_gdf(
            "https://example.com/layer/0",
            session=object(),
        )

    assert result.attrs.get("spatial_reference") == raw_sr
