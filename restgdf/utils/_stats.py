"""Async statistics/aggregation helpers for ArcGIS REST endpoints.

Private submodule; all public names are re-exported by
``restgdf.utils.getinfo`` to preserve import paths.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any


from restgdf._client._protocols import AsyncHTTPSession
from restgdf._client.request import build_conservative_query_data
from restgdf._models._drift import _parse_response
from restgdf._models.responses import FeaturesResponse
from restgdf.utils._deprecations import deprecated_alias
from restgdf.utils._http import _arcgis_request, default_headers, default_timeout
from restgdf.utils._optional import require_pandas_dataframe

if TYPE_CHECKING:
    from pandas import DataFrame


def _feature_attributes(feature: dict[str, Any]) -> dict[str, Any]:
    """Normalize a feature payload to its attributes dict."""
    return dict(feature.get("attributes") or {})


def _records_to_frame(
    records: list[dict[str, Any]],
    *,
    feature: str,
    columns: list[str] | None = None,
) -> DataFrame:
    """Build a pandas DataFrame only when a tabular result is requested."""
    DataFrame = require_pandas_dataframe(feature)
    return DataFrame.from_records(records, columns=columns)


def _sorted_scalar_values(values: list[Any | None]) -> list[Any | None]:
    """Sort scalar REST values, falling back to a stable repr-based order."""
    raw_values: list[Any] = list(values)
    try:
        return sorted(raw_values)
    except TypeError:
        return sorted(raw_values, key=lambda value: (value is None, repr(value)))


async def get_unique_values(
    url: str,
    fields: tuple | str,
    session: AsyncHTTPSession,
    sortby: str | None = None,
    **kwargs,
) -> list | DataFrame:
    """Get the unique values for a field."""
    if not isinstance(fields, str) and len(fields) > 1:
        require_pandas_dataframe("get_unique_values() with multiple fields")

    datadict = build_conservative_query_data(
        {
            "where": "1=1",
            "f": "json",
            "returnGeometry": False,
            "returnDistinctValues": True,
            "outFields": fields if isinstance(fields, str) else ",".join(fields),
        },
        kwargs.get("data"),
    )

    xkwargs: dict = {k: v for k, v in kwargs.items() if k != "data"}
    xkwargs.setdefault("timeout", default_timeout())

    response = await _arcgis_request(
        session,
        f"{url}/query",
        datadict,
        headers=default_headers(xkwargs.pop("headers", None)),
        **xkwargs,
    )
    raw = await response.json(content_type=None)
    envelope = _parse_response(FeaturesResponse, raw, context=f"{url}/query")
    features = envelope.features or []
    records = [_feature_attributes(feature) for feature in features]

    if isinstance(fields, str):
        res_l = [record.get(fields) for record in records]
        if sortby and sortby == fields:
            res_l = _sorted_scalar_values(res_l)
        return res_l

    if len(fields) == 1:
        res_l = [record.get(fields[0]) for record in records]
        if sortby and sortby == fields[0]:
            res_l = _sorted_scalar_values(res_l)
        return res_l

    res_df = _records_to_frame(
        records,
        feature="get_unique_values() with multiple fields",
        columns=list(fields),
    )
    if sortby:
        res_df = res_df.sort_values(sortby).reset_index(drop=True)
    return res_df


async def get_value_counts(
    url: str,
    field: str,
    session: AsyncHTTPSession,
    **kwargs,
) -> DataFrame:
    """Get the value counts for a field."""
    require_pandas_dataframe("get_value_counts()")
    statstr = f'[{{"statisticType":"count","onStatisticField":"{field}","outStatisticFieldName":"{field}_count"}}]'
    data = kwargs.pop("data", None) or {}
    data = {
        "where": "1=1",
        "f": "json",
        "returnGeometry": False,
        "outFields": field,
        "outStatistics": statstr,
        "groupByFieldsForStatistics": field,
        **data,
    }
    kwargs.setdefault("timeout", default_timeout())
    response = await _arcgis_request(
        session,
        f"{url}/query",
        data,
        headers=default_headers(kwargs.pop("headers", None)),
        **kwargs,
    )
    raw = await response.json(content_type=None)
    envelope = _parse_response(FeaturesResponse, raw, context=f"{url}/query")
    features = envelope.features or []
    cc = _records_to_frame(
        [_feature_attributes(feature) for feature in features],
        feature="get_value_counts()",
    )
    if cc.empty:
        return cc.reindex(columns=[field, f"{field}_count"])
    return cc.sort_values(f"{field}_count", ascending=False).reset_index(drop=True)


async def nested_count(
    url: str,
    fields,
    session: AsyncHTTPSession,
    **kwargs,
) -> DataFrame:
    """Get the nested value counts for a field."""
    require_pandas_dataframe("nested_count()")
    statstr = "".join(
        (
            "[",
            ",".join(
                f'{{"statisticType":"count","onStatisticField":"{f}","outStatisticFieldName":"{f}_count"}}'
                for f in fields
            ),
            "]",
        ),
    )
    data = kwargs.pop("data", None) or {}
    data = {
        "where": "1=1",
        "f": "json",
        "returnGeometry": False,
        "outFields": ",".join(fields),
        "outStatistics": statstr,
        "groupByFieldsForStatistics": ",".join(fields),
        **data,
    }
    kwargs.setdefault("timeout", default_timeout())
    response = await _arcgis_request(
        session,
        f"{url}/query",
        data,
        headers=default_headers(kwargs.pop("headers", None)),
        **kwargs,
    )
    raw = await response.json(content_type=None)
    envelope = _parse_response(FeaturesResponse, raw, context=f"{url}/query")
    features = envelope.features or []
    cc = _records_to_frame(
        [_feature_attributes(feature) for feature in features],
        feature="nested_count()",
    )
    if cc.empty:
        return cc.reindex(columns=[*fields, "Count"])
    dropcol = [c for c in cc.columns if c.startswith(f"{fields[0]}_count")][0]
    rencol = [c for c in cc.columns if c.startswith(f"{fields[1]}_count")][0]
    return (
        cc.drop(columns=dropcol)
        .rename(columns={rencol: "Count"})
        .sort_values([fields[0], "Count"], ascending=[True, False])
        .reset_index(drop=True)
    )


# Deprecated legacy aliases (Phase 6). See `_deprecations.deprecated_alias`.
getuniquevalues = deprecated_alias(
    get_unique_values,
    "getuniquevalues",
    "get_unique_values",
)
getvaluecounts = deprecated_alias(
    get_value_counts,
    "getvaluecounts",
    "get_value_counts",
)
nestedcount = deprecated_alias(nested_count, "nestedcount", "nested_count")
