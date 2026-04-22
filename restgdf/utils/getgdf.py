"""Get a GeoDataFrame from an ArcGIS FeatureLayer."""

from __future__ import annotations

import asyncio
from asyncio import gather
from collections.abc import AsyncGenerator, Mapping
from functools import reduce
from typing import TYPE_CHECKING, Any, Literal

from aiohttp import ClientSession

from restgdf._logging import get_logger
from restgdf._models._drift import _parse_response
from restgdf._models.responses import FeaturesResponse, LayerMetadata
from restgdf.errors import PaginationError, RestgdfResponseError
from restgdf.telemetry._spans import start_feature_layer_stream_span
from restgdf.utils.getinfo import (
    default_data,
    default_headers,
    get_feature_count,
    get_max_record_count,
    get_metadata,
    get_object_ids,
    supports_pagination,
)
from restgdf.utils._http import default_timeout
from restgdf.utils._metadata import (
    normalize_spatial_reference,
    supports_pagination_explicitly,
)
from restgdf.utils._optional import (
    require_geo_stack,
    require_geodataframe,
    require_geopandas_read_file,
    require_pandas_concat,
    require_pyogrio_list_drivers,
)
from restgdf.utils._pagination import build_pagination_plan
from restgdf.utils.token import ArcGISTokenSession
from restgdf.utils.utils import where_var_in_list

if TYPE_CHECKING:
    from geopandas import GeoDataFrame

supported_drivers: dict[str, str] | None = None


def _require_geo_query_support(feature: str) -> None:
    """Fail fast for GeoDataFrame entrypoints when the geo stack is missing."""
    require_geo_stack(feature)


def read_file(*args, **kwargs):
    """Load a vector payload with geopandas only when geo support is needed."""
    return require_geopandas_read_file("GeoDataFrame queries")(*args, **kwargs)


def _get_supported_drivers() -> dict[str, str]:
    """Load pyogrio drivers lazily so base installs can still import restgdf."""
    global supported_drivers
    if supported_drivers is None:
        supported_drivers = require_pyogrio_list_drivers("GeoDataFrame queries")()
    return supported_drivers


async def _get_sub_features(
    url: str,
    session: ClientSession | ArcGISTokenSession,
    query_data: dict,
    *,
    batch_index: int | None = None,
    **kwargs,
) -> list[dict[str, Any]]:
    """Fetch a single query batch as raw ArcGIS feature dicts."""
    kwargs = {k: v for k, v in kwargs.items() if k != "data"}
    kwargs.setdefault("timeout", default_timeout())
    response = await session.post(
        f"{url}/query",
        data=dict(query_data),
        headers=default_headers(kwargs.pop("headers", None)),
        **kwargs,
    )
    raw = await response.json(content_type=None)
    envelope = _parse_response(FeaturesResponse, raw, context=f"{url}/query")
    if envelope.exceeded_transfer_limit:
        raise PaginationError(
            f"{url}/query returned exceededTransferLimit=true; query batching missed "
            "records and the response page is incomplete.",
            batch_index=batch_index,
            page_size=query_data.get("resultRecordCount"),
        )
    return envelope.features or []


async def _feature_batch_generator(
    url: str,
    session: ClientSession | ArcGISTokenSession,
    **kwargs,
) -> AsyncGenerator[list[dict[str, Any]]]:
    """Yield raw ArcGIS feature batches without requiring pandas/geopandas."""
    query_data_batches = await get_query_data_batches(url, session, **kwargs)
    tasks = {
        asyncio.create_task(
            get_sub_features(
                url,
                session,
                query_data=query_data,
                batch_index=idx,
                **kwargs,
            ),
        )
        for idx, query_data in enumerate(query_data_batches)
    }
    for feature_batch_future in asyncio.as_completed(tasks):
        yield await feature_batch_future


def get_sub_features(*args, **kwargs):
    """Compatibility wrapper for the raw feature query helper."""
    return _get_sub_features(*args, **kwargs)


def _feature_to_row_dict(feature: dict[str, Any]) -> dict[str, Any]:
    """Flatten an ArcGIS feature into a row-shaped dictionary."""
    row = dict(feature.get("attributes") or {})
    if "geometry" in feature:
        row["geometry"] = feature["geometry"]
    for key, value in feature.items():
        if key not in {"attributes", "geometry"} and key not in row:
            row[key] = value
    return row


