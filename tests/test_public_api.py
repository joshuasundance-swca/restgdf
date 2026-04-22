"""Public API surface tests for restgdf v2.0.0.

Enumerates every name in :data:`restgdf.__all__` and asserts each is
importable and of the expected kind (class / callable / module).
"""

from __future__ import annotations

import inspect

import pytest

import restgdf


_EXPECTED_CLASSES = {
    "AGOLUserPass",
    "ArcGISServiceError",
    "ArcGISTokenSession",
    "AuthConfig",
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
    "FieldSpec",
    "LayerMetadata",
    "LimiterConfig",
    "ObjectIdsResponse",
    "OptionalDependencyError",
    "OutputConversionError",
    "PaginationError",
    "RateLimitError",
    "RestgdfError",
    "RestgdfResponseError",
    "RestgdfTimeoutError",
    "RetryConfig",
    "SchemaValidationError",
    "ServiceInfo",
    "Settings",
    "TelemetryConfig",
    "TimeoutConfig",
    "TokenResponse",
    "TokenSessionConfig",
    "TransportConfig",
    "TransportError",
}

_EXPECTED_CALLABLES = {
    "get_config",
    "get_settings",
    "reset_config_cache",
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
