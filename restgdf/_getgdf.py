import asyncio
from functools import reduce

from aiohttp import ClientSession
from fiona import supported_drivers
from geopandas import GeoDataFrame, read_file
from pandas import concat

from restgdf._getinfo import get_offset_range


async def get_gdf_newfunc(
    url: str,
    session: ClientSession,
    **kwargs,
) -> GeoDataFrame:
    return await concat_gdfs(await get_gdf_list(url, session, **kwargs))


async def get_sub_gdf(
    url: str,
    session: ClientSession,
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
    sub_gdf = read_file(await response.text(), driver=gdfdriver)
    return sub_gdf


async def get_gdf_list(url: str, session: ClientSession, **kwargs) -> list[GeoDataFrame]:
    offset_list = await get_offset_range(url, session, **kwargs)
    tasks = [get_sub_gdf(url, session, offset, **kwargs) for offset in offset_list]
    gdf_list = await asyncio.gather(*tasks)
    return gdf_list  # type: ignore


async def concat_gdfs(gdfs: list[GeoDataFrame]) -> GeoDataFrame:
    crs = gdfs[0].crs

    if not all(gdf.crs == crs for gdf in gdfs):
        raise ValueError("gdfs must have the same crs")

    def _concat_gdfs(gdf1: GeoDataFrame, gdf2: GeoDataFrame) -> GeoDataFrame:
        return GeoDataFrame(concat([gdf1, gdf2], ignore_index=True), crs=gdf1.crs)

    return reduce(_concat_gdfs, gdfs)
