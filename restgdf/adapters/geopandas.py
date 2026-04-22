"""Geopandas-gated geo-tabular adapters.

Materialize row-shaped dict iterables into a :class:`geopandas.GeoDataFrame`.
The module itself is safe to import on a base restgdf install — the geo
stack (``pandas`` + ``geopandas`` + ``pyogrio``) is loaded lazily via
:func:`restgdf.utils._optional.require_geo_stack` **inside** each adapter
function. Calling an adapter on a base install raises
:class:`restgdf.errors.OptionalDependencyError`.

Scope note
----------
Phase-2d keeps geometry handling minimal: the adapters pass the materialized
row table directly to ``geopandas.GeoDataFrame`` with ``geometry=geometry_field``.
Callers are expected to supply shapely-compatible geometry values, already-built
``GeoSeries`` elements, or to leave the field empty for tabular-only flows.
Full ArcGIS geometry-dict normalization (points, polylines, polygons,
mixed-Z/M, spatial-reference promotion) ships with MASTER-PLAN BL-27 / BL-28
in phase-2b and BL-35 in phase-4b.
"""

from __future__ import annotations

from collections.abc import AsyncIterable, Iterable
from typing import TYPE_CHECKING, Any

from restgdf.utils._optional import require_geo_stack, require_geopandas

if TYPE_CHECKING:  # pragma: no cover - import-time only
    from geopandas import GeoDataFrame

__all__ = ["arows_to_geodataframe", "rows_to_geodataframe"]


def rows_to_geodataframe(
    rows: Iterable[dict[str, Any]],
    *,
    geometry_field: str = "geometry",
    crs: Any = None,
) -> GeoDataFrame:
    """Materialize row-shaped dicts as a ``geopandas.GeoDataFrame``.

    Requires the optional geo extra: ``pip install "restgdf[geo]"`` (brings
    in ``pandas``, ``geopandas``, and ``pyogrio``).

    Parameters
    ----------
    rows:
        Iterable of row-shaped dicts, typically produced by
        :func:`restgdf.adapters.stream.iter_rows` or
        :func:`restgdf.adapters.dict.features_to_rows`. Each row's
        ``geometry_field`` entry must be shapely-compatible (or a
        ``GeoSeries`` element).
    geometry_field:
        Column name holding the geometry values. Defaults to ``"geometry"``.
    crs:
        Optional CRS passed through to ``GeoDataFrame(crs=...)``.

    Returns
    -------
    geopandas.GeoDataFrame

    Raises
    ------
    restgdf.errors.OptionalDependencyError
        When any of ``pandas``, ``geopandas``, or ``pyogrio`` is missing.
        Install via ``pip install "restgdf[geo]"``.

    Examples
    --------
    >>> from shapely.geometry import Point  # doctest: +SKIP
    >>> rows_to_geodataframe(  # doctest: +SKIP
    ...     [{"OBJECTID": 1, "geometry": Point(0, 0)}],
    ...     crs="EPSG:4326",
    ... )

    See Also
    --------
    :meth:`restgdf.FeatureLayer.get_gdf`
        High-level accessor that returns the full layer as a single
        ``GeoDataFrame``.
    :meth:`restgdf.FeatureLayer.stream_gdf_chunks`
        Async iterator yielding one ``GeoDataFrame`` per page, each with
        ``gdf.attrs["spatial_reference"]`` populated from layer metadata.
    """
    require_geo_stack("restgdf.adapters.geopandas.rows_to_geodataframe()")
    GeoDataFrameCls = require_geopandas(
        "restgdf.adapters.geopandas.rows_to_geodataframe()",
    ).GeoDataFrame
    materialized = list(rows)
    return GeoDataFrameCls(materialized, geometry=geometry_field, crs=crs)


async def arows_to_geodataframe(
    rows: AsyncIterable[dict[str, Any]],
    *,
    geometry_field: str = "geometry",
    crs: Any = None,
) -> GeoDataFrame:
    """Async counterpart of :func:`rows_to_geodataframe`.

    Consumes the async iterable to completion, then delegates. Requires the
    optional geo extra: ``pip install "restgdf[geo]"``.

    Parameters
    ----------
    rows:
        Async iterable of row-shaped dicts — typically
        :meth:`restgdf.FeatureLayer.stream_rows` or
        :func:`restgdf.adapters.stream.iter_rows`.
    geometry_field:
        Column name for the geometry column. Defaults to ``"geometry"``.
    crs:
        Optional CRS forwarded to ``GeoDataFrame(crs=...)``.

    Returns
    -------
    geopandas.GeoDataFrame

    Raises
    ------
    restgdf.errors.OptionalDependencyError
        When any of ``pandas``, ``geopandas``, or ``pyogrio`` is missing.

    See Also
    --------
    :meth:`restgdf.FeatureLayer.get_gdf`
        Equivalent to ``await arows_to_geodataframe(layer.stream_rows())``
        with geometry normalization and CRS propagation handled for you.
    """
    materialized: list[dict[str, Any]] = [row async for row in rows]
    return rows_to_geodataframe(
        materialized,
        geometry_field=geometry_field,
        crs=crs,
    )
