"""Unit tests for restgdf._client.request.build_conservative_query_data.

These are red/green contract tests pinning the exact merge semantics of
the legacy conservative-merge pattern in restgdf.utils.getinfo.
"""

from __future__ import annotations

import pytest

from restgdf._client.request import build_conservative_query_data


COUNT_BASE = {"where": "1=1", "returnCountOnly": True, "f": "json"}
IDS_BASE = {"where": "1=1", "returnIdsOnly": True, "f": "json"}
UNIQUE_BASE = {
    "where": "1=1",
    "f": "json",
    "returnGeometry": False,
    "returnDistinctValues": True,
    "outFields": "CITY",
}


class TestBuildConservativeQueryDataNoCaller:
    def test_none_caller_returns_base_copy(self):
        result = build_conservative_query_data(COUNT_BASE, None)
        assert result == COUNT_BASE

    def test_empty_caller_returns_base_copy(self):
        result = build_conservative_query_data(COUNT_BASE, {})
        assert result == COUNT_BASE

    def test_returns_new_dict_not_base_reference(self):
        result = build_conservative_query_data(COUNT_BASE)
        result["where"] = "MUTATED"
        assert COUNT_BASE["where"] == "1=1"

    def test_default_caller_argument_is_none(self):
        assert build_conservative_query_data(IDS_BASE) == IDS_BASE


class TestBuildConservativeQueryDataCallerOverrides:
    def test_caller_where_overrides_base(self):
        result = build_conservative_query_data(COUNT_BASE, {"where": "STATE='CA'"})
        assert result["where"] == "STATE='CA'"
        assert result["returnCountOnly"] is True
        assert result["f"] == "json"

    def test_caller_token_is_injected(self):
        result = build_conservative_query_data(COUNT_BASE, {"token": "abc123"})
        assert result["token"] == "abc123"

    def test_caller_where_and_token_both_injected(self):
        result = build_conservative_query_data(
            UNIQUE_BASE,
            {"where": "POP > 100", "token": "xyz"},
        )
        assert result["where"] == "POP > 100"
        assert result["token"] == "xyz"
        assert result["returnDistinctValues"] is True
        assert result["outFields"] == "CITY"


class TestBuildConservativeQueryDataDropsExtras:
    """Extras passed in caller_data MUST be dropped. This is the defining
    property of the conservative merge."""

    def test_caller_outfields_is_dropped(self):
        result = build_conservative_query_data(COUNT_BASE, {"outFields": "EVIL"})
        assert "outFields" not in result or result.get("outFields") != "EVIL"

    def test_caller_cannot_clobber_return_count_only(self):
        result = build_conservative_query_data(
            COUNT_BASE,
            {"returnCountOnly": False, "token": "t"},
        )
        assert result["returnCountOnly"] is True

    def test_caller_cannot_clobber_f_json(self):
        result = build_conservative_query_data(
            COUNT_BASE,
            {"f": "pbf", "token": "t"},
        )
        assert result["f"] == "json"

    def test_caller_cannot_add_arbitrary_keys(self):
        result = build_conservative_query_data(
            COUNT_BASE,
            {"resultOffset": 500, "resultRecordCount": 1000, "token": "t"},
        )
        assert "resultOffset" not in result
        assert "resultRecordCount" not in result


class TestBuildConservativeQueryDataQuirks:
    """Preserve exact legacy quirks so swap-in is behavior-identical."""

    def test_truthy_caller_without_where_still_resets_where_to_default(self):
        # Legacy behavior: if caller_data is truthy but has no "where" key,
        # datadict["where"] is still overwritten with "1=1". For a base that
        # already has where="1=1" this is a no-op, but the write still happens.
        base = {"where": "CUSTOM", "f": "json"}
        result = build_conservative_query_data(base, {"token": "t"})
        assert result["where"] == "1=1"

    def test_caller_with_only_extras_no_where_no_token_is_effective_noop(self):
        # caller_data is truthy but has no where/token -> only the where
        # reset quirk applies; extras are dropped.
        result = build_conservative_query_data(COUNT_BASE, {"outFields": "IGNORED"})
        assert result == COUNT_BASE

    def test_does_not_mutate_caller_data(self):
        caller = {"where": "X", "token": "t"}
        original = dict(caller)
        build_conservative_query_data(COUNT_BASE, caller)
        assert caller == original

    def test_does_not_mutate_base(self):
        base = dict(COUNT_BASE)
        build_conservative_query_data(base, {"where": "X", "token": "t"})
        assert base == COUNT_BASE


@pytest.mark.parametrize(
    "base",
    [COUNT_BASE, IDS_BASE, UNIQUE_BASE],
    ids=["count", "ids", "unique"],
)
def test_helper_works_with_all_three_conservative_bases(base):
    result = build_conservative_query_data(base, {"where": "W", "token": "T"})
    for k, v in base.items():
        if k == "where":
            assert result[k] == "W"
        else:
            assert result[k] == v
    assert result["token"] == "T"
