"""Tests for :func:`restgdf.utils._http.default_timeout` (BL-02).

Verifies that the helper resolves against ``Settings.timeout_seconds``
(float, default ``30.0``) and that every library-side ``session.get`` /
``session.post`` call-site in scope forwards a matching
:class:`aiohttp.ClientTimeout`.

Scope: BL-02 only. ``restgdf/utils/getgdf.py`` is deliberately excluded
from the call-site inventory per the phase-1b scope lock (R-47 /
forbidden-token grep).
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


def test_default_timeout_ignores_namespace_that_lacks_timeout_attr():
    """Guardrail: if a caller passes a non-Settings object, we still read attr.

    This pins the contract that ``default_timeout`` accesses
    ``timeout_seconds`` by attribute, matching ``Settings``' surface.
    """
    from restgdf.utils._http import default_timeout

    fake = SimpleNamespace(timeout_seconds=2.0)
    result = default_timeout(fake)  # type: ignore[arg-type]
    assert result.total == pytest.approx(2.0)
