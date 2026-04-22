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
    from aiohttp import ClientSession

    from restgdf.utils.token import ArcGISTokenSession

__all__ = ["iter_feature_batches", "iter_gdf_chunks", "iter_rows"]


async def iter_feature_batches(
    url: str,
    session: ClientSession | ArcGISTokenSession,
    **kwargs: Any,
) -> AsyncIterator[list[dict[str, Any]]]:
    """Yield ArcGIS feature batches (lists of raw feature dicts) from ``url``.

    Thin wrapper around :func:`restgdf.utils.getgdf._feature_batch_generator`.
    Core-install safe.
    """
    async for batch in _feature_batch_generator(url, session, **kwargs):
        yield batch


async def iter_rows(
    url: str,
    session: ClientSession | ArcGISTokenSession,
    **kwargs: Any,
) -> AsyncIterator[dict[str, Any]]:
    """Yield row-shaped dicts from ``url``.

    Thin wrapper around :func:`restgdf.utils.getgdf.row_dict_generator`.
    Core-install safe.
    """
    async for row in row_dict_generator(url, session, **kwargs):
        yield row


async def iter_gdf_chunks(
    url: str,
    session: ClientSession | ArcGISTokenSession,
    **kwargs: Any,
) -> AsyncIterator[Any]:
    """Yield ``GeoDataFrame`` chunks from ``url``.

    Thin wrapper around :func:`restgdf.utils.getgdf.chunk_generator`, which
    itself validates the optional geo stack via
    :func:`restgdf.utils._optional.require_geo_stack`. Raises
    :class:`restgdf.errors.OptionalDependencyError` on base installs.
    """
    async for chunk in chunk_generator(url, session, **kwargs):
        yield chunk
