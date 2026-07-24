"""Coverage tests for BL-23 spatial reference normalization + metadata helpers.

Targets the new code in ``restgdf/utils/_metadata.py`` that was added
as part of phase-3d so the worktree satisfies ``fail_under = 97``.
"""

from __future__ import annotations

import pytest

from restgdf._models._drift import _parse_response
from restgdf._models.responses import LayerMetadata
from restgdf.errors import FieldDoesNotExistError
from restgdf.utils._metadata import (
    _field_rows,
    get_fields,
    get_fields_frame,
    get_max_record_count,
    get_object_id_field,
    normalize_spatial_reference,
)
from tests.id_schema_fixtures import load_id_schema_fixture


class TestNormalizeSpatialReference:
    def test_none_returns_pair_of_none(self):
        assert normalize_spatial_reference(None) == (None, None)

    def test_int_passthrough(self):
        assert normalize_spatial_reference(3857) == (3857, None)

    def test_string_numeric_coerced(self):
        assert normalize_spatial_reference("4326") == (4326, None)

    def test_string_non_numeric_returns_none(self):
        assert normalize_spatial_reference("not-a-number") == (None, None)

    def test_dict_prefers_latest_wkid(self):
        epsg, raw = normalize_spatial_reference({"wkid": 102100, "latestWkid": 3857})
        assert epsg == 3857
        assert raw == {"wkid": 102100, "latestWkid": 3857}

    def test_dict_falls_back_to_wkid(self):
        epsg, raw = normalize_spatial_reference({"wkid": 4326})
        assert epsg == 4326
        assert raw == {"wkid": 4326}

    def test_dict_non_int_epsg_returns_none_but_keeps_raw(self):
        epsg, raw = normalize_spatial_reference({"wkid": "4326"})
        assert epsg is None
        assert raw == {"wkid": "4326"}

    def test_dict_no_epsg_keys(self):
        epsg, raw = normalize_spatial_reference({"other": "value"})
        assert epsg is None
        assert raw == {"other": "value"}

    def test_unknown_type_returns_pair_of_none(self):
        assert normalize_spatial_reference(3.14) == (None, None)


class TestObjectIdFieldLookup:
    def test_objectidfield_string_maps_via_case_insensitive_lookup(self):
        metadata = {
            "objectIdField": "OBJECTID",
            "fields": [{"name": "ObjectId", "type": "esriFieldTypeOID"}],
        }
        # With a single OID field the OID path returns first; this test
        # exercises the objectidfield fallback when no explicit OID field
        # is typed.
        metadata_without_oid_type = {
            "objectIdField": "OBJECTID",
            "fields": [{"name": "ObjectId", "type": "esriFieldTypeInteger"}],
        }
        assert get_object_id_field(metadata_without_oid_type) == "ObjectId"
        # Sanity: canonical path still works.
        assert get_object_id_field(metadata) == "ObjectId"


class TestGetMaxRecordCount:
    def test_raises_when_no_matching_key(self):
        with pytest.raises(FieldDoesNotExistError):
            get_max_record_count({})

    def test_returns_value_for_canonical_key(self):
        assert get_max_record_count({"maxRecordCount": 2000}) == 2000


class TestFieldsPermissiveTierMissingNameOrType:
    """W5-4 (ADAPTERS-01).

    ``FieldSpec`` declares both ``name`` and ``type`` as
    ``str | None = None`` (permissive tier) -- a field entry missing
    either key is individually VALID and validates cleanly with no
    drift logged. Before the fix, ``get_fields(types=True)``/
    ``_field_rows``/``get_fields_frame`` raised ``KeyError`` (missing
    key) or ``AttributeError`` (explicit ``None``) instead of returning
    the resolvable subset.
    """

    @staticmethod
    def _validated_metadata() -> LayerMetadata:
        # Real permissive-tier shape: goes through the SAME validated-model
        # path production code uses (FeatureLayer.prep -> LayerMetadata),
        # not a hand-built dict -- see the fixture's own docstring for why
        # this differs from "malformed-field-entry".
        payload = load_id_schema_fixture("field-missing-name-or-type")
        return _parse_response(
            LayerMetadata,
            payload,
            context="field-missing-name-or-type",
        )

    def test_get_fields_drops_the_nameless_field(self):
        layer = self._validated_metadata()
        assert get_fields(layer) == ["OBJECTID", "UPDATED_AT"]

    def test_get_fields_types_true_defaults_missing_type_and_drops_nameless(self):
        layer = self._validated_metadata()
        assert get_fields(layer, types=True) == {
            "OBJECTID": "OID",
            "UPDATED_AT": "",
        }

    def test_field_rows_defaults_missing_type_and_drops_nameless(self):
        layer = self._validated_metadata()
        assert _field_rows(layer) == [
            ("OBJECTID", "OID"),
            ("UPDATED_AT", ""),
        ]

    def test_get_fields_frame_agrees_with_field_rows_and_get_fields(self):
        layer = self._validated_metadata()
        frame = get_fields_frame(layer)
        assert list(frame["name"]) == ["OBJECTID", "UPDATED_AT"]
        assert list(frame["type"]) == ["OID", ""]

    def test_raw_dict_explicit_none_type_does_not_attributeerror(self):
        """Anti-recommendation case (per audit-recommendations/08): a raw

        dict bypassing model validation where a server sent an explicit
        ``"type": null`` must not surface
        ``AttributeError: 'NoneType' object has no attribute 'replace'``.
        """
        raw = {
            "fields": [
                {"name": "OBJECTID", "type": None},
                {"name": None, "type": "esriFieldTypeString"},
            ],
        }
        assert get_fields(raw) == ["OBJECTID"]
        assert get_fields(raw, types=True) == {"OBJECTID": ""}
        assert _field_rows(raw) == [("OBJECTID", "")]
