"""Transport typing seam for restgdf (BL-17).

Defines :class:`AsyncHTTPSession`, a :class:`typing.Protocol` that
captures the subset of :class:`aiohttp.ClientSession` behavior restgdf
call sites rely on (``get`` / ``post`` / ``close`` / ``closed``).
Flagged :func:`typing.runtime_checkable` so adapter classes
(resilience, tracing, mock) can be validated via ``isinstance``.

Internal call sites that previously accepted
``aiohttp.ClientSession | ArcGISTokenSession`` were widened to
``AsyncHTTPSession`` in R-71 (v3 follow-up T7).
:class:`~restgdf.utils.token.ArcGISTokenSession` exposes ``close()`` /
``closed`` delegating to its inner :class:`aiohttp.ClientSession`, so
both concrete implementations satisfy this Protocol uniformly.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class AsyncHTTPSession(Protocol):
    """Structural type for restgdf transport sessions.

    Matches :class:`aiohttp.ClientSession` and
    :class:`~restgdf.utils.token.ArcGISTokenSession`, and is the
    forward-compatible target for resilience/telemetry adapters
    (BL-31 / BL-32). Only method/attribute *presence* is checked at
    ``isinstance`` time; signature details are advisory per
    :class:`typing.Protocol`.

    .. note::
       ``get`` and ``post`` are declared as non-async ``def`` because
       :meth:`aiohttp.ClientSession.get` is itself a synchronous method
       returning an awaitable ``_RequestContextManager``. Declaring
       them ``async def`` would make
       ``isinstance(aiohttp.ClientSession(), AsyncHTTPSession)`` fail at
       runtime on Python versions that check
       :func:`inspect.iscoroutinefunction` for Protocol members.
    """

    @property
    def closed(self) -> bool:
        ...

    async def close(self) -> None:
        ...

    def get(
        self,
        url: str,
        *,
        params: Any = None,
        headers: Any = None,
        ssl: Any = None,
        timeout: Any = None,
        **kwargs: Any,
    ) -> Any:
        ...

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
    ) -> Any:
        ...


__all__ = ["AsyncHTTPSession"]