def combine_where_clauses(base_where: str | None, extra_where: str) -> str:
    """Combine where clauses without changing the default all-records predicate."""
    if base_where in (None, "", "1=1"):
        return extra_where
    return f"({base_where}) AND ({extra_where})"


def chunk_values(values: list[int], chunk_size: int) -> list[list[int]]:
    """Split values into evenly-sized chunks."""
    return [values[i : i + chunk_size] for i in range(0, len(values), chunk_size)]


async def get_query_data_batches(
    url: str,
    session: ClientSession | ArcGISTokenSession,
    **kwargs,
) -> list[dict]:
    """Build query payloads for each request needed to read a layer."""
    request_data = dict(kwargs.get("data") or {})
    feature_count = await get_feature_count(url, session, **kwargs)
    token = request_data.get("token")
    metadata = await get_metadata(url, session, token=token)
    max_record_count = get_max_record_count(metadata)
    requested_page_size = request_data.get("resultRecordCount")
    if isinstance(requested_page_size, int) and requested_page_size > 0:
        page_size = min(requested_page_size, max_record_count)
    else:
        page_size = max_record_count

    if feature_count <= max_record_count:
        return [request_data]

    if supports_pagination(metadata) and supports_pagination_explicitly(metadata):
        if isinstance(requested_page_size, int) and requested_page_size > 0:
            return [
                {
                    **request_data,
                    "resultOffset": offset,
                    "resultRecordCount": min(page_size, feature_count - offset),
                }
                for offset in range(0, feature_count, page_size)
            ]
        plan = build_pagination_plan(feature_count, max_record_count)
        # NOTE (BL-21/22 deferred): maxRecordCountFactor from
        # advancedQueryCapabilities is intentionally NOT plumbed here in
        # phase-2c. The planner API accepts `advertised_factor` / `factor`
        # and will clamp with a warning via `get_logger("pagination")`;
        # the live wire-up is deferred to a future phase to preserve
        # byte-exact batch sizes during the 3.0 migration.
        return [
            {
                **request_data,
                "resultOffset": offset,
                "resultRecordCount": count,
            }
            for offset, count in plan.batches
        ]

    object_id_field_name, object_ids = await get_object_ids(url, session, **kwargs)
    base_where = request_data.get("where")
    return [
        {
            **request_data,
            "where": combine_where_clauses(
                base_where,
                where_var_in_list(object_id_field_name, object_id_chunk),
            ),
        }
        for object_id_chunk in chunk_values(object_ids, max_record_count)
    ]


async def get_sub_gdf(
    url: str,
    session: ClientSession | ArcGISTokenSession,
    query_data: dict,
    **kwargs,
) -> GeoDataFrame:
    _require_geo_query_support("get_sub_gdf()")
    data = dict(query_data)
    gdfdriver = "ESRIJSON" if "ESRIJSON" in _get_supported_drivers() else "GeoJSON"
    if gdfdriver == "GeoJSON":
        data["f"] = "GeoJSON"
    kwargs = {k: v for k, v in kwargs.items() if k != "data"}
    kwargs.setdefault("timeout", default_timeout())

    response = await session.post(
        f"{url}/query",
        data=data,
        headers=default_headers(kwargs.pop("headers", None)),
        **kwargs,
    )
    sub_gdf = read_file(
        await response.text(),
        # driver=gdfdriver,  # this line raises a warning when using pyogrio w/ ESRIJSON
        engine="pyogrio",
    )
    return sub_gdf


async def get_gdf_list(
    url: str,
    session: ClientSession | ArcGISTokenSession,
    **kwargs,
) -> list[GeoDataFrame]:
    _require_geo_query_support("get_gdf_list()")
    query_data_batches = await get_query_data_batches(url, session, **kwargs)
    tasks = [
        get_sub_gdf(url, session, query_data=query_data, **kwargs)
        for query_data in query_data_batches
    ]
    gdf_list = await gather(*tasks)
    return gdf_list


