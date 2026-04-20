"""Pydantic 2.x response/config models for restgdf 2.x.

This subpackage is the single source of truth for runtime-validated data
shapes. It grew out of the TypedDicts previously declared in
:mod:`restgdf._types`; those names are now deprecated aliases that re-export
from here.

Submodules are added slice-by-slice per the v2.0.0 integration plan:

* :mod:`restgdf._models._drift` — shared response-validation adapter and
  deduped drift logging.
* :mod:`restgdf._models.responses` — ArcGIS payload envelopes
  (``LayerMetadata``, ``CountResponse``, etc.).
* :mod:`restgdf._models.crawl` — crawl-report models.
* :mod:`restgdf._models.credentials` — ``AGOLUserPass`` and
  ``TokenSessionConfig``.
* :mod:`restgdf._models.settings` — process-level runtime settings.
"""

from __future__ import annotations

from restgdf._models._errors import RestgdfResponseError
from restgdf._models._settings import Settings, get_settings, reset_settings_cache
from restgdf._models.crawl import CrawlError, CrawlReport, CrawlServiceEntry
from restgdf._models.credentials import AGOLUserPass, TokenSessionConfig
from restgdf._models.responses import (
    CountResponse,
    ErrorInfo,
    ErrorResponse,
    Feature,
    FeaturesResponse,
    FieldSpec,
    LayerMetadata,
    ObjectIdsResponse,
    ServiceInfo,
    TokenResponse,
)

__all__ = [
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
    "reset_settings_cache",
]
