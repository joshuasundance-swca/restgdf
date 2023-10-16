from __future__ import annotations
from typing import Any
from collections.abc import Iterable

from aiohttp import ClientSession
from geopandas import GeoDataFrame
from pandas import DataFrame
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


async def get_gdf(
    url: str,
    session: ClientSession | None = None,
    where: str | None = None,
    token: str | None = None,
    **kwargs,
) -> GeoDataFrame:
    session = session or ClientSession()
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
        session: ClientSession | None = None,
        auth: Any | None = None,
        where: str = "1=1",
        token: str | None = None,
        **kwargs,
    ):
        self.url = url
        self.session = session or ClientSession()
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

        self.uniquevalues: dict[Any, Any] = {}
        self.valuecounts: dict[Any, Any] = {}
        self.nestedcount: dict[Any, Any] = {}

        self.gdf: GeoDataFrame | None = None

    async def prep_from_url(self):
        self.jsondict = await get_jsondict(self.url, self.session, **self.kwargs)
        self.name = get_name(self.jsondict)
        self.fields = await getfields(self.jsondict)
        self.fieldtypes = await getfields_df(self.jsondict)
        self.count = await get_feature_count(self.url, self.session, **self.kwargs)

    @classmethod
    async def from_url(cls, url: str, **kwargs) -> Rest:
        self = cls(url, **kwargs)
        await self.prep_from_url()
        return self

    async def getgdf(self) -> GeoDataFrame:
        if self.gdf is None:
            self.gdf = await get_gdf(self.url, self.session, **self.kwargs)
        return self.gdf

    async def getuniquevalues(
        self,
        fields: tuple | str,
        sortby: str | None = None,
    ) -> list | DataFrame:
        if fields not in self.uniquevalues:
            if (isinstance(fields, str) and fields not in self.fields) or (
                not isinstance(fields, str)
                and any(field not in self.fields for field in fields)
            ):
                raise FIELDDOESNOTEXIST
            self.uniquevalues[fields] = await getuniquevalues(
                self.url,
                fields,
                sortby,
                self.session,
                **self.kwargs,
            )
        return self.uniquevalues[fields]

    async def getvaluecounts(self, field: str) -> DataFrame:
        if field not in self.valuecounts:
            if field not in self.fields:
                raise FIELDDOESNOTEXIST
            self.valuecounts[field] = await getvaluecounts(
                self.url,
                field,
                self.session,
                **self.kwargs,
            )
        return self.valuecounts[field]

    async def getnestedcount(self, fields: tuple) -> DataFrame:
        if fields not in self.nestedcount:
            if any(field not in self.fields for field in fields):
                raise FIELDDOESNOTEXIST
            self.nestedcount[fields] = await nestedcount(
                self.url,
                fields,
                self.session,
                **self.kwargs,
            )
        return self.nestedcount[fields]

    async def where(self, wherestr: str) -> Rest:
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
