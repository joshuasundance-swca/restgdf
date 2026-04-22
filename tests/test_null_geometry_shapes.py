"""R-27 red tests — null geometry 5-shape normalization.

Five forms of "null geometry" that servers emit in the wild:
  1. ``None``
  2. ``{}`` (empty dict)
  3. missing ``"geometry"`` key
  4. ``{"x": None, "y": None}``
  5. ``{"x": "NaN", "y": "NaN"}``

After R-27 green, *all* five should yield ``geometry is None`` on the
NormalizedFeature — callers should not need to check coords for
emptiness or sentinel NaN values.
"""

from __future__ import annotations


from restgdf._models.responses import (
    FeaturesResponse,
    iter_normalized_features,
)


def _single_feature_geometry(geometry_value, *, include_key: bool = True):
    """Build a FeaturesResponse with one feature and extract its geometry."""
    if include_key:
        raw = [{"attributes": {"OBJECTID": 1}, "geometry": geometry_value}]
    else:
        raw = [{"attributes": {"OBJECTID": 1}}]
    response = FeaturesResponse(features=raw)
    feature = next(iter_normalized_features(response))
    return feature.geometry


class TestNullGeometryShapes:
    """All five null-geometry shapes must yield ``geometry is None``."""

    def test_shape1_none(self):
        geo = _single_feature_geometry(None)
        assert geo is None

    def test_shape2_empty_dict(self):
        geo = _single_feature_geometry({})
        assert geo is None, f"empty dict should yield None geometry, got {geo}"

    def test_shape3_missing_key(self):
        geo = _single_feature_geometry(None, include_key=False)
        assert geo is None

    def test_shape4_x_none_y_none(self):
        geo = _single_feature_geometry({"x": None, "y": None})
        assert geo is None, f"{{x:None, y:None}} should yield None geometry, got {geo}"

    def test_shape5_x_nan_y_nan(self):
        geo = _single_feature_geometry({"x": "NaN", "y": "NaN"})
        assert (
            geo is None
        ), f"{{x:'NaN', y:'NaN'}} should yield None geometry, got {geo}"

    def test_shape6_spatial_reference_only(self):
        """A dict with ONLY SR / has-z / has-m keys and no coordinate keys
        is a degenerate null geometry (``coord_keys`` empty at
        ``_is_null_geometry``). Covers the short-circuit branch."""
        geo = _single_feature_geometry(
            {"spatialReference": {"wkid": 4326}, "hasZ": False},
        )
        assert geo is None, f"SR-only dict should yield None geometry, got {geo}"
