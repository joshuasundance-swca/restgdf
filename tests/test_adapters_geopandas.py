from __future__ import annotations

import importlib
from typing import Any

import pytest

from restgdf.errors import OptionalDependencyError


def test_rows_to_geodataframe_happy_path() -> None:
    pytest.importorskip("pandas")
    gpd = pytest.importorskip("geopandas")
    pytest.importorskip("pyogrio")
    from shapely.geometry import Point

    from restgdf.adapters.geopandas import rows_to_geodataframe

    gdf = rows_to_geodataframe(
        [
            {"name": "A", "geometry": Point(0, 0)},
            {"name": "B", "geometry": Point(1, 1)},
        ],
        crs="EPSG:4326",
    )

    assert isinstance(gdf, gpd.GeoDataFrame)
    assert list(gdf.columns) == ["name", "geometry"]
    assert gdf.crs is not None
    assert str(gdf.crs).endswith("4326")


@pytest.mark.asyncio
async def test_arows_to_geodataframe_happy_path() -> None:
    pytest.importorskip("pandas")
    gpd = pytest.importorskip("geopandas")
    pytest.importorskip("pyogrio")
    from shapely.geometry import Point

    from restgdf.adapters.geopandas import arows_to_geodataframe

    async def _gen():
        yield {"name": "A", "geometry": Point(0, 0)}
        yield {"name": "B", "geometry": Point(1, 1)}

    gdf = await arows_to_geodataframe(_gen(), crs="EPSG:4326")

    assert isinstance(gdf, gpd.GeoDataFrame)
    assert len(gdf) == 2


def test_rows_to_geodataframe_raises_without_geo_stack(monkeypatch) -> None:
    from restgdf.adapters import geopandas as geopandas_adapter

    def _missing(module_name: str) -> Any:
        exc = ModuleNotFoundError(f"No module named '{module_name}'")
        exc.name = module_name
        raise exc

    monkeypatch.setattr(
        "restgdf.utils._optional.import_module",
        _missing,
    )
    importlib.reload(geopandas_adapter)

    with pytest.raises(OptionalDependencyError) as excinfo:
        geopandas_adapter.rows_to_geodataframe([{"geometry": None}])

    assert "restgdf[geo]" in str(excinfo.value)


@pytest.mark.asyncio
async def test_arows_to_geodataframe_raises_without_geo_stack(monkeypatch) -> None:
    from restgdf.adapters import geopandas as geopandas_adapter

    def _missing(module_name: str) -> Any:
        exc = ModuleNotFoundError(f"No module named '{module_name}'")
        exc.name = module_name
        raise exc

    monkeypatch.setattr(
        "restgdf.utils._optional.import_module",
        _missing,
    )
    importlib.reload(geopandas_adapter)

    async def _gen():
        yield {"geometry": None}

    with pytest.raises(OptionalDependencyError):
        await geopandas_adapter.arows_to_geodataframe(_gen())
