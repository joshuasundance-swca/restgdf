"""Correctness tests for resilience core (3.3.0 lane IMPL-1).

Covers four defects surfaced by the H1 adversarial health review, all latent
behind the pre-3.3 all-green suite:

* **H1-M1** — a sub-1.0 rate limit crashed with a raw, unmapped ``ValueError``.
* **H1-M2** — dispatch-time server disconnects / connection resets were neither
  retried nor mapped to a :class:`restgdf.errors.RestgdfError`. The retry
  wrapper covers dispatch through *headers received* only, so a failure raised
  while the response **body** is read stays out of scope — pinned below as a
  known limitation rather than assumed away by a fixture that raises from
  ``session.get()`` (which is not where aiohttp raises payload errors).
* **H1-N2** — ``CooldownRegistry.wait_if_cooling`` could erase a concurrently-set
  *fresher* 429 cooldown deadline.
* **H1-N4** — the ``restgdf.retry`` logger was dead; no retry/cooldown/mapping
  logging existed despite the tracing recipe promising it.

Red tests land first (``xfail(strict=True)``) then flip green in the fix commit
per the repo's red-first rule.
"""

from __future__ import annotations

import errno
import logging
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
# H1-M2 — dispatch-time transport errors must be retried and mapped
# ---------------------------------------------------------------------------


def _server_disconnected() -> aiohttp.ServerDisconnectedError:
    return aiohttp.ServerDisconnectedError("server dropped the connection")


def _conn_reset_oserror() -> aiohttp.ClientOSError:
    return aiohttp.ClientOSError(errno.ECONNRESET, "connection reset by peer")


def _conn_reset() -> aiohttp.ClientConnectionResetError:
    return aiohttp.ClientConnectionResetError("cannot write to closing transport")


def _payload_error() -> aiohttp.ClientPayloadError:
    return aiohttp.ClientPayloadError("response payload was not fully received")


# Failures a real aiohttp session raises from the request await itself, i.e.
# inside the retry wrapper's scope. ``ClientPayloadError`` is deliberately NOT
# here: aiohttp raises it on the payload stream, so it is covered separately.
_TRANSPORT_FACTORIES: list[tuple[str, Callable[[], Exception]]] = [
    ("server_disconnected", _server_disconnected),
    ("client_os_error_econnreset", _conn_reset_oserror),
    ("client_connection_reset", _conn_reset),
]


class _BodyFailingResponse(_FakeResponse):
    """Response whose headers arrive fine but whose BODY read raises.

    This is the shape aiohttp actually produces for a truncated / malformed
    chunked / short-content-length body: the request await resolves once
    headers are in, and ``ClientPayloadError`` is set on the payload stream
    (``aiohttp/client_proto.py`` ``set_exception(self._payload, ...)``), so it
    surfaces at ``resp.json()`` / ``resp.read()`` — after the retry wrapper has
    already returned.
    """

    def __init__(self, exc: Exception, status: int = 200) -> None:
        super().__init__(status)
        self._exc = exc

    async def read(self) -> bytes:
        raise self._exc

    async def json(self, *args: Any, **kwargs: Any) -> Any:
        raise self._exc


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
        # Connection-shaped dispatch failures surface as TransportError
        # (isinstance RestgdfError) after retrying to exhaustion.
        assert isinstance(exc_info.value, TransportError)
        assert stub._call_count == 5

    @pytest.mark.asyncio
    async def test_payload_error_from_dispatch_is_mapped(
        self,
        _fast_sleep: None,
    ) -> None:
        """Defensive branch: an inner session that raises the payload error from
        dispatch (a wrapping session, or aiohttp draining a redirect body) is
        still retried and mapped. This is NOT the common truncated-body shape —
        see ``TestPayloadErrorIsOutOfRetryScope`` for that.
        """
        stub = StubSession([_payload_error()] * 10)
        session = ResilientSession(inner=stub, config=ResilienceConfig(enabled=True))
        with pytest.raises(TransportError):
            async with session.get(_SVC_URL) as resp:
                await resp.read()
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
# H1-M2 (scope) — body-read failures are OUTSIDE the retry wrapper
# ---------------------------------------------------------------------------

_META_URL = "http://host/rest/services/X/FeatureServer/0"


