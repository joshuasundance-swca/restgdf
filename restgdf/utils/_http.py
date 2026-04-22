"""HTTP defaults for ArcGIS REST helpers.

Private submodule; all public names are re-exported by
``restgdf.utils.getinfo`` to preserve import paths.
"""

from __future__ import annotations

from typing import Literal
from collections.abc import Mapping
from urllib.parse import urlsplit

DEFAULT_METADATA_HEADERS = {
    "Accept": "application/json,text/plain,*/*",
    "User-Agent": "Mozilla/5.0",
}

DEFAULTDICT: dict = {
    "where": "1=1",
    "outFields": "*",
    "returnGeometry": True,
    "returnCountOnly": False,
    "f": "json",
}


def default_headers(headers: dict | None = None) -> dict:
    """Return request headers merged with ArcGIS-compatible defaults."""
    return {**DEFAULT_METADATA_HEADERS, **(headers or {})}


def default_data(
    data: dict | None = None,
    default_dict: dict | None = None,
) -> dict:
    """Return a dict with default values for ArcGIS REST API requests."""
    default_dict = default_dict or DEFAULTDICT
    return {**default_dict, **(data or {})}


_POST_ENDPOINT_SUFFIXES: tuple[str, ...] = ("/query", "/queryRelatedRecords")
_GET_PARENT_SEGMENTS: tuple[str, ...] = (
    "MapServer",
    "FeatureServer",
    "ImageServer",
    "GPServer",
)


def _choose_verb(
    url: str,
    body: Mapping[str, object] | None = None,
) -> Literal["POST", "GET"]:
    """Return the HTTP verb restgdf should use for ``url``.

    BL-20 seam (MASTER-PLAN §5 BL-20, plan.md §3c R-34/R-35/R-38,
    kickoff phase-1a §10.1).

    Rules (deterministic, call-sites not yet rewired in this slice):

    * ArcGIS ``/query`` and ``/queryRelatedRecords`` endpoints → ``POST``
      (queries can carry long ``where`` clauses and arbitrary geometry).
    * Bare service / layer URLs whose path ends in a server family
      segment (``MapServer``, ``FeatureServer``, ``ImageServer``,
      ``GPServer``) or a numeric layer index directly under one →
      ``GET`` (short, idempotent metadata fetches).
    * Everything else → ``POST`` (conservative default — avoids URL
      length blowups and tolerates unknown ArcGIS operations).

    The ``body`` parameter is accepted for forward compatibility but
    currently ignored. BL-50 will extend this helper to auto-switch a
    ``GET`` to ``POST`` when the serialized ``where``/``outFields``
    payload pushes a GET URL past the ArcGIS ~1800-byte budget.
    """
    path = urlsplit(url).path.rstrip("/")
    for suffix in _POST_ENDPOINT_SUFFIXES:
        if path.endswith(suffix):
            return "POST"
    segments = path.split("/")
    if segments and segments[-1] in _GET_PARENT_SEGMENTS:
        return "GET"
    if (
        len(segments) >= 2
        and segments[-1].isdigit()
        and segments[-2] in _GET_PARENT_SEGMENTS
    ):
        return "GET"
    return "POST"
