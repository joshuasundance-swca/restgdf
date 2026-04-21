from __future__ import annotations

from tests.id_schema_fixtures import (
    list_id_schema_fixtures,
    load_id_schema_fixture,
)


def test_id_schema_fixture_names_are_stable() -> None:
    assert list_id_schema_fixtures() == (
        "object-ids-null",
        "object-id-key-variants",
        "unique-id-info-no-oid",
        "new-field-types",
        "malformed-field-entry",
    )


def test_load_id_schema_fixture_returns_deep_copy() -> None:
    payload = load_id_schema_fixture("new-field-types")
    payload["fields"][0]["name"] = "mutated"

    fresh = load_id_schema_fixture("new-field-types")
    assert fresh["fields"][0]["name"] == "ASSET_BIGID"


def test_object_ids_null_fixture_keeps_arcgis_null_shape() -> None:
    payload = load_id_schema_fixture("object-ids-null")

    assert payload == {
        "objectIdFieldName": "OBJECTID",
        "objectIds": None,
    }


def test_object_id_key_variants_fixture_captures_alias_drift_examples() -> None:
    payload = load_id_schema_fixture("object-id-key-variants")

    assert set(payload["responses"]) == {"objectIdFieldName", "objectIdField"}
    assert payload["responses"]["objectIdFieldName"]["objectIdFieldName"] == "OBJECTID"
    assert payload["responses"]["objectIdField"]["objectIdField"] == "OBJECTID"
    assert payload["responses"]["objectIdField"]["objectIds"][-1] > 2**31
    assert payload["metadata"]["lowercase-objectid"]["objectIdField"] == "objectid"
    assert payload["metadata"]["lowercase-objectid"]["fields"][0]["name"] == "objectid"


def test_unique_id_info_fixture_has_no_classic_oid_field() -> None:
    payload = load_id_schema_fixture("unique-id-info-no-oid")

    assert payload["uniqueIdInfo"]["name"] == "GLOBALID"
    assert payload["uniqueIdInfo"]["isSystemMaintained"] is True
    assert all(field["type"] != "esriFieldTypeOID" for field in payload["fields"])
    assert any(
        field["type"] == "esriFieldTypeBigInteger" for field in payload["fields"]
    )


def test_new_field_types_fixture_captures_new_arcgis_types_and_large_id_sample() -> (
    None
):
    payload = load_id_schema_fixture("new-field-types")

    field_types = {field["type"] for field in payload["fields"]}
    assert field_types == {
        "esriFieldTypeBigInteger",
        "esriFieldTypeDateOnly",
        "esriFieldTypeTimeOnly",
        "esriFieldTypeTimestampOffset",
    }
    assert payload["sampleAttributes"]["ASSET_BIGID"] > 2**53


def test_malformed_field_fixture_contains_one_bad_entry_among_valid_fields() -> None:
    payload = load_id_schema_fixture("malformed-field-entry")

    malformed = [
        field for field in payload["fields"] if not isinstance(field["type"], str)
    ]
    assert len(payload["fields"]) == 4
    assert len(malformed) == 1
    assert malformed[0]["name"] == "BROKEN_FIELD"
