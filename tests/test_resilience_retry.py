"""Red tests for ResilientSession retry wrapper (BL-31, commit 1)."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock

import aiohttp
import pytest
import stamina

from restgdf._client._protocols import AsyncHTTPSession
from restgdf._config import ResilienceConfig
from restgdf.errors import (
    RateLimitError,
    RestgdfResponseError,
    RestgdfTimeoutError,
    TransportError,
)
from restgdf.resilience import ResilientSession


# ---------------------------------------------------------------------------
# Stubs
# ---------------------------------------------------------------------------

class _FakeResponse:
    """Minimal response stub."""

    def __init__(self, status: int, headers: dict[str, str] | None = None, body: bytes = b"ok") -> None:
        self.status = status
        self.headers = headers or {}
        self._body = body

    async def read(self) -> bytes:
        return self._body

    async def json(self, **kw: Any) -> dict[str, Any]:
        return {"status": "ok"}

    async def __aenter__(self) -> "_FakeResponse":
        return self

    async def __aexit__(self, *args: Any) -> None:
        pass

    def raise_for_status(self) -> None:
        if self.status >= 400:
            raise aiohttp.ClientResponseError(
                request_info=aiohttp.RequestInfo(
                    url=yarl.URL("http://test"),
                    method="GET",
                    headers={},
                    real_url=yarl.URL("http://test"),
                ),
                history=(),
                status=self.status,
                headers=self.headers,
            )


import yarl  # noqa: E402 (grouped with stub)


class StubSession:
    """Minimal AsyncHTTPSession stub with call counting."""

    def __init__(self, responses: list[_FakeResponse | Exception] | None = None) -> None:
        self._responses = list(responses or [])
        self._call_count = 0
        self._closed = False

    @property
    def closed(self) -> bool:
        return self._closed

    async def close(self) -> None:
        self._closed = True

    def get(self, url: str, **kwargs: Any) -> Any:
        return self._dispatch(url)

    def post(self, url: str, **kwargs: Any) -> Any:
        return self._dispatch(url)

    def _dispatch(self, url: str) -> Any:
        self._call_count += 1
        idx = min(self._call_count - 1, len(self._responses) - 1)
        resp = self._responses[idx]
        if isinstance(resp, Exception):
            raise resp
        return resp


# ---------------------------------------------------------------------------
# Fast fixture: stamina inactive (call-count tests)
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=False)
def _stamina_inactive() -> Any:
    stamina.set_active(False)
    yield
    stamina.set_active(True)


class TestRetryFastFixture:
    """Tests using stamina.set_active(False)."""

    @pytest.fixture(autouse=True)
    def _disable_stamina(self, _stamina_inactive: Any) -> None:
        pass

    @pytest.mark.asyncio
    async def test_retry_disabled_by_default_no_extra_calls(self) -> None:
        stub = StubSession([Exception("fail")])
        session = ResilientSession(inner=stub, config=ResilienceConfig(enabled=False))
        with pytest.raises(Exception):
            async with session.get("http://test/query") as resp:
                await resp.read()
        assert stub._call_count == 1

    @pytest.mark.asyncio
    async def test_retry_stops_after_max_attempts(self) -> None:
        exc = aiohttp.ClientConnectorError(
            connection_key=aiohttp.connector.ConnectionKey(
                host="test", port=80, is_ssl=False, ssl=None,
                proxy=None, proxy_auth=None, proxy_headers_hash=None,
            ),
            os_error=OSError("DNS failed"),
        )
        stub = StubSession([exc] * 10)
        session = ResilientSession(
            inner=stub, config=ResilienceConfig(enabled=True)
        )
        with pytest.raises(TransportError):
            async with session.get("http://test/query") as resp:
                await resp.read()
        assert stub._call_count == 5

    @pytest.mark.asyncio
    async def test_retry_triggers_on_429_and_503(self) -> None:
        stub = StubSession([
            _FakeResponse(429, {"Retry-After": "0"}),
            _FakeResponse(503),
            _FakeResponse(200),
        ])
        session = ResilientSession(
            inner=stub, config=ResilienceConfig(enabled=True)
        )
        async with session.get("http://test/query") as resp:
            body = await resp.read()
        assert stub._call_count == 3

    @pytest.mark.asyncio
    async def test_retry_stops_on_total_delay_cap(self) -> None:
        exc = aiohttp.ClientConnectorError(
            connection_key=aiohttp.connector.ConnectionKey(
                host="test", port=80, is_ssl=False, ssl=None,
                proxy=None, proxy_auth=None, proxy_headers_hash=None,
            ),
            os_error=OSError("timeout"),
        )
        stub = StubSession([exc] * 100)
        session = ResilientSession(
            inner=stub, config=ResilienceConfig(enabled=True)
        )
        with pytest.raises(TransportError):
            async with session.get("http://test/query") as resp:
                await resp.read()

    @pytest.mark.asyncio
    async def test_retry_never_triggers_on_4xx_non_429(self) -> None:
        stub = StubSession([_FakeResponse(400)])
        session = ResilientSession(
            inner=stub, config=ResilienceConfig(enabled=True)
        )
        with pytest.raises(RestgdfResponseError):
            async with session.get("http://test/query") as resp:
                await resp.read()
        assert stub._call_count == 1

    @pytest.mark.asyncio
    async def test_retry_never_triggers_on_5xx_after_exhaustion_raises_response_error(self) -> None:
        stub = StubSession([_FakeResponse(503)] * 10)
        session = ResilientSession(
            inner=stub, config=ResilienceConfig(enabled=True)
        )
        with pytest.raises(RestgdfResponseError) as exc_info:
            async with session.get("http://test/query") as resp:
                await resp.read()
        assert exc_info.value.status_code == 503
        assert stub._call_count == 5

    def test_resilient_session_satisfies_async_http_session_protocol(self) -> None:
        stub = StubSession([_FakeResponse(200)])
        session = ResilientSession(inner=stub, config=ResilienceConfig())
        assert isinstance(session, AsyncHTTPSession)

    @pytest.mark.asyncio
    async def test_resilient_session_pass_through_when_disabled(self) -> None:
        stub = StubSession([_FakeResponse(200)])
        session = ResilientSession(inner=stub, config=ResilienceConfig(enabled=False))
        async with session.get("http://test/query") as resp:
            body = await resp.read()
        assert body == b"ok"
        assert stub._call_count == 1


class TestRetryStaminaActive:
    """Jitter test — stamina active."""

    @pytest.mark.asyncio
    async def test_retry_enabled_stamina_jitter_observed(self) -> None:
        call_count = 0
        delays: list[float] = []
        orig_sleep = asyncio.sleep

        async def _patched_sleep(d: float, *a: Any, **kw: Any) -> None:
            delays.append(d)
            # don't actually sleep; just record
            return None

        exc = aiohttp.ClientConnectorError(
            connection_key=aiohttp.connector.ConnectionKey(
                host="test", port=80, is_ssl=False, ssl=None,
                proxy=None, proxy_auth=None, proxy_headers_hash=None,
            ),
            os_error=OSError("transient"),
        )

        class _FlakyStub(StubSession):
            def _dispatch(self, url: str) -> Any:
                self._call_count += 1
                if self._call_count < 3:
                    raise exc
                return _FakeResponse(200)

        stub = _FlakyStub()
        session = ResilientSession(inner=stub, config=ResilienceConfig(enabled=True))
        import unittest.mock
        with unittest.mock.patch("asyncio.sleep", side_effect=_patched_sleep):
            async with session.get("http://test/query") as resp:
                await resp.read()
        assert stub._call_count >= 3
        assert any(d > 0 for d in delays)
