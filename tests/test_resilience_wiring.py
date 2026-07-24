"""Config-wiring tests for the resilience executor (3.3.0 lane IMPL-2).

Covers the two additive, default-preserving wirings that finish restgdf's
declared "wire ResilienceConfig fully" debt:

* **R1** — ``ResilienceConfig.limiter_key`` selects the rate-limit / 429-cooldown
  key granularity (``"service_root"`` default vs ``"host"``); the token bucket
  and the cooldown share the SAME selected key (politeness decision D1).
* **R2** — the stamina executor reads ``max_attempts`` / ``retry_budget_s`` /
  ``wait_initial_s`` / ``wait_max_s`` / ``wait_jitter_s`` from the config it
  already receives, instead of hardcoded literals. Defaults preserve the old
  policy byte-for-byte and ``ResilienceConfig.enabled`` stays the sole gate.

These are additive with behaviour-preserving defaults, so tests ship alongside
the code (no red-first flip required).
"""

from __future__ import annotations

from typing import Any

import aiohttp
import pytest
import stamina

from restgdf._config import ResilienceConfig
from restgdf.errors import TransportError
from restgdf.resilience import ResilientSession
from restgdf.resilience._limiter import CooldownRegistry
from restgdf.resilience._retry import _do_retried_request


# ---------------------------------------------------------------------------
# Stubs
# ---------------------------------------------------------------------------


class _FakeResponse:
    """Minimal response stub supporting async-context use."""

    def __init__(self, status: int, headers: dict[str, str] | None = None) -> None:
        self.status = status
        self.headers = headers or {}

    async def read(self) -> bytes:
        return b"ok"

    async def __aenter__(self) -> _FakeResponse:
        return self

    async def __aexit__(self, *args: Any) -> None:
        pass


class StubSession:
    """AsyncHTTPSession stub replaying queued responses/exceptions."""

    def __init__(
        self,
        responses: list[_FakeResponse | Exception] | None = None,
    ) -> None:
        self._responses = list(responses or [])
        self._call_count = 0
        self._closed = False

    @property
    def closed(self) -> bool:
        return self._closed

    async def close(self) -> None:
        self._closed = True

    def get(self, url: str, **kwargs: Any) -> Any:
        return self._dispatch()

    def post(self, url: str, **kwargs: Any) -> Any:
        return self._dispatch()

    def _dispatch(self) -> Any:
        self._call_count += 1
        idx = min(self._call_count - 1, len(self._responses) - 1)
        resp = self._responses[idx]
        if isinstance(resp, Exception):
            raise resp
        return resp


class _CooldownSpy(CooldownRegistry):
    """Records the keys passed to wait/set without doing real waits."""

    def __init__(self) -> None:
        super().__init__()
        self.wait_keys: list[str] = []
        self.set_calls: list[tuple[str, float]] = []

    async def wait_if_cooling(self, key: str) -> None:
        self.wait_keys.append(key)

    def set_cooldown(self, key: str, seconds: float) -> None:
        self.set_calls.append((key, seconds))


@pytest.fixture()
def _fast_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    """Patch ``asyncio.sleep`` so retry tests do not actually wait."""

    async def _instant_sleep(_d: float, *a: Any, **kw: Any) -> None:
        return None

    monkeypatch.setattr("asyncio.sleep", _instant_sleep)


_URL_A = "http://host/rest/services/A/FeatureServer/0/query"
_URL_B = "http://host/rest/services/B/FeatureServer/0/query"


# ---------------------------------------------------------------------------
# R1 — limiter_key granularity: token-bucket keying
# ---------------------------------------------------------------------------


class TestLimiterKeyBucketing:
    @pytest.mark.asyncio
    async def test_service_root_default_keys_per_service(
        self,
        _fast_sleep: None,
    ) -> None:
        stub = StubSession([_FakeResponse(200)] * 4)
        session = ResilientSession(
            inner=stub,
            config=ResilienceConfig(
                enabled=True,
                rate_per_service_root_per_second=100.0,
            ),
        )
        for url in (_URL_A, _URL_B):
            async with session.get(url) as resp:
                await resp.read()
        assert session._limiter is not None
        assert set(session._limiter._limiters) == {
            "http://host/rest/services/A/FeatureServer",
            "http://host/rest/services/B/FeatureServer",
        }

    @pytest.mark.asyncio
    async def test_host_granularity_shares_one_bucket_across_services(
        self,
        _fast_sleep: None,
    ) -> None:
        stub = StubSession([_FakeResponse(200)] * 4)
        session = ResilientSession(
            inner=stub,
            config=ResilienceConfig(
                enabled=True,
                rate_per_service_root_per_second=100.0,
                limiter_key="host",
            ),
        )
        for url in (_URL_A, _URL_B):
            async with session.get(url) as resp:
                await resp.read()
        assert session._limiter is not None
        # Both services on the same host collapse to a single host bucket.
        assert set(session._limiter._limiters) == {"http://host"}


