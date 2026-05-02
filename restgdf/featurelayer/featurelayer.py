"""A package for getting GeoDataFrames from ArcGIS FeatureLayers."""

from __future__ import annotations

import random
import warnings
from collections.abc import AsyncIterable, AsyncIterator
from typing import TYPE_CHECKING, Any, Literal


from restgdf._client._protocols import AsyncHTTPSession
from restgdf._compat import _warn_deprecated, aclosing
from restgdf._models.responses import LayerMetadata
from restgdf.errors import FieldDoesNotExistError
from restgdf.utils._optional import require_geo_stack
from restgdf.utils.getgdf import (
    _feature_to_row_dict,
    _iter_pages_raw,
    chunk_generator,
    get_gdf,
    row_dict_generator,
)
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
        session: AsyncHTTPSession,
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
        """Get a GeoDataFrame from an ArcGIS FeatureLayer.

        The returned ``GeoDataFrame`` carries
        ``gdf.attrs["spatial_reference"]`` populated from the layer's
        metadata envelope (R-65) when the layer advertises a spatial
        reference via ``extent.spatialReference`` or top-level
        ``spatialReference``.
        """
        if self.gdf is None:
            _require_featurelayer_geo_support("FeatureLayer.get_gdf()")
            self.gdf = await get_gdf(self.url, self.session, **self.kwargs)
        return self.gdf

    # -----------------------------------------------------------------
    # Streaming primitives (BL-24 / Q-A11). ``iter_pages`` is the single
    # low-level async generator every public streaming helper composes
    # on top of. ``stream_features`` is a deliberate alias of
    # ``iter_features`` so callers have a single canonical name.
    # -----------------------------------------------------------------
    async def iter_pages(
        self,
        *,
        order: Literal["request", "completion"] = "request",
        max_concurrent_pages: int | None = None,
        on_truncation: Literal["raise", "ignore", "split"] = "raise",
        **kwargs: Any,
    ) -> AsyncIterator[dict[str, Any]]:
        """Yield raw ArcGIS query-page envelopes from this FeatureLayer.

        Parameters
        ----------
        order
            ``"request"`` (default) yields pages in submit order.
            ``"completion"`` yields pages as the underlying fetches
            complete (may reorder relative to the pagination plan).
        max_concurrent_pages
            Upper bound on concurrent in-flight page fetches.
            ``None`` (default) leaves concurrency unbounded.
        on_truncation
            Behavior when a page reports ``exceededTransferLimit=true``:

            * ``"raise"`` (default) — raise
              :class:`restgdf.errors.RestgdfResponseError` with
              ``context='exceededTransferLimit'``.
            * ``"ignore"`` — log a ``restgdf.pagination`` warning and
              yield the truncated page anyway.
            * ``"split"`` — bisect the predicate's OID list and recurse
              (max depth 32; irreducible partitions raise).

        Yields
        ------
        dict
            The full raw response envelope for each page (``features``,
            ``objectIdFieldName``, ``exceededTransferLimit``, etc.).

        Notes
        -----
        When telemetry is enabled, emits exactly ONE INTERNAL parent
        span named ``feature_layer.stream`` wrapping the per-page loop
        (R-61). No per-page restgdf child spans are emitted.
        """
        merged_kwargs = {**self.kwargs, **kwargs}
        if "data" in self.kwargs or "data" in kwargs:
            merged_kwargs["data"] = default_data(
                kwargs.get("data"),
                self.kwargs.get("data"),
            )

        metadata = getattr(self, "metadata", None)
        layer_id = getattr(metadata, "id", None) if metadata is not None else None
        out_fields = self.datadict.get("outFields")
        span_where = self.wherestr if self.wherestr and self.wherestr != "1=1" else None

        # ``aclosing`` ensures the underlying async generator's ``finally``
        # (which ends the R-61 INTERNAL span) runs when the consumer breaks
        # early or calls ``aclose()``. Without it, GC-deferred cleanup would
        # leak the span until the next event-loop tick.
        async with aclosing(
            _iter_pages_raw(
                self.url,
                self.session,
                order=order,
                max_concurrent_pages=max_concurrent_pages,
                on_truncation=on_truncation,
                span_layer_id=layer_id,
                span_out_fields=out_fields,
                span_where=span_where,
                **merged_kwargs,
            ),
        ) as pages:
            async for page in pages:
                yield page

    async def iter_features(
        self,
        *,
        order: Literal["request", "completion"] = "request",
        max_concurrent_pages: int | None = None,
        on_truncation: Literal["raise", "ignore", "split"] = "raise",
        **kwargs: Any,
    ) -> AsyncIterator[dict[str, Any]]:
        """Yield one raw ArcGIS feature dict at a time.

        Thin wrapper over :meth:`iter_pages` that flattens each page's
        ``features`` list. See :meth:`iter_pages` for parameter
        semantics.
        """
        async with aclosing(
            self.iter_pages(  # type: ignore[type-var]
                order=order,
                max_concurrent_pages=max_concurrent_pages,
                on_truncation=on_truncation,
                **kwargs,
            ),
        ) as pages:
            async for page in pages:
                for feature in page.get("features", []):
                    yield feature

    # ``stream_features`` is the canonical public name; ``iter_features``
    # is the lower-level iterator primitive. Keep them as the same
    # coroutine function so introspection and import paths agree
    # (see tests/test_feature_layer_streaming_public.py).
    stream_features = iter_features

    async def stream_feature_batches(
        self,
        *,
        order: Literal["request", "completion"] = "request",
        max_concurrent_pages: int | None = None,
        on_truncation: Literal["raise", "ignore", "split"] = "raise",
        **kwargs: Any,
    ) -> AsyncIterator[list[dict[str, Any]]]:
        """Yield one list of raw feature dicts per page.

        See :meth:`iter_pages` for parameter semantics.
        """
        async with aclosing(
            self.iter_pages(  # type: ignore[type-var]
                order=order,
                max_concurrent_pages=max_concurrent_pages,
                on_truncation=on_truncation,
                **kwargs,
            ),
        ) as pages:
            async for page in pages:
                yield list(page.get("features", []))

    async def stream_rows(
        self,
        *,
        order: Literal["request", "completion"] = "request",
        max_concurrent_pages: int | None = None,
        on_truncation: Literal["raise", "ignore", "split"] = "raise",
        **kwargs: Any,
    ) -> AsyncIterator[dict[str, Any]]:
        """Yield row-shaped dicts (attributes plus raw geometry).

        Each row is the layer feature's ``attributes`` merged with a
        ``geometry`` key holding the ArcGIS geometry dict verbatim.
        See :meth:`iter_pages` for parameter semantics.
        """
        async with aclosing(
            self.iter_features(  # type: ignore[type-var]
                order=order,
                max_concurrent_pages=max_concurrent_pages,
                on_truncation=on_truncation,
                **kwargs,
            ),
        ) as features:
            async for feature in features:
                yield _feature_to_row_dict(feature)

    async def stream_gdf_chunks(
        self,
        **kwargs: Any,
    ) -> AsyncIterator[GeoDataFrame]:
        """Yield ``GeoDataFrame`` chunks; each chunk's ``attrs`` carries spatial_reference (R-65).

        Requires the optional geo stack (``geopandas`` / ``pyogrio``).
        """
        _require_featurelayer_geo_support("FeatureLayer.stream_gdf_chunks()")
        merged_kwargs = {**self.kwargs, **kwargs}
        if "data" in self.kwargs or "data" in kwargs:
            merged_kwargs["data"] = default_data(
                kwargs.get("data"),
                self.kwargs.get("data"),
            )
        async for chunk in chunk_generator(self.url, self.session, **merged_kwargs):
            yield chunk

    async def get_df(self, resolve_domains: bool = False) -> DataFrame:
        """Get a pandas DataFrame from an ArcGIS FeatureLayer.

        Tabular row view: attributes plus any raw ``geometry`` dict returned
        by the server, with no geopandas/pyogrio dependency. Raises
        :class:`restgdf.errors.OptionalDependencyError` when ``pandas`` is
        not installed.

        This is the pandas-only counterpart to :meth:`get_gdf` — prefer it
        when callers only need tabular access and want to avoid the full geo
        dependency stack.

        Parameters
        ----------
        resolve_domains:
            When ``True``, coded-value domain fields are post-processed
            so the DataFrame contains the human-readable ``name`` rather
            than the raw ``code``. Codes absent from the domain's
            ``codedValues`` table pass through unchanged. Range domains
            are not validated or coerced. Defaults to ``False`` — the
            historical behavior where the DataFrame faithfully mirrors
            the server payload. No additional HTTP traffic is issued;
            resolution uses the already-loaded
            :attr:`FeatureLayer.metadata` fetched during :meth:`prep`.

        Examples
        --------
        >>> df = await layer.get_df(resolve_domains=True)  # doctest: +SKIP
        >>> df["STATUS"].head().tolist()  # doctest: +SKIP
        ['Active', 'Inactive', 'Active', ...]
        """
        from restgdf.adapters.pandas import (
            arows_to_dataframe,
            resolve_domains as _resolve_domains,
        )

        df = await arows_to_dataframe(self.stream_rows())
        if resolve_domains:
            fields = getattr(getattr(self, "metadata", None), "fields", None)
            df = _resolve_domains(df, fields)
        return df

    async def row_dict_generator(
        self,
        **kwargs,
    ) -> AsyncIterable[dict]:
        """Asynchronously yield rows from a GeoDataFrame as dictionaries.

        .. deprecated:: 2.0
            Use :meth:`stream_rows` instead. This method emits a
            :class:`DeprecationWarning` and continues to delegate to the
            module-level ``row_dict_generator`` helper for backwards
            compatibility with existing ``unittest.mock.patch`` targets.
            Scheduled for removal in a future release.
        """
        _warn_deprecated(
            "FeatureLayer.row_dict_generator is deprecated; "
            "use FeatureLayer.stream_rows instead.",
        )
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
        """Create a refined ``FeatureLayer`` bound to ``wherestr``.

        BL-46: when the current instance has already resolved its
        schema via :meth:`prep`, the refined child reuses the parent's
        cached ``metadata`` / ``name`` / ``fields`` / ``object_id_field``
        so the expensive metadata GET (``?f=json``) is not re-issued.
        The feature-count POST is still issued, but scoped to the
        refined ``where_clause`` so ``refined.count`` is correct for
        the refined filter.
        """
        wherestr_plus = (
            wherestr if self.wherestr == "1=1" else f"{self.wherestr} AND {wherestr}"
        )
        if not hasattr(self, "metadata"):
            return await FeatureLayer.from_url(
                self.url,
                session=self.session,
                where=wherestr_plus,
                **self.kwargs,
            )

        refined_kwargs = {k: v for k, v in self.kwargs.items() if k != "data"}
        refined_data = {
            k: v for k, v in self.kwargs.get("data", {}).items() if k != "where"
        }
        refined = FeatureLayer(
            self.url,
            session=self.session,
            where=wherestr_plus,
            data=refined_data,
            **refined_kwargs,
        )
        refined.metadata = self.metadata
        refined.name = self.name
        refined.fields = self.fields
        refined._fieldtypes_frame = None
        refined.object_id_field = self.object_id_field
        refined.count = await get_feature_count(
            refined.url,
            refined.session,
            **refined.kwargs,
        )
        return refined

    def __repr__(self) -> str:
        """Return a string representation of the Rest object."""
        kwargstr = ", ".join(f"{k}={v}" for k, v in self.kwargs.items())
        return f"Rest({self.url}, {self.session}, {self.wherestr}, {kwargstr})"

    def __str__(self) -> str:
        """Return a string representation of the Rest object."""
        return f"{self.name} ({self.url})"
