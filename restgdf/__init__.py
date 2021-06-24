# __future__.annotations needed for
#   class.method -> class signature
#   and type | None = None signature

from __future__ import annotations
from typing import Any, Iterable

from geopandas import GeoDataFrame
from pandas import DataFrame
from requests import Session

from ._getgdf import concat_gdf_iter, gdf_gen
from ._getinfo import (
    default_data,
    get_feature_count,
    get_jsondict,
    get_name,
    getfields,
    getfields_df,
    getuniquevalues,
    getvaluecounts,
    nestedcount,
    FIELDDOESNOTEXIST,
)


def wherevarinlist(var: str, vals: Iterable[str]) -> str:
    """Return str sql query for when variable value is in a list of values
    >>> wherevarinlist("STATE", ["FL", "GA", "SC", "NC"])
    "STATE In ('FL', 'GA', 'SC', 'NC')"
    """
    vals = [f"'{val}'" for val in vals]
    vals_str = f"({', '.join(vals)})"
    return f"{var} In {vals_str}"


def get_gdf(
    url: str,
    session: Session | None = None,
    where: str = None,
    token: str = None,
    **kwargs,
) -> GeoDataFrame:
    """Return GeoDataFrame for service
    Keyword arguments are passed on to post request
    Include query parameters like where str and token str in data dict
    """
    session = session or Session()
    datadict: dict = default_data(kwargs.get("data", {}))
    if where is not None:
        datadict["where"] = where
    if token is not None:
        datadict["token"] = token
    xkwargs: dict = {k: v for k, v in kwargs.items() if k != "data"}
    # cumulatively concat gdfs from generator
    return concat_gdf_iter(gdf_gen(url, session, data=datadict, **xkwargs))


class Rest:
    """Class for facilitating use of get_gdf and associated functions"""

    def __init__(
        self,
        url: str,
        session: Session | None = None,
        auth: Any | None = None,
        where: str = "1=1",
        token: str | None = None,
        **kwargs,
    ):
        self.url: str = url
        self.session: Session = session or Session()
        self.auth: Any = auth
        if self.auth is not None:
            self.session.auth = self.auth

        self.wherestr: str = where
        self.token: str | None = token
        self.kwargs: dict = kwargs
        self.datadict: dict = default_data(kwargs.get("data", {}))
        self.datadict["where"] = self.wherestr
        if self.token is not None:
            self.datadict["token"] = self.token
        self.kwargs["data"] = self.datadict

        self.jsondict: dict = get_jsondict(self.url, self.session, **self.kwargs)
        self.name: str = get_name(self.jsondict)
        self.fields: list = getfields(self.jsondict)
        self.fieldtypes: DataFrame = getfields_df(self.jsondict)
        self.count: int = get_feature_count(self.url, self.session, **self.kwargs)

        self.uniquevalues: dict = {}
        self.valuecounts: dict = {}
        self.nestedcount: dict = {}

        self.gdf: GeoDataFrame | None = None

    def getgdf(self) -> GeoDataFrame:
        """Return data pulled from server and store it as self.gdf"""
        if self.gdf is None:
            self.gdf = get_gdf(self.url, self.session, **self.kwargs)
        return self.gdf

    def getuniquevalues(
        self, fields: tuple | str, sortby: str | None = None
    ) -> list | DataFrame:
        """Get unique values (like pd.Series.unique())"""
        if fields not in self.uniquevalues:
            if (isinstance(fields, str) and fields not in self.fields) or (
                not isinstance(fields, str)
                and any(field not in self.fields for field in fields)
            ):
                raise FIELDDOESNOTEXIST
            self.uniquevalues[fields] = getuniquevalues(
                self.url, fields, sortby, self.session, **self.kwargs
            )
        return self.uniquevalues[fields]

    def getvaluecounts(self, field: str) -> DataFrame:
        """Get unique values and their counts (like pd.DataFrame.value_counts())"""
        if field not in self.valuecounts:
            if field not in self.fields:
                raise FIELDDOESNOTEXIST
            self.valuecounts[field] = getvaluecounts(
                self.url, field, self.session, **self.kwargs
            )
        return self.valuecounts[field]

    def getnestedcount(self, fields: tuple) -> DataFrame:
        """Meant to be used with two fields but 3 works with added wrangling
        ie drop, rename, groupby, agg
        """
        # fields is a tuple so it can be a key in self.nestedcount
        # storing these values to avoid unnecessary queries may be dumb
        if fields not in self.nestedcount:
            if any(field not in self.fields for field in fields):
                raise FIELDDOESNOTEXIST
            self.nestedcount[fields] = nestedcount(
                self.url, fields, self.session, **self.kwargs
            )
        return self.nestedcount[fields]

    def where(self, wherestr: str) -> Rest:
        """Return child Rest object with added wherestr"""
        wherestr_plus = (
            wherestr if self.wherestr == "1=1" else f"{self.wherestr} AND {wherestr}"
        )
        return Rest(
            self.url, self.session, self.auth, wherestr_plus, self.token, **self.kwargs
        )

    def __repr__(self) -> str:
        kwargstr = ", ".join(f"{k}={v}" for k, v in self.kwargs.items())
        return f"Rest({self.url}, {self.session}, {self.auth}, {self.wherestr}, {self.token}, {kwargstr})"

    def __str__(self) -> str:
        return f"{self.name} ({self.url})"
