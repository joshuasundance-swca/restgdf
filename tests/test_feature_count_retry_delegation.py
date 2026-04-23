"""BL-51: `_feature_count_with_timeout` delegates retry to the shared
``restgdf.resilience`` module when available, with an inline fallback.

These tests complement ``test_feature_count_timeout_retry.py`` (which
covers the user-visible contract) by verifying the delegation seam:

* When ``_resilience_bounded_retry`` is present, it is invoked.
* When it is absent (simulated by monkeypatching to ``None``), the inline
  loop still runs and preserves the same semantics (timeout retry,
  ClientConnectionError propagation, RestgdfTimeoutError wrapping).
"""

from __future__ import annotations

import asyncio

import pytest
from aiohttp import ClientConnectionError, ClientSession

from restgdf.errors import RestgdfTimeoutError
from restgdf.utils import getinfo
from restgdf.utils.getinfo import _feature_count_with_timeout


@pytest.mark.asyncio
async def test_delegates_to_resilience_when_available(monkeypatch):
    """When ``_resilience_bounded_retry`` is set, it must be invoked."""
    calls: dict[str, object] = {}

    async def _probe(func, *, max_attempts, url):
        calls["invoked"] = True
        calls["max_attempts"] = max_attempts
        calls["url"] = url
        return await func()

    async def _fake_get_feature_count(*args, **kwargs):
        calls["inner_called"] = True
        return 7

    monkeypatch.setattr(getinfo, "_resilience_bounded_retry", _probe)
    monkeypatch.setattr(getinfo, "get_feature_count", _fake_get_feature_count)

    async with ClientSession() as session:
        result = await _feature_count_with_timeout(
            session,
            "https://svc.example/0",
            None,
            max_attempts=4,
        )

    assert result == 7
    assert calls.get("invoked") is True
    assert calls["max_attempts"] == 4
    assert calls["url"] == "https://svc.example/0"
    assert calls.get("inner_called") is True


@pytest.mark.asyncio
async def test_inline_fallback_when_resilience_absent(monkeypatch):
    """With the delegation hook unset, the inline loop handles retries."""
    attempts: list[int] = []

    async def _flaky(*args, **kwargs):
        attempts.append(1)
        if len(attempts) < 3:
            raise asyncio.TimeoutError
        return 11

    monkeypatch.setattr(getinfo, "_resilience_bounded_retry", None)
    monkeypatch.setattr(getinfo, "get_feature_count", _flaky)

    async with ClientSession() as session:
        result = await _feature_count_with_timeout(
            session,
            "https://svc.example/0",
            None,
            max_attempts=3,
        )

    assert result == 11
    assert len(attempts) == 3


@pytest.mark.asyncio
async def test_inline_fallback_preserves_R69_connection_propagation(monkeypatch):
    """Fallback path must propagate ClientConnectionError without retry."""
    attempts: list[int] = []

    async def _raising(*args, **kwargs):
        attempts.append(1)
        raise ClientConnectionError("reset")

    monkeypatch.setattr(getinfo, "_resilience_bounded_retry", None)
    monkeypatch.setattr(getinfo, "get_feature_count", _raising)

    async with ClientSession() as session:
        with pytest.raises(ClientConnectionError):
            await _feature_count_with_timeout(
                session,
                "https://svc.example/0",
                None,
                max_attempts=3,
            )
    assert len(attempts) == 1


@pytest.mark.asyncio
async def test_inline_fallback_wraps_timeout_after_exhaustion(monkeypatch):
    """Fallback path: exhausted timeouts wrap to RestgdfTimeoutError."""

    async def _always_timeout(*args, **kwargs):
        raise asyncio.TimeoutError

    monkeypatch.setattr(getinfo, "_resilience_bounded_retry", None)
    monkeypatch.setattr(getinfo, "get_feature_count", _always_timeout)

    async with ClientSession() as session:
        with pytest.raises(RestgdfTimeoutError) as exc_info:
            await _feature_count_with_timeout(
                session,
                "https://svc.example/0",
                None,
                max_attempts=2,
            )
    assert isinstance(exc_info.value.__cause__, (asyncio.TimeoutError, TimeoutError))


@pytest.mark.asyncio
async def test_delegation_path_propagates_connection_error(monkeypatch):
    """Through the resilience helper, ClientConnectionError must NOT be
    retried or wrapped — it must surface unchanged (R-69)."""
    from restgdf.resilience import bounded_retry_timeout

    attempts: list[int] = []

    async def _raising(*args, **kwargs):
        attempts.append(1)
        raise ClientConnectionError("reset")

    # Use the real helper (not monkeypatched) to prove the contract.
    monkeypatch.setattr(getinfo, "_resilience_bounded_retry", bounded_retry_timeout)
    monkeypatch.setattr(getinfo, "get_feature_count", _raising)

    async with ClientSession() as session:
        with pytest.raises(ClientConnectionError):
            await _feature_count_with_timeout(
                session,
                "https://svc.example/0",
                None,
                max_attempts=3,
            )
    assert len(attempts) == 1


@pytest.mark.asyncio
async def test_delegation_path_wraps_timeout_after_exhaustion(monkeypatch):
    """Through the resilience helper, exhausted timeouts wrap to
    RestgdfTimeoutError with the original timeout as __cause__."""
    from restgdf.resilience import bounded_retry_timeout

    attempts: list[int] = []

    async def _always_timeout(*args, **kwargs):
        attempts.append(1)
        raise asyncio.TimeoutError

    monkeypatch.setattr(getinfo, "_resilience_bounded_retry", bounded_retry_timeout)
    monkeypatch.setattr(getinfo, "get_feature_count", _always_timeout)

    async with ClientSession() as session:
        with pytest.raises(RestgdfTimeoutError) as exc_info:
            await _feature_count_with_timeout(
                session,
                "https://svc.example/0",
                None,
                max_attempts=2,
            )
    assert len(attempts) == 2
    assert isinstance(exc_info.value.__cause__, (asyncio.TimeoutError, TimeoutError))
