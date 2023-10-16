from __future__ import annotations

from typing import Any

from collections.abc import Iterable

from geopandas import GeoDataFrame
from pandas import DataFrame
from requests import Session

from restgdf._getgdf import concat_gdfs, gdf_gen
from restgdf._getinfo import (
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


def _wherevarinlist(var: str, vals: Iterable[str]) -> str:
    vals_str = ", ".join(f"'{val}'" for val in vals)
    return f"{var} In ({vals_str})"


def get_gdf(
    url: str,
    session: Session | None = None,
    where: str | None = None,
    token: str | None = None,
    **kwargs,
) -> GeoDataFrame:
    session = session or Session()
    datadict = default_data(kwargs.pop("data", {}))
    if where is not None:
        datadict["where"] = where
    if token is not None:
        datadict["token"] = token
    return concat_gdfs(gdf_gen(url, session, data=datadict, **kwargs))


class Rest:
    def __init__(
        self,
        url: str,
        session: Session | None = None,
        auth: Any | None = None,
        where: str = "1=1",
        token: str | None = None,
        **kwargs,
    ):
        self.url = url
        self.session = session or Session()
        self.auth = auth
        if self.auth is not None:
            self.session.auth = self.auth

        self.wherestr = where
        self.token = token
        self.kwargs = kwargs
        self.datadict = default_data(kwargs.pop("data", {}))
        self.datadict["where"] = self.wherestr
        if self.token is not None:
            self.datadict["token"] = self.token
        self.kwargs["data"] = self.datadict

        self.jsondict = get_jsondict(self.url, self.session, **self.kwargs)
        self.name = get_name(self.jsondict)
        self.fields = getfields(self.jsondict)
        self.fieldtypes = getfields_df(self.jsondict)
        self.count = get_feature_count(self.url, self.session, **self.kwargs)

        self.uniquevalues: dict[Any, Any] = {}
        self.valuecounts: dict[Any, Any] = {}
        self.nestedcount: dict[Any, Any] = {}

        self.gdf: GeoDataFrame | None = None

    def getgdf(self) -> GeoDataFrame:
        """Return data pulled from server and store it as self.gdf"""
        if self.gdf is None:
            self.gdf = get_gdf(self.url, self.session, **self.kwargs)
        return self.gdf

    def getuniquevalues(
        self,
        fields: tuple | str,
        sortby: str | None = None,
    ) -> list | DataFrame:
        """Get unique values (like pd.Series.unique())"""
        if fields not in self.uniquevalues:
            if (isinstance(fields, str) and fields not in self.fields) or (
                not isinstance(fields, str)
                and any(field not in self.fields for field in fields)
            ):
                raise FIELDDOESNOTEXIST
            self.uniquevalues[fields] = getuniquevalues(
                self.url,
                fields,
                sortby,
                self.session,
                **self.kwargs,
            )
        return self.uniquevalues[fields]

    def getvaluecounts(self, field: str) -> DataFrame:
        """Get unique values and their counts (like pd.DataFrame.value_counts())"""
        if field not in self.valuecounts:
            if field not in self.fields:
                raise FIELDDOESNOTEXIST
            self.valuecounts[field] = getvaluecounts(
                self.url,
                field,
                self.session,
                **self.kwargs,
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
                self.url,
                fields,
                self.session,
                **self.kwargs,
            )
        return self.nestedcount[fields]

    def where(self, wherestr: str) -> Rest:
        """Return child Rest object with added wherestr"""
        wherestr_plus = (
            wherestr if self.wherestr == "1=1" else f"{self.wherestr} AND {wherestr}"
        )
        return Rest(
            self.url,
            self.session,
            self.auth,
            wherestr_plus,
            self.token,
            **self.kwargs,
        )

    def __repr__(self) -> str:
        kwargstr = ", ".join(f"{k}={v}" for k, v in self.kwargs.items())
        return f"Rest({self.url}, {self.session}, {self.auth}, {self.wherestr}, {self.token}, {kwargstr})"

    def __str__(self) -> str:
        return f"{self.name} ({self.url})"
