"""T8 (R-74): ``_choose_verb`` wired at every ArcGIS request site.

Short bodies (URL + encoded body under the ArcGIS 8k practical limit) must
route through HTTP GET; long bodies flip to POST so restgdf never emits a
request that a real ArcGIS server will refuse with 414 URI Too Long.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from restgdf.utils._http import _choose_verb, _ARCGIS_URL_BODY_LIMIT
from restgdf.utils._query import get_feature_count, get_object_ids
from restgdf.utils._stats import get_unique_values
from restgdf.utils.getgdf import _fetch_page_dict, _get_sub_features


class _RecordingResponse:
    """Async response stub matching the shape restgdf helpers consume."""

    def __init__(self, payload: Any):
        self._payload = payload

    def __await__(self):
        async def _resolve() -> _RecordingResponse:
            return self

        return _resolve().__await__()

    async def __aenter__(self) -> _RecordingResponse:
        return self

    async def __aexit__(self, exc_type, exc_value, traceback) -> None:
        return None

    async def json(self, content_type: str | None = None):
        return self._payload

    async def text(self) -> str:
        return json.dumps(self._payload)


class _RecordingSession:
    """Session double that records the HTTP verb used per call."""

    def __init__(self, payload: Any):
        self._payload = payload
        self._closed = False
        self.verbs: list[str] = []
        self.calls: list[tuple[str, str, dict]] = []

    @property
    def closed(self) -> bool:
        return self._closed

    async def close(self) -> None:
        self._closed = True

    def get(self, url: str, **kwargs) -> _RecordingResponse:
        self.verbs.append("GET")
        self.calls.append(("GET", url, dict(kwargs)))
        return _RecordingResponse(self._payload)

    def post(self, url: str, **kwargs) -> _RecordingResponse:
        self.verbs.append("POST")
        self.calls.append(("POST", url, dict(kwargs)))
        return _RecordingResponse(self._payload)


# ---------------------------------------------------------------------------
# Helper-level invariants
# ---------------------------------------------------------------------------


def test_choose_verb_short_body_returns_get() -> None:
    body = {"where": "1=1", "f": "json", "returnCountOnly": True}
    assert _choose_verb("https://example.com/s/FeatureServer/0/query", body) == "GET"


def test_choose_verb_no_body_returns_get() -> None:
    assert _choose_verb("https://example.com/s/FeatureServer/0") == "GET"


def test_choose_verb_oversized_body_returns_post() -> None:
    long_where = "OBJECTID IN (" + ",".join(str(i) for i in range(2000)) + ")"
    body = {"where": long_where, "f": "json", "returnCountOnly": True}
    assert _choose_verb("https://example.com/s/FeatureServer/0/query", body) == "POST"


def test_choose_verb_threshold_is_arcgis_practical_limit() -> None:
    assert _ARCGIS_URL_BODY_LIMIT == 8192


# ---------------------------------------------------------------------------
# Call-site wiring — get_count / get_feature_count
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_feature_count_short_where_routes_to_get() -> None:
    session = _RecordingSession({"count": 42})

    count = await get_feature_count(
        "https://example.com/service/0",
        session,
    )

    assert count == 42
    assert session.verbs == ["GET"]
    verb, url, kwargs = session.calls[0]
    assert url == "https://example.com/service/0/query"
    assert kwargs["params"]["where"] == "1=1"
    assert kwargs["params"]["returnCountOnly"] == "true"


@pytest.mark.asyncio
async def test_get_feature_count_long_where_routes_to_post() -> None:
    long_where = "OBJECTID IN (" + ",".join(str(i) for i in range(2000)) + ")"
    session = _RecordingSession({"count": 99})

    count = await get_feature_count(
        "https://example.com/service/0",
        session,
        data={"where": long_where},
    )

    assert count == 99
    assert session.verbs == ["POST"]
    verb, url, kwargs = session.calls[0]
    assert url == "https://example.com/service/0/query"
    assert kwargs["data"]["where"] == long_where


# ---------------------------------------------------------------------------
# Call-site wiring — other /query helpers
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_object_ids_short_where_routes_to_get() -> None:
    session = _RecordingSession(
        {"objectIdFieldName": "OBJECTID", "objectIds": [1, 2, 3]},
    )
    field, ids = await get_object_ids("https://example.com/service/0", session)

    assert field == "OBJECTID"
    assert ids == [1, 2, 3]
    assert session.verbs == ["GET"]


@pytest.mark.asyncio
async def test_get_object_ids_long_where_routes_to_post() -> None:
    long_where = "OBJECTID IN (" + ",".join(str(i) for i in range(2000)) + ")"
    session = _RecordingSession(
        {"objectIdFieldName": "OBJECTID", "objectIds": []},
    )
    await get_object_ids(
        "https://example.com/service/0",
        session,
        data={"where": long_where},
    )
    assert session.verbs == ["POST"]


@pytest.mark.asyncio
async def test_get_unique_values_long_outfields_routes_to_post() -> None:
    long_field = "F_" + ("X" * 9000)
    session = _RecordingSession({"features": []})
    await get_unique_values(
        "https://example.com/service/0",
        long_field,
        session,
    )
    assert session.verbs == ["POST"]


@pytest.mark.asyncio
async def test_get_sub_features_short_query_routes_to_get() -> None:
    session = _RecordingSession({"features": [], "exceededTransferLimit": False})
    await _get_sub_features(
        "https://example.com/service/0",
        session,
        {"where": "1=1", "f": "json"},
    )
    assert session.verbs == ["GET"]


@pytest.mark.asyncio
async def test_get_sub_features_long_query_routes_to_post() -> None:
    long_where = "OBJECTID IN (" + ",".join(str(i) for i in range(2000)) + ")"
    session = _RecordingSession({"features": [], "exceededTransferLimit": False})
    await _get_sub_features(
        "https://example.com/service/0",
        session,
        {"where": long_where, "f": "json"},
    )
    assert session.verbs == ["POST"]


@pytest.mark.asyncio
async def test_fetch_page_dict_short_query_routes_to_get() -> None:
    session = _RecordingSession({"features": []})
    await _fetch_page_dict(
        "https://example.com/service/0",
        session,
        {"where": "1=1", "f": "json"},
    )
    assert session.verbs == ["GET"]


@pytest.mark.asyncio
async def test_fetch_page_dict_long_query_routes_to_post() -> None:
    long_where = "OBJECTID IN (" + ",".join(str(i) for i in range(2000)) + ")"
    session = _RecordingSession({"features": []})
    await _fetch_page_dict(
        "https://example.com/service/0",
        session,
        {"where": long_where, "f": "json"},
    )
    assert session.verbs == ["POST"]
