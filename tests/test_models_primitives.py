"""S-1: Pydantic primitives for ArcGIS response parsing.

These tests pin the public contract of the new primitive models
(:class:`FieldSpec`, :class:`ErrorInfo`, :class:`ErrorResponse`,
:class:`Feature`) and of the shared drift adapter
(``restgdf._models._drift._parse_response``).

The two-tier validation contract is:

* Permissive models accept extras and treat all consumed fields as
  optional. Extras are logged at ``DEBUG`` via the
  ``restgdf.schema_drift`` logger. Missing optional fields do not raise.
* Strict models tolerate extras silently (so vendor additions never
  break us) but raise :class:`RestgdfResponseError` when a required
  field is missing or ill-typed.

Dedupe is keyed on ``(model_name, path, kind, value_type)`` so the same
drift only logs once per process.
"""

from __future__ import annotations

import logging
from typing import Any

import pytest

from restgdf._models import RestgdfResponseError
from restgdf._models._drift import (
    PermissiveModel,
    StrictModel,
    _parse_response,
    reset_drift_cache,
)
from restgdf._models.responses import (
    ErrorInfo,
    ErrorResponse,
    Feature,
    FieldSpec,
)


@pytest.fixture(autouse=True)
def _reset_drift_cache() -> None:
    reset_drift_cache()


# --------------------------------------------------------------------------- #
# FieldSpec                                                                   #
# --------------------------------------------------------------------------- #


def test_fieldspec_accepts_typical_arcgis_shape() -> None:
    raw = {
        "name": "OBJECTID",
        "type": "esriFieldTypeOID",
        "alias": "OBJECTID",
        "length": 4,
        "domain": None,
        "nullable": False,
        "editable": False,
    }
    field = FieldSpec.model_validate(raw)
    assert field.name == "OBJECTID"
    assert field.type == "esriFieldTypeOID"
    assert field.alias == "OBJECTID"
    assert field.length == 4
    assert field.domain is None
    assert field.nullable is False


def test_fieldspec_preserves_unknown_extras() -> None:
    raw = {"name": "FOO", "type": "esriFieldTypeString", "sqlType": "sqlTypeNVarchar"}
    field = FieldSpec.model_validate(raw)
    # extra="allow" → unknown keys available on model via attribute or dump
    assert field.model_dump(exclude_none=True).get("sqlType") == "sqlTypeNVarchar"


def test_fieldspec_missing_name_and_type_are_optional() -> None:
    # Permissive tier: even "expected" keys are Optional so ArcGIS drift
    # does not explode. Downstream parsers still raise their own errors.
    field = FieldSpec.model_validate({})
    assert field.name is None
    assert field.type is None


# --------------------------------------------------------------------------- #
# ErrorInfo / ErrorResponse                                                   #
# --------------------------------------------------------------------------- #


def test_error_info_accepts_code_message_details() -> None:
    info = ErrorInfo.model_validate(
        {"code": 400, "message": "Invalid", "details": ["field X bad"]},
    )
    assert info.code == 400
    assert info.message == "Invalid"
    assert info.details == ["field X bad"]


def test_error_response_is_strict_requires_error_key() -> None:
    with pytest.raises(RestgdfResponseError) as exc_info:
        _parse_response(ErrorResponse, {"not_error": 1}, context="test")
    err = exc_info.value
    assert err.model_name == "ErrorResponse"
    assert err.context == "test"
    assert err.raw == {"not_error": 1}


def test_error_response_validates_well_formed_error_envelope() -> None:
    raw = {"error": {"code": 498, "message": "Invalid Token"}}
    resp = _parse_response(ErrorResponse, raw, context="token-refresh")
    assert resp.error.code == 498
    assert resp.error.message == "Invalid Token"


def test_error_response_tolerates_extra_keys_silently() -> None:
    raw = {
        "error": {"code": 400, "message": "bad"},
        "requestId": "abc-123",
    }
    resp = _parse_response(ErrorResponse, raw, context="test")
    assert resp.error.code == 400


# --------------------------------------------------------------------------- #
# Feature                                                                     #
# --------------------------------------------------------------------------- #


def test_feature_accepts_attributes_and_optional_geometry() -> None:
    f = Feature.model_validate(
        {"attributes": {"OBJECTID": 1, "NAME": "X"}, "geometry": {"x": 1.0, "y": 2.0}},
    )
    assert f.attributes == {"OBJECTID": 1, "NAME": "X"}
    assert f.geometry == {"x": 1.0, "y": 2.0}


def test_feature_geometry_optional() -> None:
    f = Feature.model_validate({"attributes": {"X": 1}})
    assert f.geometry is None


# --------------------------------------------------------------------------- #
# _parse_response drift logging                                               #
# --------------------------------------------------------------------------- #


def test_parse_response_logs_unknown_extras_at_debug_for_permissive(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG, logger="restgdf.schema_drift")
    _parse_response(FieldSpec, {"name": "X", "type": "Y", "weirdKey": 1}, context="ctx")
    debug_records = [
        r
        for r in caplog.records
        if r.levelno == logging.DEBUG and r.name == "restgdf.schema_drift"
    ]
    assert debug_records, "expected at least one DEBUG record for unknown extras"
    assert any("weirdKey" in r.getMessage() for r in debug_records)


def test_parse_response_strict_validation_error_includes_context(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG, logger="restgdf.schema_drift")
    with pytest.raises(RestgdfResponseError) as exc_info:
        _parse_response(ErrorResponse, {"bogus": 1}, context="some-url")
    assert exc_info.value.context == "some-url"


