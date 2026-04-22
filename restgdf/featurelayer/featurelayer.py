"""A package for getting GeoDataFrames from ArcGIS FeatureLayers."""

from __future__ import annotations

import random
import warnings
from collections.abc import AsyncIterable
from typing import TYPE_CHECKING

from aiohttp import ClientSession

from restgdf._models.responses import LayerMetadata
from restgdf.errors import FieldDoesNotExistError
from restgdf.utils._optional import require_geo_stack
from restgdf.utils.getgdf import get_gdf, row_dict_generator
from restgdf.utils.getinfo import (
    default_data,
    get_feature_count,
    get_fields,
    get_fields_frame,
    get_metadata,
    get_name,
    get_object_id_field,
    get_unique_values,
    get_value_counts,
    nested_count,
)

# Deprecated names re-imported at module scope so callers can still patch
# them via ``unittest.mock.patch("restgdf.featurelayer.featurelayer.<old>")``.
# These look unused to linters but are required by backward-compat tests
# (see ``tests/test_compat.py::test_featurelayer_patch_targets``).
# Do NOT remove — emit DeprecationWarning via the shim, not by deletion.
from restgdf.utils.getinfo import (  # noqa: F401
    getuniquevalues,
    getvaluecounts,
    nestedcount,
)

# Keep the deprecated names reachable via ``__all__`` so static-analysis tools
# that respect ``__all__`` treat them as public re-exports.
__all__ = [
    "FeatureLayer",
    "get_unique_values",
    "get_value_counts",
    "nested_count",
    "getuniquevalues",
    "getvaluecounts",
    "nestedcount",
]
from restgdf.utils.token import ArcGISTokenSession
from restgdf.utils.utils import where_var_in_list, ends_with_num

if TYPE_CHECKING:
    from geopandas import GeoDataFrame
    from pandas import DataFrame


def _require_featurelayer_geo_support(feature: str) -> None:
    """Fail fast for FeatureLayer GeoDataFrame helpers on base installs."""
    require_geo_stack(feature)


