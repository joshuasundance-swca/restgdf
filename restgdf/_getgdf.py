"""restgdf/_getgdf.py: read ArcGIS REST service as geopandas GeoDataFrame

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


from functools import reduce
from typing import Generator, Iterable, Optional

from fiona import supported_drivers
from geopandas import GeoDataFrame, read_file
from pandas import concat
from requests import Session, Response

from ._getinfo import get_offset_range


# TODO: is -> Generator the proper signature?
def gdf_gen(
    url: str, session: Optional[Session] = None, **kwargs
) -> Generator[GeoDataFrame, None, None]:
    """Generate gdfs for a service whose feature count exceeds max record count
    (yields one GeoDataFrame per chunk)
    Keyword arguments are passed on to post request
    """
    session = session or Session()
    datadict: dict = {k: v for k, v in kwargs["data"].items()}
    # TODO: determine best way of handling esrijson vs geojson. use only geojson? check supported drivers?
    # The code below may complicate attempts to read tables. Could check layer type or export format from jsondict
    gdfdriver: str
    if "ESRIJSON" in supported_drivers:
        gdfdriver = "ESRIJSON"
    else:
        gdfdriver = "GeoJSON"
        datadict["f"] = "GeoJSON"
    xkwargs: dict = {k: v for k, v in kwargs.items() if k != "data"}

    for offset in get_offset_range(url, session, **kwargs):
        datadict["resultOffset"] = offset
        response: Response = session.post(f"{url}/query", data=datadict, **xkwargs)
        sub_gdf: GeoDataFrame = read_file(response.text, driver=gdfdriver)
        yield sub_gdf


def concat_gdfs(gdf1: GeoDataFrame, gdf2: GeoDataFrame) -> GeoDataFrame:
    """Return GeoDataFrame by concatenating two with the same crs"""
    if gdf1.crs != gdf2.crs:
        # TODO: find a better exception to use for crs mismatch
        # TODO: consider optional use of gpd.GeoDataFrame.to_crs()
        raise ValueError("gdfs must have the same crs")
    return GeoDataFrame(concat([gdf1, gdf2], ignore_index=True), crs=gdf1.crs)


def concat_gdf_iter(gdf_list: Iterable[GeoDataFrame]) -> GeoDataFrame:
    """Return GeoDataFrame by concatenating all GeoDataFrames
    in an iterable (eg list, tuple, generator, etc)
    """
    return reduce(concat_gdfs, gdf_list)
