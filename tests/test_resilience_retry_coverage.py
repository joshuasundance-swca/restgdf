"""Behavioral coverage tests for ``restgdf.resilience._retry`` (v3-followup T1).

These tests complement :mod:`tests.test_resilience_retry` by exercising
previously-uncovered branches:

* ``_ResponseCtx`` shim (async-context + attribute delegation)
* ``ResilientSession.close`` / ``.post`` / ``._reset_limiters``
* limiter-backed construction and acquire
* ``ServerTimeoutError`` retry + exhaustion paths
* 429 exhaustion → :class:`RateLimitError` with ``retry_after``
* 429 cooldown -> subsequent retry reuses cooldown wait path
"""

from __future__ import annotations

from typing import Any

import aiohttp
import pytest

from restgdf._config import ResilienceConfig
from restgdf.errors import (
    RateLimitError,
    RestgdfTimeoutError,
    TransportError,
)
from restgdf.resilience import ResilientSession
from restgdf.resilience._limiter import CooldownRegistry
from restgdf.resilience._retry import _ResponseCtx, _do_retried_request, _enter_request


# ---------------------------------------------------------------------------
# Stubs (mirrors patterns in tests/test_resilience_retry.py)
# ---------------------------------------------------------------------------


class _FakeResponse:
    """Minimal response stub supporting async-context use."""

    def __init__(
        self,
        status: int,
        headers: dict[str, str] | None = None,
        body: bytes = b"ok",
    ) -> None:
        self.status = status
        self.headers = headers or {}
        self._body = body

    async def read(self) -> bytes:
        return self._body

    async def __aenter__(self) -> _FakeResponse:
        return self

    async def __aexit__(self, *args: Any) -> None:
        pass


class StubSession:
    """AsyncHTTPSession stub recording calls and replaying queued outcomes."""

    def __init__(
        self,
        responses: list[_FakeResponse | Exception] | None = None,
    ) -> None:
        self._responses = list(responses or [])
        self._call_count = 0
        self._closed = False
        self._last_method: str | None = None

    @property
    def closed(self) -> bool:
        return self._closed

    async def close(self) -> None:
        self._closed = True

    def get(self, url: str, **kwargs: Any) -> Any:
        self._last_method = "get"
        return self._dispatch(url)

    def post(self, url: str, **kwargs: Any) -> Any:
        self._last_method = "post"
        return self._dispatch(url)

    def _dispatch(self, url: str) -> Any:
        self._call_count += 1
        idx = min(self._call_count - 1, len(self._responses) - 1)
        resp = self._responses[idx]
        if isinstance(resp, Exception):
            raise resp
        return resp


def _make_server_timeout() -> aiohttp.ServerTimeoutError:
    return aiohttp.ServerTimeoutError("simulated read timeout")


@pytest.fixture()
def _fast_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    """Patch ``asyncio.sleep`` so retry tests do not actually wait."""

    async def _instant_sleep(_d: float, *a: Any, **kw: Any) -> None:
        return None

    monkeypatch.setattr("asyncio.sleep", _instant_sleep)


# ---------------------------------------------------------------------------
# _ResponseCtx shim
# ---------------------------------------------------------------------------


