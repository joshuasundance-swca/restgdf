"""Tests for ArcGIS spatial filter payload construction helpers."""

from __future__ import annotations

import json

from aiohttp import ClientResponseError
import pytest

from restgdf.utils._geometry import _apply_dimension_flags
from restgdf.utils._geometry import _iter_coordinate_lists
from restgdf.utils.getinfo import build_spatial_filter_payload


def _skip_on_transient_network_failure(exc: ClientResponseError) -> None:
    """Skip opt-in live tests when the upstream ArcGIS service is unhealthy."""
    if exc.status in {502, 503, 504}:
        pytest.skip(
            f"live ArcGIS service transiently unavailable: HTTP {exc.status}",
        )
    raise exc


class PolygonLike:
    __geo_interface__ = {
        "type": "Polygon",
        "coordinates": [
            [
                (0.0, 0.0),
                (2.0, 0.0),
                (2.0, 1.0),
                (0.0, 1.0),
                (0.0, 0.0),
            ],
        ],
    }


def test_build_spatial_filter_payload_from_geo_interface_polygon() -> None:
    payload = build_spatial_filter_payload(PolygonLike(), in_sr=4326)

    assert payload == {
        "geometry": {
            "rings": [
                [
                    [0.0, 0.0],
                    [2.0, 0.0],
                    [2.0, 1.0],
                    [0.0, 1.0],
                    [0.0, 0.0],
                ],
            ],
        },
        "geometryType": "esriGeometryPolygon",
        "inSR": 4326,
        "spatialRel": "esriSpatialRelIntersects",
    }


def test_build_spatial_filter_payload_normalizes_spatial_reference_mapping() -> None:
    payload = build_spatial_filter_payload(
        {"type": "Point", "coordinates": [1.5, 2.5]},
        in_sr={"wkid": 102100, "latestWkid": 3857},
        spatial_rel="esriSpatialRelWithin",
    )

    assert payload == {
        "geometry": {"x": 1.5, "y": 2.5},
        "geometryType": "esriGeometryPoint",
        "inSR": 3857,
        "spatialRel": "esriSpatialRelWithin",
    }


def test_build_spatial_filter_payload_supports_arcgis_envelopes() -> None:
    payload = build_spatial_filter_payload(
        {
            "xmin": -82.8,
            "ymin": 28.9,
            "xmax": -81.9,
            "ymax": 29.7,
            "zmin": 0.0,
            "zmax": 10.0,
        },
        in_sr={"wkid": 102100, "latestWkid": 3857},
    )

    assert payload == {
        "geometry": {
            "xmin": -82.8,
            "ymin": 28.9,
            "xmax": -81.9,
            "ymax": 29.7,
            "zmin": 0.0,
            "zmax": 10.0,
        },
        "geometryType": "esriGeometryEnvelope",
        "inSR": 3857,
        "spatialRel": "esriSpatialRelIntersects",
    }


def test_build_spatial_filter_payload_preserves_point_z_and_m() -> None:
    payload = build_spatial_filter_payload(
        {"type": "Point", "coordinates": [1.5, 2.5, 3.5, 4.5]},
        in_sr=4326,
    )

    assert payload == {
        "geometry": {"x": 1.5, "y": 2.5, "z": 3.5, "m": 4.5},
        "geometryType": "esriGeometryPoint",
        "inSR": 4326,
        "spatialRel": "esriSpatialRelIntersects",
    }


def test_build_spatial_filter_payload_sets_dimension_flags_for_3d_linestring() -> None:
    payload = build_spatial_filter_payload(
        {
            "type": "LineString",
            "coordinates": [
                [0.0, 0.0, 1.0],
                [2.0, 1.0, 3.0],
            ],
        },
    )

    assert payload == {
        "geometry": {
            "hasZ": True,
            "paths": [[[0.0, 0.0, 1.0], [2.0, 1.0, 3.0]]],
        },
        "geometryType": "esriGeometryPolyline",
        "spatialRel": "esriSpatialRelIntersects",
    }


