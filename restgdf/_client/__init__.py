"""Internal client helpers.

This subpackage is private (underscore-prefixed) and not part of the public API.
It exists to consolidate request-body construction used by the ArcGIS REST
helpers so the duplicated merge logic in :mod:`restgdf.utils.getinfo` and
related modules has a single source of truth.
"""

from restgdf._client._protocols import AsyncHTTPSession
from restgdf._client.request import build_conservative_query_data

__all__ = ["AsyncHTTPSession", "build_conservative_query_data"]
