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
from typing import Any

from aiohttp import ClientSession
from pydantic import BaseModel

from restgdf.utils._http import (
    DEFAULT_METADATA_HEADERS,
    DEFAULTDICT,
    default_data,
    default_headers,
)
from restgdf.utils._concurrency import bounded_gather
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
from restgdf._models._drift import _parse_response
from restgdf._config import get_config
from restgdf._models.responses import LayerMetadata
from restgdf.utils._query import get_feature_count, get_metadata, get_object_ids
from restgdf.utils._pagination import PaginationPlan, build_pagination_plan
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
    "PaginationPlan",
    "build_pagination_plan",
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
    _sem: asyncio.Semaphore | None = None,
) -> LayerMetadata:
    """Asynchronously retrieve layers for a single service.

    Orchestrator: resolves ``get_metadata`` and ``get_feature_count`` through
    this module's namespace so that
    ``unittest.mock.patch("restgdf.utils.getinfo.<helper>")`` intercepts.
    The aggregated payload is validated against :class:`LayerMetadata` via
    the drift adapter before being returned, so vendor-variance extras are
    logged (not raised) and callers get a typed envelope.

    BL-01: ``_sem`` is a private kwarg allowing a caller (e.g. the
    ``fetch_all_data`` / ``safe_crawl`` orchestrators) to share ONE
    ``BoundedSemaphore`` across nested fan-outs so the cap is global per
    top-level request. When ``None``, a fresh sem is created and the
    direct-call semantics are preserved.
    """
    # BL-01: when called nested (``_sem`` supplied), every HTTP call made by
    # this orchestrator must compete for the same cap as the caller's fan-out.
    # When called standalone, a fresh sem preserves the direct-call contract.
    sem = _sem or asyncio.BoundedSemaphore(
        get_config().concurrency.max_concurrent_requests,
    )

    # Service-level metadata is a single HTTP call — gate it explicitly so it
    # participates in the shared cap without being wrapped by the
    # ``bounded_gather`` below (which would introduce a double-acquire).
    async with sem:
        _raw = await get_metadata(service_url, session, token=token)
    _service_metadata: dict[str, Any] = (
        _raw.model_dump(by_alias=True) if isinstance(_raw, BaseModel) else dict(_raw)
    )

    async def _comprehensive_metadata(layer_url: str) -> dict[str, Any]:
        # ``bounded_gather`` below acquires ``sem`` once per task, so do NOT
        # re-acquire here — ``asyncio.Semaphore`` is not re-entrant.
        layer_raw = await get_metadata(layer_url, session, token=token)
        metadata: dict[str, Any] = (
            layer_raw.model_dump(by_alias=True)
            if isinstance(layer_raw, BaseModel)
            else dict(layer_raw)
        )
        metadata["url"] = layer_url
        if return_feature_count and metadata.get("type") == "Feature Layer":
            try:
                feature_count = await get_feature_count(
                    layer_url,
                    session,
                    **({"data": {"token": token}} if token is not None else {}),
                )
            except KeyError:
                feature_count = None
            metadata["feature_count"] = feature_count
        return metadata

    tasks = [
        _comprehensive_metadata(f"{service_url}/{layer['id']}")
        for layer in _service_metadata.get("layers") or []
    ]
    # BL-01: enumerated fan-out site. ``bounded_gather`` holds ``sem`` for
    # each task (plan.md §3c R-18/R-44, kickoff §10.3). When a shared sem is
    # passed in by a top-level orchestrator, the cap is truly global.
    results = await bounded_gather(*tasks, semaphore=sem)
    _service_metadata["layers"] = results
    return _parse_response(LayerMetadata, _service_metadata, context=service_url)
