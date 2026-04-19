"""A package for getting GeoDataFrames from ArcGIS FeatureLayers."""

from __future__ import annotations

import random
from collections.abc import AsyncIterable
from typing import Dict, Optional, Tuple, Union

from aiohttp import ClientSession
from geopandas import GeoDataFrame
from pandas import DataFrame

from restgdf.utils.getgdf import get_gdf, row_dict_generator
from restgdf.utils.getinfo import (
    default_data,
    get_feature_count,
    get_metadata,
    get_name,
    get_object_id_field,
    getfields,
    getfields_df,
    getuniquevalues,
    getvaluecounts,
    nestedcount,
    FIELDDOESNOTEXIST,
)
from restgdf.utils.token import ArcGISTokenSession
from restgdf.utils.utils import where_var_in_list, ends_with_num


class FeatureLayer:
    """A class for interacting with ArcGIS FeatureLayers."""

    def __init__(
        self,
        url: str,
        session: Union[ClientSession, ArcGISTokenSession],
        where: str = "1=1",
        token: Optional[str] = None,
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
        self.kwargs = kwargs
        self.datadict = default_data(kwargs.pop("data", {}))
        self.datadict["where"] = self.wherestr
        if token is not None:
            existing_token = self.datadict.get("token")
            if existing_token is not None and existing_token != token:
                raise ValueError(
                    "Pass token either via token= or data['token'], not both with different values.",
                )
            self.datadict["token"] = token
        self.kwargs["data"] = self.datadict

        self.uniquevalues: Dict[
            Tuple[Union[str, tuple], Optional[str]],
            Union[list, DataFrame],
        ] = {}
        self.valuecounts: dict = {}
        self.nestedcount: dict = {}

        self.gdf: Optional[GeoDataFrame] = None

        self.metadata: dict
        self.name: str
        self.fields: tuple[str, ...]
        self.fieldtypes: DataFrame
        self.object_id_field: str
        self.count: int

    async def prep(self):
        """Prepare the Rest object."""
        self.metadata = await get_metadata(
            self.url,
            self.session,
            token=self.kwargs["data"].get("token"),
        )
        try:
            if not self.metadata["type"] == "Feature Layer":
                raise ValueError("The url must point to a FeatureLayer.")
        except KeyError:
            raise ValueError("The url must point to a FeatureLayer.")
        self.name = get_name(self.metadata)
        self.fields = getfields(self.metadata)
        self.fieldtypes = getfields_df(self.metadata)
        self.object_id_field = get_object_id_field(self.metadata)
        self.count = await get_feature_count(self.url, self.session, **self.kwargs)

    @classmethod
    async def from_url(cls, url: str, **kwargs) -> FeatureLayer:
        """Create a Rest object from a url."""
        self = cls(url, **kwargs)
        await self.prep()
        return self

    async def getoids(self) -> list[int]:
        """Get the object ids for the Rest object."""
        object_id_field = getattr(self, "object_id_field", "OBJECTID")
        return await self.getuniquevalues(object_id_field)

    async def samplegdf(self, n: int = 10) -> GeoDataFrame:
        """Get n random features as a GeoDataFrame."""
        oids = await getuniquevalues(
            self.url,
            self.object_id_field,
            self.session,
            **self.kwargs,
        )
        sample_oids = random.sample(oids, min(n, len(oids)))
        wherestr = where_var_in_list(self.object_id_field, sample_oids)
        new_rest = await self.where(wherestr)
        return await new_rest.getgdf()

    async def headgdf(self, n: int = 10) -> GeoDataFrame:
        """Get the n first features as a GeoDataFrame."""
        oids = await getuniquevalues(
            self.url,
            self.object_id_field,
            self.session,
            **self.kwargs,
        )
        head_oids = oids[:n]
        wherestr = where_var_in_list(self.object_id_field, head_oids)
        new_rest = await self.where(wherestr)
        return await new_rest.getgdf()

    async def getgdf(self) -> GeoDataFrame:
        """Get a GeoDataFrame from an ArcGIS FeatureLayer."""
        if self.gdf is None:
            self.gdf = await get_gdf(self.url, self.session, **self.kwargs)
        return self.gdf

    async def row_dict_generator(
        self,
        **kwargs,
    ) -> AsyncIterable[dict]:
        """Asynchronously yield rows from a GeoDataFrame as dictionaries."""
        merged_kwargs = {**self.kwargs, **kwargs}
        if "data" in self.kwargs or "data" in kwargs:
            merged_kwargs["data"] = default_data(
                kwargs.get("data"),
                self.kwargs.get("data"),
            )
        _gen = row_dict_generator(self.url, self.session, **merged_kwargs)
        async for row in _gen:
            yield row

    async def getuniquevalues(
        self,
        fields: Union[tuple, str],
        sortby: Optional[str] = None,
    ) -> Union[list, DataFrame]:
        """Get the unique values for a field."""
        cache_key = (fields, sortby)
        if cache_key not in self.uniquevalues:
            if (isinstance(fields, str) and fields not in self.fields) or (
                not isinstance(fields, str)
                and any(field not in self.fields for field in fields)
            ):
                raise FIELDDOESNOTEXIST
            self.uniquevalues[cache_key] = await getuniquevalues(
                self.url,
                fields,
                self.session,
                sortby,
                **self.kwargs,
            )
        return self.uniquevalues[cache_key]

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
            **self.kwargs,
        )

    def __repr__(self) -> str:
        """Return a string representation of the Rest object."""
        kwargstr = ", ".join(f"{k}={v}" for k, v in self.kwargs.items())
        return f"Rest({self.url}, {self.session}, {self.wherestr}, {kwargstr})"

    def __str__(self) -> str:
        """Return a string representation of the Rest object."""
        return f"{self.name} ({self.url})"