def test_parse_response_dedupes_drift_logs(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG, logger="restgdf.schema_drift")
    payload = {"name": "X", "type": "Y", "weirdKey": 1}
    _parse_response(FieldSpec, payload, context="ctx")
    _parse_response(FieldSpec, payload, context="ctx")
    weird_records = [r for r in caplog.records if "weirdKey" in r.getMessage()]
    assert len(weird_records) == 1, (
        f"expected deduped drift log, got {len(weird_records)}"
    )


def test_parse_response_passes_through_valid_permissive_model() -> None:
    raw = {"name": "X", "type": "Y"}
    result = _parse_response(FieldSpec, raw, context="ctx")
    assert isinstance(result, FieldSpec)
    assert result.name == "X"


def test_tier_base_classes_have_expected_configs() -> None:
    assert PermissiveModel.model_config.get("extra") == "allow"
    assert PermissiveModel.model_config.get("populate_by_name") is True
    assert StrictModel.model_config.get("extra") == "ignore"
    assert StrictModel.model_config.get("populate_by_name") is True


def test_reset_drift_cache_clears_dedupe(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG, logger="restgdf.schema_drift")
    payload = {"name": "X", "type": "Y", "weirdKey": 1}
    _parse_response(FieldSpec, payload, context="ctx")
    reset_drift_cache()
    _parse_response(FieldSpec, payload, context="ctx")
    weird_records = [r for r in caplog.records if "weirdKey" in r.getMessage()]
    assert len(weird_records) == 2


def test_parse_response_rejects_non_mapping_for_strict(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG, logger="restgdf.schema_drift")
    with pytest.raises(RestgdfResponseError):
        _parse_response(ErrorResponse, "not a dict", context="ctx")  # type: ignore[arg-type]


def test_field_spec_is_permissive_subclass() -> None:
    assert issubclass(FieldSpec, PermissiveModel)


def test_error_response_is_strict_subclass() -> None:
    assert issubclass(ErrorResponse, StrictModel)


def test_feature_is_permissive_subclass() -> None:
    assert issubclass(Feature, PermissiveModel)


def test_error_info_is_permissive_subclass() -> None:
    # ErrorInfo nested inside strict ErrorResponse stays permissive — ArcGIS
    # error payloads often carry extra troubleshooting keys we do not model.
    assert issubclass(ErrorInfo, PermissiveModel)


def test_parse_response_accepts_dict_of_arbitrary_types(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Permissive parsing should never raise, even with nonsense types."""
    caplog.set_level(logging.DEBUG, logger="restgdf.schema_drift")
    bad: dict[str, Any] = {"name": "X", "type": "Y", "length": "not-an-int"}
    # length has declared type; coerce or drop-to-None but never raise
    result = _parse_response(FieldSpec, bad, context="ctx")
    # We do not pin what length resolves to — only that parse did not raise.
    assert result.name == "X"


# --------------------------------------------------------------------------- #
# Drift adapter edge cases                                                    #
# --------------------------------------------------------------------------- #


def test_parse_response_permissive_non_mapping_logs_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG, logger="restgdf.schema_drift")
    result = _parse_response(FieldSpec, "not a dict", context="ctx")  # type: ignore[arg-type]
    assert isinstance(result, FieldSpec)
    assert result.name is None
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert any("not_a_mapping" in r.getMessage() for r in warnings)


def test_parse_response_permissive_bad_type_falls_back_and_logs(
    caplog: pytest.LogCaptureFixture,
) -> None:
    from pydantic import BaseModel

    from restgdf._models._drift import PermissiveModel as _Perm
    from restgdf._models._drift import _parse_response as _pr

    class _ModelWithStrictInt(_Perm):
        n: int = 0

    caplog.set_level(logging.DEBUG, logger="restgdf.schema_drift")
    result = _pr(_ModelWithStrictInt, {"n": "definitely-not-int"}, context="ctx")
    # Bad-typed field is stripped; default (0) applies
    assert isinstance(result, BaseModel)
    bad_records = [r for r in caplog.records if "bad_type" in r.getMessage()]
    assert bad_records


def test_known_keys_includes_field_alias_and_alias_choices() -> None:
    from pydantic import AliasChoices, Field

    from restgdf._models._drift import PermissiveModel as _Perm
    from restgdf._models._drift import _known_keys

    class _Aliased(_Perm):
        object_id_field: str = Field(
            default="",
            alias="objectIdFieldName",
            validation_alias=AliasChoices("objectIdFieldName", "OBJECTID_FIELD"),
        )

    keys = _known_keys(_Aliased)
    assert {"object_id_field", "objectIdFieldName", "OBJECTID_FIELD"} <= keys


def test_parse_response_ignores_validation_errors_without_loc(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """An error row without a usable ``loc`` should not explode the adapter."""
    from pydantic import model_validator

    from restgdf._models._drift import PermissiveModel as _Perm
    from restgdf._models._drift import _parse_response as _pr

    class _Whole(_Perm):
        x: int = 0

        @model_validator(mode="after")
        def _reject(self) -> _Whole:
            raise ValueError("bad whole")

    caplog.set_level(logging.DEBUG, logger="restgdf.schema_drift")
    # model_validator errors have loc=() — adapter should tolerate, but then
    # revalidation still fails. We assert the failure path is a ValidationError
    # re-raised (permissive models surface underlying errors when no field can
    # be stripped).
    with pytest.raises(Exception):
        _pr(_Whole, {"x": 1}, context="ctx")
