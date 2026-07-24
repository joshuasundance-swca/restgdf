"""Per-service-root token-bucket and cooldown registries (BL-52)."""

from __future__ import annotations

import asyncio
import re
import time
from urllib.parse import urlparse

from aiolimiter import AsyncLimiter


# Matches the first ArcGIS "server type" path segment.
_SERVER_TYPE_RE = re.compile(
    r"(.*?/(?:FeatureServer|MapServer|ImageServer|SceneServer))",
    re.IGNORECASE,
)


def _host(url: str) -> str:
    """Derive a per-host rate-limit key (``scheme://netloc``) from a URL.

    This is the coarser granularity selected by
    :attr:`restgdf.ResilienceConfig.limiter_key` ``= "host"``: every service
    on one host shares a single token bucket (and 429 cooldown), the polite
    default when many independent ArcGIS services sit behind a single
    government host. It is exactly :func:`_service_root`'s
    no-server-suffix fallback branch, factored out for reuse.
    """
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"


def _service_root(url: str) -> str:
    """Derive a per-service rate-limit key from a request URL.

    Truncates at the first ``FeatureServer``, ``MapServer``,
    ``ImageServer``, or ``SceneServer`` path segment. Falls back to
    ``scheme://host`` (:func:`_host`) when none of those segments are present.
    """
    parsed = urlparse(url)
    m = _SERVER_TYPE_RE.match(parsed.path)
    if m:
        return f"{parsed.scheme}://{parsed.netloc}{m.group(1)}"
    return _host(url)


class LimiterRegistry:
    """Lazy per-service-root :class:`AsyncLimiter` cache.

    Each unique *service_root* key gets its own token-bucket limiter
    capped at *rate_per_second* requests/s.
    """

    def __init__(self, rate_per_second: float) -> None:
        self._rate = rate_per_second
        self._limiters: dict[str, AsyncLimiter] = {}

    def get(self, service_root: str) -> AsyncLimiter:
        """Return (or create) the limiter for *service_root*.

        ``AsyncLimiter.acquire(1)`` refuses any amount above ``max_rate``,
        so a fractional ``max_rate`` (rate < 1 req/s with ``time_period=1``)
        crashes on the very first request. For sub-1 rates we instead spell
        the bucket as one token per ``1 / rate`` seconds — the idiomatic
        aiolimiter form — which paces at the requested rate. Rates >= 1 keep
        the historical ``AsyncLimiter(rate, 1)`` burst semantics exactly.
        """
        lim = self._limiters.get(service_root)
        if lim is None:
            if self._rate >= 1:
                lim = AsyncLimiter(max_rate=self._rate, time_period=1)
            else:
                lim = AsyncLimiter(max_rate=1, time_period=1 / self._rate)
            self._limiters[service_root] = lim
        return lim

    def reset(self) -> None:
        """Drop all cached limiters."""
        self._limiters.clear()


class CooldownRegistry:
    """Per-service-root 429-cooldown tracker.

    A cooldown is a *monotonic deadline* until which requests should be
    paused.  This is intentionally **separate** from the token-bucket
    limiter — we do NOT drain ``AsyncLimiter`` tokens on 429.
    """

    def __init__(self) -> None:
        self._deadlines: dict[str, float] = {}

    def set_cooldown(self, key: str, seconds: float) -> None:
        """Park *key* for *seconds* from now."""
        self._deadlines[key] = time.monotonic() + seconds

    async def wait_if_cooling(self, key: str) -> None:
        """Sleep until *key*'s cooldown expires (no-op if none set).

        **Bounded by construction:** one call sleeps at most until the deadline
        observed on entry. It never chains a second sleep.

        After sleeping, the deadline is re-read before being cleared. A
        concurrent :meth:`set_cooldown` (a fresh 429 on the same key) may have
        installed a *newer* deadline while this waiter slept; unconditionally
        popping would erase it, so the newer deadline is left in place for the
        next attempt/request to honour (H1-N2). Only a deadline this call
        actually waited out — unchanged since entry — is cleared.

        Trade-off (R2): the waking waiter itself *proceeds* — its request may
        dispatch while that fresher deadline is still in force. One request
        per waking waiter can slip into a live cooldown window; the next
        attempt on the key waits it out. This is the accepted cost of keeping
        a single wait bounded.

        Re-waiting here instead would make a single in-attempt wait scale with
        the number of concurrent waiters on the key (measured: 0.52s at
        concurrency 1 rising to 14.8s at 16 against a 0.5s cooldown), which
        neither ``max_attempts`` nor ``retry_budget_s`` can interrupt —
        stamina evaluates ``stop_after_delay`` only *between* attempts — and
        would falsify
        :attr:`restgdf.ResilienceConfig.respect_retry_after_max_s`'s cap on a
        single honoured ``Retry-After``.
        """
        deadline = self._deadlines.get(key)
        if deadline is None:
            return
        remaining = deadline - time.monotonic()
        if remaining > 0:
            await asyncio.sleep(remaining)
        # Re-read after sleeping: a concurrent set_cooldown may have replaced
        # the deadline we just waited on.
        current = self._deadlines.get(key)
        if current is None:
            return
        if current != deadline:
            # A fresher deadline was installed while we slept. Leave it for the
            # next attempt/request rather than chaining another wait here.
            return
        # Unchanged — this call waited it out, so clear it.
        self._deadlines.pop(key, None)