class TestResponseCtx:
    """_ResponseCtx must behave like an async CM and proxy attributes."""

    @pytest.mark.asyncio
    async def test_async_context_yields_underlying_response(self) -> None:
        resp = _FakeResponse(200, body=b"hello")
        ctx = _ResponseCtx(resp)
        async with ctx as entered:
            assert entered is resp
            assert await entered.read() == b"hello"

    @pytest.mark.asyncio
    async def test_aexit_is_noop_and_does_not_close_response(self) -> None:
        resp = _FakeResponse(200)
        ctx = _ResponseCtx(resp)
        await ctx.__aenter__()
        await ctx.__aexit__(None, None, None)
        # Attribute still accessible — proves no teardown happened.
        assert ctx.status == 200

    def test_getattr_delegates_to_wrapped_response(self) -> None:
        resp = _FakeResponse(418, headers={"X-Flavor": "tea"})
        ctx = _ResponseCtx(resp)
        # Both exercise __getattr__ (attr not in __slots__).
        assert ctx.status == 418
        assert ctx.headers == {"X-Flavor": "tea"}

    @pytest.mark.asyncio
    async def test_retried_context_manager_forwards_aexit(self) -> None:
        exited = False

        class _Ctx:
            async def __aenter__(self) -> _FakeResponse:
                return _FakeResponse(200)

            async def __aexit__(self, *args: Any) -> None:
                nonlocal exited
                exited = True

        class _Inner(StubSession):
            def get(self, url: str, **kwargs: Any) -> Any:
                return _Ctx()

        session = ResilientSession(
            inner=_Inner(),
            config=ResilienceConfig(enabled=True),
        )

        async with session.get("http://test/query") as resp:
            assert resp.status == 200

        assert exited is True


class TestEnterRequest:
    @pytest.mark.asyncio
    async def test_awaitable_response_is_wrapped_in_response_ctx(self) -> None:
        class _AwaitableResponse(_FakeResponse):
            def __await__(self):
                async def _resolve() -> _AwaitableResponse:
                    return self

                return _resolve().__await__()

        resp = _AwaitableResponse(200, body=b"awaited")

        ctx, entered = await _enter_request(resp)

        assert isinstance(ctx, _ResponseCtx)
        assert entered is resp

    @pytest.mark.asyncio
    async def test_plain_response_is_wrapped_in_response_ctx(self) -> None:
        class _PlainResponse:
            status = 204

        plain = _PlainResponse()

        ctx, entered = await _enter_request(plain)

        assert isinstance(ctx, _ResponseCtx)
        assert entered is plain


# ---------------------------------------------------------------------------
# ResilientSession lifecycle / delegation
# ---------------------------------------------------------------------------


class TestSessionLifecycle:
    @pytest.mark.asyncio
    async def test_close_delegates_to_inner(self) -> None:
        stub = StubSession([_FakeResponse(200)])
        session = ResilientSession(inner=stub, config=ResilienceConfig(enabled=True))
        assert session.closed is False
        await session.close()
        assert stub._closed is True
        assert session.closed is True

    @pytest.mark.asyncio
    async def test_post_is_retried_like_get(self, _fast_sleep: None) -> None:
        stub = StubSession(
            [
                _FakeResponse(503),
                _FakeResponse(200, body=b"posted"),
            ],
        )
        session = ResilientSession(inner=stub, config=ResilienceConfig(enabled=True))
        async with session.post("http://test/query") as resp:
            body = await resp.read()
        assert body == b"posted"
        assert stub._call_count == 2
        assert stub._last_method == "post"

    @pytest.mark.asyncio
    async def test_post_bypasses_retry_when_disabled(self) -> None:
        stub = StubSession([_FakeResponse(200, body=b"direct")])
        session = ResilientSession(inner=stub, config=ResilienceConfig(enabled=False))
        async with session.post("http://test/query") as resp:
            body = await resp.read()
        assert body == b"direct"
        assert stub._call_count == 1
        assert stub._last_method == "post"

    @pytest.mark.asyncio
    async def test_get_bypasses_retry_when_disabled(self) -> None:
        stub = StubSession([_FakeResponse(200, body=b"direct")])
        session = ResilientSession(inner=stub, config=ResilienceConfig(enabled=False))
        async with session.get("http://test/query") as resp:
            body = await resp.read()
        assert body == b"direct"
        assert stub._call_count == 1
        assert stub._last_method == "get"


# ---------------------------------------------------------------------------
# Limiter wiring
# ---------------------------------------------------------------------------


