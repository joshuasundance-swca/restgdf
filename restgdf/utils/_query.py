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
from restgdf._types import CountResponse, LayerMetadata, ObjectIdsResponse
from restgdf.utils._http import default_headers
from restgdf.utils.token import ArcGISTokenSession


async def get_feature_count(
    url: str,
    session: ClientSession | ArcGISTokenSession,
    **kwargs,
) -> int:
    """Get the feature count for a layer."""
    datadict = build_conservative_query_data(
        {"where": "1=1", "returnCountOnly": True, "f": "json"},
        kwargs.get("data"),
    )
    xkwargs: dict = {k: v for k, v in kwargs.items() if k != "data"}
    response = await session.post(
        f"{url}/query",
        data=datadict,
        headers=default_headers(xkwargs.pop("headers", None)),
        **xkwargs,
    )
    response_json: CountResponse = await response.json(content_type=None)
    try:
        return response_json["count"]
    except KeyError as e:
        raise e


async def get_metadata(
    url: str,
    session: ClientSession | ArcGISTokenSession,
    token: str | None = None,
) -> LayerMetadata:
    """Get the JSON dict for a layer."""
    data = {"f": "json"}
    if token is not None:
        data["token"] = token
    response = await session.get(url, params=data, headers=default_headers())
    return await response.json(content_type=None)


async def get_object_ids(
    url: str,
    session: ClientSession | ArcGISTokenSession,
    **kwargs,
) -> tuple[str, list[int]]:
    """Get the object id field name and matching object ids for a layer query."""
    datadict = build_conservative_query_data(
        {"where": "1=1", "returnIdsOnly": True, "f": "json"},
        kwargs.get("data"),
    )
    xkwargs: dict = {k: v for k, v in kwargs.items() if k != "data"}
    response = await session.post(
        f"{url}/query",
        data=datadict,
        headers=default_headers(xkwargs.pop("headers", None)),
        **xkwargs,
    )
    response_json: ObjectIdsResponse = await response.json(content_type=None)
    return response_json["objectIdFieldName"], response_json["objectIds"]
