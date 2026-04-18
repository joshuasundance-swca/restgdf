"""
Upgrade-safety regression tests for getgdf module.

These tests protect against silent breakage when upgrading pandas/geopandas,
particularly around the GeoDataFrame concatenation pattern used in concat_gdfs().
"""

import pytest
from geopandas import GeoDataFrame
from pandas import concat
from shapely.geometry import Point


@pytest.mark.asyncio
async def test_concat_gdfs_import():
    """Verify concat_gdfs function is importable."""
    from restgdf.utils.getgdf import concat_gdfs

    assert callable(concat_gdfs)


def test_concat_gdfs_pattern_with_mock_gdfs():
    """
    Regression test for the concat_gdfs pattern.

    Protects against pandas version changes that might affect:
    - concat() with ignore_index=True
    - GeoDataFrame constructor wrapping
    - Index handling after concatenation
    """
    # Create two minimal GeoDataFrames
    gdf1 = GeoDataFrame(
        {"id": [1, 2], "geometry": [Point(0, 0), Point(1, 1)]},
        crs="EPSG:4326",
    )
    gdf2 = GeoDataFrame(
        {"id": [3, 4], "geometry": [Point(2, 2), Point(3, 3)]},
        crs="EPSG:4326",
    )

    # Replicate the exact pattern from concat_gdfs
    result = GeoDataFrame(
        concat([gdf1, gdf2], ignore_index=True),
        crs=gdf1.crs,
    )

    # Verify the result is valid
    assert isinstance(result, GeoDataFrame)
    assert len(result) == 4
    assert list(result["id"]) == [1, 2, 3, 4]
    assert result.crs == "EPSG:4326"
    assert result.index.tolist() == [0, 1, 2, 3]  # ignore_index worked
    assert all(geom is not None for geom in result.geometry)


def test_concat_gdfs_pattern_mismatched_crs():
    """
    Test that concat_gdfs validates CRS match (as per its check).
    """
    from restgdf.utils.getgdf import concat_gdfs
    import asyncio

    gdf1 = GeoDataFrame(
        {"id": [1], "geometry": [Point(0, 0)]},
        crs="EPSG:4326",
    )
    gdf2 = GeoDataFrame(
        {"id": [2], "geometry": [Point(1, 1)]},
        crs="EPSG:3857",  # different CRS
    )

    with pytest.raises(ValueError, match="same crs"):
        asyncio.run(concat_gdfs([gdf1, gdf2]))


def test_concat_pattern_preserves_geometry():
    """
    Ensure the concat pattern doesn't lose geometry information.
    """
    gdf1 = GeoDataFrame(
        {"name": ["A"], "geometry": [Point(0, 0)]},
        crs="EPSG:4326",
    )
    gdf2 = GeoDataFrame(
        {"name": ["B"], "geometry": [Point(1, 1)]},
        crs="EPSG:4326",
    )

    result = GeoDataFrame(
        concat([gdf1, gdf2], ignore_index=True),
        crs=gdf1.crs,
    )

    assert "geometry" in result.columns
    assert len(result.geometry) == 2
    assert result.geometry[0].equals(Point(0, 0))
    assert result.geometry[1].equals(Point(1, 1))
