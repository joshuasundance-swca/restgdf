"""A package for getting GeoDataFrames from ArcGIS FeatureLayers."""

from __future__ import annotations

import random

from aiohttp import ClientSession
from geopandas import GeoDataFrame
from pandas import DataFrame

from restgdf.utils.getgdf import get_gdf
from restgdf.utils.getinfo import (
    default_data,
    get_feature_count,
    get_metadata,
    get_name,
    getfields,
    getfields_df,
    getuniquevalues,
    getvaluecounts,
    nestedcount,
    FIELDDOESNOTEXIST,
)
from restgdf.utils.utils import where_var_in_list, ends_with_num


class FeatureLayer:
    """A class for interacting with ArcGIS FeatureLayers."""

    def __init__(
        self,
        url: str,
        session: ClientSession,
        where: str = "1=1",
        token: str | None = None,
        **kwargs,
    ):
        """A class for interacting with ArcGIS FeatureLayers."""
        if not ends_with_num(url):
            raise ValueError(
                "The url must end with a number, which is the layer id of the FeatureLayer.",
            )
        self.url = url
        self.session = session

        self.wherestr = where
        self.token = token
        self.kwargs = kwargs
        self.datadict = default_data(kwargs.pop("data", {}))
        self.datadict["where"] = self.wherestr
        if self.token is not None:
            self.datadict["token"] = self.token
        self.kwargs["data"] = self.datadict

        self.uniquevalues: dict = {}
        self.valuecounts: dict = {}
        self.nestedcount: dict = {}

        self.gdf: GeoDataFrame | None = None

        self.metadata: dict
        self.name: str
        self.fields: tuple[str, ...]
        self.fieldtypes: DataFrame
        self.count: int

    async def prep(self):
        """Prepare the Rest object."""
        self.metadata = await get_metadata(
            self.url,
            self.session,
            token=self.token,
        )
        try:
            if not self.metadata["type"] == "Feature Layer":
                raise ValueError("The url must point to a FeatureLayer.")
        except KeyError:
            raise ValueError("The url must point to a FeatureLayer.")
        self.name = get_name(self.metadata)
        self.fields = getfields(self.metadata)
        self.fieldtypes = getfields_df(self.metadata)
        self.count = await get_feature_count(self.url, self.session, **self.kwargs)

    @classmethod
    async def from_url(cls, url: str, **kwargs) -> FeatureLayer:
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
        wherestr = where_var_in_list("OBJECTID", sample_oids)
        new_rest = await self.where(wherestr)
        return await new_rest.getgdf()

    async def headgdf(self, n: int = 10) -> GeoDataFrame:
        """Get the n first features as a GeoDataFrame."""
        oids = await getuniquevalues(self.url, "OBJECTID", self.session, **self.kwargs)
        head_oids = oids[:n]
        wherestr = where_var_in_list("OBJECTID", head_oids)
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

    async def where(self, wherestr: str) -> FeatureLayer:
        """Create a new Rest object with a where clause."""
        wherestr_plus = (
            wherestr if self.wherestr == "1=1" else f"{self.wherestr} AND {wherestr}"
        )
        return await FeatureLayer.from_url(
            self.url,
            session=self.session,
            where=wherestr_plus,
            token=self.token,
            **self.kwargs,
        )

    def __repr__(self) -> str:
        """Return a string representation of the Rest object."""
        kwargstr = ", ".join(f"{k}={v}" for k, v in self.kwargs.items())
        return f"Rest({self.url}, {self.session}, {self.wherestr}, {self.token}, {kwargstr})"

    def __str__(self) -> str:
        """Return a string representation of the Rest object."""
        return f"{self.name} ({self.url})"