def test_build_spatial_filter_payload_preserves_arcgis_curve_paths() -> None:
    geometry = {
        "curvePaths": [
            [
                [0.0, 0.0],
                {"c": [[3.0, 3.0], [1.0, 4.0]]},
            ],
        ],
        "spatialReference": {"wkid": 4326},
    }

    payload = build_spatial_filter_payload(geometry, in_sr=4326)

    assert payload == {
        "geometry": geometry,
        "geometryType": "esriGeometryPolyline",
        "inSR": 4326,
        "spatialRel": "esriSpatialRelIntersects",
    }


def test_build_spatial_filter_payload_preserves_arcgis_curve_rings() -> None:
    geometry = {
        "curveRings": [
            [
                [15.0, 15.0, 1.0],
                {"c": [[20.0, 16.0, 3.0], [20.0, 14.0]]},
                [15.0, 15.0, 3.0],
            ],
        ],
        "hasM": True,
        "spatialReference": {"wkid": 4326},
    }

    payload = build_spatial_filter_payload(geometry, in_sr=4326)

    assert payload == {
        "geometry": geometry,
        "geometryType": "esriGeometryPolygon",
        "inSR": 4326,
        "spatialRel": "esriSpatialRelIntersects",
    }


@pytest.mark.asyncio
@pytest.mark.network
async def test_build_spatial_filter_payload_curve_rings_live_query(
    client_session,
) -> None:
    geometry = {
        "curveRings": [
            [
                [-124.0, 32.0],
                {"c": [[-114.0, 42.0], [-119.0, 46.0]]},
                [-124.0, 32.0],
            ],
        ],
        "spatialReference": {"wkid": 4326},
    }
    payload = build_spatial_filter_payload(geometry, in_sr=4326)

    async with client_session.get(
        "https://sampleserver6.arcgisonline.com/arcgis/rest/services/Census/MapServer/3/query",
        params={
            "where": "1=1",
            "geometry": json.dumps(payload["geometry"]),
            "geometryType": payload["geometryType"],
            "inSR": payload["inSR"],
            "spatialRel": payload["spatialRel"],
            "returnCountOnly": "true",
            "f": "pjson",
        },
    ) as response:
        try:
            response.raise_for_status()
        except ClientResponseError as exc:
            _skip_on_transient_network_failure(exc)
        data = await response.json(content_type=None)

    assert isinstance(data.get("count"), int)
    assert data["count"] > 0


@pytest.mark.asyncio
@pytest.mark.network
async def test_build_spatial_filter_payload_curve_paths_live_query(
    client_session,
) -> None:
    geometry = {
        "curvePaths": [
            [
                [-124.0, 32.0],
                {"c": [[-114.0, 42.0], [-119.0, 46.0]]},
            ],
        ],
        "spatialReference": {"wkid": 4326},
    }
    payload = build_spatial_filter_payload(geometry, in_sr=4326)

    async with client_session.get(
        "https://sampleserver6.arcgisonline.com/arcgis/rest/services/Census/MapServer/3/query",
        params={
            "where": "1=1",
            "geometry": json.dumps(payload["geometry"]),
            "geometryType": payload["geometryType"],
            "inSR": payload["inSR"],
            "spatialRel": payload["spatialRel"],
            "returnCountOnly": "true",
            "f": "pjson",
        },
    ) as response:
        try:
            response.raise_for_status()
        except ClientResponseError as exc:
            _skip_on_transient_network_failure(exc)
        data = await response.json(content_type=None)

    assert isinstance(data.get("count"), int)
    assert data["count"] > 0


def test_build_spatial_filter_payload_rejects_feature_collections() -> None:
    with pytest.raises(ValueError, match="FeatureCollection"):
        build_spatial_filter_payload(
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "geometry": {
                            "type": "Polygon",
                            "coordinates": [[(0, 0), (1, 0), (1, 1), (0, 0)]],
                        },
                    },
                ],
            },
        )


