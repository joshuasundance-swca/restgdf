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
    """Flatten a single ArcGIS feature envelope into a row-shaped dict.

    Merges ``feature["attributes"]`` with a ``"geometry"`` key holding the
    raw ArcGIS geometry dict verbatim. Safe on a base install — no
    pandas/geopandas dependency.

    Parameters
    ----------
    feature:
        A raw ArcGIS feature dict as returned by a ``/query`` response
        (the elements of ``response["features"]``).

    Returns
    -------
    dict[str, Any]
        ``{**feature["attributes"], "geometry": feature.get("geometry")}``.

    Examples
    --------
    >>> feature_to_row({"attributes": {"OBJECTID": 1}, "geometry": {"x": 0, "y": 0}})
    {'OBJECTID': 1, 'geometry': {'x': 0, 'y': 0}}

    See Also
    --------
    :meth:`restgdf.FeatureLayer.stream_rows`
        High-level async iterator that yields row-shaped dicts directly
        from a live layer.
    :func:`restgdf.utils.getgdf._feature_to_row_dict`
        Underlying flattening primitive.
    """
    return _feature_to_row_dict(feature)


def features_to_rows(features: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Materialize an iterable of ArcGIS features as a list of row-shaped dicts.

    Parameters
    ----------
    features:
        Any iterable of raw ArcGIS feature dicts (e.g. a page's
        ``"features"`` list).

    Returns
    -------
    list[dict[str, Any]]
        One :func:`feature_to_row` output per input feature.

    Examples
    --------
    >>> features_to_rows([{"attributes": {"OBJECTID": 1}, "geometry": None}])
    [{'OBJECTID': 1, 'geometry': None}]

    See Also
    --------
    :meth:`restgdf.FeatureLayer.stream_feature_batches`
        Async iterator yielding one ``list[feature_dict]`` per page; feed
        each batch through this helper to materialize row tables.
    """
    return [feature_to_row(feature) for feature in features]
