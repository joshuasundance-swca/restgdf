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

from typing import Any

from pydantic import AliasChoices, Field, field_validator

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


__all__ = [
    "CountResponse",
    "ErrorInfo",
    "ErrorResponse",
    "Feature",
    "FeaturesResponse",
    "FieldSpec",
    "LayerMetadata",
    "ObjectIdsResponse",
    "ServiceInfo",
    "TokenResponse",
]
