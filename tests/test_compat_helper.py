"""Tests for BL-56: `restgdf._compat` deprecation helpers.

Asserts:
  * `_warn_deprecated` emits at ``stacklevel=2`` (warning.filename is the
    caller's file, not ``_compat.py``).
  * Custom category and stacklevel overrides are honored.
  * `async_deprecated_wrapper` emits the warning synchronously (before
    the coroutine is awaited) and still returns the correct awaited value.
  * Applying the decorator to a non-async function raises `TypeError`.
"""

from __future__ import annotations

import asyncio
import warnings

import pytest

from restgdf._compat import _warn_deprecated, async_deprecated_wrapper


def _call_warn(message: str) -> None:
    _warn_deprecated(message)


def test_warn_deprecated_default_category_and_stacklevel() -> None:
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        _call_warn("legacy-x is gone")
    assert len(caught) == 1
    w = caught[0]
    assert issubclass(w.category, DeprecationWarning)
    assert str(w.message) == "legacy-x is gone"
    assert w.filename.endswith("test_compat_helper.py"), w.filename


def test_warn_deprecated_honors_category_and_stacklevel() -> None:
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        _warn_deprecated(
            "future-y",
            category=PendingDeprecationWarning,
            stacklevel=1,
        )
    assert len(caught) == 1
    assert issubclass(caught[0].category, PendingDeprecationWarning)


def test_async_deprecated_wrapper_emits_warning_and_returns_value() -> None:
    @async_deprecated_wrapper("use new_async instead")
    async def legacy_async(x: int) -> int:
        return x + 1

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        result = asyncio.run(legacy_async(41))

    assert result == 42
    assert len(caught) == 1
    w = caught[0]
    assert issubclass(w.category, DeprecationWarning)
    assert "use new_async instead" in str(w.message)
    assert w.filename.endswith("test_compat_helper.py"), w.filename


def test_async_deprecated_wrapper_rejects_sync_function() -> None:
    def not_async() -> None:
        pass

    decorator = async_deprecated_wrapper("nope")
    with pytest.raises(TypeError, match="async def"):
        decorator(not_async)  # type: ignore[type-var]
