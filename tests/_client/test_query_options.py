"""Phase 5 TDD tests for :class:`restgdf._client.query_options.QueryOptions`.

``QueryOptions`` is the typed, frozen request-payload builder that wraps
the legacy ``dict``-based datadict construction used across ``getinfo``
and ``getgdf``. It is introduced in Phase 5 as an **optional** new API:
existing ``FeatureLayer`` and ``getgdf`` call sites are NOT migrated in
this phase, so every pre-Phase-5 test must remain green.

Contract (locked by these tests):

1. Typed fields always win over ``extra`` on key conflict.
2. ``None``-valued optional typed fields are omitted from the payload.
3. Defaults match the legacy ``DEFAULTDICT`` exactly, so a no-arg
   ``QueryOptions().to_data()`` equals ``default_data()``.
4. ``extra`` is copied and its immutable view does not leak the caller's
   dict.
5. ``from_legacy_kwargs`` parses the existing ``dict``-style kwargs used
   by ``FeatureLayer`` without mutating the caller's input.
"""

from __future__ import annotations

import dataclasses

import pytest

from restgdf._client.query_options import QueryOptions
from restgdf.utils._http import DEFAULTDICT, default_data


def test_default_to_data_matches_legacy_default_data():
    assert QueryOptions().to_data() == default_data()


def test_explicit_where_and_outfields_override_defaults():
    opts = QueryOptions(where="CITY = 'DAYTONA'", out_fields="CITY,STATE")
    data = opts.to_data()
    assert data["where"] == "CITY = 'DAYTONA'"
    assert data["outFields"] == "CITY,STATE"
    assert data["f"] == "json"


def test_optional_fields_omitted_when_none():
    data = QueryOptions().to_data()
    assert "token" not in data
    assert "resultOffset" not in data
    assert "resultRecordCount" not in data


def test_token_included_when_provided():
    opts = QueryOptions(token="abc123")
    assert opts.to_data()["token"] == "abc123"


def test_result_offset_and_record_count_serialized_when_set():
    opts = QueryOptions(result_offset=100, result_record_count=2000)
    data = opts.to_data()
    assert data["resultOffset"] == 100
    assert data["resultRecordCount"] == 2000


def test_return_ids_only_and_count_only_flags():
    assert QueryOptions(return_ids_only=True).to_data()["returnIdsOnly"] is True
    assert QueryOptions(return_count_only=True).to_data()["returnCountOnly"] is True


def test_return_geometry_default_true_can_be_overridden():
    assert QueryOptions().to_data()["returnGeometry"] is True
    assert QueryOptions(return_geometry=False).to_data()["returnGeometry"] is False


def test_extra_fills_non_reserved_keys():
    opts = QueryOptions(extra={"orderByFields": "OBJECTID"})
    data = opts.to_data()
    assert data["orderByFields"] == "OBJECTID"
    assert data["where"] == "1=1"  # typed default still applies


def test_typed_fields_win_over_extra_on_conflict():
    opts = QueryOptions(
        where="CITY = 'DAYTONA'",
        token="typed-tok",
        extra={"where": "SHOULD_LOSE = 1", "token": "ignored", "orderByFields": "X"},
    )
    data = opts.to_data()
    assert data["where"] == "CITY = 'DAYTONA'"
    assert data["token"] == "typed-tok"
    assert data["orderByFields"] == "X"


def test_queryoptions_is_frozen():
    opts = QueryOptions()
    with pytest.raises(dataclasses.FrozenInstanceError):
        opts.where = "X=1"  # type: ignore[misc]


def test_extra_is_immutable_view():
    src = {"orderByFields": "OBJECTID"}
    opts = QueryOptions(extra=src)
    with pytest.raises(TypeError):
        opts.extra["orderByFields"] = "X"  # type: ignore[index]
    # mutating source does not leak into the options
    src["orderByFields"] = "MUTATED"
    assert opts.extra["orderByFields"] == "OBJECTID"


def test_to_data_produces_fresh_dict_each_call():
    opts = QueryOptions()
    first = opts.to_data()
    second = opts.to_data()
    assert first == second
    assert first is not second
    first["where"] = "MUTATED"
    assert QueryOptions().to_data()["where"] == "1=1"


def test_from_legacy_kwargs_extracts_where_and_token():
    kwargs = {"where": "CITY = 'DAYTONA'", "data": {"token": "legacy-tok"}}
    opts = QueryOptions.from_legacy_kwargs(kwargs)
    assert opts.where == "CITY = 'DAYTONA'"
    assert opts.token == "legacy-tok"
    # caller input untouched
    assert kwargs == {"where": "CITY = 'DAYTONA'", "data": {"token": "legacy-tok"}}


def test_from_legacy_kwargs_data_where_takes_precedence_over_top_level():
    # Mirrors FeatureLayer.__init__: datadict["where"] = wherestr is the
    # final say, but when only data={"where": ...} is passed, it wins.
    kwargs = {"data": {"where": "FROM_DATA = 1"}}
    opts = QueryOptions.from_legacy_kwargs(kwargs)
    assert opts.where == "FROM_DATA = 1"


def test_from_legacy_kwargs_extras_flow_to_extra():
    kwargs = {"data": {"outFields": "CITY", "orderByFields": "OBJECTID"}}
    opts = QueryOptions.from_legacy_kwargs(kwargs)
    assert opts.out_fields == "CITY"
    assert opts.extra["orderByFields"] == "OBJECTID"


def test_from_legacy_kwargs_empty_yields_defaults():
    opts = QueryOptions.from_legacy_kwargs({})
    assert opts == QueryOptions()
    assert opts.to_data() == default_data()


def test_defaultdict_is_unchanged_by_queryoptions_usage():
    snapshot = dict(DEFAULTDICT)
    QueryOptions(where="X=1", extra={"a": 1}).to_data()
    assert DEFAULTDICT == snapshot
