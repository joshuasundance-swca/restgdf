"""Tests for :mod:`restgdf._models.responses` normalized feature helpers (BL-28)."""

from __future__ import annotations

from restgdf._models._drift import PermissiveModel
from restgdf._models.responses import (
    FeaturesResponse,
    NormalizedFeature,
    NormalizedGeometry,
    iter_normalized_features,
)


def _features_response(
    features: list[dict],
    *,
    object_id_field_name: str | None = None,
) -> FeaturesResponse:
    payload: dict[str, object] = {"features": features}
    if object_id_field_name is not None:
        payload["objectIdFieldName"] = object_id_field_name
    return FeaturesResponse.model_validate(payload)


def test_normalized_types_are_permissive_models() -> None:
    assert issubclass(NormalizedGeometry, PermissiveModel)
    assert issubclass(NormalizedFeature, PermissiveModel)


def test_empty_response_yields_no_features() -> None:
    assert list(iter_normalized_features(_features_response([]))) == []


def test_point_feature_hoists_object_id() -> None:
    response = _features_response(
        [
            {
                "attributes": {"OBJECTID": 7, "name": "A"},
                "geometry": {
                    "x": 1.0,
                    "y": 2.0,
                    "spatialReference": {"wkid": 4326},
                },
            },
        ],
        object_id_field_name="OBJECTID",
    )
    features = list(iter_normalized_features(response))
    assert len(features) == 1
    feature = features[0]
    assert feature.object_id == 7
    assert feature.attributes == {"OBJECTID": 7, "name": "A"}
    assert feature.geometry is not None
    assert feature.geometry.type == "point"
    assert feature.geometry.coords == {"x": 1.0, "y": 2.0}
    assert feature.geometry.spatial_reference == 4326


def test_polygon_feature_type_inferred() -> None:
    response = _features_response(
        [
            {
                "attributes": {},
                "geometry": {"rings": [[[0, 0], [1, 0], [1, 1], [0, 0]]]},
            },
        ],
    )
    feature = next(iter_normalized_features(response))
    assert feature.geometry is not None
    assert feature.geometry.type == "polygon"
    assert feature.geometry.coords == {"rings": [[[0, 0], [1, 0], [1, 1], [0, 0]]]}


def test_polyline_feature_type_inferred() -> None:
    response = _features_response(
        [{"attributes": {}, "geometry": {"paths": [[[0, 0], [1, 1]]]}}],
    )
    feature = next(iter_normalized_features(response))
    assert feature.geometry is not None
    assert feature.geometry.type == "polyline"


def test_multipoint_feature_type_inferred() -> None:
    response = _features_response(
        [{"attributes": {}, "geometry": {"points": [[0, 0], [1, 1]]}}],
    )
    feature = next(iter_normalized_features(response))
    assert feature.geometry is not None
    assert feature.geometry.type == "multipoint"


def test_envelope_feature_type_inferred() -> None:
    response = _features_response(
        [
            {
                "attributes": {},
                "geometry": {"xmin": 0, "ymin": 0, "xmax": 1, "ymax": 1},
            },
        ],
    )
    feature = next(iter_normalized_features(response))
    assert feature.geometry is not None
    assert feature.geometry.type == "envelope"


def test_unknown_geometry_shape_falls_back_to_none_type() -> None:
    response = _features_response(
        [{"attributes": {}, "geometry": {"weird": [1, 2, 3]}}],
    )
    feature = next(iter_normalized_features(response))
    assert feature.geometry is not None
    assert feature.geometry.type is None
    assert feature.geometry.coords == {"weird": [1, 2, 3]}


def test_feature_without_geometry_yields_none() -> None:
    response = _features_response([{"attributes": {"k": 1}}])
    feature = next(iter_normalized_features(response))
    assert feature.geometry is None
    assert feature.attributes == {"k": 1}


def test_feature_without_attributes_yields_empty_dict() -> None:
    response = _features_response([{"geometry": {"x": 0, "y": 0}}])
    feature = next(iter_normalized_features(response))
    assert feature.attributes == {}


def test_oid_field_override_beats_response_field() -> None:
    response = _features_response(
        [{"attributes": {"CUSTOM_OID": 11, "OBJECTID": 99}}],
        object_id_field_name="OBJECTID",
    )
    feature = next(iter_normalized_features(response, oid_field="CUSTOM_OID"))
    assert feature.object_id == 11


def test_oid_hoisting_coerces_string_integers() -> None:
    response = _features_response(
        [{"attributes": {"OBJECTID": "42"}}],
        object_id_field_name="OBJECTID",
    )
    feature = next(iter_normalized_features(response))
    assert feature.object_id == 42


def test_oid_hoisting_tolerates_unparsable_value() -> None:
    response = _features_response(
        [{"attributes": {"OBJECTID": "abc"}}],
        object_id_field_name="OBJECTID",
    )
    feature = next(iter_normalized_features(response))
    assert feature.object_id is None


def test_oid_hoisting_missing_field_stays_none() -> None:
    response = _features_response([{"attributes": {"name": "a"}}])
    feature = next(iter_normalized_features(response, oid_field="OBJECTID"))
    assert feature.object_id is None


