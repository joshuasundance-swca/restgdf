"""Pydantic response-envelope models.

Runtime-validated ArcGIS payloads consumed by restgdf, split into two
tiers by design (see :mod:`restgdf._models._drift`):

* Permissive: :class:`FieldSpec`, :class:`ErrorInfo`, :class:`Feature`,
  :class:`LayerMetadata`, :class:`ServiceInfo`.
* Strict: :class:`ErrorResponse`.

Subsequent slices (query envelopes, crawl, credentials) add more models
alongside these in this module.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from typing import Any

from pydantic import AliasChoices, Field, PrivateAttr, field_validator

from restgdf._models._drift import PermissiveModel, StrictModel


class FieldSpec(PermissiveModel):
    """A field descriptor entry in a layer's ``fields`` list.

    Real ArcGIS servers emit an open-ended set of keys here
    (``sqlType``, ``defaultValue``, ``modelName``, ...). Permissive tier
    preserves them via ``extra="allow"`` while declaring the handful of
    keys restgdf actually consumes.
    """

    name: str | None = None
    type: str | None = None
    alias: str | None = None
    length: int | None = None
    domain: dict | None = None
    nullable: bool | None = None
    editable: bool | None = None


class ErrorInfo(PermissiveModel):
    """Inner error payload: ``{"code": int, "message": str, ...}``.

    ArcGIS error payloads routinely carry diagnostic extras
    (``messageCode``, ``errorCode``, ``details``) that restgdf does not
    need but should not strip away.
    """

    code: int | None = None
    message: str | None = None
    details: list[str] | None = None


class ErrorResponse(StrictModel):
    """Top-level JSON error envelope: ``{"error": {...}}``.

    Strict tier: callers branching on ``isinstance(obj, ErrorResponse)``
    need the ``error`` key to actually be present. Missing-key drift on
    this envelope indicates a protocol-level bug, not vendor variance.
    """

    error: ErrorInfo = Field(...)


class Feature(PermissiveModel):
    """A single feature in :attr:`FeaturesResponse.features`.

    ``attributes`` is declared as a dict but not typed further — ArcGIS
    layer schemas are dynamic. ``geometry`` is optional because non-
    spatial tables and ``returnGeometry=false`` queries omit it.
    """

    attributes: dict[str, Any] | None = None
    geometry: dict[str, Any] | None = None


class AdvancedQueryCapabilities(PermissiveModel):
    """Typed view over the ``advancedQueryCapabilities`` sub-object.

    ArcGIS emits an open-ended set of capability flags here; this model
    declares the ones restgdf routes on (pagination strategy selection,
    `maxRecordCountFactor` clamp) and preserves the rest through
    permissive ``extra="allow"``. The raw dict is still available as
    :attr:`LayerMetadata.advanced_query_capabilities`; this submodel is
    an opt-in typed companion surfaced via
    :attr:`LayerMetadata.advanced_query_capabilities_typed`.
    """

    supports_pagination: bool | None = Field(
        default=None,
        alias="supportsPagination",
        validation_alias=AliasChoices("supportsPagination", "supports_pagination"),
    )
    supports_query_by_oids: bool | None = Field(
        default=None,
        alias="supportsQueryByOIDs",
        validation_alias=AliasChoices("supportsQueryByOIDs", "supports_query_by_oids"),
    )
    supports_return_exceeded_limit_features: bool | None = Field(
        default=None,
        alias="supportsReturnExceededLimitFeatures",
        validation_alias=AliasChoices(
            "supportsReturnExceededLimitFeatures",
            "supports_return_exceeded_limit_features",
        ),
    )
    supports_pagination_on_aggregated_queries: bool | None = Field(
        default=None,
        alias="supportsPaginationOnAggregatedQueries",
        validation_alias=AliasChoices(
            "supportsPaginationOnAggregatedQueries",
            "supports_pagination_on_aggregated_queries",
        ),
    )
    max_record_count_factor: float | None = Field(
        default=None,
        alias="maxRecordCountFactor",
        validation_alias=AliasChoices(
            "maxRecordCountFactor",
            "max_record_count_factor",
        ),
    )


class LayerMetadata(PermissiveModel):
    """Polymorphic ArcGIS REST metadata envelope.

    The same endpoint family (``GET <url>?f=json``) returns per-layer
    metadata (``name``, ``fields``, ``maxRecordCount``, ...), service
    roots (``services``, ``folders``), sub-layer descriptors (``id``),
    and restgdf-enriched payloads (``url``, ``feature_count``). All
    variants parse into this single permissive model; missing fields
    default to ``None`` rather than raise.

    Field aliases accept either camelCase (native ArcGIS) or snake_case
    (Python-native) input via :class:`~pydantic.AliasChoices`, and
    ``model_dump(by_alias=True)`` round-trips back to camelCase so
    downstream serialization stays ArcGIS-compatible.
    """

    name: str | None = None
    id: int | None = None
    type: str | None = None
    fields: list[FieldSpec] | None = None
    max_record_count: int | None = Field(
        default=None,
        alias="maxRecordCount",
        validation_alias=AliasChoices("maxRecordCount", "max_record_count"),
    )
    supports_pagination: bool | None = Field(
        default=None,
        alias="supportsPagination",
        validation_alias=AliasChoices("supportsPagination", "supports_pagination"),
    )
    advanced_query_capabilities: dict[str, Any] | None = Field(
        default=None,
        alias="advancedQueryCapabilities",
        validation_alias=AliasChoices(
            "advancedQueryCapabilities",
            "advanced_query_capabilities",
        ),
    )
    advanced_query_capabilities_typed: AdvancedQueryCapabilities | None = Field(
        default=None,
        alias="advancedQueryCapabilitiesTyped",
        validation_alias=AliasChoices(
            "advancedQueryCapabilitiesTyped",
            "advanced_query_capabilities_typed",
        ),
    )
    layers: list[LayerMetadata] | None = None
    services: list[dict[str, Any]] | None = None
    folders: list[str] | None = None
    url: str | None = None
    feature_count: int | None = None


class ServiceInfo(PermissiveModel):
    """Root ``GET <services_root>?f=json`` envelope.

    A narrower permissive view over the subset of keys a services-root
    crawl consumes (``services`` and ``folders``). Unlike
    :class:`LayerMetadata`, this model does not enrich nested ``services``
    entries into typed objects — the crawl report keeps them as raw
    dicts so per-service merge keys (``name``, ``type``) survive
    unchanged.
    """

    services: list[dict[str, Any]] | None = None
    folders: list[str] | None = None
    layers: list[LayerMetadata] | None = None
    url: str | None = None


LayerMetadata.model_rebuild()


class CountResponse(StrictModel):
    """Envelope for ``?returnCountOnly=true`` query results.

    Strict tier: ArcGIS *always* returns ``count`` for this query shape,
    so a missing/ill-typed key signals a protocol-level incident (for
    example an HTML error page bodied as JSON). :func:`_parse_response`
    surfaces those as :class:`RestgdfResponseError`.
    """

    count: int = Field(...)


class ObjectIdsResponse(StrictModel):
    """Envelope for ``?returnIdsOnly=true`` query results.

    Strict tier. The response is operation-critical: chunked pagination
    in :mod:`restgdf.utils.getgdf` requires both the OID field name and
    the full id list. A zero-row match produces
    ``{"objectIdFieldName": "OBJECTID", "objectIds": null}`` in the
    wild; the ``object_ids`` validator below coerces that ``None`` to an
    empty list so consumers can unconditionally iterate.
    """

    object_id_field_name: str = Field(
        ...,
        alias="objectIdFieldName",
        validation_alias=AliasChoices(
            "objectIdFieldName",
            "objectIdField",
            "object_id_field_name",
        ),
    )
    object_ids: list[int] = Field(
        default_factory=list,
        alias="objectIds",
        validation_alias=AliasChoices("objectIds", "object_ids"),
    )

    @field_validator("object_ids", mode="before")
    @classmethod
    def _coerce_null_to_empty(cls, value: Any) -> Any:
        if value is None:
            return []
        return value


class FeaturesResponse(PermissiveModel):
    """Envelope for ``?f=json`` feature queries.

    Permissive tier: only the envelope keys restgdf consumes are
    declared. ``features`` is kept as a ``list[dict]`` rather than
    ``list[Feature]`` on purpose — validating every feature of a large
    batch with pydantic would be expensive and returns no value to the
    downstream GeoPandas reader, which consumes raw ArcGIS JSON. Callers
    that need typed features can validate them explicitly via
    :class:`Feature`.
    """

    object_id_field_name: str | None = Field(
        default=None,
        alias="objectIdFieldName",
        validation_alias=AliasChoices("objectIdFieldName", "object_id_field_name"),
    )
    features: list[dict[str, Any]] = Field(default_factory=list)
    exceeded_transfer_limit: bool | None = Field(
        default=None,
        alias="exceededTransferLimit",
        validation_alias=AliasChoices(
            "exceededTransferLimit",
            "exceeded_transfer_limit",
        ),
    )


class TokenResponse(StrictModel):
    """Envelope for ArcGIS ``/generateToken`` responses.

    Strict tier: token refresh is operation-critical; a missing
    ``token`` or ``expires`` key means a token cannot be used and any
    downstream request will fail authentication. ArcGIS also returns
    error envelopes through this same endpoint (``{"error": {...}}``);
    those fail validation here and surface as
    :class:`RestgdfResponseError`, leaving the original payload on
    ``exc.raw`` for operator triage.
    """

    token: str = Field(...)
    expires: int = Field(...)
    ssl: bool | None = None


class NormalizedGeometry(PermissiveModel):
    """Typed intermediate ArcGIS geometry (BL-28; plan-domain §4.2).

    Permissive: vendor extras (``hasZ``, ``hasM``, nested
    ``spatialReference`` keys, z/m coordinate tuples) pass through
    unchanged. Only the fields restgdf consumes are declared.

    ``type`` is inferred by :func:`iter_normalized_features` from the
    geometry dict's shape (``x,y`` → ``"point"``, ``rings`` →
    ``"polygon"``, etc.) and falls back to ``None`` when the shape is
    unrecognized. It is kept as ``str | None`` (rather than a
    :class:`typing.Literal`) so heuristic inference does not raise on
    novel vendor shapes. A later phase will tighten the type once
    metadata-driven inference (BL-29) is wired.
    """

    type: str | None = None
    coords: Any = None
    spatial_reference: int | None = Field(
        default=None,
        alias="spatialReference",
        validation_alias=AliasChoices("spatialReference", "spatial_reference"),
    )
    _raw_spatial_reference: dict[str, Any] | None = PrivateAttr(default=None)
    has_z: bool = Field(
        default=False,
        alias="hasZ",
        validation_alias=AliasChoices("hasZ", "has_z"),
    )
    has_m: bool = Field(
        default=False,
        alias="hasM",
        validation_alias=AliasChoices("hasM", "has_m"),
    )


class NormalizedFeature(PermissiveModel):
    """Typed intermediate ArcGIS feature (BL-28; plan-domain §4.1).

    Wire-level :attr:`FeaturesResponse.features` stays ``list[dict]``
    for perf (avoids per-row pydantic validation across large batches).
    Consumers that want typed features opt in via
    :func:`iter_normalized_features`.
    """

    attributes: dict[str, Any] = Field(default_factory=dict)
    geometry: NormalizedGeometry | None = None
    object_id: int | None = None


def _infer_geometry_type(geometry: Mapping[str, Any]) -> str | None:
    if "x" in geometry and "y" in geometry:
        return "point"
    if "points" in geometry:
        return "multipoint"
    if "paths" in geometry:
        return "polyline"
    if "rings" in geometry:
        return "polygon"
    if {"xmin", "ymin", "xmax", "ymax"}.issubset(geometry.keys()):
        return "envelope"
    return None


def iter_normalized_features(
    response: FeaturesResponse,
    *,
    oid_field: str | None = None,
    sr: int | str | dict[str, Any] | None = None,
) -> Iterator[NormalizedFeature]:
    """Yield :class:`NormalizedFeature` for each entry in ``response.features``.

    Parameters
    ----------
    response
        A :class:`FeaturesResponse` envelope. The raw ``features``
        ``list[dict]`` is iterated; the envelope itself is not mutated.
    oid_field
        Overrides :attr:`FeaturesResponse.object_id_field_name`. When
        resolved, the value at ``attributes[oid_field]`` is coerced via
        ``int(value)`` and hoisted onto
        :attr:`NormalizedFeature.object_id`. ``TypeError`` and
        ``ValueError`` from coercion leave ``object_id`` as ``None``
        (e.g. unparsable string OIDs like ``"abc"`` are tolerated).
    sr
        Fallback spatial reference applied when the raw geometry does
        not already carry one. A server-provided ``spatialReference``
        always wins.

    Normalization is best-effort: missing geometry, missing attributes,
    and non-mapping feature entries are silently tolerated (iteration
    skips non-mapping entries rather than raising on vendor variance).

    Per-page spatial-reference drift warnings are out of scope for this
    iterator; they land with BL-29 when metadata context is available.
    """
    resolved_oid_field = oid_field or response.object_id_field_name
    for raw in response.features:
        if not isinstance(raw, Mapping):
            continue

        attributes_raw = raw.get("attributes")
        if isinstance(attributes_raw, Mapping):
            attributes = dict(attributes_raw)
        else:
            attributes = {}

        geometry_raw = raw.get("geometry")
        geometry: NormalizedGeometry | None
        if isinstance(geometry_raw, Mapping):
            geo_dict = dict(geometry_raw)
            coords = {
                key: value
                for key, value in geo_dict.items()
                if key not in {"spatialReference", "spatial_reference"}
            }
            inferred = _infer_geometry_type(geo_dict)
            spatial_ref = geo_dict.get("spatialReference")
            if spatial_ref is None:
                spatial_ref = geo_dict.get("spatial_reference")
            if spatial_ref is None:
                spatial_ref = sr

            # BL-23: normalize SR dict → EPSG int, preserve raw dict
            raw_sr_dict: dict[str, Any] | None = None
            epsg_int: int | None = None
            if isinstance(spatial_ref, Mapping):
                raw_sr_dict = dict(spatial_ref)
                epsg_int = raw_sr_dict.get("latestWkid") or raw_sr_dict.get("wkid")
                if not isinstance(epsg_int, int):
                    epsg_int = None
            elif isinstance(spatial_ref, int):
                epsg_int = spatial_ref
            elif isinstance(spatial_ref, str):
                try:
                    epsg_int = int(spatial_ref)
                except (ValueError, TypeError):
                    epsg_int = None

            geometry = NormalizedGeometry(
                type=inferred,
                coords=coords,
                spatial_reference=epsg_int,
                has_z=bool(geo_dict.get("hasZ") or geo_dict.get("has_z") or False),
                has_m=bool(geo_dict.get("hasM") or geo_dict.get("has_m") or False),
            )
            geometry._raw_spatial_reference = raw_sr_dict
        else:
            geometry = None

        object_id: int | None = None
        if resolved_oid_field and resolved_oid_field in attributes:
            try:
                object_id = int(attributes[resolved_oid_field])
            except (TypeError, ValueError):
                object_id = None

        yield NormalizedFeature(
            attributes=attributes,
            geometry=geometry,
            object_id=object_id,
        )


__all__ = [
    "CountResponse",
    "ErrorInfo",
    "ErrorResponse",
    "Feature",
    "FeaturesResponse",
    "FieldSpec",
    "LayerMetadata",
    "NormalizedFeature",
    "NormalizedGeometry",
    "ObjectIdsResponse",
    "ServiceInfo",
    "TokenResponse",
    "iter_normalized_features",
]
