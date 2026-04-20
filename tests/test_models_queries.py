"""S-3: Pydantic query envelope models.

These tests pin the public contract of the query/count/objectIds/token
envelope models added in slice S-3:

* :class:`CountResponse` — strict; ``returnCountOnly=true`` result.
* :class:`ObjectIdsResponse` — strict; ``returnIdsOnly=true`` result.
  ArcGIS emits ``{"objectIdFieldName": "OBJECTID", "objectIds": null}``
  when the query matches zero rows; the model coerces ``None`` to ``[]``
  so consumers can safely iterate.
* :class:`FeaturesResponse` — permissive envelope; the per-feature
  validation lives in :class:`Feature` and is intentionally *not* applied
  here so large feature batches flow through without per-item overhead.
* :class:`TokenResponse` — strict; validates the ``/generateToken`` reply.
"""

from __future__ import annotations

import logging

import pytest

from restgdf._models import RestgdfResponseError
from restgdf._models._drift import (
    PermissiveModel,
    StrictModel,
    _parse_response,
    reset_drift_cache,
)
from restgdf._models.responses import (
    CountResponse,
    FeaturesResponse,
    ObjectIdsResponse,
    TokenResponse,
)


@pytest.fixture(autouse=True)
def _reset_drift_cache() -> None:
    reset_drift_cache()


# --------------------------------------------------------------------------- #
# Tier membership                                                              #
# --------------------------------------------------------------------------- #


def test_count_response_is_strict_subclass() -> None:
    assert issubclass(CountResponse, StrictModel)


def test_object_ids_response_is_strict_subclass() -> None:
    assert issubclass(ObjectIdsResponse, StrictModel)


def test_features_response_is_permissive_subclass() -> None:
    assert issubclass(FeaturesResponse, PermissiveModel)


def test_token_response_is_strict_subclass() -> None:
    assert issubclass(TokenResponse, StrictModel)


# --------------------------------------------------------------------------- #
# CountResponse                                                                #
# --------------------------------------------------------------------------- #


def test_count_response_accepts_valid_payload() -> None:
    resp = _parse_response(CountResponse, {"count": 42}, context="ctx")
    assert resp.count == 42


def test_count_response_raises_on_missing_count() -> None:
    with pytest.raises(RestgdfResponseError) as exc_info:
        _parse_response(CountResponse, {"no_count_here": 1}, context="url")
    assert exc_info.value.model_name == "CountResponse"
    assert exc_info.value.context == "url"


def test_count_response_raises_on_bad_type() -> None:
    with pytest.raises(RestgdfResponseError):
        _parse_response(CountResponse, {"count": "not-an-int"}, context="url")


def test_count_response_tolerates_extra_keys_silently() -> None:
    # Strict tier: extras are ignored, not raised.
    resp = _parse_response(
        CountResponse,
        {"count": 7, "requestId": "abc", "serverGens": {}},
        context="ctx",
    )
    assert resp.count == 7


# --------------------------------------------------------------------------- #
# ObjectIdsResponse                                                            #
# --------------------------------------------------------------------------- #


def test_object_ids_response_accepts_camelcase() -> None:
    resp = _parse_response(
        ObjectIdsResponse,
        {"objectIdFieldName": "OBJECTID", "objectIds": [1, 2, 3]},
        context="ctx",
    )
    assert resp.object_id_field_name == "OBJECTID"
    assert resp.object_ids == [1, 2, 3]


def test_object_ids_response_accepts_snake_case() -> None:
    resp = _parse_response(
        ObjectIdsResponse,
        {"object_id_field_name": "FID", "object_ids": [9]},
        context="ctx",
    )
    assert resp.object_id_field_name == "FID"
    assert resp.object_ids == [9]


def test_object_ids_response_coerces_null_ids_to_empty_list() -> None:
    # ArcGIS returns `"objectIds": null` when the query matches zero rows.
    # The model coerces that to `[]` so consumers can iterate safely.
    resp = _parse_response(
        ObjectIdsResponse,
        {"objectIdFieldName": "OBJECTID", "objectIds": None},
        context="ctx",
    )
    assert resp.object_ids == []


