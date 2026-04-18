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

from restgdf.utils.getinfo import default_data, get_offset_range
from restgdf.utils.token import ArcGISTokenSession

supported_drivers = list_drivers()


async def get_sub_gdf(
    url: str,
    session: ClientSession | ArcGISTokenSession,
    offset: int,
    **kwargs,
) -> GeoDataFrame:
    data = kwargs.pop("data", {})
    gdfdriver = "ESRIJSON" if "ESRIJSON" in supported_drivers else "GeoJSON"
    if gdfdriver == "GeoJSON":
        data["f"] = "GeoJSON"
    kwargs = {k: v for k, v in kwargs.items() if k != "data"}

    data["resultOffset"] = offset
    response = await session.post(f"{url}/query", data=data, **kwargs)
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
    offset_list = await get_offset_range(url, session, **kwargs)
    tasks = [get_sub_gdf(url, session, offset, **kwargs) for offset in offset_list]
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
    offset_list = await get_offset_range(url, session, **kwargs)
    tasks = {
        asyncio.create_task(get_sub_gdf(url, session, offset, **kwargs))
        for offset in offset_list
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
    datadict = default_data(kwargs.pop("data", {}))
    if where is not None:
        datadict["where"] = where
    if token is not None:
        datadict["token"] = token
    return await gdf_by_concat(url, session, data=datadict, **kwargs)
