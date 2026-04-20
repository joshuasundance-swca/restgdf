"""A package for getting GeoDataFrames from ArcGIS FeatureLayers."""

from restgdf import compat, utils
from restgdf._models import (
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
from restgdf.directory.directory import Directory
from restgdf.featurelayer.featurelayer import FeatureLayer
from restgdf.utils.token import ArcGISTokenSession

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
