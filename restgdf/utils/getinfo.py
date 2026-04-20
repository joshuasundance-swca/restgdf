"""A package for getting GeoDataFrames from ArcGIS FeatureLayers.

Phase 2 split: this module is now a compatibility shim that re-exports public
names from the private submodules ``_http``, ``_metadata``, ``_query``, and
``_stats``. The orchestration helpers ``get_offset_range`` and
``service_metadata`` remain DEFINED here so that patches against
``restgdf.utils.getinfo.<helper>`` continue to intercept their sibling calls
(see ``tests/test_getinfo_seams.py``).

The ``from aiohttp import ClientSession`` line is PUBLIC API: tests patch
``restgdf.utils.getinfo.ClientSession.post`` / ``.get``. Do not remove it.
"""

from __future__ import annotations

import asyncio

from aiohttp import ClientSession

from restgdf.utils._http import (
    DEFAULT_METADATA_HEADERS,
    DEFAULTDICT,
    default_data,
    default_headers,
)
from restgdf.utils._metadata import (
    FIELDDOESNOTEXIST,
    get_fields,
    get_fields_frame,
    get_max_record_count,
    get_name,
    get_object_id_field,
    getfields,
    getfields_df,
    supports_pagination,
)
from restgdf._types import LayerMetadata
from restgdf.utils._query import get_feature_count, get_metadata, get_object_ids
from restgdf.utils._stats import (
    get_unique_values,
    get_value_counts,
    getuniquevalues,
    getvaluecounts,
    nested_count,
    nestedcount,
)
from restgdf.utils.token import ArcGISTokenSession

__all__ = [
    "ClientSession",
    "DEFAULTDICT",
    "DEFAULT_METADATA_HEADERS",
    "FIELDDOESNOTEXIST",
    "default_data",
    "default_headers",
    "get_feature_count",
    "get_fields",
    "get_fields_frame",
    "get_max_record_count",
    "get_metadata",
    "get_name",
    "get_object_id_field",
    "get_object_ids",
    "get_offset_range",
    "get_unique_values",
    "get_value_counts",
    "getfields",
    "getfields_df",
    "getuniquevalues",
    "getvaluecounts",
    "nested_count",
    "nestedcount",
    "service_metadata",
    "supports_pagination",
]


async def get_offset_range(
    url: str,
    session: ClientSession | ArcGISTokenSession,
    **kwargs,
) -> range:
    """Get the offset range for a layer.

    Orchestrator: resolves ``get_feature_count``, ``get_metadata``, and
    ``get_max_record_count`` through this module's namespace so that
    ``unittest.mock.patch("restgdf.utils.getinfo.<helper>")`` intercepts.
    """
    feature_count = await get_feature_count(url, session, **kwargs)
    token = (kwargs.get("data") or {}).get("token")
    metadata = await get_metadata(url, session, token=token)
    max_record_count = get_max_record_count(metadata)
    return range(0, feature_count, max_record_count)


async def service_metadata(
    session: ClientSession | ArcGISTokenSession,
    service_url: str,
    token: str | None = None,
    return_feature_count: bool = False,
) -> LayerMetadata:
    """Asynchronously retrieve layers for a single service.

    Orchestrator: resolves ``get_metadata`` and ``get_feature_count`` through
    this module's namespace so that
    ``unittest.mock.patch("restgdf.utils.getinfo.<helper>")`` intercepts.
    """
    _service_metadata = await get_metadata(service_url, session, token=token)

    async def _comprehensive_metadata(layer_url: str) -> LayerMetadata:
        metadata = await get_metadata(layer_url, session, token=token)
        metadata["url"] = layer_url
        if return_feature_count and metadata["type"] == "Feature Layer":
            try:
                feature_count = await get_feature_count(
                    layer_url,
                    session,
                    **({"data": {"token": token}} if token is not None else {}),
                )
            except KeyError:
                feature_count = None
            metadata["feature_count"] = feature_count  # type: ignore
        return metadata

    tasks = [
        _comprehensive_metadata(f"{service_url}/{layer['id']}")
        for layer in _service_metadata.get("layers") or []
    ]
    results = await asyncio.gather(*tasks)
    _service_metadata["layers"] = results
    return _service_metadata