async def chunk_generator(
    url: str,
    session: ClientSession | ArcGISTokenSession,
    **kwargs,
) -> AsyncGenerator[GeoDataFrame]:
    """
    Asynchronously yield GeoDataFrames from a FeatureLayer in chunks.
    This function retrieves GeoDataFrames in chunks based on the offset range
    and yields each GeoDataFrame as it is retrieved. Each yielded chunk has
    ``gdf.attrs["spatial_reference"]`` populated from the layer's metadata
    (R-65) when the layer reports a spatial reference.
    """
    _require_geo_query_support("chunk_generator()")
    query_data_batches = await get_query_data_batches(url, session, **kwargs)
    request_data = kwargs.get("data") or {}
    token = request_data.get("token") if isinstance(request_data, Mapping) else None
    raw_sr: dict[str, Any] | None
    try:
        metadata = await get_metadata(url, session, token=token)
    except Exception:  # pragma: no cover - metadata errors surface elsewhere
        raw_sr = None
    else:
        raw_sr = _extract_raw_spatial_reference(metadata)
    tasks = {
        asyncio.create_task(get_sub_gdf(url, session, query_data=query_data, **kwargs))
        for query_data in query_data_batches
    }
    for sub_gdf_future in asyncio.as_completed(tasks):
        chunk = await sub_gdf_future
        if raw_sr is not None:
            chunk.attrs["spatial_reference"] = raw_sr
        yield chunk


async def row_dict_generator(
    url: str,
    session: ClientSession | ArcGISTokenSession,
    **kwargs,
) -> AsyncGenerator[dict]:
    """Yield row-shaped dicts from an ArcGIS FeatureLayer.

    .. deprecated:: 2.0
        Module-level ``row_dict_generator`` is retained for backwards
        compatibility. Prefer :meth:`restgdf.FeatureLayer.stream_rows` or
        ``restgdf.adapters.stream.iter_rows`` in new code.
    """
    async for feature_batch in _feature_batch_generator(url, session, **kwargs):
        for feature in feature_batch:
            yield _feature_to_row_dict(feature)


async def concat_gdfs(gdfs: list[GeoDataFrame]) -> GeoDataFrame:
    GeoDataFrame = require_geodataframe("GeoDataFrame concatenation")
    concat = require_pandas_concat("GeoDataFrame concatenation")
    crs = gdfs[0].crs
    saved_attrs = dict(gdfs[0].attrs)

    if not all(gdf.crs == crs for gdf in gdfs):
        raise ValueError("gdfs must have the same crs")

    result = reduce(
        lambda gdf1, gdf2: GeoDataFrame(
            concat([gdf1, gdf2], ignore_index=True),
            crs=gdf1.crs,
        ),
        gdfs,
    )
    result.attrs.update(saved_attrs)
    return result


async def gdf_by_concat(
    url: str,
    session: ClientSession | ArcGISTokenSession,
    **kwargs,
) -> GeoDataFrame:
    _require_geo_query_support("gdf_by_concat()")
    gdfs = await get_gdf_list(url, session, **kwargs)
    result = await concat_gdfs(gdfs)
    await _apply_spatial_reference_attr(result, url, session, **kwargs)
    return result


async def get_gdf(
    url: str,
    session: ClientSession | None = None,
    where: str | None = None,
    token: str | None = None,
    **kwargs,
) -> GeoDataFrame:
    _require_geo_query_support("get_gdf()")
    session = session or ClientSession()
    datadict = default_data(kwargs.pop("data", None) or {})
    if where is not None:
        datadict["where"] = where
    if token is not None:
        existing_token = datadict.get("token")
        if existing_token is not None and existing_token != token:
            raise ValueError(
                "Pass token either via token= or data['token'], not both with different values.",
            )
        datadict["token"] = token
    return await gdf_by_concat(url, session, data=datadict, **kwargs)


# ---------------------------------------------------------------------------
# Spatial-reference propagation (R-65)
# ---------------------------------------------------------------------------


