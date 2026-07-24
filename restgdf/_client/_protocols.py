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

    This is a **runtime presence contract**: flagged
    :func:`typing.runtime_checkable`, ``isinstance`` verifies only that
    ``get`` / ``post`` / ``close`` / ``closed`` are present, and both
    :class:`aiohttp.ClientSession` and
    :class:`~restgdf.utils.token.ArcGISTokenSession` satisfy it at
    runtime. It is the forward-compatible target for resilience /
    telemetry adapters (BL-31 / BL-32).

    Static-typing note (TYPING-02): restgdf's own
    :class:`~restgdf.utils.token.ArcGISTokenSession` *is* a static
    structural subtype of this Protocol, but
    :class:`aiohttp.ClientSession` is **not**. Current aiohttp type
    stubs declare ``get`` / ``post`` as
    ``def get(self, url, **kwargs: Unpack[_RequestOptions])`` — a typed
    keyword-args unpack that only accepts the specific ``_RequestOptions``
    keys, which no ``**kwargs: Any`` protocol can be a supertype of. The
    ``get`` / ``post`` signatures below therefore document the call
    surface restgdf relies on; they are *not* a claim that
    ``ClientSession`` is statically assignable here (only method/attribute
    *presence* is guaranteed, per :class:`typing.Protocol`). Where a
    concrete :class:`aiohttp.ClientSession` must reach an
    ``AsyncHTTPSession``-typed seam (e.g. the bare session built inside
    :func:`restgdf.utils.getgdf.get_gdf`), an explicit
    :func:`typing.cast` bridges the runtime-valid-but-statically-unprovable
    gap rather than forcing aiohttp to conform structurally (the audit's
    explicit anti-recommendation).

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
