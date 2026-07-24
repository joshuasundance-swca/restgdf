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


def _service_root(url: str) -> str:
    """Derive a per-service rate-limit key from a request URL.

    Truncates at the first ``FeatureServer``, ``MapServer``,
    ``ImageServer``, or ``SceneServer`` path segment. Falls back to
    ``scheme://host`` when none of those segments are present.
    """
    parsed = urlparse(url)
    m = _SERVER_TYPE_RE.match(parsed.path)
    if m:
        return f"{parsed.scheme}://{parsed.netloc}{m.group(1)}"
    return f"{parsed.scheme}://{parsed.netloc}"


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

        After sleeping, re-reads the deadline before clearing it. A
        concurrent :meth:`set_cooldown` (a fresh 429 on the same key) may
        have installed a *newer* deadline while this waiter slept;
        unconditionally popping would erase it, so this waiter is occasionally
        not honoured at high concurrency (H1-N2). If the deadline changed
        while sleeping, honour the new one; only clear it when it is unchanged.
        """
        while True:
            deadline = self._deadlines.get(key)
            if deadline is None:
                return
            remaining = deadline - time.monotonic()
            if remaining > 0:
                await asyncio.sleep(remaining)
            # Re-read after sleeping: a concurrent set_cooldown may have
            # replaced the deadline we just waited on.
            current = self._deadlines.get(key)
            if current is None:
                return
            if current != deadline:
                # A different (typically fresher) deadline was set — honour it.
                continue
            # Unchanged — safe to clear and finish.
            self._deadlines.pop(key, None)
            return
