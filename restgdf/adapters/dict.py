"""Core-install safe row-shaped dict adapters.

Thin, stable aliases for the row-flattening helpers in
:mod:`restgdf.utils.getgdf`. No heavy dependencies — this module is safe to
import and use on a minimal restgdf install.

See also
--------
:func:`restgdf.compat.as_dict`, :func:`restgdf.compat.as_json_dict`
    Plain-dict views of restgdf pydantic models (metadata, crawl reports,
    etc.). Re-exported from this module so all dict-shaped adapters live
    under a single namespace.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from restgdf.compat import as_dict, as_json_dict
from restgdf.utils.getgdf import _feature_to_row_dict

__all__ = ["as_dict", "as_json_dict", "feature_to_row", "features_to_rows"]


def feature_to_row(feature: dict[str, Any]) -> dict[str, Any]:
    """Flatten a single ArcGIS feature into a row-shaped dict.

    Stable public alias for :func:`restgdf.utils.getgdf._feature_to_row_dict`.
    """
    return _feature_to_row_dict(feature)


def features_to_rows(features: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Materialize an iterable of ArcGIS features as row-shaped dicts."""
    return [feature_to_row(feature) for feature in features]