class TestPayloadErrorIsOutOfRetryScope:
    """Pin the TRUE current behaviour of a mid-body transport failure.

    ``_do_retried_request`` wraps ``dispatch(url, **kwargs)`` only, so it
    returns once headers are received; every restgdf call site then reads the
    body outside that scope (``restgdf.utils._query.get_metadata`` awaits
    ``response.json(...)``). A failure raised there is therefore neither
    retried nor mapped to a :class:`restgdf.errors.RestgdfError` — a known
    limitation, documented in CHANGELOG and pinned here so it cannot silently
    change (or silently be claimed fixed).
    """

    @pytest.mark.asyncio
    async def test_payload_error_at_body_read_surfaces_raw_and_unretried(
        self,
        _fast_sleep: None,
    ) -> None:
        from restgdf.utils._query import get_metadata

        stub = StubSession([_BodyFailingResponse(_payload_error())] * 10)
        session = ResilientSession(inner=stub, config=ResilienceConfig(enabled=True))
        with pytest.raises(aiohttp.ClientPayloadError) as exc_info:
            await get_metadata(_META_URL, session)
        # Raw aiohttp exception: unmapped ...
        assert not isinstance(exc_info.value, RestgdfError)
        # ... and unretried (one dispatch, not max_attempts).
        assert stub._call_count == 1

    @pytest.mark.asyncio
    async def test_mid_body_disconnect_also_surfaces_raw_and_unretried(
        self,
        _fast_sleep: None,
    ) -> None:
        from restgdf.utils._query import get_metadata

        stub = StubSession([_BodyFailingResponse(_server_disconnected())] * 10)
        session = ResilientSession(inner=stub, config=ResilienceConfig(enabled=True))
        with pytest.raises(aiohttp.ServerDisconnectedError):
            await get_metadata(_META_URL, session)
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
        before = reg._deadlines[key]
        await reg.wait_if_cooling(key)

        # Buggy code slept once on the 0.05s deadline then unconditionally
        # popped, erasing the fresher 100s cooldown. The fix re-reads the
        # deadline after sleeping and leaves the newer one in place for the
        # next attempt/request to honour -- WITHOUT chaining a second wait
        # inside this call (see TestCooldownWaitIsBounded).
        assert key in reg._deadlines
        assert reg._deadlines[key] > before
        assert len(sleeps) == 1

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

    @pytest.mark.asyncio
    async def test_wait_returns_when_deadline_cleared_during_sleep(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # Defensive branch: if the key is cleared concurrently while sleeping,
        # the waiter returns cleanly rather than re-looping.
        from restgdf.resilience._limiter import CooldownRegistry

        reg = CooldownRegistry()
        key = "https://example.com/arcgis/rest/services/Z/FeatureServer"
        reg.set_cooldown(key, 0.05)

        async def fake_sleep(_d: float, *a: Any, **kw: Any) -> None:
            reg._deadlines.pop(key, None)  # concurrent clear during the sleep

        monkeypatch.setattr("asyncio.sleep", fake_sleep)
        await reg.wait_if_cooling(key)
        assert key not in reg._deadlines


class TestCooldownWaitIsBounded:
    """A single in-attempt cooldown wait must not scale with concurrency.

    ``wait_if_cooling`` is awaited *inside* a retried attempt, and stamina
    evaluates ``stop_after_delay`` only between attempts, so neither
    ``max_attempts`` nor ``retry_budget_s`` can interrupt a wait that re-loops.
    Chaining waits made one attempt block for 14.8s at concurrency 16 against a
    0.5s cooldown, falsifying ``respect_retry_after_max_s``'s documented cap
    (V1-M2).
    """

    @pytest.mark.asyncio
    async def test_single_wait_even_under_repeated_concurrent_cooldowns(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from restgdf.resilience._limiter import CooldownRegistry

        reg = CooldownRegistry()
        key = "https://example.com/arcgis/rest/services/W/FeatureServer"
        reg.set_cooldown(key, 0.05)

        sleeps: list[float] = []

        async def fake_sleep(d: float, *a: Any, **kw: Any) -> None:
            sleeps.append(d)
            if len(sleeps) > 3:
                raise AssertionError(
                    "wait_if_cooling chained waits: one call must sleep once",
                )
            # Every wake loses the race to a fresh 429 on the same key -- the
            # pathological shape that serialised every waiter pre-fix.
            reg.set_cooldown(key, 100.0)

        monkeypatch.setattr("asyncio.sleep", fake_sleep)
        await reg.wait_if_cooling(key)

        assert len(sleeps) == 1
        assert sleeps[0] <= 0.05

    @pytest.mark.asyncio
    async def test_deferred_fresher_deadline_is_honoured_next_call(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # Boundedness must not cost the N2 protection: the fresher deadline is
        # deferred, not dropped -- the next attempt/request waits it out.
        from restgdf.resilience._limiter import CooldownRegistry

        reg = CooldownRegistry()
        key = "https://example.com/arcgis/rest/services/V/FeatureServer"
        reg.set_cooldown(key, 0.05)

        sleeps: list[float] = []

        async def fake_sleep(d: float, *a: Any, **kw: Any) -> None:
            sleeps.append(d)
            if len(sleeps) == 1:
                reg.set_cooldown(key, 7.0)

        monkeypatch.setattr("asyncio.sleep", fake_sleep)
        await reg.wait_if_cooling(key)
        assert len(sleeps) == 1
        assert key in reg._deadlines

        await reg.wait_if_cooling(key)
        assert len(sleeps) == 2
        assert sleeps[1] > 1.0
        assert key not in reg._deadlines


# ---------------------------------------------------------------------------
# H1-N4 — the restgdf.retry logger must actually emit (dead-logger fix)
# ---------------------------------------------------------------------------


def _retry_messages(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.name == "restgdf.retry"]


class TestRetryLogging:
    @pytest.mark.asyncio
    async def test_retry_scheduled_emits_debug_log(
        self,
        _fast_sleep: None,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        caplog.set_level(logging.DEBUG, logger="restgdf.retry")
        stub = StubSession(
            [_server_disconnected(), _server_disconnected(), _FakeResponse(200)],
        )
        session = ResilientSession(inner=stub, config=ResilienceConfig(enabled=True))
        async with session.get(_SVC_URL) as resp:
            await resp.read()
        msgs = _retry_messages(caplog)
        assert any(
            "retry scheduled" in m and "attempt=" in m and "wait=" in m for m in msgs
        ), msgs

    @pytest.mark.asyncio
    async def test_429_cooldown_set_emits_debug_log(
        self,
        _fast_sleep: None,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        caplog.set_level(logging.DEBUG, logger="restgdf.retry")
        stub = StubSession(
            [_FakeResponse(429, {"Retry-After": "0"}), _FakeResponse(200)],
        )
        session = ResilientSession(inner=stub, config=ResilienceConfig(enabled=True))
        async with session.get(_SVC_URL) as resp:
            await resp.read()
        msgs = _retry_messages(caplog)
        assert any("cooldown set" in m for m in msgs), msgs

    @pytest.mark.asyncio
    async def test_log_extra_uses_limit_key_not_service_root(
        self,
        _fast_sleep: None,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        # Under limiter_key="host" the emitted key is a bare host, so it rides
        # the dedicated ``limit_key`` extra rather than mislabelling itself as
        # ``service_root`` (V1-M6).
        caplog.set_level(logging.DEBUG, logger="restgdf.retry")
        stub = StubSession(
            [_FakeResponse(429, {"Retry-After": "0"}), _FakeResponse(200)],
        )
        session = ResilientSession(
            inner=stub,
            config=ResilienceConfig(enabled=True, limiter_key="host"),
        )
        async with session.get(_SVC_URL) as resp:
            await resp.read()
        records = [
            r
            for r in caplog.records
            if r.name == "restgdf.retry" and "cooldown set" in r.getMessage()
        ]
        assert records, [r.getMessage() for r in caplog.records]
        assert records[0].limit_key == "http://host"
        assert not hasattr(records[0], "service_root")

    @pytest.mark.asyncio
    async def test_exhaustion_mapping_emits_debug_log(
        self,
        _fast_sleep: None,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        caplog.set_level(logging.DEBUG, logger="restgdf.retry")
        stub = StubSession([_server_disconnected()] * 10)
        session = ResilientSession(inner=stub, config=ResilienceConfig(enabled=True))
        with pytest.raises(TransportError):
            async with session.get(_SVC_URL) as resp:
                await resp.read()
        msgs = _retry_messages(caplog)
        assert any("exhaust" in m.lower() and "TransportError" in m for m in msgs), msgs
