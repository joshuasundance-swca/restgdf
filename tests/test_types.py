"""Phase 3 contract tests for :mod:`restgdf._types`.

These pin the shape of the public TypedDicts so that parsers
in :mod:`restgdf.utils._metadata`, :mod:`restgdf.utils._query`, and the
orchestrators in :mod:`restgdf.utils.getinfo` have a single source of
truth for the ArcGIS REST response shapes they consume.

TypedDicts are dicts at runtime; these tests verify:
* The symbols are importable from ``restgdf._types``.
* Each TypedDict declares the keys the parsers actually access.
* Real ArcGIS-shaped payloads satisfy the schemas when passed through
  the parsers that were retrofit to consume them.
"""

from __future__ import annotations

import pytest


def test_types_module_importable() -> None:
    import restgdf._types as t  # noqa: F401


def test_public_typed_dicts_exist() -> None:
    from restgdf import _types as t

    for name in (
        "FieldSpec",
        "LayerMetadata",
        "ServiceInfo",
        "CountResponse",
        "ObjectIdsResponse",
        "Feature",
        "FeaturesResponse",
        "ErrorInfo",
        "ErrorResponse",
    ):
        assert hasattr(t, name), f"restgdf._types.{name} missing"


def test_field_spec_required_keys() -> None:
    from restgdf._types import FieldSpec

    required: frozenset[str] = getattr(FieldSpec, "__required_keys__", frozenset())
    assert {"name", "type"}.issubset(required)


def test_layer_metadata_optional_keys_include_url_and_feature_count() -> None:
    from restgdf._types import LayerMetadata

    optional: frozenset[str] = getattr(LayerMetadata, "__optional_keys__", frozenset())
    assert "url" in optional
    assert "feature_count" in optional


def test_count_response_requires_count_key() -> None:
    from restgdf._types import CountResponse

    required: frozenset[str] = getattr(CountResponse, "__required_keys__", frozenset())
    assert "count" in required


def test_object_ids_response_requires_both_keys() -> None:
    from restgdf._types import ObjectIdsResponse

    required: frozenset[str] = getattr(
        ObjectIdsResponse,
        "__required_keys__",
        frozenset(),
    )
    assert {"objectIdFieldName", "objectIds"}.issubset(required)


def test_feature_requires_attributes_key() -> None:
    from restgdf._types import Feature

    required: frozenset[str] = getattr(Feature, "__required_keys__", frozenset())
    assert "attributes" in required


def test_typed_dicts_are_dict_instances_at_runtime() -> None:
    from restgdf._types import CountResponse, FieldSpec

    fs: FieldSpec = {"name": "OBJECTID", "type": "esriFieldTypeOID"}
    cr: CountResponse = {"count": 42}
    assert isinstance(fs, dict)
    assert isinstance(cr, dict)


@pytest.mark.compat
def test_metadata_parsers_still_accept_arcgis_shaped_dicts() -> None:
    from restgdf._types import LayerMetadata
    from restgdf.utils._metadata import (
        get_max_record_count,
        get_name,
        get_object_id_field,
        getfields,
        getfields_df,
        supports_pagination,
    )

    layer: LayerMetadata = {
        "name": "Some Layer",
        "type": "Feature Layer",
        "maxRecordCount": 2000,
        "supportsPagination": True,
        "advancedQueryCapabilities": {"supportsPagination": True},
        "fields": [
            {"name": "OBJECTID", "type": "esriFieldTypeOID"},
            {"name": "FOO", "type": "esriFieldTypeString"},
        ],
    }

    assert get_name(layer) == "Some Layer"
    assert get_max_record_count(layer) == 2000
    assert get_object_id_field(layer) == "OBJECTID"
    assert supports_pagination(layer) is True
    assert getfields(layer) == ["OBJECTID", "FOO"]
    assert list(getfields_df(layer).columns) == ["name", "type"]
