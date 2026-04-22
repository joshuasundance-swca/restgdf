"""Get a GeoDataFrame from an ArcGIS FeatureLayer."""

from __future__ import annotations

import asyncio
from asyncio import gather
from collections.abc import AsyncGenerator
from functools import reduce
from typing import TYPE_CHECKING, Any

from aiohttp import ClientSession

from restgdf._models._drift import _parse_response
from restgdf._models.responses import FeaturesResponse
from restgdf.errors import PaginationError
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
from restgdf.utils._metadata import supports_pagination_explicitly
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
) -> AsyncGenerator[list[dict[str, Any]], None]:
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
) -> AsyncGenerator[GeoDataFrame, None]:
    """
    Asynchronously yield GeoDataFrames from a FeatureLayer in chunks.
    This function retrieves GeoDataFrames in chunks based on the offset range
    and yields each GeoDataFrame as it is retrieved.
    """
    _require_geo_query_support("chunk_generator()")
    query_data_batches = await get_query_data_batches(url, session, **kwargs)
    tasks = {
        asyncio.create_task(get_sub_gdf(url, session, query_data=query_data, **kwargs))
        for query_data in query_data_batches
    }
    for sub_gdf_future in asyncio.as_completed(tasks):
        yield await sub_gdf_future


async def row_dict_generator(
    url: str,
    session: ClientSession | ArcGISTokenSession,
    **kwargs,
) -> AsyncGenerator[dict, None]:
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
    return await concat_gdfs(gdfs)


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