class TestLimiterWiring:
    def test_constructs_limiter_registry_when_rate_configured(self) -> None:
        stub = StubSession([_FakeResponse(200)])
        session = ResilientSession(
            inner=stub,
            config=ResilienceConfig(
                enabled=True,
                rate_per_service_root_per_second=50.0,
            ),
        )
        assert session._limiter is not None

    def test_no_limiter_when_rate_unset(self) -> None:
        stub = StubSession([_FakeResponse(200)])
        session = ResilientSession(inner=stub, config=ResilienceConfig(enabled=True))
        assert session._limiter is None

    @pytest.mark.asyncio
    async def test_request_acquires_token_from_limiter(
        self,
        _fast_sleep: None,
    ) -> None:
        stub = StubSession([_FakeResponse(200)])
        session = ResilientSession(
            inner=stub,
            config=ResilienceConfig(
                enabled=True,
                rate_per_service_root_per_second=100.0,
            ),
        )
        async with session.get(
            "http://host/rest/services/X/FeatureServer/0/query",
        ) as resp:
            await resp.read()
        # A limiter for this service root must have been created/used.
        assert session._limiter is not None
        assert session._limiter._limiters, "limiter cache should be populated"

    @pytest.mark.asyncio
    async def test_reset_limiters_clears_state(self, _fast_sleep: None) -> None:
        stub = StubSession(
            [
                _FakeResponse(429, {"Retry-After": "0"}),
                _FakeResponse(200),
            ],
        )
        session = ResilientSession(
            inner=stub,
            config=ResilienceConfig(
                enabled=True,
                rate_per_service_root_per_second=100.0,
            ),
        )
        async with session.get(
            "http://host/rest/services/X/FeatureServer/0/query",
        ) as resp:
            await resp.read()
        assert session._limiter is not None
        assert session._limiter._limiters

        session._reset_limiters()

        assert session._limiter._limiters == {}
        # Cooldown registry should be a fresh instance with no deadlines.
        assert session._cooldown._deadlines == {}

    def test_reset_limiters_safe_without_limiter(self) -> None:
        stub = StubSession([_FakeResponse(200)])
        session = ResilientSession(inner=stub, config=ResilienceConfig(enabled=True))
        # Should be a no-op, not raise.
        session._reset_limiters()
        assert session._limiter is None


# ---------------------------------------------------------------------------
# ServerTimeoutError retry path
# ---------------------------------------------------------------------------


class TestServerTimeout:
    @pytest.mark.asyncio
    async def test_server_timeout_is_retried_then_succeeds(
        self,
        _fast_sleep: None,
    ) -> None:
        stub = StubSession(
            [
                _make_server_timeout(),
                _FakeResponse(200, body=b"recovered"),
            ],
        )
        session = ResilientSession(inner=stub, config=ResilienceConfig(enabled=True))
        async with session.get("http://test/query") as resp:
            body = await resp.read()
        assert body == b"recovered"
        assert stub._call_count == 2

    @pytest.mark.asyncio
    async def test_server_timeout_exhaustion_raises_timeout_error(
        self,
        _fast_sleep: None,
    ) -> None:
        stub = StubSession([_make_server_timeout()] * 10)
        session = ResilientSession(inner=stub, config=ResilienceConfig(enabled=True))
        with pytest.raises(RestgdfTimeoutError) as exc_info:
            async with session.get("http://test/query") as resp:
                await resp.read()
        assert exc_info.value.timeout_kind == "read"
        assert stub._call_count == 5


# ---------------------------------------------------------------------------
# 429 exhaustion + cooldown
# ---------------------------------------------------------------------------


