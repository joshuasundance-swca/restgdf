"""Tests for ArcGIS spatial filter payload construction helpers."""

from __future__ import annotations

import json

from aiohttp import ClientResponseError
import pytest

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
