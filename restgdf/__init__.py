"""A package for getting GeoDataFrames from ArcGIS FeatureLayers."""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from . import adapters, compat, utils
    from ._config import (
        AuthConfig,
        ConcurrencyConfig,
        Config,
        LimiterConfig,
        ResilienceConfig,
        RetryConfig,
        TelemetryConfig,
        TimeoutConfig,
        TransportConfig,
        get_config,
        reset_config_cache,
    )
    from ._models import (
        AGOLUserPass,
        CountResponse,
        CrawlError,
        CrawlReport,
        CrawlServiceEntry,
        ErrorInfo,
        ErrorResponse,
        Feature,
        FeaturesResponse,
        FieldSpec,
        LayerMetadata,
        ObjectIdsResponse,
        RestgdfResponseError,
        ServiceInfo,
        Settings,
        TokenResponse,
        TokenSessionConfig,
        get_settings,
    )
    from .directory.directory import Directory
    from .errors import (
        ArcGISServiceError,
        AuthNotAttachedError,
        AuthenticationError,
        ConfigurationError,
        InvalidCredentialsError,
        OptionalDependencyError,
        OutputConversionError,
        PaginationError,
        RateLimitError,
        RestgdfError,
        RestgdfTimeoutError,
        SchemaValidationError,
        TokenExpiredError,
        TokenRefreshFailedError,
        TokenRequiredError,
        TransportError,
    )
    from .featurelayer.featurelayer import FeatureLayer
    from .utils.token import ArcGISTokenSession

__all__ = [
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
    "adapters",
    "compat",
    "get_config",
    "get_settings",
    "reset_config_cache",
    "utils",
]

__version__ = "2.0.0"

_LAZY_EXPORTS: dict[str, tuple[str, str | None]] = {
    **{
        name: ("restgdf._config", name)
        for name in (
            "AuthConfig",
            "ConcurrencyConfig",
            "Config",
            "LimiterConfig",
            "ResilienceConfig",
            "RetryConfig",
            "TelemetryConfig",
            "TimeoutConfig",
            "TransportConfig",
            "get_config",
            "reset_config_cache",
        )
    },
    **{
        name: ("restgdf._models", name)
        for name in (
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
            "RestgdfResponseError",
            "ServiceInfo",
            "Settings",
            "TokenResponse",
            "TokenSessionConfig",
            "get_settings",
        )
    },
    **{
        name: ("restgdf.errors", name)
        for name in (
            "ArcGISServiceError",
            "AuthNotAttachedError",
            "AuthenticationError",
            "ConfigurationError",
            "FieldDoesNotExistError",
            "InvalidCredentialsError",
            "OptionalDependencyError",
            "OutputConversionError",
            "PaginationError",
            "RateLimitError",
            "RestgdfError",
            "RestgdfTimeoutError",
            "SchemaValidationError",
            "TokenExpiredError",
            "TokenRefreshFailedError",
            "TokenRequiredError",
            "TransportError",
        )
    },
    "ArcGISTokenSession": ("restgdf.utils.token", "ArcGISTokenSession"),
    "Directory": ("restgdf.directory.directory", "Directory"),
    "FeatureLayer": ("restgdf.featurelayer.featurelayer", "FeatureLayer"),
    "adapters": ("restgdf.adapters", None),
    "compat": ("restgdf.compat", None),
    "utils": ("restgdf.utils", None),
}

_REMOVED_EXPORTS: dict[str, str] = {}


def __getattr__(name: str) -> Any:
    try:
        module_name, attr_name = _LAZY_EXPORTS[name]
    except KeyError:
        removed_message = _REMOVED_EXPORTS.get(name)
        if removed_message is not None:
            from restgdf._compat import _warn_deprecated

            _warn_deprecated(removed_message, stacklevel=3)
            raise AttributeError(removed_message)
        raise AttributeError(f"module 'restgdf' has no attribute {name!r}")

    module = importlib.import_module(module_name)
    value = module if attr_name is None else getattr(module, attr_name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__) | set(_LAZY_EXPORTS))
