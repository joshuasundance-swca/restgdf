"""BL-09 red tests — FieldDoesNotExistError replaces FIELDDOESNOTEXIST sentinel.

These tests assert that:
1. FieldDoesNotExistError follows the correct MRO (SchemaValidationError → … → ValueError)
2. It is NOT an IndexError (R-02 hard break)
3. It is importable from restgdf and restgdf.errors
4. raise sites in _metadata.py and featurelayer.py will produce FDE (green in commit 02)
"""

from __future__ import annotations

import pytest

from restgdf.errors import (
    FieldDoesNotExistError,
    RestgdfError,
    RestgdfResponseError,
    SchemaValidationError,
)


# ---- MRO assertions -------------------------------------------------


def test_fde_is_subclass_of_schema_validation_error():
    assert issubclass(FieldDoesNotExistError, SchemaValidationError)


def test_fde_is_subclass_of_restgdf_response_error():
    assert issubclass(FieldDoesNotExistError, RestgdfResponseError)


def test_fde_is_subclass_of_restgdf_error():
    assert issubclass(FieldDoesNotExistError, RestgdfError)


def test_fde_is_subclass_of_valueerror():
    assert issubclass(FieldDoesNotExistError, ValueError)


def test_fde_is_not_subclass_of_indexerror():
    """R-02 hard break: the old IndexError compat shim is gone."""
    assert not issubclass(FieldDoesNotExistError, IndexError)


def test_fde_instance_is_catchable_as_valueerror():
    exc = FieldDoesNotExistError("missing_field")
    assert isinstance(exc, ValueError)
    assert not isinstance(exc, IndexError)


# ---- constructor / attribute assertions ------------------------------


def test_fde_stores_field_name_and_context():
    exc = FieldDoesNotExistError("ZIP", context="FeatureLayer.get_unique_values")
    assert exc.field_name == "ZIP"
    assert exc.context == "FeatureLayer.get_unique_values"
    assert "ZIP" in str(exc)


def test_fde_accepts_tuple_field_name():
    exc = FieldDoesNotExistError(("CITY", "ZIP"), context="get_nested_count")
    assert exc.field_name == ("CITY", "ZIP")


def test_fde_default_message_without_field():
    exc = FieldDoesNotExistError()
    assert "does not exist" in str(exc).lower()


# ---- red raise-site tests (will pass after commit 02 wiring) --------


@pytest.mark.asyncio
async def test_get_name_raises_fde_on_missing_name():
    """get_name({}) should raise FieldDoesNotExistError (BL-09 raise-site)."""
    from restgdf.utils.getinfo import get_name

    with pytest.raises(FieldDoesNotExistError):
        get_name({"noname": "x"})


@pytest.mark.asyncio
async def test_get_object_id_field_raises_fde_on_empty_fields():
    """get_object_id_field({\"fields\": []}) should raise FDE."""
    from restgdf.utils.getinfo import get_object_id_field

    with pytest.raises(FieldDoesNotExistError):
        get_object_id_field({"fields": []})
