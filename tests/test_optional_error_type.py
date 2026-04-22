"""Tests for BL-07: `_optional_dependency_error` returns `OptionalDependencyError`.

Asserts the new exception type is returned *and* that legacy
``except ModuleNotFoundError:`` / ``except ImportError:`` call sites keep
catching it because ``OptionalDependencyError`` multi-inherits
``ModuleNotFoundError``.
"""

from __future__ import annotations

import sys
from unittest import mock

import pytest

from restgdf.errors import ConfigurationError, OptionalDependencyError
from restgdf.utils._optional import (
    GEO_EXTRA,
    _optional_dependency_error,
    require_pandas,
)


def test_builder_returns_optional_dependency_error() -> None:
    err = _optional_dependency_error("feature.x", "pandas")
    assert isinstance(err, OptionalDependencyError)
    assert isinstance(err, ModuleNotFoundError)
    assert isinstance(err, ImportError)
    assert isinstance(err, ConfigurationError)
    assert isinstance(err, ValueError)
    assert "feature.x" in str(err)
    assert "pandas" in str(err)
    assert GEO_EXTRA in str(err)


def test_require_pandas_raises_optional_dependency_error() -> None:
    with mock.patch.dict(sys.modules, {"pandas": None}):
        with pytest.raises(OptionalDependencyError) as exc_info:
            require_pandas("test_feature")
    assert "test_feature" in str(exc_info.value)
    assert GEO_EXTRA in str(exc_info.value)


def test_legacy_module_not_found_error_still_catches() -> None:
    with mock.patch.dict(sys.modules, {"pandas": None}):
        with pytest.raises(ModuleNotFoundError):
            require_pandas("legacy_mnf_caller")


def test_legacy_import_error_still_catches() -> None:
    with mock.patch.dict(sys.modules, {"pandas": None}):
        with pytest.raises(ImportError):
            require_pandas("legacy_import_error_caller")


def test_configuration_error_also_catches() -> None:
    """BL-06/BL-07 — new taxonomy also satisfies ConfigurationError handlers."""
    with mock.patch.dict(sys.modules, {"pandas": None}):
        with pytest.raises(ConfigurationError):
            require_pandas("configuration_error_caller")
