"""Per-service-root token-bucket and cooldown registries (BL-52)."""

from __future__ import annotations

import asyncio
import re
import time
from typing import Any
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
        """Return (or create) the limiter for *service_root*."""
        lim = self._limiters.get(service_root)
        if lim is None:
            lim = AsyncLimiter(max_rate=self._rate, time_period=1)
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
        """Sleep until *key*'s cooldown expires (no-op if none set)."""
        deadline = self._deadlines.get(key)
        if deadline is None:
            return
        remaining = deadline - time.monotonic()
        if remaining > 0:
            await asyncio.sleep(remaining)
        # Expired — clean up
        self._deadlines.pop(key, None)