class TestRateLimitExhaustion:
    @pytest.mark.asyncio
    async def test_persistent_429_raises_rate_limit_with_retry_after(
        self,
        _fast_sleep: None,
    ) -> None:
        stub = StubSession(
            [_FakeResponse(429, {"Retry-After": "3"})] * 10,
        )
        session = ResilientSession(inner=stub, config=ResilienceConfig(enabled=True))
        with pytest.raises(RateLimitError) as exc_info:
            async with session.get("http://test/query") as resp:
                await resp.read()
        assert exc_info.value.status_code == 429
        assert exc_info.value.retry_after == pytest.approx(3.0)
        assert stub._call_count == 5

    @pytest.mark.asyncio
    async def test_429_sets_cooldown_then_waits_on_next_attempt(
        self,
        _fast_sleep: None,
    ) -> None:
        # First call returns 429 with a small Retry-After, then success.
        # The cooldown set on the 1st 429 will be checked by
        # ``wait_if_cooling`` on the retry — exercising line 159.
        stub = StubSession(
            [
                _FakeResponse(429, {"Retry-After": "1"}),
                _FakeResponse(200, body=b"after-cooldown"),
            ],
        )
        session = ResilientSession(inner=stub, config=ResilienceConfig(enabled=True))
        async with session.get(
            "http://host/rest/services/X/FeatureServer/0/query",
        ) as resp:
            body = await resp.read()
        assert body == b"after-cooldown"
        assert stub._call_count == 2

    @pytest.mark.asyncio
    async def test_retry_after_invalid_header_uses_fallback_cooldown(
        self,
        _fast_sleep: None,
    ) -> None:
        class _CooldownSpy(CooldownRegistry):
            def __init__(self) -> None:
                super().__init__()
                self.wait_keys: list[str] = []
                self.set_calls: list[tuple[str, float]] = []

            async def wait_if_cooling(self, key: str) -> None:
                self.wait_keys.append(key)

            def set_cooldown(self, key: str, seconds: float) -> None:
                self.set_calls.append((key, seconds))

        stub = StubSession(
            [
                _FakeResponse(429, {"Retry-After": "not-a-number"}),
                _FakeResponse(200, body=b"ok"),
            ],
        )
        cooldown = _CooldownSpy()

        ctx, resp = await _do_retried_request(
            stub,
            ResilienceConfig(enabled=True, fallback_retry_after_seconds=7.5),
            "get",
            "http://host/rest/services/X/FeatureServer/0/query",
            {},
            cooldown=cooldown,
        )

        assert resp.status == 200
        assert cooldown.wait_keys == ["http://host/rest/services/X/FeatureServer"] * 2
        assert cooldown.set_calls == [
            ("http://host/rest/services/X/FeatureServer", 7.5),
        ]
        await ctx.__aexit__(None, None, None)

    @pytest.mark.asyncio
    async def test_retry_after_is_capped_before_setting_cooldown(
        self,
        _fast_sleep: None,
    ) -> None:
        class _CooldownSpy(CooldownRegistry):
            def __init__(self) -> None:
                super().__init__()
                self.set_calls: list[tuple[str, float]] = []

            async def wait_if_cooling(self, key: str) -> None:
                return None

            def set_cooldown(self, key: str, seconds: float) -> None:
                self.set_calls.append((key, seconds))

        stub = StubSession(
            [
                _FakeResponse(429, {"Retry-After": "120"}),
                _FakeResponse(200, body=b"ok"),
            ],
        )
        cooldown = _CooldownSpy()

        ctx, resp = await _do_retried_request(
            stub,
            ResilienceConfig(enabled=True, respect_retry_after_max_s=4.0),
            "get",
            "http://host/rest/services/X/FeatureServer/0/query",
            {},
            cooldown=cooldown,
        )

        assert resp.status == 200
        assert cooldown.set_calls == [
            ("http://host/rest/services/X/FeatureServer", 4.0),
        ]
        await ctx.__aexit__(None, None, None)


# ---------------------------------------------------------------------------
# ClientConnectorError still maps to TransportError (defensive regression)
# ---------------------------------------------------------------------------


class TestConnectorErrorMapping:
    @pytest.mark.asyncio
    async def test_connector_error_exhaustion_raises_transport_error(
        self,
        _fast_sleep: None,
    ) -> None:
        exc = aiohttp.ClientConnectorError(
            connection_key=None,
            os_error=OSError("dns fail"),
        )
        stub = StubSession([exc] * 10)
        session = ResilientSession(inner=stub, config=ResilienceConfig(enabled=True))
        with pytest.raises(TransportError):
            async with session.get("http://test/query") as resp:
                await resp.read()
        assert stub._call_count == 5
