"""Internal helper for emitting ``DeprecationWarning`` from legacy aliases.

Centralizing this helper ensures a consistent message format and that
each legacy name warns in exactly **one** place (no double-wrapping
through re-exports). See Phase 6 of the TDD refactor plan and
``tests/test_deprecations.py``.
"""

from __future__ import annotations

import inspect
import warnings
from functools import wraps
from typing import Any, Callable, TypeVar

F = TypeVar("F", bound=Callable[..., Any])


def deprecated_alias(new_func: F, old_name: str, new_name: str) -> F:
    """Return a wrapper that warns once per call and delegates to ``new_func``.

    The wrapper uses ``stacklevel=2`` so the warning points at the *caller*
    of the legacy name, not at this helper.
    """
    message = (
        f"`{old_name}` is deprecated and will be removed in a future "
        f"release; use `{new_name}` instead."
    )

    if _is_async_callable(new_func):

        @wraps(new_func)
        async def _async_wrapper(*args: Any, **kwargs: Any) -> Any:
            warnings.warn(message, DeprecationWarning, stacklevel=2)
            return await new_func(*args, **kwargs)

        _async_wrapper.__name__ = old_name
        _async_wrapper.__qualname__ = old_name
        return _async_wrapper  # type: ignore[return-value]

    @wraps(new_func)
    def _wrapper(*args: Any, **kwargs: Any) -> Any:
        warnings.warn(message, DeprecationWarning, stacklevel=2)
        return new_func(*args, **kwargs)

    _wrapper.__name__ = old_name
    _wrapper.__qualname__ = old_name
    return _wrapper  # type: ignore[return-value]


def _is_async_callable(obj: Any) -> bool:
    return inspect.iscoroutinefunction(obj)


__all__ = ["deprecated_alias"]