def test_object_ids_response_raises_on_missing_field_name() -> None:
    with pytest.raises(RestgdfResponseError):
        _parse_response(
            ObjectIdsResponse,
            {"objectIds": [1, 2]},
            context="ctx",
        )


def test_object_ids_response_raises_on_bad_id_type() -> None:
    with pytest.raises(RestgdfResponseError):
        _parse_response(
            ObjectIdsResponse,
            {"objectIdFieldName": "OBJECTID", "objectIds": "not-a-list"},
            context="ctx",
        )


def test_object_ids_response_dumps_camelcase_by_alias() -> None:
    resp = _parse_response(
        ObjectIdsResponse,
        {"objectIdFieldName": "OBJECTID", "objectIds": [1]},
        context="ctx",
    )
    dumped = resp.model_dump(by_alias=True)
    assert dumped == {"objectIdFieldName": "OBJECTID", "objectIds": [1]}


# --------------------------------------------------------------------------- #
# FeaturesResponse                                                             #
# --------------------------------------------------------------------------- #


def test_features_response_accepts_features_as_list_of_dicts() -> None:
    raw = {
        "objectIdFieldName": "OBJECTID",
        "features": [
            {"attributes": {"OBJECTID": 1}, "geometry": {"x": 0, "y": 0}},
            {"attributes": {"OBJECTID": 2}},
        ],
        "exceededTransferLimit": False,
    }
    resp = _parse_response(FeaturesResponse, raw, context="ctx")
    assert resp.object_id_field_name == "OBJECTID"
    assert resp.features == raw["features"]
    # Envelope preserves features as raw dicts (not Feature instances).
    assert isinstance(resp.features[0], dict)
    assert resp.exceeded_transfer_limit is False


def test_features_response_defaults_features_to_empty_list() -> None:
    resp = _parse_response(FeaturesResponse, {}, context="ctx")
    assert resp.features == []
    assert resp.object_id_field_name is None
    assert resp.exceeded_transfer_limit is None


def test_features_response_logs_unknown_extras_as_drift(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG, logger="restgdf.schema_drift")
    _parse_response(
        FeaturesResponse,
        {"features": [], "mysteryKey": "?"},
        context="ctx",
    )
    assert any(
        r.levelno == logging.DEBUG and "mysteryKey" in r.getMessage()
        for r in caplog.records
    )


def test_features_response_accepts_snake_case_aliases() -> None:
    resp = _parse_response(
        FeaturesResponse,
        {
            "object_id_field_name": "OBJECTID",
            "features": [],
            "exceeded_transfer_limit": True,
        },
        context="ctx",
    )
    assert resp.object_id_field_name == "OBJECTID"
    assert resp.exceeded_transfer_limit is True


# --------------------------------------------------------------------------- #
# TokenResponse                                                                #
# --------------------------------------------------------------------------- #


def test_token_response_accepts_minimal_payload() -> None:
    resp = _parse_response(
        TokenResponse,
        {"token": "xyz", "expires": 32503680000000},
        context="token-refresh",
    )
    assert resp.token == "xyz"
    assert resp.expires == 32503680000000
    assert resp.ssl is None


def test_token_response_ssl_is_optional_when_present() -> None:
    resp = _parse_response(
        TokenResponse,
        {"token": "xyz", "expires": 1234, "ssl": True},
        context="ctx",
    )
    assert resp.ssl is True


def test_token_response_raises_on_missing_token() -> None:
    with pytest.raises(RestgdfResponseError) as exc_info:
        _parse_response(
            TokenResponse,
            {"expires": 1234},
            context="ctx",
        )
    assert exc_info.value.model_name == "TokenResponse"


def test_token_response_raises_on_missing_expires() -> None:
    with pytest.raises(RestgdfResponseError):
        _parse_response(TokenResponse, {"token": "x"}, context="ctx")


def test_token_response_raises_on_bad_expires_type() -> None:
    with pytest.raises(RestgdfResponseError):
        _parse_response(
            TokenResponse,
            {"token": "x", "expires": "not-ms"},
            context="ctx",
        )