def test_oid_hoisting_non_integral_float_truncates() -> None:
    # Pins current behavior: ``int(42.5)`` truncates to ``42``. The
    # normalization path uses raw ``int(...)`` coercion (responses.py
    # ``iter_normalized_features``) so a non-integral float silently
    # loses its fractional part. Callers that need strict integer
    # semantics must pre-filter. If this policy changes, update the
    # assertion rather than the docstring.
    response = _features_response(
        [{"attributes": {"OBJECTID": 42.5}}],
        object_id_field_name="OBJECTID",
    )
    feature = next(iter_normalized_features(response))
    assert feature.object_id == 42


def test_sr_kwarg_fills_when_geometry_missing_sr() -> None:
    response = _features_response([{"geometry": {"x": 1, "y": 2}}])
    feature = next(iter_normalized_features(response, sr=4326))
    assert feature.geometry is not None
    assert feature.geometry.spatial_reference == 4326


def test_server_sr_wins_over_kwarg() -> None:
    response = _features_response(
        [{"geometry": {"x": 1, "y": 2, "spatialReference": {"wkid": 3857}}}],
    )
    feature = next(iter_normalized_features(response, sr=4326))
    assert feature.geometry is not None
    assert feature.geometry.spatial_reference == 3857


def test_non_mapping_feature_entry_is_skipped() -> None:
    # Construct the envelope directly, bypassing pydantic validation, so
    # we can exercise the iterator's defense-in-depth guard against
    # non-mapping feature entries (which the wire-level list[dict] type
    # would otherwise reject at parse time).
    response = FeaturesResponse.model_construct(
        features=["not a feature", {"attributes": {"k": 1}}],  # type: ignore[list-item]
    )
    features = list(iter_normalized_features(response))
    assert len(features) == 1
    assert features[0].attributes == {"k": 1}


def test_geometry_has_z_and_has_m_defaults_and_aliases() -> None:
    default = NormalizedGeometry()
    assert default.has_z is False
    assert default.has_m is False

    aliased = NormalizedGeometry.model_validate({"hasZ": True, "hasM": True})
    assert aliased.has_z is True
    assert aliased.has_m is True


def test_point_feature_propagates_has_z_and_has_m() -> None:
    response = _features_response(
        [
            {
                "attributes": {},
                "geometry": {"x": 1, "y": 2, "z": 3, "hasZ": True, "hasM": True},
            },
        ],
    )
    feature = next(iter_normalized_features(response))
    assert feature.geometry is not None
    assert feature.geometry.type == "point"
    assert feature.geometry.has_z is True
    assert feature.geometry.has_m is True


def test_polyline_feature_propagates_has_z() -> None:
    response = _features_response(
        [
            {
                "attributes": {},
                "geometry": {"paths": [[[0, 0, 5], [1, 1, 5]]], "hasZ": True},
            },
        ],
    )
    feature = next(iter_normalized_features(response))
    assert feature.geometry is not None
    assert feature.geometry.has_z is True
    assert feature.geometry.has_m is False


def test_empty_rings_polygon_preserved_as_empty_coords() -> None:
    response = _features_response([{"attributes": {}, "geometry": {"rings": []}}])
    feature = next(iter_normalized_features(response))
    assert feature.geometry is not None
    assert feature.geometry.type == "polygon"
    assert feature.geometry.coords == {"rings": []}


def test_empty_paths_polyline_preserved_as_empty_coords() -> None:
    response = _features_response([{"attributes": {}, "geometry": {"paths": []}}])
    feature = next(iter_normalized_features(response))
    assert feature.geometry is not None
    assert feature.geometry.type == "polyline"
    assert feature.geometry.coords == {"paths": []}


def test_empty_dict_geometry_yields_none_typed_geometry() -> None:
    # An empty geometry dict is still a Mapping, so the iterator
    # produces a NormalizedGeometry with unknown type and empty coords
    # rather than crashing or returning None. This pins defense-in-
    # depth behavior against vendor payloads that omit coord keys.
    response = _features_response([{"attributes": {"k": 1}, "geometry": {}}])
    feature = next(iter_normalized_features(response))
    assert feature.geometry is not None
    assert feature.geometry.type is None
    assert feature.geometry.coords == {}


def test_curve_ring_geometry_falls_back_to_none_type() -> None:
    response = _features_response(
        [
            {
                "attributes": {},
                "geometry": {"curveRings": [[[0, 0], {"c": [[1, 1], [0.5, 0.5]]}]]},
            },
        ],
    )
    feature = next(iter_normalized_features(response))
    assert feature.geometry is not None
    assert feature.geometry.type is None
    assert "curveRings" in feature.geometry.coords


def test_curve_path_geometry_falls_back_to_none_type() -> None:
    response = _features_response(
        [
            {
                "attributes": {},
                "geometry": {"curvePaths": [[[0, 0], {"c": [[1, 1], [0.5, 0.5]]}]]},
            },
        ],
    )
    feature = next(iter_normalized_features(response))
    assert feature.geometry is not None
    assert feature.geometry.type is None
    assert "curvePaths" in feature.geometry.coords
