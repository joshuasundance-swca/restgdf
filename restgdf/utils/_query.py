"""Async HTTP query helpers for ArcGIS REST endpoints.

Private submodule; all public names are re-exported by
``restgdf.utils.getinfo`` to preserve import paths.

Note: orchestration functions that dispatch to helpers in this module
(``get_offset_range``, ``service_metadata``) live in ``getinfo.py`` itself so
that patching ``restgdf.utils.getinfo.<helper>`` intercepts those calls.
"""

from __future__ import annotations

from aiohttp import ClientSession

from restgdf._client.request import build_conservative_query_data
from restgdf._models._drift import _parse_response
from restgdf._models.responses import (
    CountResponse,
    LayerMetadata,
    ObjectIdsResponse,
)
from restgdf.utils._http import default_headers, default_timeout
from restgdf.utils.token import ArcGISTokenSession


async def get_feature_count(
    url: str,
    session: ClientSession | ArcGISTokenSession,
    **kwargs,
) -> int:
    """Get the feature count for a layer.

    The JSON body is validated against :class:`CountResponse` (strict
    tier). A missing/ill-typed ``count`` key raises
    :class:`~restgdf._models.RestgdfResponseError` with the original
    payload and request URL attached for operator triage.
    """
    datadict = build_conservative_query_data(
        {"where": "1=1", "returnCountOnly": True, "f": "json"},
        kwargs.get("data"),
    )
    xkwargs: dict = {k: v for k, v in kwargs.items() if k != "data"}
    xkwargs.setdefault("timeout", default_timeout())
    query_url = f"{url}/query"
    response = await session.post(
        query_url,
        data=datadict,
        headers=default_headers(xkwargs.pop("headers", None)),
        **xkwargs,
    )
    response_json = await response.json(content_type=None)
    envelope = _parse_response(CountResponse, response_json, context=query_url)
    return envelope.count


async def get_metadata(
    url: str,
    session: ClientSession | ArcGISTokenSession,
    token: str | None = None,
) -> LayerMetadata:
    """Get the parsed metadata model for a layer.

    The JSON body is validated against :class:`LayerMetadata` (permissive
    tier). Vendor-variance extras are preserved via ``extra="allow"``;
    missing fields default to ``None`` rather than raise. Drift is logged
    through :mod:`restgdf._models._drift` rather than returned to the
    caller.
    """
    data = {"f": "json"}
    if token is not None:
        data["token"] = token
    response = await session.get(
        url,
        params=data,
        headers=default_headers(),
        timeout=default_timeout(),
    )
    raw = await response.json(content_type=None)
    return _parse_response(LayerMetadata, raw, context=url)


async def get_object_ids(
    url: str,
    session: ClientSession | ArcGISTokenSession,
    **kwargs,
) -> tuple[str, list[int]]:
    """Get the object id field name and matching object ids for a layer query.

    The JSON body is validated against :class:`ObjectIdsResponse` (strict
    tier) so missing field names or non-list id payloads raise
    :class:`~restgdf._models.RestgdfResponseError` before the caller can
    misuse them. ArcGIS returns ``objectIds: null`` for zero-row
    matches; the model coerces that to ``[]``.
    """
    datadict = build_conservative_query_data(
        {"where": "1=1", "returnIdsOnly": True, "f": "json"},
        kwargs.get("data"),
    )
    xkwargs: dict = {k: v for k, v in kwargs.items() if k != "data"}
    xkwargs.setdefault("timeout", default_timeout())
    query_url = f"{url}/query"
    response = await session.post(
        query_url,
        data=datadict,
        headers=default_headers(xkwargs.pop("headers", None)),
        **xkwargs,
    )
    response_json = await response.json(content_type=None)
    envelope = _parse_response(ObjectIdsResponse, response_json, context=query_url)
    return envelope.object_id_field_name, envelope.object_ids
