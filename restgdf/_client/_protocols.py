"""Transport typing seam for restgdf (BL-17).

Defines :class:`AsyncHTTPSession`, a :class:`typing.Protocol` that
captures the subset of :class:`aiohttp.ClientSession` behavior restgdf
call sites rely on (``get`` / ``post`` / ``close`` / ``closed``).
Flagged :func:`typing.runtime_checkable` so adapter classes
(resilience, tracing, mock) can be validated via ``isinstance``.

Phase-2b ships this Protocol **definition only**; widening call-site
annotations currently typed ``aiohttp.ClientSession | ArcGISTokenSession``
lands in later phases so BL-17 stays additive.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class AsyncHTTPSession(Protocol):
    """Structural type for restgdf transport sessions.

    Matches :class:`aiohttp.ClientSession` and is the forward-compatible
    target for resilience/telemetry adapters (BL-31 / BL-32). Only
    method/attribute *presence* is checked at ``isinstance`` time;
    signature details are advisory per :class:`typing.Protocol`.

    .. note::
       ``get`` and ``post`` are declared as non-async ``def`` because
       :meth:`aiohttp.ClientSession.get` is itself a synchronous method
       returning an awaitable ``_RequestContextManager``. Declaring
       them ``async def`` would make
       ``isinstance(aiohttp.ClientSession(), AsyncHTTPSession)`` fail at
       runtime on Python versions that check
       :func:`inspect.iscoroutinefunction` for Protocol members.

    .. note::
       :class:`~restgdf.utils.token.ArcGISTokenSession` does **not**
       currently expose ``closed`` / ``close``. Making it Protocol-
       compatible (or narrowing the Protocol) is deferred: phase-2b
       does not migrate any call-site annotations, so no breakage.
    """

    @property
    def closed(self) -> bool: ...

    async def close(self) -> None: ...

    def get(
        self,
        url: str,
        *,
        params: Any = None,
        headers: Any = None,
        ssl: Any = None,
        timeout: Any = None,
        **kwargs: Any,
    ) -> Any: ...

    def post(
        self,
        url: str,
        *,
        data: Any = None,
        json: Any = None,
        params: Any = None,
        headers: Any = None,
        ssl: Any = None,
        timeout: Any = None,
        **kwargs: Any,
    ) -> Any: ...


__all__ = ["AsyncHTTPSession"]
