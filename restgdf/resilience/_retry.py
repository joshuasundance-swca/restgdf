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
) -> Any:
    """Execute request with stamina retry."""
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
            raise _RetryableHTTPError(resp.status, headers)

        if 400 <= resp.status < 500:
            raise RestgdfResponseError(
                f"Client error ({resp.status}) at {url}",
                model_name="",
                context=url,
                raw=None,
            )

        return resp

    try:
        return await _attempt()
    except _RetryableHTTPError as exc:
        if exc.status == 429:
            raise RateLimitError(
                f"Rate limited (429) at {url}",
                retry_after=None,
            ) from exc
        raise RestgdfResponseError(
            f"Server error ({exc.status}) at {url}",
            model_name="",
            context=url,
            raw=None,
        ) from exc
    except aiohttp.ClientConnectorError as exc:
        raise TransportError(
            f"Connection failed for {url}",
        ) from exc
    except aiohttp.ServerTimeoutError as exc:
        raise RestgdfTimeoutError(
            f"Read timeout: {exc}",
        ) from exc