# ---------------------------------------------------------------------------
# R1 — limiter_key granularity: 429 cooldown keying follows the same selector
# ---------------------------------------------------------------------------


class TestCooldownKeyGranularity:
    @pytest.mark.asyncio
    async def test_service_root_default_cools_per_service(
        self,
        _fast_sleep: None,
    ) -> None:
        stub = StubSession(
            [_FakeResponse(429, {"Retry-After": "1"}), _FakeResponse(200)],
        )
        cooldown = _CooldownSpy()
        ctx, resp = await _do_retried_request(
            stub,
            ResilienceConfig(enabled=True),
            "get",
            _URL_A,
            {},
            cooldown=cooldown,
        )
        assert resp.status == 200
        assert cooldown.set_calls == [
            ("http://host/rest/services/A/FeatureServer", 1.0),
        ]
        assert (
            cooldown.wait_keys
            == [
                "http://host/rest/services/A/FeatureServer",
            ]
            * 2
        )
        await ctx.__aexit__(None, None, None)

    @pytest.mark.asyncio
    async def test_host_granularity_cools_per_host(
        self,
        _fast_sleep: None,
    ) -> None:
        stub = StubSession(
            [_FakeResponse(429, {"Retry-After": "1"}), _FakeResponse(200)],
        )
        cooldown = _CooldownSpy()
        ctx, resp = await _do_retried_request(
            stub,
            ResilienceConfig(enabled=True, limiter_key="host"),
            "get",
            _URL_A,
            {},
            cooldown=cooldown,
        )
        assert resp.status == 200
        # Cooldown keys on the host, matching the bucket granularity (D1).
        assert cooldown.set_calls == [("http://host", 1.0)]
        assert cooldown.wait_keys == ["http://host"] * 2
        await ctx.__aexit__(None, None, None)


# ---------------------------------------------------------------------------
# R2 — retry knobs read from config
# ---------------------------------------------------------------------------


def _capture_retry_context(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Spy on ``stamina.retry_context`` kwargs while keeping real behaviour."""
    captured: dict[str, Any] = {}
    real = stamina.retry_context

    def _spy(**kwargs: Any) -> Any:
        captured.update(kwargs)
        return real(**kwargs)

    monkeypatch.setattr(stamina, "retry_context", _spy)
    return captured


class TestRetryKnobsFromConfig:
    @pytest.mark.asyncio
    async def test_defaults_preserve_hardcoded_policy_byte_for_byte(
        self,
        _fast_sleep: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        captured = _capture_retry_context(monkeypatch)
        stub = StubSession([_FakeResponse(200)])
        session = ResilientSession(inner=stub, config=ResilienceConfig(enabled=True))
        async with session.get(_URL_A) as resp:
            await resp.read()
        assert captured["attempts"] == 5
        assert captured["timeout"] == 60.0
        assert captured["wait_initial"] == 0.5
        assert captured["wait_max"] == 10.0
        assert captured["wait_jitter"] == 1.0

    @pytest.mark.asyncio
    async def test_config_values_flow_into_stamina(
        self,
        _fast_sleep: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        captured = _capture_retry_context(monkeypatch)
        stub = StubSession([_FakeResponse(200)])
        session = ResilientSession(
            inner=stub,
            config=ResilienceConfig(
                enabled=True,
                max_attempts=2,
                retry_budget_s=30.0,
                wait_initial_s=0.1,
                wait_max_s=2.0,
                wait_jitter_s=0.0,
            ),
        )
        async with session.get(_URL_A) as resp:
            await resp.read()
        assert captured["attempts"] == 2
        assert captured["timeout"] == 30.0
        assert captured["wait_initial"] == 0.1
        assert captured["wait_max"] == 2.0
        assert captured["wait_jitter"] == 0.0

    @pytest.mark.asyncio
    async def test_raised_max_attempts_limits_dispatch_count(
        self,
        _fast_sleep: None,
    ) -> None:
        # A behaviour proof (not just kwargs): max_attempts=2 => exactly two
        # dispatches to the inner session before exhaustion maps to TransportError.
        stub = StubSession([aiohttp.ServerDisconnectedError("drop")] * 10)
        session = ResilientSession(
            inner=stub,
            config=ResilienceConfig(enabled=True, max_attempts=2),
        )
        with pytest.raises(TransportError):
            async with session.get(_URL_A) as resp:
                await resp.read()
        assert stub._call_count == 2

    @pytest.mark.asyncio
    async def test_default_max_attempts_still_five(
        self,
        _fast_sleep: None,
    ) -> None:
        # Behaviour-preservation guard: unset max_attempts keeps the historical
        # 5-attempt exhaustion count.
        stub = StubSession([aiohttp.ServerDisconnectedError("drop")] * 10)
        session = ResilientSession(inner=stub, config=ResilienceConfig(enabled=True))
        with pytest.raises(TransportError):
            async with session.get(_URL_A) as resp:
                await resp.read()
        assert stub._call_count == 5
