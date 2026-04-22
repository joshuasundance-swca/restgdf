"""BL-23 red tests — spatial_reference normalization to EPSG int.

After BL-23 green:
- NormalizedGeometry.spatial_reference → int | None (EPSG only)
- NormalizedGeometry._raw_spatial_reference → dict (private, raw SR dict)
- normalize_spatial_reference() helper extracts latestWkid > wkid > None
"""

from __future__ import annotations

import pytest

from restgdf._models.responses import (
    FeaturesResponse,
    NormalizedGeometry,
    iter_normalized_features,
)


def _features_response(features, sr=None):
    return FeaturesResponse.model_construct(
        features=features,
        object_id_field_name="OBJECTID",
        spatial_reference=sr,
    )


# ---- NormalizedGeometry.spatial_reference must be int | None --------


def test_sr_wkid_normalizes_to_int():
    """{"wkid": 4326} → spatial_reference == 4326."""
    response = _features_response(
        [{"attributes": {"OBJECTID": 1}, "geometry": {"x": 1, "y": 2, "spatialReference": {"wkid": 4326}}}],
    )
    feat = next(iter_normalized_features(response))
    assert feat.geometry is not None
    assert feat.geometry.spatial_reference == 4326
    assert isinstance(feat.geometry.spatial_reference, int)


def test_sr_latestwkid_preferred_over_wkid():
    """latestWkid takes precedence when both are present."""
    response = _features_response(
        [{"attributes": {}, "geometry": {"x": 1, "y": 2, "spatialReference": {"wkid": 102100, "latestWkid": 3857}}}],
    )
    feat = next(iter_normalized_features(response))
    assert feat.geometry is not None
    assert feat.geometry.spatial_reference == 3857


def test_sr_none_when_absent():
    """Missing spatialReference → spatial_reference == None."""
    response = _features_response([{"attributes": {}, "geometry": {"x": 1, "y": 2}}])
    feat = next(iter_normalized_features(response))
    assert feat.geometry is not None
    assert feat.geometry.spatial_reference is None


def test_sr_kwarg_fills_as_int():
    """sr=4326 kwarg → spatial_reference == 4326 (int)."""
    response = _features_response([{"geometry": {"x": 1, "y": 2}}])
    feat = next(iter_normalized_features(response, sr=4326))
    assert feat.geometry is not None
    assert feat.geometry.spatial_reference == 4326
    assert isinstance(feat.geometry.spatial_reference, int)


def test_raw_sr_preserved_as_private_attr():
    """_raw_spatial_reference preserves the original dict."""
    response = _features_response(
        [{"attributes": {}, "geometry": {"x": 1, "y": 2, "spatialReference": {"wkid": 4326, "latestWkid": 4326}}}],
    )
    feat = next(iter_normalized_features(response))
    assert feat.geometry is not None
    assert feat.geometry._raw_spatial_reference == {"wkid": 4326, "latestWkid": 4326}
