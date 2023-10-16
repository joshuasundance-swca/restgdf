from contextlib import asynccontextmanager
from typing import Optional
from collections.abc import AsyncGenerator

from aiohttp import ClientSession
from fiona import supported_drivers
from geopandas import GeoDataFrame, read_file
from pandas import concat

from restgdf._getinfo import get_offset_range


@asynccontextmanager
async def get_session():
    async with ClientSession() as session:
        yield session


async def gdf_gen(
    url: str,
    session: Optional[ClientSession] = None,
    **kwargs,
) -> AsyncGenerator[GeoDataFrame, None]:
    async with get_session() as s:
        data = kwargs.pop("data", {})
        gdfdriver = "ESRIJSON" if "ESRIJSON" in supported_drivers else "GeoJSON"
        if gdfdriver == "GeoJSON":
            data["f"] = "GeoJSON"
        kwargs = {k: v for k, v in kwargs.items() if k != "data"}

        for offset in await get_offset_range(url, session, **kwargs):
            data["resultOffset"] = offset
            response = await s.post(f"{url}/query", data=data, **kwargs)
            sub_gdf = read_file(await response.text(), driver=gdfdriver)
            yield sub_gdf


async def concat_gdfs(gdf_list: AsyncGenerator[GeoDataFrame, None]) -> GeoDataFrame:
    gdfs = [gdf async for gdf in gdf_list]
    return concat(gdfs, ignore_index=True)