class FeatureLayer:
    """A class for interacting with an ArcGIS REST FeatureLayer.

    Attributes
    ----------
    metadata : restgdf.LayerMetadata
        Pydantic-validated layer metadata (name, fields, max record
        count, advanced query capabilities, ...). Replaces the pre-2.0
        raw ``dict``. Extra keys sent by the server are preserved via
        ``extra="allow"`` and reachable through ``metadata.model_extra``.
    name : str
        Convenience alias for ``metadata.name``.
    fields : tuple[str, ...]
        Field names consumed by restgdf.
    object_id_field : str
        Resolved object-id field name (``"OBJECTID"`` when the server
        omits it).
    count : int
        Feature count, validated via ``CountResponse`` at prep time.
    """

    def __init__(
        self,
        url: str,
        session: ClientSession | ArcGISTokenSession,
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

        self.uniquevalues: dict[
            tuple[str | tuple, str | None],
            list | DataFrame,
        ] = {}
        self.valuecounts: dict = {}
        self.nestedcount: dict = {}

        self.gdf: GeoDataFrame | None = None
        self._fieldtypes_frame: DataFrame | None = None

        self.metadata: LayerMetadata
        self.name: str
        self.fields: tuple[str, ...]
        self.object_id_field: str
        self.count: int

    async def prep(self):
        """Prepare the Rest object."""
        raw = await get_metadata(
            self.url,
            self.session,
            token=self.kwargs["data"].get("token"),
        )
        self.metadata = (
            raw if isinstance(raw, LayerMetadata) else LayerMetadata.model_validate(raw)
        )
        if self.metadata.type != "Feature Layer":
            raise ValueError("The url must point to a FeatureLayer.")
        self.name = get_name(self.metadata)
        self.fields = get_fields(self.metadata)
        self._fieldtypes_frame = None
        self.object_id_field = get_object_id_field(self.metadata)
        self.count = await get_feature_count(self.url, self.session, **self.kwargs)

    @property
    def fieldtypes(self) -> DataFrame:
        """Return field metadata as a DataFrame when pandas is available."""
        if not hasattr(self, "metadata"):
            raise AttributeError("fieldtypes")
        if self._fieldtypes_frame is None:
            self._fieldtypes_frame = get_fields_frame(self.metadata)
        return self._fieldtypes_frame

    @classmethod
    async def from_url(cls, url: str, **kwargs) -> FeatureLayer:
        """Create a Rest object from a url."""
        self = cls(url, **kwargs)
        await self.prep()
        return self

    async def get_oids(self) -> list[int]:
        """Get the object ids for the Rest object."""
        object_id_field = getattr(self, "object_id_field", "OBJECTID")
        return await self.get_unique_values(object_id_field)

    async def sample_gdf(self, n: int = 10) -> GeoDataFrame:
        """Get n random features as a GeoDataFrame."""
        _require_featurelayer_geo_support("FeatureLayer.sample_gdf()")
        oids = await get_unique_values(
            self.url,
            self.object_id_field,
            self.session,
            **self.kwargs,
        )
        sample_oids = random.sample(oids, min(n, len(oids)))
        wherestr = where_var_in_list(self.object_id_field, sample_oids)
        new_rest = await self.where(wherestr)
        return await new_rest.get_gdf()

    async def head_gdf(self, n: int = 10) -> GeoDataFrame:
        """Get the n first features as a GeoDataFrame."""
        _require_featurelayer_geo_support("FeatureLayer.head_gdf()")
        oids = await get_unique_values(
            self.url,
            self.object_id_field,
            self.session,
            **self.kwargs,
        )
        head_oids = oids[:n]
        wherestr = where_var_in_list(self.object_id_field, head_oids)
        new_rest = await self.where(wherestr)
        return await new_rest.get_gdf()

    async def get_gdf(self) -> GeoDataFrame:
        """Get a GeoDataFrame from an ArcGIS FeatureLayer."""
        if self.gdf is None:
            _require_featurelayer_geo_support("FeatureLayer.get_gdf()")
            self.gdf = await get_gdf(self.url, self.session, **self.kwargs)
        return self.gdf

    async def get_df(self) -> DataFrame:
        """Get a pandas DataFrame from an ArcGIS FeatureLayer.

        Tabular row view: attributes plus any raw ``geometry`` dict returned
        by the server, with no geopandas/pyogrio dependency. Raises
        :class:`restgdf.errors.OptionalDependencyError` when ``pandas`` is
        not installed.

        This is the pandas-only counterpart to :meth:`get_gdf` — prefer it
        when callers only need tabular access and want to avoid the full geo
        dependency stack.
        """
        from restgdf.adapters.pandas import arows_to_dataframe

        return await arows_to_dataframe(self.row_dict_generator())

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

    async def get_unique_values(
        self,
        fields: tuple | str,
        sortby: str | None = None,
    ) -> list | DataFrame:
        """Get the unique values for a field."""
        cache_key = (fields, sortby)
        if cache_key not in self.uniquevalues:
            if (isinstance(fields, str) and fields not in self.fields) or (
                not isinstance(fields, str)
                and any(field not in self.fields for field in fields)
            ):
                raise FieldDoesNotExistError(
                    fields,
                    context="FeatureLayer.get_unique_values",
                )
            self.uniquevalues[cache_key] = await get_unique_values(
                self.url,
                fields,
                self.session,
                sortby,
                **self.kwargs,
            )
        return self.uniquevalues[cache_key]

    async def get_value_counts(self, field: str) -> DataFrame:
        """Get the value counts for a field."""
        if field not in self.valuecounts:
            if field not in self.fields:
                raise FieldDoesNotExistError(
                    field,
                    context="FeatureLayer.get_value_counts",
                )
            self.valuecounts[field] = await get_value_counts(
                self.url,
                field,
                self.session,
                **self.kwargs,
            )
        return self.valuecounts[field]

    async def get_nested_count(self, fields: tuple) -> DataFrame:
        """Get the nested value counts for a field."""
        if fields not in self.nestedcount:
            if any(field not in self.fields for field in fields):
                raise FieldDoesNotExistError(
                    fields,
                    context="FeatureLayer.get_nested_count",
                )
            self.nestedcount[fields] = await nested_count(
                self.url,
                fields,
                self.session,
                **self.kwargs,
            )
        return self.nestedcount[fields]

    # -----------------------------------------------------------------
    # Deprecated legacy method names (Phase 6). Emit DeprecationWarning
    # and delegate to the canonical implementation. Kept for backward
    # compatibility; will be removed in a future release.
    # -----------------------------------------------------------------
    async def getoids(self) -> list[int]:
        """Deprecated alias for :meth:`get_oids`."""
        warnings.warn(
            "`FeatureLayer.getoids` is deprecated; use `get_oids` instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return await self.get_oids()

    async def samplegdf(self, n: int = 10) -> GeoDataFrame:
        """Deprecated alias for :meth:`sample_gdf`."""
        warnings.warn(
            "`FeatureLayer.samplegdf` is deprecated; use `sample_gdf` instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return await self.sample_gdf(n)

    async def headgdf(self, n: int = 10) -> GeoDataFrame:
        """Deprecated alias for :meth:`head_gdf`."""
        warnings.warn(
            "`FeatureLayer.headgdf` is deprecated; use `head_gdf` instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return await self.head_gdf(n)

    async def getgdf(self) -> GeoDataFrame:
        """Deprecated alias for :meth:`get_gdf`."""
        warnings.warn(
            "`FeatureLayer.getgdf` is deprecated; use `get_gdf` instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return await self.get_gdf()

    async def getuniquevalues(
        self,
        fields: tuple | str,
        sortby: str | None = None,
    ) -> list | DataFrame:
        """Deprecated alias for :meth:`get_unique_values`."""
        warnings.warn(
            "`FeatureLayer.getuniquevalues` is deprecated; use "
            "`get_unique_values` instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return await self.get_unique_values(fields, sortby)

    async def getvaluecounts(self, field: str) -> DataFrame:
        """Deprecated alias for :meth:`get_value_counts`."""
        warnings.warn(
            "`FeatureLayer.getvaluecounts` is deprecated; use "
            "`get_value_counts` instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return await self.get_value_counts(field)

    async def getnestedcount(self, fields: tuple) -> DataFrame:
        """Deprecated alias for :meth:`get_nested_count`."""
        warnings.warn(
            "`FeatureLayer.getnestedcount` is deprecated; use "
            "`get_nested_count` instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return await self.get_nested_count(fields)

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
