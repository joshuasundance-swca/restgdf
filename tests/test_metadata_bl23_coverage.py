"""Coverage tests for BL-23 spatial reference normalization + metadata helpers.

Targets the new code in ``restgdf/utils/_metadata.py`` that was added
as part of phase-3d so the worktree satisfies ``fail_under = 97``.
"""

from __future__ import annotations

import pytest

from restgdf.errors import FieldDoesNotExistError
from restgdf.utils._metadata import (
    get_max_record_count,
    get_object_id_field,
    normalize_spatial_reference,
)


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
