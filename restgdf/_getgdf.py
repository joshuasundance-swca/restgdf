"""
Read ArcGIS REST service as geopandas GeoDataFrame

gpd.read_file(url, driver='ESRIJSON') does not account for max record count limitations
so if you read a service with 100,000 features
but there's a limit of 1000 records per query
then your gdf will only have 1000 features

these functions use a generator to read all features from a service
not limited by max record count

these functions also provide enhanced control over queries
and allow use of any valid authentication scheme
https://developers.arcgis.com/rest/

Joshua Sundance Bailey
36394687+joshuasundance@users.noreply.github.com
"""

from contextlib import closing
from typing import Optional

from collections.abc import Generator, Iterable

from fiona import supported_drivers
from geopandas import GeoDataFrame, read_file
from pandas import concat
from requests import Session

from restgdf._getinfo import get_offset_range


def gdf_gen(
    url: str,
    session: Optional[Session] = None,
    **kwargs,
) -> Generator[GeoDataFrame, None, None]:
    """
    Generate gdfs for a service whose feature count exceeds max record count
    (yields one GeoDataFrame per chunk)
    Keyword arguments are passed on to post request
    """
    with closing(session or Session()) as s:
        data = kwargs.pop("data", {})
        gdfdriver = "ESRIJSON" if "ESRIJSON" in supported_drivers else "GeoJSON"
        if gdfdriver == "GeoJSON":
            data["f"] = "GeoJSON"
        kwargs = {k: v for k, v in kwargs.items() if k != "data"}

        for offset in get_offset_range(url, session, **kwargs):
            data["resultOffset"] = offset
            response = s.post(f"{url}/query", data=data, **kwargs)
            sub_gdf = read_file(response.text, driver=gdfdriver)
            yield sub_gdf


def concat_gdfs(gdf_list: Iterable[GeoDataFrame]) -> GeoDataFrame:
    """
    Return GeoDataFrame by concatenating all GeoDataFrames in an iterable (eg list, tuple, generator, etc)
    """
    return concat(gdf_list, ignore_index=True)
