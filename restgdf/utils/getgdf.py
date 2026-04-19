"""Get a GeoDataFrame from an ArcGIS FeatureLayer."""

import asyncio
from asyncio import gather
from collections.abc import AsyncGenerator
from functools import reduce
from typing import Union

from aiohttp import ClientSession
from geopandas import GeoDataFrame, read_file
from pandas import concat
from pyogrio import list_drivers

from restgdf.utils.getinfo import (
    default_data,
    default_headers,
    get_feature_count,
    get_max_record_count,
    get_metadata,
    get_object_ids,
    supports_pagination,
)
from restgdf.utils.token import ArcGISTokenSession
from restgdf.utils.utils import where_var_in_list

supported_drivers = list_drivers()


def combine_where_clauses(base_where: str | None, extra_where: str) -> str:
    """Combine where clauses without changing the default all-records predicate."""
    if base_where in (None, "", "1=1"):
        return extra_where
    return f"({base_where}) AND ({extra_where})"


def chunk_values(values: list[int], chunk_size: int) -> list[list[int]]:
    """Split values into evenly-sized chunks."""
    return [values[i : i + chunk_size] for i in range(0, len(values), chunk_size)]


async def get_query_data_batches(
    url: str,
    session: ClientSession | ArcGISTokenSession,
    **kwargs,
) -> list[dict]:
    """Build query payloads for each request needed to read a layer."""
    request_data = dict(kwargs.get("data") or {})
    feature_count = await get_feature_count(url, session, **kwargs)
    token = request_data.get("token")
    metadata = await get_metadata(url, session, token=token)
    max_record_count = get_max_record_count(metadata)

    if feature_count <= max_record_count:
        return [request_data]

    if supports_pagination(metadata):
        return [
            {**request_data, "resultOffset": offset}
            for offset in range(0, feature_count, max_record_count)
        ]

    object_id_field_name, object_ids = await get_object_ids(url, session, **kwargs)
    base_where = request_data.get("where")
    return [
        {
            **request_data,
            "where": combine_where_clauses(
                base_where,
                where_var_in_list(object_id_field_name, object_id_chunk),
            ),
        }
        for object_id_chunk in chunk_values(object_ids, max_record_count)
    ]


async def get_sub_gdf(
    url: str,
    session: ClientSession | ArcGISTokenSession,
    query_data: dict,
    **kwargs,
) -> GeoDataFrame:
    data = dict(query_data)
    gdfdriver = "ESRIJSON" if "ESRIJSON" in supported_drivers else "GeoJSON"
    if gdfdriver == "GeoJSON":
        data["f"] = "GeoJSON"
    kwargs = {k: v for k, v in kwargs.items() if k != "data"}

    response = await session.post(
        f"{url}/query",
        data=data,
        headers=default_headers(kwargs.pop("headers", None)),
        **kwargs,
    )
    sub_gdf = read_file(
        await response.text(),
        # driver=gdfdriver,  # this line raises a warning when using pyogrio w/ ESRIJSON
        engine="pyogrio",
    )
    return sub_gdf


async def get_gdf_list(
    url: str,
    session: ClientSession | ArcGISTokenSession,
    **kwargs,
) -> list[GeoDataFrame]:
    query_data_batches = await get_query_data_batches(url, session, **kwargs)
    tasks = [
        get_sub_gdf(url, session, query_data=query_data, **kwargs)
        for query_data in query_data_batches
    ]
    gdf_list = await gather(*tasks)
    return gdf_list


async def chunk_generator(
    url: str,
    session: ClientSession | ArcGISTokenSession,
    **kwargs,
) -> AsyncGenerator[GeoDataFrame, None]:
    """
    Asynchronously yield GeoDataFrames from a FeatureLayer in chunks.
    This function retrieves GeoDataFrames in chunks based on the offset range
    and yields each GeoDataFrame as it is retrieved.
    """
    query_data_batches = await get_query_data_batches(url, session, **kwargs)
    tasks = {
        asyncio.create_task(get_sub_gdf(url, session, query_data=query_data, **kwargs))
        for query_data in query_data_batches
    }
    for sub_gdf_future in asyncio.as_completed(tasks):
        yield await sub_gdf_future


async def row_dict_generator(
    url: str,
    session: ClientSession | ArcGISTokenSession,
    **kwargs,
) -> AsyncGenerator[dict, None]:
    async for sub_gdf in chunk_generator(url, session, **kwargs):
        for _, row in sub_gdf.iterrows():
            yield row.to_dict()


async def concat_gdfs(gdfs: list[GeoDataFrame]) -> GeoDataFrame:
    crs = gdfs[0].crs

    if not all(gdf.crs == crs for gdf in gdfs):
        raise ValueError("gdfs must have the same crs")

    return reduce(
        lambda gdf1, gdf2: GeoDataFrame(
            concat([gdf1, gdf2], ignore_index=True),
            crs=gdf1.crs,
        ),
        gdfs,
    )


async def gdf_by_concat(
    url: str,
    session: ClientSession | ArcGISTokenSession,
    **kwargs,
) -> GeoDataFrame:
    gdfs = await get_gdf_list(url, session, **kwargs)
    return await concat_gdfs(gdfs)


async def get_gdf(
    url: str,
    session: Union[ClientSession, None] = None,
    where: Union[str, None] = None,
    token: Union[str, None] = None,
    **kwargs,
) -> GeoDataFrame:
    session = session or ClientSession()
    datadict = default_data(kwargs.pop("data", None) or {})
    if where is not None:
        datadict["where"] = where
    if token is not None:
        existing_token = datadict.get("token")
        if existing_token is not None and existing_token != token:
            raise ValueError(
                "Pass token either via token= or data['token'], not both with different values.",
            )
        datadict["token"] = token
    return await gdf_by_concat(url, session, data=datadict, **kwargs)
