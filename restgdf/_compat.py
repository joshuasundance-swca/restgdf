"""Shared compatibility helpers for restgdf deprecations.

This module is **internal**: it is deliberately not re-exported from
:mod:`restgdf`'s top-level namespace. It exists so that every
``DeprecationWarning`` emission in the package shares one implementation
with stable ``stacklevel`` semantics. Callers should import the helpers
directly as ``from restgdf._compat import _warn_deprecated`` or
``from restgdf._compat import async_deprecated_wrapper``.

Stacklevel rationale
--------------------
``_warn_deprecated`` defaults to ``stacklevel=2`` so the warning points at
the caller of ``_warn_deprecated``, not at this module. When wrapping an
async helper, emit the warning from the outer sync wrapper (before
scheduling the coroutine); that keeps ``stacklevel=2`` pointing at the
caller of the wrapped helper rather than at internals of this module.
"""

from __future__ import annotations

import functools
import inspect
import warnings
from typing import Any, Callable, TypeVar
from collections.abc import Awaitable

try:
    from contextlib import aclosing  # type: ignore[attr-defined]  # py310+
except ImportError:  # pragma: no cover - exercised on py39 only
    # Minimal backport of :class:`contextlib.aclosing` for Python 3.9.
    # Upstream added ``aclosing`` in 3.10 (bpo-41229); restgdf still targets
    # py39 per ``pyproject.toml`` ``requires-python = ">=3.9"`` and the
    # streaming iterators need deterministic ``aclose()`` on early break so
    # the R-61 INTERNAL span's ``finally`` runs without GC delay.
    from contextlib import AbstractAsyncContextManager

    class aclosing(AbstractAsyncContextManager):  # type: ignore[no-redef]
        """Async context manager that ``aclose()``s its target on exit."""

        def __init__(self, thing: Any) -> None:
            self.thing = thing

        async def __aenter__(self) -> Any:
            return self.thing

        async def __aexit__(self, *exc_info: Any) -> None:
            await self.thing.aclose()


__all__ = ["aclosing", "_warn_deprecated", "async_deprecated_wrapper"]


_F = TypeVar("_F", bound=Callable[..., Awaitable[Any]])


def _warn_deprecated(
    message: str,
    *,
    category: type = DeprecationWarning,
    stacklevel: int = 2,
) -> None:
    """Emit a ``DeprecationWarning`` that points at the immediate caller.

    Parameters
    ----------
    message
        Human-readable deprecation message.
    category
        Warning category to emit. Defaults to :class:`DeprecationWarning`.
    stacklevel
        ``warnings.warn`` stacklevel. The default of ``2`` resolves to the
        caller of ``_warn_deprecated``; decorators that add a frame should
        pass ``stacklevel=3``.
    """

    warnings.warn(message, category=category, stacklevel=stacklevel)


def async_deprecated_wrapper(
    message: str,
    *,
    category: type = DeprecationWarning,
) -> Callable[[_F], _F]:
    """Return a decorator that marks an async helper as deprecated.

    The warning is emitted synchronously *before* the coroutine is
    scheduled, so ``stacklevel=2`` still points at the caller's frame
    rather than at the event-loop internals. The wrapped coroutine still
    awaits to its original result.

    Parameters
    ----------
    message
        Deprecation message passed to :func:`_warn_deprecated`.
    category
        Warning category. Defaults to :class:`DeprecationWarning`.
    """

    def decorator(fn: _F) -> _F:
        if not inspect.iscoroutinefunction(fn):
            raise TypeError(
                "async_deprecated_wrapper requires an async def function",
            )

        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            _warn_deprecated(message, category=category, stacklevel=3)
            return fn(*args, **kwargs)

        return wrapper  # type: ignore[return-value]

    return decorator


__all__ = ["_warn_deprecated", "async_deprecated_wrapper"]
