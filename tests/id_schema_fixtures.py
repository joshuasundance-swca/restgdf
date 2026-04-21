"""Stable ArcGIS ID/schema drift fixtures distilled from live/doc examples.

These payloads are intentionally small and vendored so follow-on hardening
work can exercise known ArcGIS edge cases without depending on live services.
Call :func:`load_id_schema_fixture` to get a deep-copied payload that tests
may mutate freely.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

_ID_SCHEMA_FIXTURES: dict[str, dict[str, Any]] = {
    "object-ids-null": {
        "objectIdFieldName": "OBJECTID",
        "objectIds": None,
    },
    "object-id-key-variants": {
        "responses": {
            "objectIdFieldName": {
                "objectIdFieldName": "OBJECTID",
                "objectIds": [1, 2, 2147483649],
            },
            "objectIdField": {
                "objectIdField": "OBJECTID",
                "objectIds": [1, 2, 2147483649],
            },
        },
        "metadata": {
            "lowercase-objectid": {
                "name": "Lowercase OID Layer",
                "type": "Feature Layer",
                "objectIdField": "objectid",
                "fields": [
                    {"name": "objectid", "type": "esriFieldTypeOID"},
                    {"name": "NAME", "type": "esriFieldTypeString"},
                ],
            },
        },
    },
    "unique-id-info-no-oid": {
        "name": "Branch Inspections",
        "type": "Table",
        "fields": [
            {"name": "GLOBALID", "type": "esriFieldTypeGlobalID", "nullable": False},
            {
                "name": "ASSET_BIGID",
                "type": "esriFieldTypeBigInteger",
                "sqlType": "sqlTypeBigInt",
                "nullable": False,
            },
            {"name": "INSPECTED_ON", "type": "esriFieldTypeDateOnly"},
        ],
        "uniqueIdInfo": {
            "type": "simple",
            "name": "GLOBALID",
            "isSystemMaintained": True,
        },
    },
    "new-field-types": {
        "name": "Temporal + Big Integer Layer",
        "fields": [
            {
                "name": "ASSET_BIGID",
                "type": "esriFieldTypeBigInteger",
                "alias": "ASSET_BIGID",
                "sqlType": "sqlTypeBigInt",
            },
            {
                "name": "INSPECTION_DATE",
                "type": "esriFieldTypeDateOnly",
                "alias": "INSPECTION_DATE",
            },
            {
                "name": "INSPECTION_TIME",
                "type": "esriFieldTypeTimeOnly",
                "alias": "INSPECTION_TIME",
            },
            {
                "name": "LAST_EDITED_AT",
                "type": "esriFieldTypeTimestampOffset",
                "alias": "LAST_EDITED_AT",
            },
        ],
        "sampleAttributes": {
            "ASSET_BIGID": 9007199254740993,
            "INSPECTION_DATE": "2025-01-15",
            "INSPECTION_TIME": "13:45:12",
            "LAST_EDITED_AT": "2025-01-15T13:45:12-05:00",
        },
    },
    "malformed-field-entry": {
        "name": "Mostly Valid Fields",
        "fields": [
            {"name": "OBJECTID", "type": "esriFieldTypeOID"},
            {"name": "CITY", "type": "esriFieldTypeString", "length": 64},
            {"name": "BROKEN_FIELD", "type": ["esriFieldTypeString"]},
            {"name": "UPDATED_AT", "type": "esriFieldTypeDate"},
        ],
    },
}


def list_id_schema_fixtures() -> tuple[str, ...]:
    """Return the vendored ID/schema fixture names in a stable order."""
    return tuple(_ID_SCHEMA_FIXTURES)


def load_id_schema_fixture(name: str) -> dict[str, Any]:
    """Return a deep-copied ID/schema fixture payload."""
    return deepcopy(_ID_SCHEMA_FIXTURES[name])
