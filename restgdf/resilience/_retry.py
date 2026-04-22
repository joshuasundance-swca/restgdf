"""Stamina-based retry wrapper implementing AsyncHTTPSession (BL-31)."""

from __future__ import annotations

import contextlib
from typing import Any

import aiohttp
import stamina
import yarl

from restgdf._config import ResilienceConfig
from restgdf._logging import get_logger
from restgdf.errors import (
    RateLimitError,
    RestgdfResponseError,
    RestgdfTimeoutError,
    TransportError,
)
from restgdf.resilience._errors import _parse_retry_after
from restgdf.resilience._limiter import CooldownRegistry, LimiterRegistry, _service_root


_log = get_logger("retry")

# Retryable HTTP status codes
_RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})


class _ResponseCtx:
    """Thin async-context-manager wrapping an already-resolved response."""

    __slots__ = ("_resp",)

    def __init__(self, resp: Any) -> None:
        self._resp = resp

    async def __aenter__(self) -> Any:
        return self._resp

    async def __aexit__(self, *args: Any) -> None:
        pass

    def __getattr__(self, name: str) -> Any:
        return getattr(self._resp, name)


class ResilientSession:
    """Retry + rate-limit adapter wrapping an inner AsyncHTTPSession."""

    def __init__(
        self,
        inner: Any,
        config: ResilienceConfig,
    ) -> None:
        self._inner = inner
        self._config = config
        self._cooldown = CooldownRegistry()
        self._limiter: LimiterRegistry | None = None
        if config.rate_per_service_root_per_second is not None:
            self._limiter = LimiterRegistry(config.rate_per_service_root_per_second)

    @property
    def closed(self) -> bool:
        return self._inner.closed

    async def close(self) -> None:
        await self._inner.close()

    def get(self, url: str, **kwargs: Any) -> Any:
        if not self._config.enabled:
            return self._inner.get(url, **kwargs)
        return self._retried_request("get", url, **kwargs)

    def post(self, url: str, **kwargs: Any) -> Any:
        if not self._config.enabled:
            return self._inner.post(url, **kwargs)
        return self._retried_request("post", url, **kwargs)

    def _retried_request(self, method: str, url: str, **kwargs: Any) -> _ResponseCtx:
        return _RetriedCtx(self, method, url, kwargs)

    def _reset_limiters(self) -> None:
        """Reset all limiter and cooldown state (for testing)."""
        self._cooldown = CooldownRegistry()
        if self._limiter is not None:
            self._limiter.reset()


class _RetriedCtx:
    """Async context manager that performs retried request on __aenter__."""

    __slots__ = ("_session", "_method", "_url", "_kwargs", "_resp")

    def __init__(self, session: ResilientSession, method: str, url: str, kwargs: dict[str, Any]) -> None:
        self._session = session
        self._method = method
        self._url = url
        self._kwargs = kwargs
        self._resp: Any = None

    async def __aenter__(self) -> Any:
        self._resp = await _do_retried_request(
            self._session._inner,
            self._session._config,
            self._method,
            self._url,
            self._kwargs,
            limiter=self._session._limiter,
            cooldown=self._session._cooldown,
        )
        return self._resp

    async def __aexit__(self, *args: Any) -> None:
        pass


class _RetryableHTTPError(Exception):
    """Internal sentinel for stamina retry loop."""

    def __init__(self, status: int, headers: dict[str, str] | None = None) -> None:
        self.status = status
        self.headers = headers or {}


async def _do_retried_request(
    inner: Any,
    config: ResilienceConfig,
    method: str,
    url: str,
    kwargs: dict[str, Any],
    *,
    limiter: LimiterRegistry | None = None,
    cooldown: CooldownRegistry | None = None,
) -> Any:
    """Execute request with stamina retry, token-bucket, and cooldown."""
    svc_root = _service_root(url)
    retry_on = (
        _RetryableHTTPError,
        aiohttp.ClientConnectorError,
        aiohttp.ServerTimeoutError,
    )

    @stamina.retry(
        on=retry_on,
        attempts=5,
        timeout=60.0,
        wait_initial=0.5,
        wait_max=10.0,
        wait_jitter=1.0,
    )
    async def _attempt() -> Any:
        # 429 cooldown: wait if a previous 429 set a deadline for this service
        if cooldown is not None:
            await cooldown.wait_if_cooling(svc_root)
        # Token-bucket rate limit
        if limiter is not None:
            await limiter.get(svc_root).acquire()
        try:
            dispatch = getattr(inner, method)
            ctx = dispatch(url, **kwargs)
            resp = await ctx.__aenter__()
        except aiohttp.ClientConnectorError:
            raise  # retryable
        except aiohttp.ServerTimeoutError:
            raise  # retryable

        if resp.status in _RETRYABLE_STATUS:
            headers = dict(getattr(resp, "headers", {}))
            # Set cooldown on 429 so the next retry waits
            if resp.status == 429 and cooldown is not None:
                ra = _parse_retry_after(headers.get("Retry-After", ""))
                cd = min(ra, config.respect_retry_after_max_s) if ra else config.fallback_retry_after_seconds
                cooldown.set_cooldown(svc_root, cd)
            raise _RetryableHTTPError(resp.status, headers)

        if 400 <= resp.status < 500:
            raise RestgdfResponseError(
                f"Client error ({resp.status}) at {url}",
                model_name="",
                context=url,
                raw=None,
                url=url,
                status_code=resp.status,
            )

        return resp

    try:
        return await _attempt()
    except _RetryableHTTPError as exc:
        if exc.status == 429:
            retry_after = _parse_retry_after(exc.headers.get("Retry-After", ""))
            raise RateLimitError(
                f"Rate limited (429) at {url}",
                retry_after=retry_after,
                url=url,
                status_code=429,
            ) from exc
        raise RestgdfResponseError(
            f"Server error ({exc.status}) at {url}",
            model_name="",
            context=url,
            raw=None,
            url=url,
            status_code=exc.status,
        ) from exc
    except aiohttp.ClientConnectorError as exc:
        raise TransportError(
            f"Connection failed for {url}",
            url=url,
            status_code=None,
        ) from exc
    except aiohttp.ServerTimeoutError as exc:
        raise RestgdfTimeoutError(
            f"Read timeout: {exc}",
            url=url,
            timeout_kind="read",
        ) from exc
