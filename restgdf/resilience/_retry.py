"""Stamina-based retry wrapper implementing AsyncHTTPSession (BL-31)."""

from __future__ import annotations

import inspect
from typing import Any

import aiohttp
import stamina

from restgdf._config import ResilienceConfig
from restgdf._logging import build_log_extra, get_logger
from restgdf.errors import (
    RateLimitError,
    RestgdfResponseError,
    RestgdfTimeoutError,
    TransportError,
)
from restgdf.resilience._errors import _parse_retry_after
from restgdf.resilience._limiter import (
    CooldownRegistry,
    LimiterRegistry,
    _host,
    _service_root,
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

    def _retried_request(self, method: str, url: str, **kwargs: Any) -> Any:
        return _RetriedCtx(self, method, url, kwargs)

    def _reset_limiters(self) -> None:
        """Reset all limiter and cooldown state (for testing)."""
        self._cooldown = CooldownRegistry()
        if self._limiter is not None:
            self._limiter.reset()


class _RetriedCtx:
    """Dual-interface wrapper: works as ``await session.get(url)`` AND
    as ``async with session.get(url) as resp:``.

    Mirrors :class:`aiohttp.client._RequestContextManager` so
    :class:`ResilientSession` behaves identically to
    :class:`aiohttp.ClientSession` regardless of whether callers use
    the awaitable or async-context-manager pattern. :mod:`restgdf.utils._http`
    awaits the result of ``session.get`` / ``session.post`` directly,
    so this dual shape is required for the helper to work against a
    :class:`ResilientSession`-wrapped inner session.
    """

    __slots__ = ("_session", "_method", "_url", "_kwargs", "_resp", "_resp_ctx")

    def __init__(
        self,
        session: ResilientSession,
        method: str,
        url: str,
        kwargs: dict[str, Any],
    ) -> None:
        self._session = session
        self._method = method
        self._url = url
        self._kwargs = kwargs
        self._resp: Any = None
        self._resp_ctx: Any = None

    async def _run(self) -> Any:
        self._resp_ctx, self._resp = await _do_retried_request(
            self._session._inner,
            self._session._config,
            self._method,
            self._url,
            self._kwargs,
            limiter=self._session._limiter,
            cooldown=self._session._cooldown,
        )
        return self._resp

    async def __aenter__(self) -> Any:
        return await self._run()

    async def __aexit__(self, *args: Any) -> None:
        if self._resp_ctx is not None:
            await self._resp_ctx.__aexit__(*args)

    def __await__(self) -> Any:
        return self._run().__await__()


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
) -> tuple[Any, Any]:
    """Execute request with stamina retry, token-bucket, and cooldown."""
    # Select the rate-limit/cooldown key granularity once from config, and use
    # the SAME key for the token bucket AND the 429 cooldown (politeness
    # decision D1: a host-level block wants a host-wide cooldown). Default
    # "service_root" preserves the historical per-service keying exactly.
    key_fn = _host if config.limiter_key == "host" else _service_root
    limit_key = key_fn(url)
    # ``ClientConnectionError`` is the common base for every connection-shaped
    # aiohttp failure — ``ClientConnectorError`` (DNS/connect), ``ClientOSError``
    # (incl. ECONNRESET), ``ClientConnectionResetError``, ``ServerDisconnectedError``,
    # and ``ServerTimeoutError`` — so retrying it covers dispatch-time disconnects and
    # resets that a bulk crawl routinely hits, not just connect-time and read-timeout
    # failures.
    #
    # SCOPE (verified): this wrapper covers the request only up to *headers
    # received* — ``_enter_request(dispatch(...))``. Callers read the body after
    # ``_do_retried_request`` has returned (``restgdf.utils._query`` awaits
    # ``response.json(...)``), and aiohttp raises ``ClientPayloadError`` on the
    # payload stream, not from the request await. A truncated/mid-body failure
    # therefore surfaces raw at the read, outside this retry loop; the
    # ``ClientPayloadError`` entry below only covers inner sessions that surface
    # it from dispatch itself (a wrapping session, or aiohttp draining a redirect
    # body). Extending retry across the body read needs ``_RetriedCtx`` to own
    # response consumption — a deliberate design item, not done here.
    retry_on = (
        _RetryableHTTPError,
        aiohttp.ClientConnectionError,
        aiohttp.ClientPayloadError,
    )
    # Cause of the most recent failed attempt. stamina swallows the exception
    # between attempts, so we record it here to name it in the retry-scheduled
    # and exhaustion-mapping DEBUG logs (H1-N4).
    last_cause: dict[str, str] = {}

    async def _attempt() -> tuple[Any, Any]:
        # 429 cooldown: wait if a previous 429 set a deadline for this service
        if cooldown is not None:
            await cooldown.wait_if_cooling(limit_key)
        # Token-bucket rate limit
        if limiter is not None:
            await limiter.get(limit_key).acquire()
        dispatch = getattr(inner, method)
        try:
            ctx, resp = await _enter_request(dispatch(url, **kwargs))
        except (aiohttp.ClientConnectionError, aiohttp.ClientPayloadError) as exc:
            last_cause["cause"] = type(exc).__name__
            raise

        if resp.status in _RETRYABLE_STATUS:
            headers = dict(getattr(resp, "headers", {}))
            # Set cooldown on 429 so the next retry waits
            if resp.status == 429 and cooldown is not None:
                ra = _parse_retry_after(headers.get("Retry-After", ""))
                cd = (
                    min(ra, config.respect_retry_after_max_s)
                    if ra
                    else config.fallback_retry_after_seconds
                )
                cooldown.set_cooldown(limit_key, cd)
                _log.debug(
                    "429 cooldown set: key=%s seconds=%.3f",
                    limit_key,
                    cd,
                    extra=build_log_extra(
                        limit_key=limit_key,
                        operation="cooldown",
                        limiter_wait_s=cd,
                    ),
                )
            await ctx.__aexit__(None, None, None)
            last_cause["cause"] = f"status={resp.status}"
            raise _RetryableHTTPError(resp.status, headers)

        if 400 <= resp.status < 500:
            await ctx.__aexit__(None, None, None)
            raise RestgdfResponseError(
                f"Client error ({resp.status}) at {url}",
                model_name="",
                context=url,
                raw=None,
                url=url,
                status_code=resp.status,
            )

        return ctx, resp

    # ``retry_context`` is the equivalent of the ``@stamina.retry`` decorator
    # (same kwargs) but exposes each attempt's number and backoff, so the
    # per-retry DEBUG log can name them (H1-N4). ``prev_wait`` carries the
    # backoff that was applied *before* the current attempt. The retry policy
    # is read from ``config`` (R2); the defaults on ``ResilienceConfig``
    # (5 / 60.0 / 0.5 / 10.0 / 1.0) preserve the historical hardcoded values
    # byte-for-byte, and ``config.enabled`` remains the sole retry gate.
    prev_wait = 0.0
    try:
        async for attempt in stamina.retry_context(
            on=retry_on,
            attempts=config.max_attempts,
            timeout=config.retry_budget_s,
            wait_initial=config.wait_initial_s,
            wait_max=config.wait_max_s,
            wait_jitter=config.wait_jitter_s,
        ):
            if attempt.num > 1:
                _log.debug(
                    "retry scheduled: attempt=%d wait=%.3fs caused_by=%s",
                    attempt.num,
                    prev_wait,
                    last_cause.get("cause", "unknown"),
                    extra=build_log_extra(
                        limit_key=limit_key,
                        retry_attempt=attempt.num,
                        retry_delay_s=prev_wait,
                        exception_type=last_cause.get("cause"),
                    ),
                )
            prev_wait = attempt.next_wait
            with attempt:
                return await _attempt()
        raise AssertionError(  # pragma: no cover - retry_context always returns or raises
            "stamina.retry_context exited without returning or raising",
        )
    except _RetryableHTTPError as exc:
        if exc.status == 429:
            _log.debug(
                "retry exhausted: status=429 mapped to RateLimitError",
                extra=build_log_extra(
                    limit_key=limit_key,
                    exception_type="RateLimitError",
                ),
            )
            retry_after = _parse_retry_after(exc.headers.get("Retry-After", ""))
            raise RateLimitError(
                f"Rate limited (429) at {url}",
                retry_after=retry_after,
                url=url,
                status_code=429,
            ) from exc
        _log.debug(
            "retry exhausted: status=%d mapped to RestgdfResponseError",
            exc.status,
            extra=build_log_extra(
                limit_key=limit_key,
                exception_type="RestgdfResponseError",
            ),
        )
        raise RestgdfResponseError(
            f"Server error ({exc.status}) at {url}",
            model_name="",
            context=url,
            raw=None,
            url=url,
            status_code=exc.status,
        ) from exc
    except aiohttp.ServerTimeoutError as exc:
        # ServerTimeoutError subclasses ClientConnectionError — map it first so
        # read timeouts keep their dedicated RestgdfTimeoutError type fidelity.
        _log.debug(
            "retry exhausted: %s mapped to RestgdfTimeoutError",
            type(exc).__name__,
            extra=build_log_extra(
                limit_key=limit_key,
                exception_type="RestgdfTimeoutError",
            ),
        )
        raise RestgdfTimeoutError(
            f"Read timeout: {exc}",
            url=url,
            timeout_kind="read",
        ) from exc
    except aiohttp.ClientPayloadError as exc:
        _log.debug(
            "retry exhausted: %s mapped to TransportError",
            type(exc).__name__,
            extra=build_log_extra(
                limit_key=limit_key,
                exception_type="TransportError",
            ),
        )
        raise TransportError(
            f"Truncated or incomplete response body for {url}",
            url=url,
            status_code=None,
        ) from exc
    except aiohttp.ClientConnectionError as exc:
        _log.debug(
            "retry exhausted: %s mapped to TransportError",
            type(exc).__name__,
            extra=build_log_extra(
                limit_key=limit_key,
                exception_type="TransportError",
            ),
        )
        raise TransportError(
            f"Connection failed for {url}",
            url=url,
            status_code=None,
        ) from exc


async def _enter_request(result: Any) -> tuple[Any, Any]:
    """Normalize a session dispatch result to an entered async context."""
    if inspect.isawaitable(result):
        response = await result
        ctx = _ResponseCtx(response)
        return ctx, await ctx.__aenter__()

    if hasattr(result, "__aenter__") and hasattr(result, "__aexit__"):
        return result, await result.__aenter__()

    ctx = _ResponseCtx(result)
    return ctx, await ctx.__aenter__()