def _extract_raw_spatial_reference(
    metadata: LayerMetadata | Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    """Return the raw ``spatialReference`` dict from a layer metadata envelope.

    Reads ``extent.spatialReference`` first (preferred), then falls back to a
    top-level ``spatialReference`` key (sometimes present on non-spatial or
    non-extent-bearing layers). Returns ``None`` when neither is present.
    """
    if metadata is None:
        return None
    if isinstance(metadata, LayerMetadata):
        extras = metadata.model_extra or {}
        dumped = metadata.model_dump(by_alias=True, exclude_none=True)
    elif isinstance(metadata, Mapping):
        extras = dict(metadata)
        dumped = dict(metadata)
    else:
        return None
    for source in (extras, dumped):
        extent = source.get("extent")
        if isinstance(extent, Mapping):
            sr = extent.get("spatialReference")
            if sr is not None:
                _, raw = normalize_spatial_reference(sr)
                if raw is not None:
                    return raw
        sr = source.get("spatialReference")
        if sr is not None:
            _, raw = normalize_spatial_reference(sr)
            if raw is not None:
                return raw
    return None


async def _apply_spatial_reference_attr(
    gdf: GeoDataFrame,
    url: str,
    session: ClientSession | ArcGISTokenSession,
    **kwargs,
) -> None:
    """Stamp ``gdf.attrs['spatial_reference']`` from layer metadata (R-65).

    Silent no-op when the metadata envelope carries no spatial reference.
    """
    request_data = kwargs.get("data") or {}
    token = request_data.get("token") if isinstance(request_data, Mapping) else None
    try:
        metadata = await get_metadata(url, session, token=token)
    except Exception:  # pragma: no cover - metadata errors surface elsewhere
        return
    raw_sr = _extract_raw_spatial_reference(metadata)
    if raw_sr is not None:
        gdf.attrs["spatial_reference"] = raw_sr


# ---------------------------------------------------------------------------
# Streaming page-level primitive (BL-24)
# ---------------------------------------------------------------------------


async def _fetch_page_dict(
    url: str,
    session: ClientSession | ArcGISTokenSession,
    query_data: Mapping[str, Any],
    **kwargs,
) -> dict[str, Any]:
    """Fetch one query page and return the raw envelope dict."""
    kwargs = {k: v for k, v in kwargs.items() if k != "data"}
    kwargs.setdefault("timeout", default_timeout())
    response = await session.post(
        f"{url}/query",
        data=dict(query_data),
        headers=default_headers(kwargs.pop("headers", None)),
        **kwargs,
    )
    raw = await response.json(content_type=None)
    return raw if isinstance(raw, dict) else {}


async def _resolve_page(
    url: str,
    session: ClientSession | ArcGISTokenSession,
    page: dict[str, Any],
    query_data: Mapping[str, Any],
    *,
    on_truncation: Literal["raise", "ignore", "split"],
    depth: int,
    max_depth: int,
    request_kwargs: dict[str, Any],
) -> AsyncGenerator[dict[str, Any]]:
    """Yield ``page`` (and any sub-pages) honoring ``on_truncation``."""
    envelope = _parse_response(
        FeaturesResponse,
        page,
        context=f"{url}/query",
    )
    if not envelope.exceeded_transfer_limit:
        yield page
        return

    if on_truncation == "ignore":
        get_logger("pagination").warning(
            "exceededTransferLimit=true on page; continuing (on_truncation='ignore'); "
            "response is incomplete for url=%s",
            url,
        )
        yield page
        return

    if on_truncation == "raise":
        raise RestgdfResponseError(
            f"{url}/query returned exceededTransferLimit=true; response page is incomplete.",
            context="exceededTransferLimit",
            raw=page,
            url=f"{url}/query",
        )

    # on_truncation == "split": bisect OID list under the current predicate.
    if depth >= max_depth:
        raise RestgdfResponseError(
            f"{url}/query: on_truncation='split' reached max depth {max_depth}; "
            "layer cannot be bisected further.",
            context="exceededTransferLimit",
            raw=page,
            url=f"{url}/query",
        )
    current_where = query_data.get("where", "1=1") or "1=1"
    split_kwargs = {k: v for k, v in request_kwargs.items() if k != "data"}
    split_kwargs["data"] = {
        **(request_kwargs.get("data") or {}),
        "where": current_where,
    }
    oid_field, oids = await get_object_ids(url, session, **split_kwargs)
    if len(oids) <= 1:
        raise RestgdfResponseError(
            f"{url}/query: on_truncation='split' could not bisect "
            f"{len(oids)} OID(s) further.",
            context="exceededTransferLimit",
            raw=page,
            url=f"{url}/query",
        )
    mid = len(oids) // 2
    halves = (oids[:mid], oids[mid:])
    for half in halves:
        half_where = combine_where_clauses(
            current_where,
            where_var_in_list(oid_field, half),
        )
        sub_qd = dict(query_data)
        sub_qd["where"] = half_where
        # Bisection changes the partitioning scheme; offset/count no longer apply.
        sub_qd.pop("resultOffset", None)
        sub_qd.pop("resultRecordCount", None)
        sub_page = await _fetch_page_dict(
            url,
            session,
            sub_qd,
            **{k: v for k, v in request_kwargs.items() if k != "data"},
        )
        async for resolved in _resolve_page(
            url,
            session,
            sub_page,
            sub_qd,
            on_truncation=on_truncation,
            depth=depth + 1,
            max_depth=max_depth,
            request_kwargs=request_kwargs,
        ):
            yield resolved


async def _iter_pages_raw(
    url: str,
    session: ClientSession | ArcGISTokenSession,
    *,
    order: Literal["request", "completion"] = "request",
    max_concurrent_pages: int | None = None,
    on_truncation: Literal["raise", "ignore", "split"] = "raise",
    max_split_depth: int = 32,
    span_layer_id: int | None = None,
    span_out_fields: Any = None,
    span_where: str | None = None,
    **kwargs,
) -> AsyncGenerator[dict[str, Any]]:
    """Yield raw ArcGIS page envelopes for a FeatureLayer query.

    Implements the streaming primitive that powers
    :meth:`FeatureLayer.iter_pages`. See that method for the public
    contract on ordering, concurrency, and truncation handling.

    The optional ``span_*`` parameters carry the FeatureLayer-derived
    attributes for the R-61 INTERNAL parent span so the caller does not
    need to import telemetry helpers from ``restgdf.featurelayer`` (see
    ``tests/test_telemetry_no_dangling_imports_from_featurelayer.py``).
    """
    if order not in ("request", "completion"):
        raise ValueError(
            f"order must be 'request' or 'completion', got {order!r}",
        )
    if on_truncation not in ("raise", "ignore", "split"):
        raise ValueError(
            "on_truncation must be 'raise', 'ignore', or 'split'; "
            f"got {on_truncation!r}",
        )
    if max_concurrent_pages is not None and max_concurrent_pages < 1:
        raise ValueError(
            f"max_concurrent_pages must be >= 1, got {max_concurrent_pages!r}",
        )

    # R-61: open a NON-current INTERNAL span and end it from the outer
    # ``finally:`` block. Using ``start_as_current_span`` here would attach
    # an asyncio Context token that the async-generator machinery cannot
    # safely detach when the consumer breaks early / calls ``aclose()`` /
    # is cancelled, producing "Failed to detach context" errors and a
    # leaked span. See rd-gate2-phase4a remediation.
    span = start_feature_layer_stream_span(
        layer_url=url,
        layer_id=span_layer_id,
        out_fields=span_out_fields,
        where=span_where,
        order=order,
    )
    tasks: list[asyncio.Task] = []
    try:
        query_data_batches = await get_query_data_batches(url, session, **kwargs)
        fetch_kwargs = {k: v for k, v in kwargs.items() if k != "data"}
        sem = (
            asyncio.Semaphore(max_concurrent_pages)
            if max_concurrent_pages is not None
            else None
        )

        async def _fetch_bounded(query_data: dict) -> tuple[dict, dict[str, Any]]:
            if sem is None:
                page = await _fetch_page_dict(url, session, query_data, **fetch_kwargs)
            else:
                async with sem:
                    page = await _fetch_page_dict(
                        url,
                        session,
                        query_data,
                        **fetch_kwargs,
                    )
            return query_data, page

        tasks = [asyncio.create_task(_fetch_bounded(qd)) for qd in query_data_batches]

        if order == "completion":
            for fut in asyncio.as_completed(tasks):
                query_data, page = await fut
                async for resolved in _resolve_page(
                    url,
                    session,
                    page,
                    query_data,
                    on_truncation=on_truncation,
                    depth=0,
                    max_depth=max_split_depth,
                    request_kwargs=kwargs,
                ):
                    yield resolved
        else:
            for task in tasks:
                query_data, page = await task
                async for resolved in _resolve_page(
                    url,
                    session,
                    page,
                    query_data,
                    on_truncation=on_truncation,
                    depth=0,
                    max_depth=max_split_depth,
                    request_kwargs=kwargs,
                ):
                    yield resolved
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        if span is not None:
            span.end()
