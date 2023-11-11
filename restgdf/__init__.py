"""A package for getting GeoDataFrames from ArcGIS FeatureLayers."""

from __future__ import annotations

import random
import re
from collections.abc import Iterable
from typing import Any

from aiohttp import ClientSession
from geopandas import GeoDataFrame
from pandas import DataFrame

from restgdf._getgdf import get_gdf_newfunc
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

__version__ = "0.3.0"

ends_with_num_pat = re.compile(r"\d+$")


def _wherevarinlist(var: str, vals: Iterable[str]) -> str:
    """Return a where clause for a variable in a list of values."""
    vals_str = ", ".join(f"'{val}'" for val in vals)
    return f"{var} In ({vals_str})"


async def get_gdf(
    url: str,
    session: ClientSession | None = None,
    where: str | None = None,
    token: str | None = None,
    **kwargs,
) -> GeoDataFrame:
    """Get a GeoDataFrame from an ArcGIS FeatureLayer."""
    session = session or ClientSession()
    datadict = default_data(kwargs.pop("data", {}))
    if where is not None:
        datadict["where"] = where
    if token is not None:
        datadict["token"] = token
    return await get_gdf_newfunc(url, session, data=datadict, **kwargs)


class Rest:
    """A class for interacting with ArcGIS FeatureLayers."""

    def __init__(
        self,
        url: str,
        session: ClientSession | None = None,
        auth: Any | None = None,
        where: str = "1=1",
        token: str | None = None,
        **kwargs,
    ):
        """A class for interacting with ArcGIS FeatureLayers."""
        if not ends_with_num_pat.search(url):
            raise ValueError(
                "The url must end with a number, which is the layer id of the FeatureLayer.",
            )
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

        self.jsondict: dict
        self.name: str
        self.fields: tuple[str, ...]
        self.fieldtypes: DataFrame
        self.count: int

    async def prep(self):
        """Prepare the Rest object."""
        self.jsondict = await get_jsondict(self.url, self.session, **self.kwargs)
        try:
            if not self.jsondict["type"] == "Feature Layer":
                raise ValueError("The url must point to a FeatureLayer.")
        except KeyError:
            raise ValueError("The url must point to a FeatureLayer.")
        self.name = get_name(self.jsondict)
        self.fields = getfields(self.jsondict)
        self.fieldtypes = getfields_df(self.jsondict)
        self.count = await get_feature_count(self.url, self.session, **self.kwargs)

    @classmethod
    async def from_url(cls, url: str, **kwargs) -> Rest:
        """Create a Rest object from a url."""
        self = cls(url, **kwargs)
        await self.prep()
        return self

    async def getoids(self) -> list[int]:
        """Get the object ids for the Rest object."""
        return await self.getuniquevalues(self.url, "OBJECTID")

    async def samplegdf(self, n: int = 10) -> GeoDataFrame:
        """Get n random features as a GeoDataFrame."""
        oids = await getuniquevalues(self.url, "OBJECTID", self.session, **self.kwargs)
        sample_oids = random.sample(oids, min(n, len(oids)))
        wherestr = _wherevarinlist("OBJECTID", sample_oids)
        new_rest = await self.where(wherestr)
        return await new_rest.getgdf()

    async def headgdf(self, n: int = 10) -> GeoDataFrame:
        """Get the n first features as a GeoDataFrame."""
        oids = await getuniquevalues(self.url, "OBJECTID", self.session, **self.kwargs)
        head_oids = oids[:n]
        wherestr = _wherevarinlist("OBJECTID", head_oids)
        new_rest = await self.where(wherestr)
        return await new_rest.getgdf()

    async def getgdf(self) -> GeoDataFrame:
        """Get a GeoDataFrame from an ArcGIS FeatureLayer."""
        if self.gdf is None:
            self.gdf = await get_gdf(self.url, self.session, **self.kwargs)
        return self.gdf

    async def getuniquevalues(
        self,
        fields: tuple | str,
        sortby: str | None = None,
    ) -> list | DataFrame:
        """Get the unique values for a field."""
        if fields not in self.uniquevalues:
            if (isinstance(fields, str) and fields not in self.fields) or (
                not isinstance(fields, str)
                and any(field not in self.fields for field in fields)
            ):
                raise FIELDDOESNOTEXIST
            self.uniquevalues[fields] = await getuniquevalues(
                self.url,
                fields,
                self.session,
                sortby,
                **self.kwargs,
            )
        return self.uniquevalues[fields]

    async def getvaluecounts(self, field: str) -> DataFrame:
        """Get the value counts for a field."""
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
        """Get the nested value counts for a field."""
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
        """Create a new Rest object with a where clause."""
        wherestr_plus = (
            wherestr if self.wherestr == "1=1" else f"{self.wherestr} AND {wherestr}"
        )
        return await Rest.from_url(
            self.url,
            session=self.session,
            auth=self.auth,
            where=wherestr_plus,
            token=self.token,
            **self.kwargs,
        )

    def __repr__(self) -> str:
        """Return a string representation of the Rest object."""
        kwargstr = ", ".join(f"{k}={v}" for k, v in self.kwargs.items())
        return f"Rest({self.url}, {self.session}, {self.auth}, {self.wherestr}, {self.token}, {kwargstr})"

    def __str__(self) -> str:
        """Return a string representation of the Rest object."""
        return f"{self.name} ({self.url})"
