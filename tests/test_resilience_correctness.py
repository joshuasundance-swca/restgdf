"""Correctness tests for resilience core (3.3.0 lane IMPL-1).

Covers four defects surfaced by the H1 adversarial health review, all latent
behind the pre-3.3 all-green suite:

* **H1-M1** — a sub-1.0 rate limit crashed with a raw, unmapped ``ValueError``.
* **H1-M2** — mid-flight server disconnects / connection resets / truncated
  bodies were neither retried nor mapped to a :class:`restgdf.errors.RestgdfError`.
* **H1-N2** — ``CooldownRegistry.wait_if_cooling`` could erase a concurrently-set
  *fresher* 429 cooldown deadline.
* **H1-N4** — the ``restgdf.retry`` logger was dead; no retry/cooldown/mapping
  logging existed despite the tracing recipe promising it.

Red tests land first (``xfail(strict=True)``) then flip green in the fix commit
per the repo's red-first rule.
"""

from __future__ import annotations

import errno
from collections.abc import Callable
from typing import Any

import aiohttp
import pytest

from restgdf._config import ResilienceConfig
from restgdf.errors import RestgdfError, TransportError
from restgdf.resilience import ResilientSession
from restgdf.resilience._limiter import LimiterRegistry


# ---------------------------------------------------------------------------
# Shared stubs (mirror tests/test_resilience_retry.py's harness)
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


@pytest.fixture()
def _fast_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    """Patch ``asyncio.sleep`` so retry tests do not actually wait."""

    async def _instant_sleep(_d: float, *a: Any, **kw: Any) -> None:
        return None

    monkeypatch.setattr("asyncio.sleep", _instant_sleep)


# ---------------------------------------------------------------------------
# H1-M1 — sub-1.0 rate must not crash
# ---------------------------------------------------------------------------

_SVC_URL = "http://host/rest/services/X/FeatureServer/0/query"


class TestSubOneRateLimit:
    def test_rate_ge_one_construction_unchanged(self) -> None:
        # Behaviour-preservation guard: rate >= 1 keeps AsyncLimiter(rate, 1).
        lim = LimiterRegistry(rate_per_second=5.0).get("svc")
        assert lim.max_rate == 5.0
        assert lim.time_period == 1

    def test_sub_one_rate_construction_uses_stretched_period(self) -> None:
        # 0.5 req/s => 1 token every 2 seconds, not AsyncLimiter(0.5, 1).
        lim = LimiterRegistry(rate_per_second=0.5).get("svc")
        assert lim.max_rate == 1
        assert lim.time_period == pytest.approx(2.0)

    @pytest.mark.asyncio
    async def test_sub_one_rate_request_succeeds(self, _fast_sleep: None) -> None:
        stub = StubSession([_FakeResponse(200)])
        session = ResilientSession(
            inner=stub,
            config=ResilienceConfig(
                enabled=True,
                rate_per_service_root_per_second=0.5,
            ),
        )
        async with session.get(_SVC_URL) as resp:
            assert resp.status == 200
        assert stub._call_count == 1


# ---------------------------------------------------------------------------
# H1-M2 — mid-flight transport errors must be retried and mapped
# ---------------------------------------------------------------------------


def _server_disconnected() -> aiohttp.ServerDisconnectedError:
    return aiohttp.ServerDisconnectedError("server dropped the connection")


def _conn_reset_oserror() -> aiohttp.ClientOSError:
    return aiohttp.ClientOSError(errno.ECONNRESET, "connection reset by peer")


def _conn_reset() -> aiohttp.ClientConnectionResetError:
    return aiohttp.ClientConnectionResetError("cannot write to closing transport")


def _payload_error() -> aiohttp.ClientPayloadError:
    return aiohttp.ClientPayloadError("response payload was not fully received")


_TRANSPORT_FACTORIES: list[tuple[str, Callable[[], Exception]]] = [
    ("server_disconnected", _server_disconnected),
    ("client_os_error_econnreset", _conn_reset_oserror),
    ("client_connection_reset", _conn_reset),
    ("client_payload_error", _payload_error),
]


class TestTransportErrorRetryAndMapping:
    @pytest.mark.parametrize(
        ("_id", "make_exc"),
        _TRANSPORT_FACTORIES,
        ids=[c[0] for c in _TRANSPORT_FACTORIES],
    )
    @pytest.mark.asyncio
    async def test_transport_error_retried_to_exhaustion_and_mapped(
        self,
        _fast_sleep: None,
        _id: str,
        make_exc: Callable[[], Exception],
    ) -> None:
        stub = StubSession([make_exc()] * 10)
        session = ResilientSession(inner=stub, config=ResilienceConfig(enabled=True))
        with pytest.raises(RestgdfError) as exc_info:
            async with session.get(_SVC_URL) as resp:
                await resp.read()
        # Connection-shaped and payload/truncated-body failures both surface as
        # TransportError (isinstance RestgdfError) after retrying to exhaustion.
        assert isinstance(exc_info.value, TransportError)
        assert stub._call_count == 5

    @pytest.mark.asyncio
    async def test_deterministic_4xx_still_not_retried(
        self,
        _fast_sleep: None,
    ) -> None:
        # Behaviour-preservation guard: a non-429 4xx must never retry.
        from restgdf.errors import RestgdfResponseError

        stub = StubSession([_FakeResponse(404)])
        session = ResilientSession(inner=stub, config=ResilienceConfig(enabled=True))
        with pytest.raises(RestgdfResponseError):
            async with session.get(_SVC_URL) as resp:
                await resp.read()
        assert stub._call_count == 1


# ---------------------------------------------------------------------------
# H1-N2 — cooldown wait must not erase a concurrently-set fresher deadline
# ---------------------------------------------------------------------------


class TestCooldownRaceSafety:
    @pytest.mark.asyncio
    async def test_wait_preserves_fresher_concurrent_deadline(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from restgdf.resilience._limiter import CooldownRegistry

        reg = CooldownRegistry()
        key = "https://example.com/arcgis/rest/services/X/FeatureServer"
        reg.set_cooldown(key, 0.05)  # short initial deadline

        sleeps: list[float] = []

        async def fake_sleep(d: float, *a: Any, **kw: Any) -> None:
            sleeps.append(d)
            if len(sleeps) == 1:
                # Simulate a concurrent 429 installing a *fresher* (longer)
                # deadline while this waiter is asleep on the original one.
                reg.set_cooldown(key, 100.0)

        monkeypatch.setattr("asyncio.sleep", fake_sleep)
        await reg.wait_if_cooling(key)

        # Buggy code slept once on the 0.05s deadline then unconditionally
        # popped, erasing the fresher 100s cooldown. The fix re-reads the
        # deadline after sleeping and honours the newer one (a second sleep).
        assert len(sleeps) >= 2
        assert max(sleeps) > 1.0

    @pytest.mark.asyncio
    async def test_wait_clears_own_deadline_when_unchanged(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # Behaviour-preservation guard: with no concurrent set, the waiter
        # still clears its own (expired) deadline exactly once.
        from restgdf.resilience._limiter import CooldownRegistry

        reg = CooldownRegistry()
        key = "https://example.com/arcgis/rest/services/Y/FeatureServer"
        reg.set_cooldown(key, 0.05)

        async def fake_sleep(_d: float, *a: Any, **kw: Any) -> None:
            return None

        monkeypatch.setattr("asyncio.sleep", fake_sleep)
        await reg.wait_if_cooling(key)
        assert key not in reg._deadlines
