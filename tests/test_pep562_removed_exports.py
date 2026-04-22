"""Tests for BL-57: `restgdf.__getattr__` `_REMOVED_EXPORTS` extension point.

The PEP-562 module-level `__getattr__` must:

1. Preserve the existing lazy-import path for every name in
   `_LAZY_EXPORTS` (FeatureLayer, Directory, utils, compat, and every
   pydantic model / error class re-exported from submodules).
2. When a name is **not** in `_LAZY_EXPORTS` but **is** in
   `_REMOVED_EXPORTS`, emit a `DeprecationWarning` at the caller's
   stacklevel and raise `AttributeError(migration_message)`.
3. For any other unknown name, raise a plain `AttributeError`.
4. `dir(restgdf)` advertises every lazy-export key so REPL completion
   and tooling continue to work after phase-1c.
"""

from __future__ import annotations

import warnings

import pytest

import restgdf


def test_existing_lazy_exports_still_work() -> None:
    from restgdf import FeatureLayer, Directory, compat, utils

    assert FeatureLayer.__name__ == "FeatureLayer"
    assert Directory.__name__ == "Directory"
    assert getattr(compat, "__name__", "") == "restgdf.compat"
    assert getattr(utils, "__name__", "") == "restgdf.utils"


def test_error_lazy_exports_still_work() -> None:
    from restgdf import (  # noqa: F401
        ArcGISServiceError,
        AuthenticationError,
        ConfigurationError,
        OptionalDependencyError,
        PaginationError,
        RateLimitError,
        RestgdfError,
        RestgdfTimeoutError,
        TransportError,
    )


def test_removed_export_emits_deprecation_and_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(
        restgdf._REMOVED_EXPORTS,
        "LegacyThing",
        "restgdf.LegacyThing has been removed; import restgdf.new_thing.NewThing instead.",
    )

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        with pytest.raises(AttributeError, match="restgdf.new_thing.NewThing"):
            restgdf.LegacyThing  # noqa: B018

    assert any(issubclass(w.category, DeprecationWarning) for w in caught)
    msg = next(w for w in caught if issubclass(w.category, DeprecationWarning))
    assert "LegacyThing" in str(msg.message)
    assert msg.filename.endswith("test_pep562_removed_exports.py"), msg.filename


def test_unknown_name_raises_plain_attributeerror() -> None:
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        with pytest.raises(AttributeError, match="no attribute"):
            restgdf.this_name_does_not_exist  # noqa: B018
    assert not any(issubclass(w.category, DeprecationWarning) for w in caught)


def test_dir_reports_lazy_exports() -> None:
    visible = set(dir(restgdf))
    assert "FeatureLayer" in visible
    assert "Directory" in visible
    assert "RestgdfError" in visible
    assert "PaginationError" in visible


def test_removed_exports_default_mapping_is_empty() -> None:
    assert restgdf._REMOVED_EXPORTS == {}