# --- ArcGIS-JSON passthrough branches (mapping already in ArcGIS shape) ---


def test_build_spatial_filter_payload_passes_through_arcgis_point() -> None:
    # A native ArcGIS point geometry (esri geometry JSON), not GeoJSON.
    payload = build_spatial_filter_payload(
        {"x": -118.2437, "y": 34.0522, "spatialReference": {"wkid": 4326}},
        in_sr=4326,
    )

    assert payload == {
        "geometry": {
            "x": -118.2437,
            "y": 34.0522,
            "spatialReference": {"wkid": 4326},
        },
        "geometryType": "esriGeometryPoint",
        "inSR": 4326,
        "spatialRel": "esriSpatialRelIntersects",
    }


def test_build_spatial_filter_payload_passes_through_arcgis_multipoint() -> None:
    # Native ArcGIS multipoint geometry JSON.
    payload = build_spatial_filter_payload(
        {
            "points": [[-118.24, 34.05], [-117.16, 32.72]],
            "spatialReference": {"wkid": 4326},
        },
    )

    assert payload == {
        "geometry": {
            "points": [[-118.24, 34.05], [-117.16, 32.72]],
            "spatialReference": {"wkid": 4326},
        },
        "geometryType": "esriGeometryMultipoint",
        "spatialRel": "esriSpatialRelIntersects",
    }


def test_build_spatial_filter_payload_rejects_ambiguous_arcgis_mapping() -> None:
    # Looks like ArcGIS geometry (has "x") but carries no "y" -> unsupported.
    with pytest.raises(ValueError, match="Unsupported ArcGIS geometry mapping"):
        build_spatial_filter_payload({"x": -118.24})


# --- GeoJSON array geometries: Z/M flags, MultiPoint, MultiLineString, MultiPolygon ---


def test_build_spatial_filter_payload_sets_z_and_m_flags_for_multipoint() -> None:
    # GeoJSON MultiPoint with (x, y, z, m) ordinates -> hasZ and hasM.
    payload = build_spatial_filter_payload(
        {
            "type": "MultiPoint",
            "coordinates": [
                [-118.24, 34.05, 100.0, 1.0],
                [-117.16, 32.72, 120.0, 2.0],
            ],
        },
        in_sr=4326,
    )

    assert payload == {
        "geometry": {
            "points": [
                [-118.24, 34.05, 100.0, 1.0],
                [-117.16, 32.72, 120.0, 2.0],
            ],
            "hasZ": True,
            "hasM": True,
        },
        "geometryType": "esriGeometryMultipoint",
        "inSR": 4326,
        "spatialRel": "esriSpatialRelIntersects",
    }


def test_build_spatial_filter_payload_converts_multilinestring() -> None:
    payload = build_spatial_filter_payload(
        {
            "type": "MultiLineString",
            "coordinates": [
                [[-118.5, 34.0], [-118.4, 34.1]],
                [[-118.3, 34.2], [-118.2, 34.3]],
            ],
        },
        in_sr=4326,
    )

    assert payload == {
        "geometry": {
            "paths": [
                [[-118.5, 34.0], [-118.4, 34.1]],
                [[-118.3, 34.2], [-118.2, 34.3]],
            ],
        },
        "geometryType": "esriGeometryPolyline",
        "inSR": 4326,
        "spatialRel": "esriSpatialRelIntersects",
    }


def test_build_spatial_filter_payload_flattens_multipolygon_rings() -> None:
    # GeoJSON MultiPolygon (two disjoint square polygons) -> flat esri rings.
    payload = build_spatial_filter_payload(
        {
            "type": "MultiPolygon",
            "coordinates": [
                [[[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0], [0.0, 0.0]]],
                [[[5.0, 5.0], [6.0, 5.0], [6.0, 6.0], [5.0, 6.0], [5.0, 5.0]]],
            ],
        },
        in_sr=4326,
    )

    assert payload == {
        "geometry": {
            "rings": [
                [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0], [0.0, 0.0]],
                [[5.0, 5.0], [6.0, 5.0], [6.0, 6.0], [5.0, 6.0], [5.0, 5.0]],
            ],
        },
        "geometryType": "esriGeometryPolygon",
        "inSR": 4326,
        "spatialRel": "esriSpatialRelIntersects",
    }


