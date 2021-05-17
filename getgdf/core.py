"""getgdf/core.py: read ArcGIS REST service as geopandas GeoDataFrame

gpd.read_file(url, driver='ESRIJSON') does not account for max record count limitations
so if you read a service with 100,000 features
but there's a limit of 1000 records per query
then your gdf will only have 1000 features

these functions use a generator to read all features from a service
not limited by max record count

these functions also provide enhanced control over queries
and allow use of any valid authentication scheme
https://developers.arcgis.com/rest/

Joshua Sundance Bailey, SWCA Environmental Consultants
Joshua.Bailey@SWCA.com
05/16/2021
"""


from functools import reduce
from typing import Iterable, Generator

from geopandas import read_file, GeoDataFrame
from pandas import concat
from requests import Session

from helpers import get_offset_range


def default_data(data: dict, default_dict: dict = None) -> dict:
    """Return data dict after adding default values
    Will not replace existing values
    Defaults:
    where: 1=1
    outFields: *
    returnGeometry: True
    returnCountOnly: False
    returnOffset: 0
    f: json
    """
    if default_dict is None:
        default_dict = {
            "where": "1=1",
            "outFields": "*",
            "returnGeometry": True,
            "returnCountOnly": False,
            "resultOffset": 0,
            "f": "json",
        }
    new_data = {k: v for k, v in data.items()}
    for k, v in default_dict.items():
        new_data[k] = new_data.get(k, v)
    return new_data


def gdf_gen(
    url: str, session: Session = Session(), **kwargs
) -> Generator[GeoDataFrame, None, None]:
    """Generate gdfs for a service whose feature count exceeds max record count
    (yields one GeoDataFrame per chunk)
    Keyword arguments are passed on to post request
    """
    for offset in get_offset_range(url, session, **kwargs):
        kwargs["data"]["resultOffset"] = offset
        response = session.post(f"{url}/query", **kwargs)
        sub_gdf = read_file(response.text, driver="ESRIJSON")
        yield sub_gdf
    kwargs["data"]["resultOffset"] = 0


def concat_gdfs(gdf1: GeoDataFrame, gdf2: GeoDataFrame) -> GeoDataFrame:
    """Return GeoDataFrame by concatenating two with the same crs"""
    if gdf1.crs != gdf2.crs:
        # TODO: find a better exception to use for crs mismatch
        raise ValueError("gdfs must have the same crs")
    return GeoDataFrame(concat([gdf1, gdf2], ignore_index=True), crs=gdf1.crs)


def concat_gdf_iter(gdf_list: Iterable[GeoDataFrame]) -> GeoDataFrame:
    """Return GeoDataFrame by concatenating all GeoDataFrames
    in an iterable (eg list, tuple, generator, etc)
    """
    return reduce(concat_gdfs, gdf_list)


def getgdf(url: str, session: Session = Session(), **kwargs) -> GeoDataFrame:
    """Return GeoDataFrame for service

    Keyword arguments are passed on to post request

    Include query parameters like where str and token str in data dict
    """
    # add default values to data dict but don't overwrite existing values
    kwargs["data"] = default_data(kwargs.get("data", {}))
    # cumulatively concat gdfs from generator
    return concat_gdf_iter(gdf_gen(url, session, **kwargs))
