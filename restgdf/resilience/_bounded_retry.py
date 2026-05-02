"""Bounded-retry helper for timeout-only retries (BL-51).

Public entry point: :func:`bounded_retry_timeout`. This module centralises
the retry semantics used by :func:`restgdf.utils.getinfo._feature_count_with_timeout`
so the inline loop there can be replaced with a single delegation call when
the ``resilience`` extra is installed.

Retry contract (must match the inline fallback byte-for-byte semantically):

* Retry ONLY on timeout exceptions:
  :class:`asyncio.TimeoutError`, :class:`TimeoutError`,
  :class:`aiohttp.ServerTimeoutError`.
* Every other exception — in particular :class:`aiohttp.ClientConnectionError`
  (R-69) and :class:`~restgdf.errors.RestgdfResponseError` — propagates
  unchanged on the first attempt.
* After ``max_attempts`` timeouts, raise
  :class:`~restgdf.errors.RestgdfTimeoutError` with the last timeout
  exception preserved as ``__cause__``.
"""

from __future__ import annotations

import asyncio
from typing import Callable, TypeVar
from collections.abc import Awaitable

import aiohttp
import stamina

from restgdf.errors import RestgdfTimeoutError

__all__ = ["bounded_retry_timeout"]

T = TypeVar("T")

_TIMEOUT_EXCS: tuple[type[BaseException], ...] = (
    asyncio.TimeoutError,
    TimeoutError,
    aiohttp.ServerTimeoutError,
)


async def bounded_retry_timeout(
    func: Callable[[], Awaitable[T]],
    *,
    max_attempts: int,
    url: str,
) -> T:
    """Invoke ``func`` with bounded retry on timeout exceptions.

    Parameters
    ----------
    func:
        Zero-argument awaitable factory (call produces the coroutine to run).
    max_attempts:
        Maximum number of attempts, identical to the inline fallback.
    url:
        Used only to build the ``RestgdfTimeoutError`` message on exhaustion.
    """

    @stamina.retry(
        on=_TIMEOUT_EXCS,
        attempts=max_attempts,
        timeout=None,
        wait_initial=0.1,
        wait_max=1.0,
        wait_jitter=0.0,
        wait_exp_base=2.0,
    )
    async def _attempt() -> T:
        return await func()

    try:
        return await _attempt()
    except _TIMEOUT_EXCS as exc:
        raise RestgdfTimeoutError(
            f"feature_count for {url} timed out after {max_attempts} attempts",
        ) from exc
