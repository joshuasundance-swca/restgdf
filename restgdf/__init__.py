"""A package for getting GeoDataFrames from ArcGIS FeatureLayers."""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from . import compat, utils
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
    from .featurelayer.featurelayer import FeatureLayer
    from .utils.token import ArcGISTokenSession

__all__ = [
    "AGOLUserPass",
    "ArcGISTokenSession",
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
    "ObjectIdsResponse",
    "RestgdfResponseError",
    "ServiceInfo",
    "Settings",
    "TokenResponse",
    "TokenSessionConfig",
    "compat",
    "get_settings",
    "utils",
]

__version__ = "2.0.0"

_LAZY_EXPORTS: dict[str, tuple[str, str | None]] = {
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
    "ArcGISTokenSession": ("restgdf.utils.token", "ArcGISTokenSession"),
    "Directory": ("restgdf.directory.directory", "Directory"),
    "FeatureLayer": ("restgdf.featurelayer.featurelayer", "FeatureLayer"),
    "compat": ("restgdf.compat", None),
    "utils": ("restgdf.utils", None),
}


def __getattr__(name: str) -> Any:
    try:
        module_name, attr_name = _LAZY_EXPORTS[name]
    except KeyError as exc:
        raise AttributeError(f"module 'restgdf' has no attribute {name!r}") from exc

    module = importlib.import_module(module_name)
    value = module if attr_name is None else getattr(module, attr_name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