# --- GeoJSON Feature wrapper handling ---


def test_build_spatial_filter_payload_unwraps_geojson_feature() -> None:
    payload = build_spatial_filter_payload(
        {
            "type": "Feature",
            "properties": {"name": "downtown"},
            "geometry": {"type": "Point", "coordinates": [-118.24, 34.05]},
        },
        in_sr=4326,
    )

    assert payload == {
        "geometry": {"x": -118.24, "y": 34.05},
        "geometryType": "esriGeometryPoint",
        "inSR": 4326,
        "spatialRel": "esriSpatialRelIntersects",
    }


def test_build_spatial_filter_payload_rejects_feature_without_geometry() -> None:
    with pytest.raises(ValueError, match="Feature input must include a geometry"):
        build_spatial_filter_payload(
            {"type": "Feature", "properties": {}, "geometry": None},
        )


# --- error branches: malformed point, wrong input type ---


def test_build_spatial_filter_payload_rejects_underspecified_point() -> None:
    with pytest.raises(ValueError, match="at least x and y"):
        build_spatial_filter_payload({"type": "Point", "coordinates": [-118.24]})


def test_build_spatial_filter_payload_rejects_unsupported_geojson_type() -> None:
    with pytest.raises(ValueError, match="Unsupported geometry type"):
        build_spatial_filter_payload(
            {
                "type": "GeometryCollection",
                "geometries": [{"type": "Point", "coordinates": [-118.24, 34.05]}],
            },
        )


def test_build_spatial_filter_payload_rejects_non_mapping_input() -> None:
    with pytest.raises(TypeError, match="__geo_interface__"):
        build_spatial_filter_payload("POINT(-118.24 34.05)")


# --- spatial reference: WKT-only reference has no EPSG, preserved as raw inSR ---


def test_build_spatial_filter_payload_preserves_wkt_spatial_reference() -> None:
    # A WKT-defined spatial reference carries no wkid/latestWkid, so the payload
    # must fall back to emitting the raw reference dict as inSR (BL-23 raw path).
    wkt_sr = {
        "wkt": (
            'PROJCS["NAD_1983_UTM_Zone_11N",'
            'GEOGCS["GCS_North_American_1983",'
            'DATUM["D_North_American_1983",'
            'SPHEROID["GRS_1980",6378137.0,298.257222101]]]]'
        ),
    }
    payload = build_spatial_filter_payload(
        {"x": 500000.0, "y": 3762000.0},
        in_sr=wkt_sr,
    )

    assert payload == {
        "geometry": {"x": 500000.0, "y": 3762000.0},
        "geometryType": "esriGeometryPoint",
        "inSR": wkt_sr,
        "spatialRel": "esriSpatialRelIntersects",
    }


# --- direct helper coverage for defensive branches unreachable via public shapes ---


def test_apply_dimension_flags_is_noop_when_flags_unsupported() -> None:
    # Envelope-style geometries never carry per-vertex Z/M, so callers pass
    # supports_flags=False and the geometry is returned untouched.
    geometry: dict[str, object] = {
        "xmin": -118.5,
        "ymin": 34.0,
        "xmax": -118.0,
        "ymax": 34.5,
    }
    result = _apply_dimension_flags(
        geometry,
        [[-118.5, 34.0, 10.0, 1.0]],
        supports_flags=False,
    )

    assert result is geometry
    assert "hasZ" not in result
    assert "hasM" not in result


def test_iter_coordinate_lists_ignores_scalar_leaves() -> None:
    # Defensive guard: a bare scalar (not a coordinate sequence) yields nothing.
    assert list(_iter_coordinate_lists(34.05)) == []
