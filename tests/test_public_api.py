"""Public API surface tests for restgdf v2.0.0.

Enumerates every name in :data:`restgdf.__all__` and asserts each is
importable and of the expected kind (class / callable / module).
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

import restgdf


_EXPECTED_CLASSES = {
    "AGOLUserPass",
    "ArcGISServiceError",
    "ArcGISTokenSession",
    "AuthConfig",
    "AuthNotAttachedError",
    "AuthenticationError",
    "ConcurrencyConfig",
    "Config",
    "ConfigurationError",
    "CountResponse",
    "CrawlError",
    "CrawlReport",
    "CrawlServiceEntry",
    "Directory",
    "ErrorInfo",
    "ErrorResponse",
    "Feature",
    "FeatureLayer",
    "FeaturesResponse",
    "FieldDoesNotExistError",
    "FieldSpec",
    "InvalidCredentialsError",
    "LayerMetadata",
    "LimiterConfig",
    "ObjectIdsResponse",
    "OptionalDependencyError",
    "OutputConversionError",
    "PaginationInconsistencyWarning",
    "PaginationError",
    "RateLimitError",
    "ResilienceConfig",
    "RestgdfError",
    "RestgdfResponseError",
    "RestgdfTimeoutError",
    "RetryConfig",
    "SchemaValidationError",
    "ServiceInfo",
    "Settings",
    "TelemetryConfig",
    "TimeoutConfig",
    "TokenExpiredError",
    "TokenRefreshFailedError",
    "TokenRequiredError",
    "TokenResponse",
    "TokenSessionConfig",
    "TransportConfig",
    "TransportError",
}

_EXPECTED_CALLABLES = {
    "get_config",
    "get_settings",
    "reset_config_cache",
    "reset_settings_cache",
}

_EXPECTED_MODULES = {
    "adapters",
    "compat",
    "utils",
}


def test_public_all_is_complete() -> None:
    assert set(restgdf.__all__) == (
        _EXPECTED_CLASSES | _EXPECTED_CALLABLES | _EXPECTED_MODULES
    )


@pytest.mark.parametrize("name", sorted(_EXPECTED_CLASSES))
def test_class_is_importable_and_is_a_class(name: str) -> None:
    obj = getattr(restgdf, name)
    assert inspect.isclass(obj), f"{name} should be a class, got {type(obj)!r}"


@pytest.mark.parametrize("name", sorted(_EXPECTED_CALLABLES))
def test_callable_is_importable_and_callable(name: str) -> None:
    obj = getattr(restgdf, name)
    assert callable(obj), f"{name} should be callable"
    assert not inspect.isclass(obj), f"{name} should not be a class"


@pytest.mark.parametrize("name", sorted(_EXPECTED_MODULES))
def test_module_is_importable_and_is_a_module(name: str) -> None:
    obj = getattr(restgdf, name)
    assert inspect.ismodule(obj), f"{name} should be a module"


def test_all_names_in_all_are_attributes() -> None:
    for name in restgdf.__all__:
        assert hasattr(restgdf, name), f"restgdf.{name} in __all__ but missing"


def test_flat_import_forms_work() -> None:
    from restgdf import (  # noqa: F401
        AGOLUserPass,
        ArcGISTokenSession,
        CountResponse,
        CrawlError,
        CrawlReport,
        CrawlServiceEntry,
        Directory,
        ErrorInfo,
        ErrorResponse,
        Feature,
        FeatureLayer,
        FeaturesResponse,
        FieldSpec,
        LayerMetadata,
        ObjectIdsResponse,
        RestgdfResponseError,
        ServiceInfo,
        Settings,
        TokenResponse,
        TokenSessionConfig,
        compat,
        get_settings,
        reset_settings_cache,
        utils,
    )


def test_models_are_pydantic_basemodels() -> None:
    from pydantic import BaseModel

    model_names = {
        "AGOLUserPass",
        "CountResponse",
        "CrawlError",
        "CrawlReport",
        "CrawlServiceEntry",
        "ErrorInfo",
        "ErrorResponse",
        "Feature",
        "FeaturesResponse",
        "FieldSpec",
        "LayerMetadata",
        "ObjectIdsResponse",
        "ServiceInfo",
        "Settings",
        "TokenResponse",
        "TokenSessionConfig",
    }
    for name in model_names:
        cls = getattr(restgdf, name)
        assert issubclass(cls, BaseModel), f"{name} must be a pydantic BaseModel"


def test_error_is_exception_subclass() -> None:
    assert issubclass(restgdf.RestgdfResponseError, Exception)


def _is_type_checking_test(test: ast.expr) -> bool:
    """Match ``if TYPE_CHECKING:`` and ``if typing.TYPE_CHECKING:`` forms."""
    if isinstance(test, ast.Name):
        return test.id == "TYPE_CHECKING"
    if isinstance(test, ast.Attribute):
        return test.attr == "TYPE_CHECKING"
    return False


def _type_checking_bound_names(source: str) -> set[str]:
    """Collect every name statically bound inside ``if TYPE_CHECKING:``.

    W5-8 (API-03). ``restgdf/__init__.py`` uses two ``ImportFrom`` shapes
    inside its ``TYPE_CHECKING`` block and this must handle both:

    * ``from . import adapters, compat, utils`` -- a *module-valued*
      import (``module`` is ``None``, ``level=1``); each alias binds a
      submodule name directly (``adapters``, ``compat``, ``utils``).
      These are exactly ``_EXPECTED_MODULES`` above, and there is
      nothing to "resolve through" for a module import, so this walker
      treats them the same as any other bound name rather than special-
      casing them -- the module names land in the same returned set as
      every class/callable name and are compared against the full
      ``__all__`` set (which already includes them) as one axis, per
      the class docstring below.
    * ``from ._config import (Name1, Name2, ...)`` /
      ``from .errors import (...)`` / etc. -- ordinary submodule
      ``ImportFrom`` nodes; each alias binds ``asname`` if aliased,
      else its own name.

    A plain ``import x`` node (unused in the current tree, but a
    plausible future authoring style) is also tolerated: it binds
    ``asname`` if given, else the first dotted component of the
    imported name.
    """
    tree = ast.parse(source)
    names: set[str] = set()
    for node in ast.walk(tree):
        if not (isinstance(node, ast.If) and _is_type_checking_test(node.test)):
            continue
        for stmt in node.body:
            if isinstance(stmt, (ast.ImportFrom, ast.Import)):
                for alias in stmt.names:
                    names.add(alias.asname or alias.name.split(".")[0])
    return names


def test_type_checking_block_matches_all_and_lazy_exports() -> None:
    """W5-8 (API-03): the static ``TYPE_CHECKING`` import block must stay

    set-equal to the runtime public-surface sources of truth.

    ``set(restgdf.__all__) == set(restgdf._LAZY_EXPORTS)`` already holds
    by construction at runtime -- ``test_public_all_is_complete`` and
    ``test_all_names_in_all_are_attributes`` above cover that axis. The
    ONLY axis nothing previously guarded is the static
    ``if TYPE_CHECKING:`` block that a type-checker (mypy/pyright)
    actually reads: a name present in ``__all__``/``_LAZY_EXPORTS`` but
    missing there resolves to the module's ``def __getattr__(name) ->
    Any`` fallback under static analysis instead of its real type --
    exactly what happened to ``FieldDoesNotExistError`` before W5-7
    (API-02). This test does not touch or weaken that ``__getattr__``
    lazy-import boundary (``test_lazy_imports.py`` covers it
    separately) -- it only checks type-*precision*, not type-*safety*:
    a drifted name here still works fine at runtime, it just loses its
    static type.
    """
    source = Path(restgdf.__file__).read_text(encoding="utf-8")
    type_checking_names = _type_checking_bound_names(source)

    all_names = set(restgdf.__all__)
    lazy_export_names = set(restgdf._LAZY_EXPORTS)
    assert all_names == lazy_export_names, (
        "sanity precondition for this test: __all__ and _LAZY_EXPORTS "
        "were assumed set-equal at runtime, but drifted -- that is a "
        "different bug than the one this test guards"
    )

    missing_from_type_checking = all_names - type_checking_names
    assert not missing_from_type_checking, (
        f"names in __all__/_LAZY_EXPORTS but missing from the static "
        f"`if TYPE_CHECKING:` import block (unresolved under mypy/"
        f"pyright): {sorted(missing_from_type_checking)}"
    )
    extra_in_type_checking = type_checking_names - all_names
    assert not extra_in_type_checking, (
        f"names statically imported under `if TYPE_CHECKING:` but not "
        f"exported via __all__: {sorted(extra_in_type_checking)}"
    )
