"""Pandas-gated tabular adapters.

Materialize row-shaped dict iterables into a :class:`pandas.DataFrame`. The
module itself is safe to import on a base restgdf install — pandas is loaded
lazily via :func:`restgdf.utils._optional.require_pandas` **inside** each
adapter function, so importing this module on a pandas-free install does not
raise. Calling an adapter function on such an install raises
:class:`restgdf.errors.OptionalDependencyError` with the canonical
``restgdf[geo]`` guidance.
"""

from __future__ import annotations

from collections.abc import AsyncIterable, Iterable
from typing import TYPE_CHECKING, Any

from restgdf.utils._optional import require_pandas

if TYPE_CHECKING:  # pragma: no cover - import-time only
    from pandas import DataFrame

__all__ = ["arows_to_dataframe", "rows_to_dataframe"]


def rows_to_dataframe(rows: Iterable[dict[str, Any]]) -> DataFrame:
    """Materialize an iterable of row-shaped dicts as a ``pandas.DataFrame``.

    Parameters
    ----------
    rows:
        Any iterable of row-shaped dicts — typically produced by
        :func:`restgdf.adapters.dict.features_to_rows` or collected from
        :meth:`restgdf.FeatureLayer.stream_rows`.

    Returns
    -------
    pandas.DataFrame

    Raises
    ------
    restgdf.errors.OptionalDependencyError
        When ``pandas`` is not installed. Install the optional extra via
        ``pip install "restgdf[geo]"`` (which ships pandas alongside the
        geo stack) or install ``pandas`` directly.

    Examples
    --------
    >>> from restgdf.adapters.pandas import rows_to_dataframe
    >>> rows_to_dataframe([{"OBJECTID": 1, "NAME": "A"}])  # doctest: +SKIP
       OBJECTID NAME
    0         1    A

    See Also
    --------
    :meth:`restgdf.FeatureLayer.get_df`
        Async pandas-first tabular accessor that wraps this adapter over
        a live layer.
    """
    pd = require_pandas("restgdf.adapters.pandas.rows_to_dataframe()")
    return pd.DataFrame(list(rows))


async def arows_to_dataframe(rows: AsyncIterable[dict[str, Any]]) -> DataFrame:
    """Async counterpart of :func:`rows_to_dataframe`.

    Consumes the async iterable to completion, then delegates to
    :func:`rows_to_dataframe`.

    Parameters
    ----------
    rows:
        Async iterable of row-shaped dicts — typically
        :meth:`restgdf.FeatureLayer.stream_rows` or
        :func:`restgdf.adapters.stream.iter_rows`.

    Returns
    -------
    pandas.DataFrame

    Raises
    ------
    restgdf.errors.OptionalDependencyError
        When ``pandas`` is not installed. Install via ``pip install
        "restgdf[geo]"`` (geo extra bundles pandas) or ``pip install pandas``.

    Examples
    --------
    >>> import asyncio
    >>> from restgdf.adapters.pandas import arows_to_dataframe
    >>> async def demo():
    ...     async def rows():
    ...         yield {"OBJECTID": 1}
    ...     return await arows_to_dataframe(rows())
    >>> asyncio.run(demo())  # doctest: +SKIP
       OBJECTID
    0         1

    See Also
    --------
    :meth:`restgdf.FeatureLayer.get_df`
        Convenience accessor equivalent to
        ``await arows_to_dataframe(layer.stream_rows())``.
    """
    materialized: list[dict[str, Any]] = [row async for row in rows]
    return rows_to_dataframe(materialized)
