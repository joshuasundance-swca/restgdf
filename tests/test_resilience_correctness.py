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
import logging
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

    @pytest.mark.xfail(strict=True, reason="H1-M1: fixed in next commit")
    def test_sub_one_rate_construction_uses_stretched_period(self) -> None:
        # 0.5 req/s => 1 token every 2 seconds, not AsyncLimiter(0.5, 1).
        lim = LimiterRegistry(rate_per_second=0.5).get("svc")
        assert lim.max_rate == 1
        assert lim.time_period == pytest.approx(2.0)

    @pytest.mark.xfail(strict=True, reason="H1-M1: fixed in next commit")
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
