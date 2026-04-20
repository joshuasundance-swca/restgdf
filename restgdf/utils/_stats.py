"""Async statistics/aggregation helpers for ArcGIS REST endpoints.

Private submodule; all public names are re-exported by
``restgdf.utils.getinfo`` to preserve import paths.
"""

from __future__ import annotations

from aiohttp import ClientSession
from pandas import DataFrame, concat

from restgdf._client.request import build_conservative_query_data
from restgdf.utils._http import default_headers
from restgdf.utils.token import ArcGISTokenSession


async def getuniquevalues(
    url: str,
    fields: tuple | str,
    session: ClientSession | ArcGISTokenSession,
    sortby: str | None = None,
    **kwargs,
) -> list | DataFrame:
    """Get the unique values for a field."""
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

    response = await session.post(
        f"{url}/query",
        data=datadict,
        headers=default_headers(xkwargs.pop("headers", None)),
        **xkwargs,
    )
    metadata = await response.json(content_type=None)

    res_l: list | None = None
    res_df: DataFrame | None = None

    if isinstance(fields, str):
        res_l = [x["attributes"][fields] for x in metadata["features"]]
        if sortby and sortby == fields:
            res_l = sorted(res_l)
    elif len(fields) == 1:
        res_l = [x["attributes"][fields[0]] for x in metadata["features"]]
        if sortby and sortby == fields[0]:
            res_l = sorted(res_l)
    else:
        res_df = concat(
            [DataFrame(x).T.reset_index(drop=True) for x in metadata["features"]],
            ignore_index=True,
        )
        if sortby:
            res_df = res_df.sort_values(sortby).reset_index(drop=True)
    return res_l or res_df


async def getvaluecounts(
    url: str,
    field: str,
    session: ClientSession | ArcGISTokenSession,
    **kwargs,
) -> DataFrame:
    """Get the value counts for a field."""
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
    response = await session.post(
        f"{url}/query",
        data=data,
        headers=default_headers(kwargs.pop("headers", None)),
        **kwargs,
    )
    metadata = await response.json(content_type=None)
    features = metadata["features"]
    cc = concat(
        [DataFrame(x["attributes"], index=[0]) for x in features],
        ignore_index=True,
    )
    return cc.sort_values(f"{field}_count", ascending=False).reset_index(drop=True)


async def nestedcount(
    url: str,
    fields,
    session: ClientSession | ArcGISTokenSession,
    **kwargs,
) -> DataFrame:
    """Get the nested value counts for a field."""
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
    response = await session.post(
        f"{url}/query",
        data=data,
        headers=default_headers(kwargs.pop("headers", None)),
        **kwargs,
    )
    metadata = await response.json(content_type=None)
    features = metadata["features"]
    cc = concat(
        [DataFrame(x).T.reset_index(drop=True) for x in features],
        ignore_index=True,
    )
    dropcol = [c for c in cc.columns if c.startswith(f"{fields[0]}_count")][0]
    rencol = [c for c in cc.columns if c.startswith(f"{fields[1]}_count")][0]
    return (
        cc.drop(columns=dropcol)
        .rename(columns={rencol: "Count"})
        .sort_values([fields[0], "Count"], ascending=[True, False])
        .reset_index(drop=True)
    )
