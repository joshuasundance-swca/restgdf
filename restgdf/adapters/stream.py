"""Core-install safe streaming adapters over ArcGIS pagination.

Thin async-iterator wrappers over the existing pagination helpers in
:mod:`restgdf.utils.getgdf`. Row-level and feature-batch-level iteration are
safe on a base install; ``iter_gdf_chunks`` requires the optional geo stack
and gates at call time via :func:`restgdf.utils.getgdf.chunk_generator`'s
internal call to :func:`restgdf.utils._optional.require_geo_stack`.

The public streaming surface (``stream_features``, ``stream_feature_batches``,
ordering guarantees, backpressure options) is planned to expand in phase-4a
under MASTER-PLAN BL-24. The names exposed here are the minimum viable set
that today's callers can depend on; their shape is compatible with the
planned BL-24 expansion.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

from restgdf.utils.getgdf import (
    _feature_batch_generator,
    chunk_generator,
    row_dict_generator,
)

if TYPE_CHECKING:  # pragma: no cover - import-time only
    from restgdf._client._protocols import AsyncHTTPSession

__all__ = ["iter_feature_batches", "iter_gdf_chunks", "iter_rows"]


async def iter_feature_batches(
    url: str,
    session: AsyncHTTPSession,
    **kwargs: Any,
) -> AsyncIterator[list[dict[str, Any]]]:
    """Yield ArcGIS feature batches (lists of raw feature dicts) from ``url``.

    Thin wrapper around :func:`restgdf.utils.getgdf._feature_batch_generator`.
    Core-install safe — no pandas / geopandas dependency.

    Parameters
    ----------
    url:
        Fully qualified ArcGIS FeatureServer/MapServer layer URL.
    session:
        An :class:`aiohttp.ClientSession` or
        :class:`restgdf.ArcGISTokenSession`.
    **kwargs:
        Forwarded to the underlying batch generator (``data``,
        ``where``, ``outFields``, ``token``, etc.).

    Yields
    ------
    list[dict[str, Any]]
        One list of raw ArcGIS feature dicts per page.

    Examples
    --------
    >>> import asyncio, aiohttp
    >>> from restgdf.adapters.stream import iter_feature_batches
    >>> async def demo(url):  # doctest: +SKIP
    ...     async with aiohttp.ClientSession() as s:
    ...         async for batch in iter_feature_batches(url, s):
    ...             print(len(batch))

    See Also
    --------
    :meth:`restgdf.FeatureLayer.stream_feature_batches`
        Preferred high-level entrypoint with ``order``,
        ``max_concurrent_pages``, and ``on_truncation`` knobs.
    """
    async for batch in _feature_batch_generator(url, session, **kwargs):
        yield batch


async def iter_rows(
    url: str,
    session: AsyncHTTPSession,
    **kwargs: Any,
) -> AsyncIterator[dict[str, Any]]:
    """Yield row-shaped dicts from ``url``.

    Thin wrapper around :func:`restgdf.utils.getgdf.row_dict_generator`.
    Core-install safe — no pandas / geopandas dependency.

    Parameters
    ----------
    url:
        Fully qualified ArcGIS FeatureServer/MapServer layer URL.
    session:
        An :class:`aiohttp.ClientSession` or
        :class:`restgdf.ArcGISTokenSession`.
    **kwargs:
        Forwarded to :func:`restgdf.utils.getgdf.row_dict_generator`.

    Yields
    ------
    dict[str, Any]
        ``{**feature["attributes"], "geometry": feature.get("geometry")}``
        per feature.

    Examples
    --------
    >>> async for row in iter_rows(url, session):  # doctest: +SKIP
    ...     print(row["OBJECTID"], row["geometry"])

    See Also
    --------
    :meth:`restgdf.FeatureLayer.stream_rows`
        Preferred high-level entrypoint with streaming ordering and
        truncation-handling knobs.
    """
    async for row in row_dict_generator(url, session, **kwargs):
        yield row


async def iter_gdf_chunks(
    url: str,
    session: AsyncHTTPSession,
    **kwargs: Any,
) -> AsyncIterator[Any]:
    """Yield ``GeoDataFrame`` chunks from ``url``.

    Requires the optional geo extra: ``pip install "restgdf[geo]"``. Thin
    wrapper around :func:`restgdf.utils.getgdf.chunk_generator`, which
    itself validates the optional geo stack via
    :func:`restgdf.utils._optional.require_geo_stack`.

    Parameters
    ----------
    url:
        Fully qualified ArcGIS FeatureServer/MapServer layer URL.
    session:
        An :class:`aiohttp.ClientSession` or
        :class:`restgdf.ArcGISTokenSession`.
    **kwargs:
        Forwarded to :func:`restgdf.utils.getgdf.chunk_generator`.

    Yields
    ------
    geopandas.GeoDataFrame
        One chunk per ArcGIS query page.

    Raises
    ------
    restgdf.errors.OptionalDependencyError
        When ``pandas``, ``geopandas``, or ``pyogrio`` is missing.

    See Also
    --------
    :meth:`restgdf.FeatureLayer.stream_gdf_chunks`
        Preferred high-level entrypoint. Each yielded chunk carries
        ``gdf.attrs["spatial_reference"]`` populated from layer metadata
        (R-65).
    """
    async for chunk in chunk_generator(url, session, **kwargs):
        yield chunk
