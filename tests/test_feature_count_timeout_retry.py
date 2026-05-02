"""BL-51: feature_count timeout + bounded retry (inline-only).

Tests for :func:`restgdf.utils.getinfo._feature_count_with_timeout` —
the inline retry wrapper that converts ``asyncio.TimeoutError`` into
:class:`~restgdf.errors.RestgdfTimeoutError`` after bounded retries.
"""

from __future__ import annotations

import asyncio
import re

import pytest
from aiohttp import ClientSession
from aioresponses import aioresponses

from restgdf.errors import RestgdfTimeoutError
from restgdf.utils.getinfo import _feature_count_with_timeout

# T8 (R-74): short count queries now route to GET with a query string,
# so aioresponses needs a regex pattern that matches any `?...` suffix.
_QUERY_URL_RE = re.compile(r"^https://svc\.example/0/query(\?.*)?$")


@pytest.mark.asyncio
async def test_feature_count_timeout_raises_RestgdfTimeoutError():
    """All attempts timeout → RestgdfTimeoutError raised."""
    async with ClientSession() as session:
        with aioresponses() as m:
            m.get(
                _QUERY_URL_RE,
                exception=asyncio.TimeoutError(),
                repeat=True,
            )
            with pytest.raises(RestgdfTimeoutError):
                await _feature_count_with_timeout(
                    session,
                    "https://svc.example/0",
                    None,
                    timeout=0.5,
                    max_attempts=3,
                )


@pytest.mark.asyncio
async def test_feature_count_chains_timeout_cause():
    """RestgdfTimeoutError.__cause__ should be the original TimeoutError."""
    async with ClientSession() as session:
        with aioresponses() as m:
            m.get(
                _QUERY_URL_RE,
                exception=asyncio.TimeoutError(),
                repeat=True,
            )
            with pytest.raises(RestgdfTimeoutError) as exc_info:
                await _feature_count_with_timeout(
                    session,
                    "https://svc.example/0",
                    None,
                    max_attempts=2,
                )
            assert isinstance(
                exc_info.value.__cause__,
                (asyncio.TimeoutError, TimeoutError),
            )


@pytest.mark.asyncio
async def test_feature_count_retries_on_transient_failure():
    """Two failures then success → returns count."""
    async with ClientSession() as session:
        with aioresponses() as m:
            m.get(_QUERY_URL_RE, exception=asyncio.TimeoutError())
            m.get(_QUERY_URL_RE, exception=asyncio.TimeoutError())
            m.get(
                _QUERY_URL_RE,
                payload={"count": 42},
            )
            result = await _feature_count_with_timeout(
                session,
                "https://svc.example/0",
                None,
                max_attempts=3,
            )
            assert result == 42


@pytest.mark.asyncio
async def test_feature_count_single_success_no_retry():
    """First attempt succeeds → no retry, returns count."""
    async with ClientSession() as session:
        with aioresponses() as m:
            m.get(
                _QUERY_URL_RE,
                payload={"count": 100},
            )
            result = await _feature_count_with_timeout(
                session,
                "https://svc.example/0",
                None,
                max_attempts=3,
            )
            assert result == 100


@pytest.mark.asyncio
async def test_feature_count_does_not_retry_on_non_transient():
    """Deterministic failure (e.g., 4xx / RestgdfResponseError) must NOT
    be retried — it propagates on the first attempt (BL-51 narrowing)."""
    from restgdf.errors import RestgdfResponseError

    call_count = {"n": 0}
    original = _feature_count_with_timeout.__globals__["get_feature_count"]

    async def _raising(*args, **kwargs):
        call_count["n"] += 1
        raise RestgdfResponseError("HTTP 400 Bad Request")

    _feature_count_with_timeout.__globals__["get_feature_count"] = _raising
    try:
        async with ClientSession() as session:
            with pytest.raises(RestgdfResponseError):
                await _feature_count_with_timeout(
                    session,
                    "https://svc.example/0",
                    None,
                    max_attempts=3,
                )
        assert (
            call_count["n"] == 1
        ), f"non-transient error retried {call_count['n']} times; expected 1"
    finally:
        _feature_count_with_timeout.__globals__["get_feature_count"] = original


@pytest.mark.asyncio
async def test_feature_count_does_not_retry_on_connection_error():
    """BL-51 narrowing (RD gate-2 round-2 HIGH #1): ClientConnectionError
    is NOT a timeout and must NOT be retried, so real transport failures
    are not silently misreported as ``RestgdfTimeoutError``."""
    from aiohttp import ClientConnectionError

    call_count = {"n": 0}
    original = _feature_count_with_timeout.__globals__["get_feature_count"]

    async def _raising(*args, **kwargs):
        call_count["n"] += 1
        raise ClientConnectionError("connection reset")

    _feature_count_with_timeout.__globals__["get_feature_count"] = _raising
    try:
        async with ClientSession() as session:
            with pytest.raises(ClientConnectionError):
                await _feature_count_with_timeout(
                    session,
                    "https://svc.example/0",
                    None,
                    max_attempts=3,
                )
        assert (
            call_count["n"] == 1
        ), f"ClientConnectionError retried {call_count['n']} times; expected 1"
    finally:
        _feature_count_with_timeout.__globals__["get_feature_count"] = original
