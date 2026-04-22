"""BL-21 tests: :class:`restgdf._models.responses.AdvancedQueryCapabilities`.

Verifies the typed submodel parses a realistic
``advancedQueryCapabilities`` dict from live ArcGIS metadata, accepts
both camelCase and snake_case input, preserves unknown keys via the
permissive tier, and that the companion
``LayerMetadata.advanced_query_capabilities_typed`` field is additive
(the raw ``advanced_query_capabilities: dict`` survives untouched).
"""

from __future__ import annotations

from restgdf._models.responses import (
    AdvancedQueryCapabilities,
    LayerMetadata,
)


REAL_WORLD_PAYLOAD = {
    "supportsPagination": True,
    "supportsPaginationOnAggregatedQueries": False,
    "supportsQueryByOIDs": True,
    "supportsReturnExceededLimitFeatures": True,
    "supportsQueryWithDistance": True,
    "supportsStatistics": True,
    "maxRecordCountFactor": 2.0,
    "supportsOrderBy": True,
}


def test_parses_realistic_advanced_query_capabilities_dict():
    aqc = AdvancedQueryCapabilities(**REAL_WORLD_PAYLOAD)
    assert aqc.supports_pagination is True
    assert aqc.supports_pagination_on_aggregated_queries is False
    assert aqc.supports_query_by_oids is True
    assert aqc.supports_return_exceeded_limit_features is True
    assert aqc.max_record_count_factor == 2.0


def test_accepts_snake_case_input():
    aqc = AdvancedQueryCapabilities(
        supports_pagination=True,
        supports_query_by_oids=False,
        max_record_count_factor=1.5,
    )
    assert aqc.supports_pagination is True
    assert aqc.supports_query_by_oids is False
    assert aqc.max_record_count_factor == 1.5


def test_preserves_unknown_keys_permissively():
    aqc = AdvancedQueryCapabilities(**REAL_WORLD_PAYLOAD)
    dumped = aqc.model_dump(by_alias=True)
    # Known fields round-trip via camelCase.
    assert dumped["supportsPagination"] is True
    assert dumped["maxRecordCountFactor"] == 2.0
    # Unknown keys from the permissive tier stay addressable on the model.
    assert aqc.model_extra is not None
    assert aqc.model_extra.get("supportsStatistics") is True


def test_layer_metadata_keeps_raw_dict_field_unchanged():
    """The raw ``advanced_query_capabilities`` dict stays the default
    representation; BL-21's typed companion is additive-only."""
    layer = LayerMetadata(
        name="test",
        advancedQueryCapabilities={"supportsPagination": False},
    )
    assert layer.advanced_query_capabilities == {"supportsPagination": False}
    # Typed field defaults to None unless callers opt in.
    assert layer.advanced_query_capabilities_typed is None


def test_layer_metadata_typed_field_accepts_submodel():
    aqc = AdvancedQueryCapabilities(**REAL_WORLD_PAYLOAD)
    layer = LayerMetadata(
        name="layer",
        advancedQueryCapabilities=REAL_WORLD_PAYLOAD,
        advancedQueryCapabilitiesTyped=aqc,
    )
    assert layer.advanced_query_capabilities == REAL_WORLD_PAYLOAD
    assert isinstance(
        layer.advanced_query_capabilities_typed,
        AdvancedQueryCapabilities,
    )
    assert layer.advanced_query_capabilities_typed.max_record_count_factor == 2.0


def test_layer_metadata_typed_field_accepts_dict_and_validates():
    """Pydantic coerces the dict input through the ``AdvancedQueryCapabilities``
    validator, exercising the alias-choices wiring end-to-end."""
    layer = LayerMetadata(
        name="layer",
        advancedQueryCapabilitiesTyped=REAL_WORLD_PAYLOAD,
    )
    assert isinstance(
        layer.advanced_query_capabilities_typed,
        AdvancedQueryCapabilities,
    )
    assert layer.advanced_query_capabilities_typed.supports_query_by_oids is True


def test_advanced_query_capabilities_all_fields_optional():
    aqc = AdvancedQueryCapabilities()
    assert aqc.supports_pagination is None
    assert aqc.supports_query_by_oids is None
    assert aqc.supports_return_exceeded_limit_features is None
    assert aqc.supports_pagination_on_aggregated_queries is None
    assert aqc.max_record_count_factor is None
