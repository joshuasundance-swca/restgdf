"""Geometry payload helpers for ArcGIS REST query parameters.

Private submodule; public helpers are re-exported by
``restgdf.utils.getinfo`` to preserve stable import paths.
"""

from __future__ import annotations

from collections.abc import Iterable
from collections.abc import Mapping
from collections.abc import Sequence
from typing import Any

from restgdf.utils._metadata import normalize_spatial_reference


def _is_arcgis_geometry_mapping(geometry: Mapping[str, object]) -> bool:
    """Return whether the mapping already looks like ArcGIS geometry JSON."""
    return {"xmin", "ymin", "xmax", "ymax"}.issubset(geometry) or any(
        key in geometry
        for key in ("x", "points", "paths", "curvePaths", "rings", "curveRings")
    )


def _infer_arcgis_geometry_type(geometry: Mapping[str, object]) -> str:
    """Infer the ArcGIS geometry type from ArcGIS JSON keys."""
    if "x" in geometry and "y" in geometry:
        return "esriGeometryPoint"
    if "points" in geometry:
        return "esriGeometryMultipoint"
    if "paths" in geometry or "curvePaths" in geometry:
        return "esriGeometryPolyline"
    if "rings" in geometry or "curveRings" in geometry:
        return "esriGeometryPolygon"
    if {"xmin", "ymin", "xmax", "ymax"}.issubset(geometry):
        return "esriGeometryEnvelope"
    raise ValueError("Unsupported ArcGIS geometry mapping.")


def _to_coordinate_list(coords: Sequence[object]) -> list[object]:
    """Convert coordinate tuples from geo-interface inputs into JSON lists."""
    return list(coords)


def _iter_coordinate_lists(candidate: object) -> Iterable[list[object]]:
    """Yield point coordinate lists from nested GeoJSON-style arrays."""
    if isinstance(candidate, Sequence) and not isinstance(
        candidate,
        (str, bytes, bytearray),
    ):
        if candidate and all(not isinstance(item, (list, tuple)) for item in candidate):
            yield _to_coordinate_list(candidate)
            return
        for item in candidate:
            yield from _iter_coordinate_lists(item)


def _coordinate_dimension_flags(candidate: object) -> tuple[bool, bool]:
    """Infer whether nested coordinate arrays carry Z and/or M ordinates."""
    has_z = False
    has_m = False
    for coordinate in _iter_coordinate_lists(candidate):
        if len(coordinate) >= 3:
            has_z = True
        if len(coordinate) >= 4:
            has_m = True
        if has_z and has_m:
            break
    return has_z, has_m


def _apply_dimension_flags(
    geometry: dict[str, object],
    coordinates: object,
    *,
    supports_flags: bool,
) -> dict[str, object]:
    """Annotate array-based ArcGIS geometries with hasZ/hasM when needed."""
    if not supports_flags:
        return geometry

    has_z, has_m = _coordinate_dimension_flags(coordinates)
    if has_z:
        geometry["hasZ"] = True
    if has_m:
        geometry["hasM"] = True
    return geometry


def _geojson_to_arcgis_geometry(
    geometry: Mapping[str, object],
) -> tuple[dict[str, object], str]:
    """Convert a GeoJSON-style geometry mapping into ArcGIS JSON."""
    geometry_type = geometry.get("type")
    if geometry_type == "Feature":
        feature_geometry = geometry.get("geometry")
        if not isinstance(feature_geometry, Mapping):
            raise ValueError("GeoJSON Feature input must include a geometry mapping.")
        return _geojson_to_arcgis_geometry(feature_geometry)
    if geometry_type == "FeatureCollection":
        raise ValueError(
            "FeatureCollection inputs are not supported; pass a single dissolved geometry.",
        )

    coordinates = geometry.get("coordinates")
    if geometry_type == "Point" and isinstance(coordinates, Sequence):
        if len(coordinates) < 2:
            raise ValueError("Point coordinates must contain at least x and y.")
        point: dict[str, object] = {"x": coordinates[0], "y": coordinates[1]}
        if len(coordinates) >= 3:
            point["z"] = coordinates[2]
        if len(coordinates) >= 4:
            point["m"] = coordinates[3]
        return point, "esriGeometryPoint"
    if geometry_type == "MultiPoint" and isinstance(coordinates, Sequence):
        return (
            _apply_dimension_flags(
                {
                    "points": [_to_coordinate_list(point) for point in coordinates],
                },
                coordinates,
                supports_flags=True,
            ),
            "esriGeometryMultipoint",
        )
    if geometry_type == "LineString" and isinstance(coordinates, Sequence):
        return (
            _apply_dimension_flags(
                {
                    "paths": [[_to_coordinate_list(point) for point in coordinates]],
                },
                coordinates,
                supports_flags=True,
            ),
            "esriGeometryPolyline",
        )
    if geometry_type == "MultiLineString" and isinstance(coordinates, Sequence):
        return (
            _apply_dimension_flags(
                {
                    "paths": [
                        [_to_coordinate_list(point) for point in path]
                        for path in coordinates
                    ],
                },
                coordinates,
                supports_flags=True,
            ),
            "esriGeometryPolyline",
        )
    if geometry_type == "Polygon" and isinstance(coordinates, Sequence):
        return (
            _apply_dimension_flags(
                {
                    "rings": [
                        [_to_coordinate_list(point) for point in ring]
                        for ring in coordinates
                    ],
                },
                coordinates,
                supports_flags=True,
            ),
            "esriGeometryPolygon",
        )
    if geometry_type == "MultiPolygon" and isinstance(coordinates, Sequence):
        rings: list[list[list[object]]] = []
        for polygon in coordinates:
            rings.extend(
                [[_to_coordinate_list(point) for point in ring] for ring in polygon],
            )
        return (
            _apply_dimension_flags(
                {"rings": rings},
                coordinates,
                supports_flags=True,
            ),
            "esriGeometryPolygon",
        )

    raise ValueError(f"Unsupported geometry type: {geometry_type!r}")


def _coerce_geometry_mapping(geometry: object) -> tuple[dict[str, object], str]:
    """Normalize mapping-like or geo-interface geometry inputs."""
    candidate = getattr(geometry, "__geo_interface__", geometry)
    if not isinstance(candidate, Mapping):
        raise TypeError(
            "geometry must be an ArcGIS JSON mapping or expose __geo_interface__.",
        )

    geometry_mapping = dict(candidate)
    if _is_arcgis_geometry_mapping(geometry_mapping):
        return geometry_mapping, _infer_arcgis_geometry_type(geometry_mapping)
    return _geojson_to_arcgis_geometry(geometry_mapping)


def build_spatial_filter_payload(
    geometry: object,
    *,
    in_sr: int | str | Mapping[str, Any] | None = None,
    spatial_rel: str = "esriSpatialRelIntersects",
) -> dict[str, object]:
    """Build an ArcGIS REST spatial-filter payload fragment.

    Accepts ArcGIS JSON mappings directly, GeoJSON-style mappings, or any
    object that exposes ``__geo_interface__`` such as shapely geometries.
    """
    geometry_payload, geometry_type = _coerce_geometry_mapping(geometry)
    sr_input = dict(in_sr) if isinstance(in_sr, Mapping) else in_sr
    epsg, raw_sr = normalize_spatial_reference(sr_input)

    payload: dict[str, object] = {
        "geometry": geometry_payload,
        "geometryType": geometry_type,
        "spatialRel": spatial_rel,
    }
    if epsg is not None:
        payload["inSR"] = epsg
    elif raw_sr is not None:
        payload["inSR"] = raw_sr
    return payload
