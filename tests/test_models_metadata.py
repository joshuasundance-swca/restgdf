"""S-2: Pydantic metadata models for ArcGIS service/layer shapes.

These tests pin the public contract of :class:`LayerMetadata` and
:class:`ServiceInfo` — permissive models that describe the polymorphic
``GET <layer_url>?f=json`` and ``GET <services_root>?f=json`` payloads
restgdf consumes. See :mod:`restgdf._models.responses` for the tier.

Key contract points:

* Both are :class:`PermissiveModel` subclasses: extras are kept and
  missing keys default to ``None`` (never raise).
* Fields use :class:`~pydantic.AliasChoices` so either camelCase ArcGIS
  keys or snake_case Python names validate. ``model_dump(by_alias=True)``
  round-trips the original camelCase for downstream serialization.
* ``LayerMetadata.layers`` is self-referential (a layer's sublayers are
  themselves :class:`LayerMetadata`). ``model_rebuild`` resolves the
  forward reference at import time.
* The drift adapter :func:`_parse_response` logs unknown extras at
  ``DEBUG`` and non-mapping roots at ``WARNING`` without raising.
"""

from __future__ import annotations

import logging

import pytest

from restgdf._models._drift import (
    PermissiveModel,
    _parse_response,
    reset_drift_cache,
)
from restgdf._models.responses import LayerMetadata, ServiceInfo
from tests.id_schema_fixtures import load_id_schema_fixture


@pytest.fixture(autouse=True)
def _reset_drift_cache() -> None:
    reset_drift_cache()


# --------------------------------------------------------------------------- #
# LayerMetadata — tier + basic contract                                       #
# --------------------------------------------------------------------------- #


def test_layer_metadata_is_permissive_subclass() -> None:
    assert issubclass(LayerMetadata, PermissiveModel)


def test_service_info_is_permissive_subclass() -> None:
    assert issubclass(ServiceInfo, PermissiveModel)


def test_layer_metadata_accepts_empty_payload_without_raising() -> None:
    layer = LayerMetadata.model_validate({})
    assert layer.name is None
    assert layer.type is None
    assert layer.id is None
    assert layer.fields is None
    assert layer.max_record_count is None
    assert layer.supports_pagination is None
    assert layer.advanced_query_capabilities is None
    assert layer.layers is None
    assert layer.services is None
    assert layer.folders is None
    assert layer.url is None
    assert layer.feature_count is None


# --------------------------------------------------------------------------- #
# LayerMetadata — camelCase ↔ snake_case aliases                              #
# --------------------------------------------------------------------------- #


def test_layer_metadata_accepts_camelcase_arcgis_payload() -> None:
    raw = {
        "id": 0,
        "name": "Parcels",
        "type": "Feature Layer",
        "maxRecordCount": 2000,
        "supportsPagination": True,
        "advancedQueryCapabilities": {"supportsPagination": True},
        "fields": [
            {"name": "OBJECTID", "type": "esriFieldTypeOID"},
            {"name": "CITY", "type": "esriFieldTypeString"},
        ],
    }
    layer = LayerMetadata.model_validate(raw)
    assert layer.id == 0
    assert layer.name == "Parcels"
    assert layer.type == "Feature Layer"
    assert layer.max_record_count == 2000
    assert layer.supports_pagination is True
    assert layer.advanced_query_capabilities == {"supportsPagination": True}
    assert layer.fields is not None
    assert layer.fields[0].name == "OBJECTID"


def test_layer_metadata_accepts_snake_case_input() -> None:
    raw = {
        "name": "L",
        "max_record_count": 50,
        "supports_pagination": False,
        "advanced_query_capabilities": {"supportsPagination": False},
        "feature_count": 7,
    }
    layer = LayerMetadata.model_validate(raw)
    assert layer.max_record_count == 50
    assert layer.supports_pagination is False
    assert layer.feature_count == 7


def test_layer_metadata_dumps_camelcase_by_alias() -> None:
    layer = LayerMetadata.model_validate(
        {
            "name": "L",
            "maxRecordCount": 10,
            "supportsPagination": True,
            "advancedQueryCapabilities": {"supportsPagination": True},
            "url": "https://example.com/0",
            "feature_count": 3,
        },
    )
    dumped = layer.model_dump(by_alias=True, exclude_none=True)
    assert dumped["maxRecordCount"] == 10
    assert dumped["supportsPagination"] is True
    assert dumped["advancedQueryCapabilities"] == {"supportsPagination": True}
    # url and feature_count are already snake_case in ArcGIS (added by restgdf),
    # so by_alias does not mangle them.
    assert dumped["url"] == "https://example.com/0"
    assert dumped["feature_count"] == 3


