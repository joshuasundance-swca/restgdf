"""Deprecated typing aliases for the pre-v2.0.0 TypedDict public surface.

.. deprecated:: 2.0.0
   The :class:`~typing.TypedDict` definitions that used to live here are
   replaced by the runtime-validated pydantic models in
   :mod:`restgdf._models.responses` and :mod:`restgdf._models.crawl`.
   Importing any name from ``restgdf._types`` emits a
   :class:`DeprecationWarning` and returns the corresponding
   :class:`pydantic.BaseModel`.

   Migration:

   ===========================================  =========================================================
   Legacy ``restgdf._types`` name               v2.x replacement
   ===========================================  =========================================================
   ``FieldSpec``                                :class:`restgdf.FieldSpec`
   ``LayerMetadata``                            :class:`restgdf.LayerMetadata`
   ``ServiceInfo``                              :class:`restgdf.ServiceInfo`
   ``CountResponse``                            :class:`restgdf.CountResponse`
   ``ObjectIdsResponse``                        :class:`restgdf.ObjectIdsResponse`
   ``Feature``                                  :class:`restgdf.Feature`
   ``FeaturesResponse``                         :class:`restgdf.FeaturesResponse`
   ``ErrorInfo``                                :class:`restgdf.ErrorInfo`
   ``ErrorResponse``                            :class:`restgdf.ErrorResponse`
   ``CrawlError``                               :class:`restgdf.CrawlError`
   ``CrawlServiceEntry``                        :class:`restgdf.CrawlServiceEntry`
   ``CrawlReport``                              :class:`restgdf.CrawlReport`
   ===========================================  =========================================================

   This shim will be removed in 3.x.
"""

from __future__ import annotations

import importlib
import warnings
from typing import Any

# Map legacy TypedDict name -> (submodule, attribute) in the new public API.
# We import these lazily in __getattr__ so that accessing any public name
# triggers the module-level DeprecationWarning exactly once per access and
# so that the names do not live in this module's __dict__ (which would
# bypass __getattr__).
_REPLACEMENTS: dict[str, tuple[str, str]] = {
    "FieldSpec": ("restgdf._models.responses", "FieldSpec"),
    "LayerMetadata": ("restgdf._models.responses", "LayerMetadata"),
    "ServiceInfo": ("restgdf._models.responses", "ServiceInfo"),
    "CountResponse": ("restgdf._models.responses", "CountResponse"),
    "ObjectIdsResponse": ("restgdf._models.responses", "ObjectIdsResponse"),
    "Feature": ("restgdf._models.responses", "Feature"),
    "FeaturesResponse": ("restgdf._models.responses", "FeaturesResponse"),
    "ErrorInfo": ("restgdf._models.responses", "ErrorInfo"),
    "ErrorResponse": ("restgdf._models.responses", "ErrorResponse"),
    "CrawlError": ("restgdf._models.crawl", "CrawlError"),
    "CrawlServiceEntry": ("restgdf._models.crawl", "CrawlServiceEntry"),
    "CrawlReport": ("restgdf._models.crawl", "CrawlReport"),
}


def __getattr__(name: str) -> Any:
    if name in _REPLACEMENTS:
        warnings.warn(
            (
                f"restgdf._types.{name} is deprecated; "
                f"import {name} from restgdf (pydantic model) instead. "
                "restgdf._types will be removed in 3.x."
            ),
            DeprecationWarning,
            stacklevel=2,
        )
        module_name, attr = _REPLACEMENTS[name]
        return getattr(importlib.import_module(module_name), attr)
    raise AttributeError(f"module 'restgdf._types' has no attribute {name!r}")


__all__ = sorted(_REPLACEMENTS)
