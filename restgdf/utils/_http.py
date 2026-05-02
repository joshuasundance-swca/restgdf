"""HTTP defaults for ArcGIS REST helpers.

Private submodule; all public names are re-exported by
``restgdf.utils.getinfo`` to preserve import paths.
"""

from __future__ import annotations

from collections.abc import Mapping
import inspect
from typing import Any, Literal
from urllib.parse import urlencode

import aiohttp

from restgdf._config import get_config

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


# T8 (R-74): ArcGIS REST practical URL-length ceiling. Past this many bytes
# (URL + encoded body), servers (and intermediaries like IIS/WAFs) routinely
# reject the GET with 414 URI Too Long, so restgdf must fall back to POST.
_ARCGIS_URL_BODY_LIMIT: int = 8192


def _encoded_body_length(body: Mapping[str, object] | None) -> int:
    """Return the byte length of ``body`` as it would be URL-encoded."""
    if not body:
        return 0
    return len(urlencode(dict(body), doseq=True))


def _choose_verb(
    url: str,
    body: Mapping[str, object] | None = None,
) -> Literal["POST", "GET"]:
    """Return the HTTP verb restgdf should use for ``url`` with ``body``.

    T8 (R-74) wires this helper at every ArcGIS call site. The decision
    is length-based against :data:`_ARCGIS_URL_BODY_LIMIT` (the 8k
    practical ceiling ArcGIS Server / IIS / common WAFs enforce for
    ``GET`` query strings):

    * ``len(url) + len(urlencode(body)) <= limit`` → ``GET`` — idempotent,
      cache-friendly, byte-for-byte equivalent to today's short-body GETs.
    * Anything larger → ``POST`` — restgdf will never emit a request that
      a real server will refuse with 414 URI Too Long.

    ``body`` is accepted as any mapping (or ``None``). The helper never
    mutates the mapping; it only measures its encoded size. A ``None``
    or empty body short-circuits to ``GET`` immediately.
    """
    encoded_len = _encoded_body_length(body)
    # Account for the "?" separator that aiohttp would add between the
    # URL path and the query string in a GET request.
    separator = 1 if encoded_len else 0
    if len(url) + separator + encoded_len <= _ARCGIS_URL_BODY_LIMIT:
        return "GET"
    return "POST"


async def _arcgis_request(
    session: Any,
    url: str,
    body: Mapping[str, object] | None,
    **kwargs: Any,
) -> Any:
    """Issue an ArcGIS request using the verb selected by :func:`_choose_verb`.

    T8 (R-74): centralizes the GET-vs-POST decision so every ArcGIS call
    site participates in length-based routing.

    * ``GET`` → ``session.get(url, params=body, **kwargs)``
    * ``POST`` → ``session.post(url, data=body, **kwargs)``

    ``body`` is forwarded untouched; the helper never injects or removes
    keys. Any extra ``kwargs`` (``headers``, ``timeout``, ``ssl`` …) are
    passed through to the underlying session call verbatim so request
    semantics stay byte-for-byte identical below the verb switch.

    **Credential safety (Gate-3 fix).** ``ArcGISTokenSession`` configured
    with ``transport="body"`` or ``transport="query"`` injects the
    bearer token into the outgoing payload. If the length-based router
    chose ``GET`` for such a session, the token would be serialized
    into the URL query string — a credential leak. To preserve the
    pre-T8 wire shape, this helper walks the session's ``_inner`` chain
    and forces ``POST`` whenever any layer reports a non-``"header"``
    transport (``ResilientSession(ArcGISTokenSession(transport="body"))``
    and similar wrappers included).
    """
    if _session_requires_body_transport(session):
        return await session.post(url, data=body, **kwargs)
    verb = _choose_verb(url, body=body)
    if verb == "GET":
        params = _coerce_params_for_get(body) if body else body
        return await session.get(url, params=params, **kwargs)
    return await session.post(url, data=body, **kwargs)


def _session_requires_body_transport(session: Any) -> bool:
    """Return ``True`` if ``session`` (or any wrapped inner session)
    injects an auth token into the request payload rather than the
    ``X-Esri-Authorization`` header.

    Walks the ``_inner`` attribute chain so adapters such as
    :class:`restgdf.resilience.ResilientSession` wrapping an
    :class:`restgdf.utils.token.ArcGISTokenSession` still trigger the
    safe ``POST`` path. ``transport="header"`` (and sessions without a
    ``_transport`` attribute at all, e.g. plain
    :class:`aiohttp.ClientSession`) are treated as verb-neutral.
    """
    current: Any = session
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        transport = _safe_static_attr_value(current, "_transport")
        if transport in ("body", "query"):
            return True
        current = _safe_static_attr_value(current, "_inner")
    return False


def _safe_static_attr_value(obj: Any, name: str) -> Any:
    """Read an attribute without fabricating mock children.

    ``inspect.getattr_static`` protects against ``AsyncMock`` creating
    synthetic attributes on demand, but returns raw descriptors for
    property-backed attributes. Resolve descriptors only after confirming
    the attribute exists statically.
    """
    value = inspect.getattr_static(obj, name, None)
    if value is None:
        return None
    if hasattr(value, "__get__"):
        try:
            return object.__getattribute__(obj, name)
        except AttributeError:
            return None
    return value


def _coerce_params_for_get(
    body: Mapping[str, object],
) -> dict[str, Any]:
    """Return ``body`` with values normalized for ``session.get(params=...)``.

    ``yarl`` (aiohttp's URL builder) rejects :class:`bool` and ``None``
    values in query params with :class:`TypeError`, while the equivalent
    ``session.post(data=...)`` path serializes them happily via
    :func:`urllib.parse.urlencode`. T8 (R-74) routes the same ArcGIS
    payloads through either verb, so this helper keeps the GET path
    byte-for-byte equivalent to what ArcGIS Server sees today:
    booleans become lowercase ``"true"``/``"false"`` (ArcGIS's own wire
    convention) and ``None`` becomes an empty string.
    """
    coerced: dict[str, Any] = {}
    for key, value in body.items():
        if isinstance(value, bool):
            coerced[key] = "true" if value else "false"
        elif value is None:
            coerced[key] = ""
        else:
            coerced[key] = value
    return coerced


def default_timeout(settings: Any | None = None) -> aiohttp.ClientTimeout:
    """Return an :class:`aiohttp.ClientTimeout` driven by restgdf config.

    When ``settings`` is ``None`` (the library-default call path), the
    timeout is resolved from :func:`restgdf.get_config` — specifically
    ``config.timeout.total_s``. When a ``settings`` object is supplied,
    the helper reads its ``timeout_seconds`` attribute (duck-typed) to
    remain backwards compatible with the legacy
    :class:`restgdf.Settings` surface and any ``SimpleNamespace``-style
    fakes used in tests.

    This helper is intentionally read-only: it never mutates its inputs
    and never caches the ``ClientTimeout`` across calls, so environment
    overrides take effect as soon as
    :func:`~restgdf.reset_config_cache` (or the legacy
    :func:`~restgdf._models._settings.reset_settings_cache`) has been
    called.
    """
    if settings is not None:
        return aiohttp.ClientTimeout(total=float(settings.timeout_seconds))
    return aiohttp.ClientTimeout(total=float(get_config().timeout.total_s))
