"""R-28 red tests — GeoDataFrame.attrs['spatial_reference'] carries raw SR dict.

After R-28 green, concat_gdfs will propagate the raw spatialReference dict
from input GDFs to the output GDF so callers needing the full envelope
(e.g. for re-projection) have it via ``gdf.attrs["spatial_reference"]``.
"""

from __future__ import annotations

import pytest

from geopandas import GeoDataFrame
from shapely.geometry import Point


@pytest.mark.asyncio
async def test_concat_gdfs_propagates_spatial_reference_attr():
    """concat_gdfs should carry .attrs['spatial_reference'] to the output."""
    from restgdf.utils.getgdf import concat_gdfs

    raw_sr = {"wkid": 4326, "latestWkid": 4326}

    gdf1 = GeoDataFrame(
        {"geometry": [Point(0, 0)], "OBJECTID": [1]},
        crs="EPSG:4326",
    )
    gdf1.attrs["spatial_reference"] = raw_sr

    gdf2 = GeoDataFrame(
        {"geometry": [Point(1, 1)], "OBJECTID": [2]},
        crs="EPSG:4326",
    )
    gdf2.attrs["spatial_reference"] = raw_sr

    result = await concat_gdfs([gdf1, gdf2])

    assert "spatial_reference" in result.attrs, (
        "concat_gdfs must propagate .attrs['spatial_reference']"
    )
    assert result.attrs["spatial_reference"] == raw_sr


@pytest.mark.asyncio
async def test_concat_gdfs_single_gdf_preserves_attrs():
    """A single-element list should still surface .attrs."""
    from restgdf.utils.getgdf import concat_gdfs

    raw_sr = {"wkid": 3857, "latestWkid": 3857}

    gdf = GeoDataFrame(
        {"geometry": [Point(0, 0)], "OBJECTID": [1]},
        crs="EPSG:3857",
    )
    gdf.attrs["spatial_reference"] = raw_sr

    result = await concat_gdfs([gdf])

    assert result.attrs.get("spatial_reference") == raw_sr


@pytest.mark.asyncio
async def test_concat_gdfs_no_attr_gives_empty_attrs():
    """When inputs lack .attrs, output should not crash (no key)."""
    from restgdf.utils.getgdf import concat_gdfs

    gdf = GeoDataFrame(
        {"geometry": [Point(0, 0)], "OBJECTID": [1]},
        crs="EPSG:4326",
    )
    # No .attrs["spatial_reference"] set

    result = await concat_gdfs([gdf])

    # Should not have the key (or at least not crash)
    assert result.attrs.get("spatial_reference") is None
