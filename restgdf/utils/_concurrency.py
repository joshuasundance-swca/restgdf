"""Internal concurrency primitives for restgdf.

Private submodule. The only public entry point today is
:func:`bounded_gather`, a drop-in replacement for
:func:`asyncio.gather` that caps concurrent execution via an
``asyncio.BoundedSemaphore`` (plan.md §3c R-18).

Threading contract (plan.md §3c R-44, kickoff phase-1a §10.3): each
top-level restgdf orchestration entry point (``service_metadata``,
``fetch_all_data``, ``safe_crawl``) constructs **one**
``asyncio.BoundedSemaphore`` at call time using
``Settings.max_concurrent_requests`` from :func:`get_settings`. That
semaphore is consumed at the three enumerated ``asyncio.gather`` fan-out
sites (``utils/getinfo.py:143``, ``utils/crawl.py:83``,
``utils/crawl.py:179``) via :func:`bounded_gather`. Leaf HTTP helpers
(e.g. ``get_metadata``) do NOT accept ``semaphore=`` kwargs; the cap is
enforced where fan-out actually happens.

Saturation semantics = wait (plan.md §3c R-19): ``asyncio.gather``'s
normal failure modes propagate; there is no ``ConcurrencySaturatedError``.
"""

from __future__ import annotations

import asyncio
from typing import Any
from collections.abc import Awaitable

__all__ = ("bounded_gather",)


async def bounded_gather(
    *aws: Awaitable[Any],
    semaphore: asyncio.Semaphore,
    return_exceptions: bool = False,
) -> list[Any]:
    """Gather awaitables while holding ``semaphore`` for each task.

    Behaves like :func:`asyncio.gather` with respect to result ordering
    (results match input order) and ``return_exceptions`` semantics,
    but guarantees that at most ``semaphore._value`` tasks execute
    their awaited body at once.

    Parameters
    ----------
    *aws
        Awaitables to run concurrently, capped by ``semaphore``.
    semaphore
        An :class:`asyncio.Semaphore` (or the recommended
        :class:`asyncio.BoundedSemaphore`) sized to
        ``Settings.max_concurrent_requests`` at the orchestration entry.
        Passed positionally is not allowed; this parameter is
        keyword-only to keep the seam explicit.
    return_exceptions
        Forwarded to :func:`asyncio.gather`. When ``True``, exceptions
        raised by any awaitable are collected into the result list at
        the corresponding index instead of propagating.

    Returns
    -------
    list[Any]
        Results in input order. When ``return_exceptions=True``, failed
        tasks appear as exception instances.

    Notes
    -----
    Cancelling the outer :func:`bounded_gather` call cancels all pending
    children; :func:`asyncio.gather` releases the semaphore slot via the
    ``async with`` exit, so no slots leak on cancellation.

    See the aiohttp ``TCPConnector`` default pool of 8 for the rationale
    behind the :class:`~restgdf._models._settings.Settings`
    ``max_concurrent_requests`` default.
    """

    async def _run(aw: Awaitable[Any]) -> Any:
        async with semaphore:
            return await aw

    return await asyncio.gather(
        *(_run(aw) for aw in aws),
        return_exceptions=return_exceptions,
    )
