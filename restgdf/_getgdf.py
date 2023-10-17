"""Get a GeoDataFrame from an ArcGIS FeatureLayer."""

from asyncio import gather
from functools import reduce

from aiohttp import ClientSession
from geopandas import GeoDataFrame, read_file
from pandas import concat
from pyogrio import list_drivers

from restgdf._getinfo import get_offset_range

supported_drivers = list_drivers()


async def get_gdf_newfunc(
    url: str,
    session: ClientSession,
    **kwargs,
) -> GeoDataFrame:
    """Get a GeoDataFrame from an ArcGIS FeatureLayer."""
    gdfs = await get_gdf_list(url, session, **kwargs)
    return await concat_gdfs(gdfs)


async def get_sub_gdf(
    url: str,
    session: ClientSession,
    offset: int,
    **kwargs,
) -> GeoDataFrame:
    """Get a GeoDataFrame from an ArcGIS FeatureLayer."""
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
    session: ClientSession,
    **kwargs,
) -> list[GeoDataFrame]:
    """Get a list of GeoDataFrames from an ArcGIS FeatureLayer."""
    offset_list = await get_offset_range(url, session, **kwargs)
    tasks = [get_sub_gdf(url, session, offset, **kwargs) for offset in offset_list]
    gdf_list = await gather(*tasks)
    return gdf_list  # type: ignore


async def concat_gdfs(gdfs: list[GeoDataFrame]) -> GeoDataFrame:
    """Concatenate a list of GeoDataFrames."""
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
