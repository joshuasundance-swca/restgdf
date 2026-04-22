"""BL-51: feature_count timeout + bounded retry (inline-only).

Tests for :func:`restgdf.utils.getinfo._feature_count_with_timeout` —
the inline retry wrapper that converts ``asyncio.TimeoutError`` into
:class:`~restgdf.errors.RestgdfTimeoutError`` after bounded retries.
"""

from __future__ import annotations

import asyncio

import pytest
from aiohttp import ClientSession
from aioresponses import aioresponses

from restgdf.errors import RestgdfTimeoutError
from restgdf.utils.getinfo import _feature_count_with_timeout


@pytest.mark.asyncio
async def test_feature_count_timeout_raises_RestgdfTimeoutError():
    """All attempts timeout → RestgdfTimeoutError raised."""
    async with ClientSession() as session:
        with aioresponses() as m:
            m.post(
                "https://svc.example/0/query",
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
            m.post(
                "https://svc.example/0/query",
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
            assert isinstance(exc_info.value.__cause__, (asyncio.TimeoutError, TimeoutError))


@pytest.mark.asyncio
async def test_feature_count_retries_on_transient_failure():
    """Two failures then success → returns count."""
    async with ClientSession() as session:
        with aioresponses() as m:
            m.post("https://svc.example/0/query", exception=asyncio.TimeoutError())
            m.post("https://svc.example/0/query", exception=asyncio.TimeoutError())
            m.post(
                "https://svc.example/0/query",
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
            m.post(
                "https://svc.example/0/query",
                payload={"count": 100},
            )
            result = await _feature_count_with_timeout(
                session,
                "https://svc.example/0",
                None,
                max_attempts=3,
            )
            assert result == 100