def test_layer_metadata_preserves_unknown_extras() -> None:
    raw = {"name": "L", "serverGens": {"minServerGen": 1}}
    layer = LayerMetadata.model_validate(raw)
    dumped = layer.model_dump(exclude_none=True)
    assert dumped.get("serverGens") == {"minServerGen": 1}


# --------------------------------------------------------------------------- #
# LayerMetadata — self-referential sublayers                                  #
# --------------------------------------------------------------------------- #


def test_layer_metadata_layers_field_is_self_referential() -> None:
    raw = {
        "layers": [
            {"id": 0, "name": "Root"},
            {"id": 1, "name": "Sub"},
        ],
    }
    layer = LayerMetadata.model_validate(raw)
    assert layer.layers is not None
    assert len(layer.layers) == 2
    assert isinstance(layer.layers[0], LayerMetadata)
    assert layer.layers[0].id == 0
    assert layer.layers[1].name == "Sub"


def test_layer_metadata_nested_layers_preserve_camelcase() -> None:
    raw = {
        "layers": [
            {"id": 0, "maxRecordCount": 100},
        ],
    }
    layer = LayerMetadata.model_validate(raw)
    assert layer.layers[0].max_record_count == 100


# --------------------------------------------------------------------------- #
# ServiceInfo — service-root payload                                          #
# --------------------------------------------------------------------------- #


def test_service_info_accepts_service_root_payload() -> None:
    raw = {
        "services": [{"name": "Root/Parcels", "type": "FeatureServer"}],
        "folders": ["Utilities"],
    }
    info = ServiceInfo.model_validate(raw)
    assert info.services == [{"name": "Root/Parcels", "type": "FeatureServer"}]
    assert info.folders == ["Utilities"]


def test_service_info_accepts_empty_payload() -> None:
    info = ServiceInfo.model_validate({})
    assert info.services is None
    assert info.folders is None


# --------------------------------------------------------------------------- #
# Drift adapter integration                                                   #
# --------------------------------------------------------------------------- #


def test_parse_response_layer_metadata_logs_unknown_extras_at_debug(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG, logger="restgdf.schema_drift")
    _parse_response(
        LayerMetadata,
        {"name": "L", "maxRecordCount": 1, "mysteryKey": "?"},
        context="https://example.com/0",
    )
    drift_records = [
        r
        for r in caplog.records
        if r.levelno == logging.DEBUG and "mysteryKey" in r.getMessage()
    ]
    assert drift_records, "expected DEBUG drift log for unknown extra"


def test_parse_response_layer_metadata_non_mapping_warns_and_returns_empty(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG, logger="restgdf.schema_drift")
    layer = _parse_response(LayerMetadata, "not a dict", context="ctx")  # type: ignore[arg-type]
    assert isinstance(layer, LayerMetadata)
    assert layer.name is None
    assert any(r.levelno == logging.WARNING for r in caplog.records)


def test_parse_response_layer_metadata_falls_back_for_bad_typed_field(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG, logger="restgdf.schema_drift")
    layer = _parse_response(
        LayerMetadata,
        {"name": "L", "maxRecordCount": "not-an-int"},
        context="ctx",
    )
    assert layer.name == "L"
    # max_record_count was stripped; defaults to None
    assert layer.max_record_count is None
    bad_type_records = [r for r in caplog.records if "bad_type" in r.getMessage()]
    assert bad_type_records


def test_layer_metadata_preserves_new_field_types_and_large_integer_fixture() -> None:
    payload = load_id_schema_fixture("new-field-types")

    layer = _parse_response(LayerMetadata, payload, context="new-field-types")

    assert layer.fields is not None
    assert [field.type for field in layer.fields] == [
        "esriFieldTypeBigInteger",
        "esriFieldTypeDateOnly",
        "esriFieldTypeTimeOnly",
        "esriFieldTypeTimestampOffset",
    ]
    dumped = layer.model_dump(by_alias=True, exclude_none=True)
    assert dumped["sampleAttributes"]["ASSET_BIGID"] > 2**53


def test_parse_response_layer_metadata_keeps_valid_fields_when_one_field_is_malformed(
    caplog: pytest.LogCaptureFixture,
) -> None:
    payload = load_id_schema_fixture("malformed-field-entry")
    caplog.set_level(logging.DEBUG, logger="restgdf.schema_drift")

    layer = _parse_response(LayerMetadata, payload, context="malformed-field-entry")

    assert layer.fields is not None
    assert [field.name for field in layer.fields] == ["OBJECTID", "CITY", "UPDATED_AT"]
    assert [field.type for field in layer.fields] == [
        "esriFieldTypeOID",
        "esriFieldTypeString",
        "esriFieldTypeDate",
    ]
    assert any("fields.2.type" in record.getMessage() for record in caplog.records)
