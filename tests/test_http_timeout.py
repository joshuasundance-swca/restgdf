"""Tests for :func:`restgdf.utils._http.default_timeout` (BL-02).

Verifies that the helper resolves against ``Settings.timeout_seconds``
(float, default ``30.0``) and that every library-side ``session.get`` /
``session.post`` call-site in scope forwards a matching
:class:`aiohttp.ClientTimeout`.

Scope: BL-02. The two ArcGIS query batch POSTs in
``restgdf/utils/getgdf.py`` (``_get_sub_features`` and
``get_sub_gdf``) plus the ``ArcGISTokenSession.get``/``post`` wrappers
are in scope here; the pagination/``supports_pagination`` callsite in
``getgdf.py`` is BL-08's problem and remains untouched.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import aiohttp
import pytest

from restgdf._models._settings import Settings, reset_settings_cache


class _FakeResponse:
    """Minimal async-response double matching the parser shape."""

    def __init__(self, payload: dict[str, Any]):
        self._payload = payload

    async def json(self, content_type: Any = None) -> dict[str, Any]:
        return self._payload

    def raise_for_status(self) -> None:
        return None

    async def __aenter__(self) -> _FakeResponse:
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None


class _RecordingSession:
    """Records kwargs for each outbound call so tests can assert timeout."""

    def __init__(self, payload: dict[str, Any]):
        self._payload = payload
        self.get_calls: list[tuple[str, dict]] = []
        self.post_calls: list[tuple[str, dict]] = []

    async def get(self, url: str, **kwargs: Any) -> _FakeResponse:
        self.get_calls.append((url, kwargs))
        return _FakeResponse(self._payload)

    async def post(self, url: str, **kwargs: Any) -> _FakeResponse:
        self.post_calls.append((url, kwargs))
        return _FakeResponse(self._payload)


def _assert_timeout_kwarg(kwargs: dict, expected_total: float) -> None:
    timeout = kwargs.get("timeout")
    assert isinstance(
        timeout,
        aiohttp.ClientTimeout,
    ), f"expected aiohttp.ClientTimeout kwarg, got {timeout!r}"
    assert timeout.total == pytest.approx(expected_total)


# ---------------------------------------------------------------------------
# default_timeout() helper contract
# ---------------------------------------------------------------------------


def test_default_timeout_uses_explicit_settings_timeout_seconds():
    from restgdf.utils._http import default_timeout

    settings = Settings(timeout_seconds=5.5)
    result = default_timeout(settings)
    assert isinstance(result, aiohttp.ClientTimeout)
    assert result.total == pytest.approx(5.5)


def test_default_timeout_default_resolves_to_settings_30_float(monkeypatch):
    from restgdf.utils._http import default_timeout

    monkeypatch.delenv("RESTGDF_TIMEOUT_SECONDS", raising=False)
    reset_settings_cache()
    try:
        result = default_timeout()
        assert isinstance(result, aiohttp.ClientTimeout)
        assert result.total == pytest.approx(30.0)
    finally:
        reset_settings_cache()


def test_default_timeout_reads_env_as_float(monkeypatch):
    from restgdf.utils._http import default_timeout

    monkeypatch.setenv("RESTGDF_TIMEOUT_SECONDS", "7.25")
    reset_settings_cache()
    try:
        result = default_timeout()
        assert result.total == pytest.approx(7.25)
    finally:
        reset_settings_cache()


# ---------------------------------------------------------------------------
# Call-site migration inventory: _query, _stats, token
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_feature_count_forwards_timeout():
    from restgdf.utils._query import get_feature_count

    session = _RecordingSession({"count": 0})
    await get_feature_count("https://example.com/service/0", session)  # type: ignore[arg-type]
    assert len(session.post_calls) == 1
    _assert_timeout_kwarg(session.post_calls[0][1], 30.0)


@pytest.mark.asyncio
async def test_get_metadata_forwards_timeout():
    from restgdf.utils._query import get_metadata

    session = _RecordingSession({"name": "layer"})
    await get_metadata("https://example.com/service/0", session)  # type: ignore[arg-type]
    assert len(session.get_calls) == 1
    _assert_timeout_kwarg(session.get_calls[0][1], 30.0)


@pytest.mark.asyncio
async def test_get_object_ids_forwards_timeout():
    from restgdf.utils._query import get_object_ids

    session = _RecordingSession(
        {"objectIdFieldName": "OBJECTID", "objectIds": []},
    )
    await get_object_ids("https://example.com/service/0", session)  # type: ignore[arg-type]
    assert len(session.post_calls) == 1
    _assert_timeout_kwarg(session.post_calls[0][1], 30.0)


@pytest.mark.asyncio
async def test_update_token_forwards_timeout(monkeypatch):
    from restgdf._models.credentials import AGOLUserPass
    from restgdf.utils.token import ArcGISTokenSession

    class _TokenCtx:
        def __init__(self, captured: dict, payload: dict):
            self._captured = captured
            self._payload = payload

        async def __aenter__(self) -> _TokenCtx:
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def json(self) -> dict:
            return self._payload

        def raise_for_status(self) -> None:
            return None

    captured: dict = {}

    class _FakeTokenSession:
        def post(self, url: str, **kwargs: Any):
            captured["url"] = url
            captured["kwargs"] = kwargs
            return _TokenCtx(
                captured,
                {"token": "t", "expires": 32503680000000},
            )

    monkeypatch.setenv("RESTGDF_TIMEOUT_SECONDS", "12.5")
    reset_settings_cache()
    try:
        token_session = ArcGISTokenSession(
            session=_FakeTokenSession(),  # type: ignore[arg-type]
            credentials=AGOLUserPass(username="u", password="p"),
        )
        await token_session.update_token()
    finally:
        reset_settings_cache()

    _assert_timeout_kwarg(captured["kwargs"], 12.5)


@pytest.mark.asyncio
async def test_get_unique_values_forwards_timeout():
    from restgdf.utils._stats import get_unique_values

    session = _RecordingSession({"features": []})
    await get_unique_values(
        "https://example.com/service/0",
        "NAME",
        session,  # type: ignore[arg-type]
    )
    assert len(session.post_calls) == 1
    _assert_timeout_kwarg(session.post_calls[0][1], 30.0)


@pytest.mark.asyncio
async def test_get_value_counts_forwards_timeout():
    pytest.importorskip("pandas")
    from restgdf.utils._stats import get_value_counts

    session = _RecordingSession({"features": []})
    await get_value_counts(
        "https://example.com/service/0",
        "NAME",
        session,  # type: ignore[arg-type]
    )
    assert len(session.post_calls) == 1
    _assert_timeout_kwarg(session.post_calls[0][1], 30.0)


@pytest.mark.asyncio
async def test_nested_count_forwards_timeout():
    pytest.importorskip("pandas")
    from restgdf.utils._stats import nested_count

    session = _RecordingSession({"features": []})
    await nested_count(
        "https://example.com/service/0",
        ["A", "B"],
        session,  # type: ignore[arg-type]
    )
    assert len(session.post_calls) == 1
    _assert_timeout_kwarg(session.post_calls[0][1], 30.0)


@pytest.mark.asyncio
async def test_get_sub_features_forwards_timeout():
    """BL-02 completion: ``_get_sub_features`` (getgdf.py) forwards timeout."""
    from restgdf.utils.getgdf import _get_sub_features

    session = _RecordingSession({"features": [], "exceededTransferLimit": False})
    await _get_sub_features(
        "https://example.com/service/0",
        session,  # type: ignore[arg-type]
        {"where": "1=1", "outFields": "*", "f": "json"},
    )
    assert len(session.post_calls) == 1
    _assert_timeout_kwarg(session.post_calls[0][1], 30.0)


@pytest.mark.asyncio
async def test_get_sub_gdf_forwards_timeout(monkeypatch):
    """BL-02 completion: ``get_sub_gdf`` (getgdf.py) forwards timeout."""
    pytest.importorskip("pyogrio")
    import restgdf.utils.getgdf as getgdf_mod

    class _GdfResponse(_FakeResponse):
        async def text(self) -> str:
            return "{}"

    class _TextRecordingSession(_RecordingSession):
        async def post(self, url: str, **kwargs: Any) -> _GdfResponse:
            self.post_calls.append((url, kwargs))
            return _GdfResponse(self._payload)

    monkeypatch.setattr(getgdf_mod, "_require_geo_query_support", lambda feature: None)
    monkeypatch.setattr(getgdf_mod, "_get_supported_drivers", lambda: {"GeoJSON": "rw"})
    monkeypatch.setattr(getgdf_mod, "read_file", lambda *a, **kw: "sentinel")

    session = _TextRecordingSession({"features": []})
    await getgdf_mod.get_sub_gdf(
        "https://example.com/service/0",
        session,  # type: ignore[arg-type]
        {"where": "1=1", "outFields": "*", "f": "json"},
    )
    assert len(session.post_calls) == 1
    _assert_timeout_kwarg(session.post_calls[0][1], 30.0)


@pytest.mark.asyncio
async def test_arcgis_token_session_get_defaults_timeout():
    """BL-02 completion: ``ArcGISTokenSession.get`` defaults timeout kwarg."""
    from restgdf.utils.token import ArcGISTokenSession

    inner = _RecordingSession({"ok": True})
    ts = ArcGISTokenSession(
        session=inner,  # type: ignore[arg-type]
        token="existing",
        expires=32503680000000,
    )
    await ts.get("https://example.com/service/0")
    assert len(inner.get_calls) == 1
    _assert_timeout_kwarg(inner.get_calls[0][1], 30.0)


@pytest.mark.asyncio
async def test_arcgis_token_session_post_defaults_timeout():
    """BL-02 completion: ``ArcGISTokenSession.post`` defaults timeout kwarg."""
    from restgdf.utils.token import ArcGISTokenSession

    inner = _RecordingSession({"ok": True})
    ts = ArcGISTokenSession(
        session=inner,  # type: ignore[arg-type]
        token="existing",
        expires=32503680000000,
    )
    await ts.post("https://example.com/service/0", data={"f": "json"})
    assert len(inner.post_calls) == 1
    _assert_timeout_kwarg(inner.post_calls[0][1], 30.0)


@pytest.mark.asyncio
async def test_arcgis_token_session_get_respects_caller_timeout():
    """Explicit caller timeouts must override the default (regression guard)."""
    from restgdf.utils.token import ArcGISTokenSession

    inner = _RecordingSession({"ok": True})
    ts = ArcGISTokenSession(
        session=inner,  # type: ignore[arg-type]
        token="existing",
        expires=32503680000000,
    )
    caller_timeout = aiohttp.ClientTimeout(total=1.25)
    await ts.get("https://example.com/service/0", timeout=caller_timeout)
    assert len(inner.get_calls) == 1
    assert inner.get_calls[0][1].get("timeout") is caller_timeout


def test_default_timeout_ignores_namespace_that_lacks_timeout_attr():
    """Guardrail: if a caller passes a non-Settings object, we still read attr.

    This pins the contract that ``default_timeout`` accesses
    ``timeout_seconds`` by attribute, matching ``Settings``' surface.
    """
    from restgdf.utils._http import default_timeout

    fake = SimpleNamespace(timeout_seconds=2.0)
    result = default_timeout(fake)  # type: ignore[arg-type]
    assert result.total == pytest.approx(2.0)
