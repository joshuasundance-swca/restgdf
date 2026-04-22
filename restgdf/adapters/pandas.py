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


def rows_to_dataframe(rows: Iterable[dict[str, Any]]) -> "DataFrame":
    """Materialize an iterable of row-shaped dicts as a ``pandas.DataFrame``.

    Raises :class:`restgdf.errors.OptionalDependencyError` when ``pandas`` is
    not installed.
    """
    pd = require_pandas("restgdf.adapters.pandas.rows_to_dataframe()")
    return pd.DataFrame(list(rows))


async def arows_to_dataframe(rows: AsyncIterable[dict[str, Any]]) -> "DataFrame":
    """Async counterpart of :func:`rows_to_dataframe`.

    Consumes the async iterable to completion, then delegates to
    :func:`rows_to_dataframe`. Raises
    :class:`restgdf.errors.OptionalDependencyError` when ``pandas`` is not
    installed.
    """
    materialized: list[dict[str, Any]] = [row async for row in rows]
    return rows_to_dataframe(materialized)
