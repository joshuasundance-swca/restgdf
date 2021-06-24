# Joshua Bailey 6/8/2020
# Inspired by DataPillager but didn't see the need for arcpy
# Probably not as robust but it's a start, right?

# ripped apart by jb starting 05/19/2021

from requests import get

from pandas import DataFrame, concat

# from importlib.util import find_spec

# def pkgcheck(pkg: str) -> bool:
#     """Return True if pkg is available for import, else return False"""
#     return find_spec(pkg) is not none

# def supportedqueryformats(jsondict: dict = None) -> list:
#     """Return supported query output datatypes"""
#     return [
#         x.strip().lower()
#         for x in {k.lower().replace(" ", ""): v for k, v in jsondict.items()}[
#             "supportedqueryformats"
#         ].split(",")
#     ]


# def jsontogdf(jsondict: dict) -> GeoDataFrame:
#     """Return geodataframe given json parsed to dict (for when geojson is not available)"""
#     try:
#         return GeoDataFrame(
#             concat(
#                 [DataFrame(x["attributes"], index=[0]) for x in jsondict["features"]],
#                 ignore_index=True,
#             ),
#             geometry=points_from_xy(
#                 [f["geometry"]["x"] for f in jsondict["features"]],
#                 [f["geometry"]["y"] for f in jsondict["features"]],
#             ),
#             crs=f"EPSG:{jsondict['spatialReference']['latestWkid']}",
#         )
#     except KeyError:
#         print("keyerror")
#         print(jsondict)
#         raise


# class Ripper:
#     """Class for pulling data from ArcGIS REST Services layers"""
#
#     def __init__(self, url: str, wherestr: str = "1=1"):
#         """Create Ripper instance given url and optional filtering wherestr
#         Set variables: url, name, count, fields, etc
#         """
#         self.url = url
#         self._wherestr = wherestr
#         self._jsondict = get(f"{self.url}?f=json").json()
#         self._ltype = self._jsondict["type"]
#         if self._ltype == "Feature Layer":
#             self._extent = self._jsondict["extent"]
#         self._outputs = supportedqueryformats(jsondict=self._jsondict)
#         self.name, self._mrc = getNameAndMRC(jsondict=self._jsondict)
#         self.count = getNumberOfFeatures(self.url, wherestr=self._wherestr)
#         self.fields = getfields(jsondict=self._jsondict, types=True)
#
#     def uniquevalues(self, fields, sortby: str = None):
#         """Return list of unique values if fields is str or list of len 1
#         Otherwise return pandas DataFrame of unique combinations, optionally sorted by field sortby
#         """
#         return getuniquevalues(self.url, fields, sortby, self._wherestr)
#
#     def valuecounts(self, fields, retdict: bool = False) -> DataFrame:
#         """Return DataFrame containing value counts (or dict if retdict=True) if fields is a str
#         Return DataFrame containing count values for 2-field combinations if fields is a list
#         """
#         if type(fields) == list:
#             if len(fields) > 1:
#                 return nestedcount(self.url, fields, self._wherestr)
#             else:
#                 fields = fields[0]
#         if type(fields) == str:
#             return getvaluecounts(self.url, fields, retdict, self._wherestr)
#
#     def rip(self) -> GeoDataFrame:
#         """Return geodataframe using current wherestr and store as self.gdf or self.df"""
#         res = ripdata(
#             url=self.url,
#             wherestr=self._wherestr,
#             name=self.name,
#             mrc=self._mrc,
#             nof=self.count,
#             ltype=self._ltype,
#             jsondict=self._jsondict,
#         )
#         if self._ltype == "Feature Layer":
#             self.gdf = res
#         elif self._ltype == "Table":
#             self.df = res
#         return res
#
#     def where(self, wherestr: str):
#         """Return new Ripper object using current URL with ADDITIONAL filter/wherestr
#         For a new wherestr without current filters, use Ripper(url, [wherestr])
#         """
#         return Ripper(
#             self.url,
#             f"{f'{self._wherestr} AND ' if self._wherestr != '1=1' else ''}{wherestr}",
#         )
