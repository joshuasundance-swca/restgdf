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

from collections.abc import AsyncIterable, Iterable, Sequence
from typing import TYPE_CHECKING, Any

from restgdf.utils._optional import require_pandas

if TYPE_CHECKING:  # pragma: no cover - import-time only
    from pandas import DataFrame

__all__ = ["arows_to_dataframe", "resolve_domains", "rows_to_dataframe"]


def _field_as_dict(field: Any) -> dict[str, Any]:
    """Normalize a ``FieldSpec`` or raw-dict field descriptor to a dict."""
    if isinstance(field, dict):
        return field
    # pydantic v2 model → dict (includes ``model_extra`` keys).
    dump = getattr(field, "model_dump", None)
    if callable(dump):
        return dump()
    return dict(getattr(field, "__dict__", {}))


def resolve_domains(
    df: DataFrame,
    fields: Sequence[Any] | None,
) -> DataFrame:
    """Replace coded-value domain codes with their human-readable names.

    Post-processes an already-materialized ``pandas.DataFrame`` using
    ArcGIS layer field metadata:

    * **Coded-value domains** — values present in the domain's
      ``codedValues`` table are substituted for their ``name``. Codes
      absent from the table pass through unchanged.
    * **Range domains** — values are left as-is. Out-of-range values are
      not flagged or coerced (callers who need strict validation should
      check ``[min, max]`` themselves using the layer's field metadata).

    The input DataFrame is **not** mutated; a shallow copy is returned
    when any substitution is performed, and the original object is
    returned unchanged when ``fields`` is empty / ``None`` or carries no
    applicable domains.

    Parameters
    ----------
    df:
        DataFrame produced by :func:`rows_to_dataframe` /
        :func:`arows_to_dataframe`.
    fields:
        Sequence of field descriptors (either
        :class:`restgdf._models.responses.FieldSpec` instances or raw
        dicts) as found on :attr:`restgdf.FeatureLayer.metadata.fields`.

    Returns
    -------
    pandas.DataFrame
        A DataFrame with applicable coded-value columns resolved.

    Examples
    --------
    >>> import pandas as pd
    >>> from restgdf.adapters.pandas import resolve_domains
    >>> df = pd.DataFrame({"STATUS": [1, 2, 99]})
    >>> fields = [{
    ...     "name": "STATUS",
    ...     "domain": {
    ...         "type": "codedValue",
    ...         "codedValues": [
    ...             {"name": "Active", "code": 1},
    ...             {"name": "Inactive", "code": 2},
    ...         ],
    ...     },
    ... }]
    >>> resolve_domains(df, fields)["STATUS"].tolist()
    ['Active', 'Inactive', 99]
    """
    if not fields:
        return df

    coded_maps: dict[str, dict[Any, Any]] = {}
    for raw_field in fields:
        field = _field_as_dict(raw_field)
        name = field.get("name")
        domain = field.get("domain")
        if not name or not domain or name not in df.columns:
            continue
        if domain.get("type") != "codedValue":
            # Range domains (and any unknown variants) are intentionally
            # pass-through; see the docstring.
            continue
        coded_values = domain.get("codedValues") or []
        mapping = {cv["code"]: cv["name"] for cv in coded_values if "code" in cv}
        if mapping:
            coded_maps[name] = mapping

    if not coded_maps:
        return df

    out = df.copy()
    for col, mapping in coded_maps.items():
        # ``Series.map`` with a dict leaves unmapped values as NaN; we
        # instead use ``replace`` so unknown codes pass through unchanged.
        out[col] = out[col].replace(mapping)
    return out


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
