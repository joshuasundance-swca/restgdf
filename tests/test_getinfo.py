import asyncio
from unittest.mock import patch

import pytest
from aiohttp import ClientSession
from pandas import DataFrame

from restgdf.utils.utils import ends_with_num, where_var_in_list
from restgdf.utils.getinfo import (
    DEFAULTDICT,
    default_data,
    get_feature_count,
    getuniquevalues,
    get_metadata,
    get_max_record_count,
    get_name,
    get_offset_range,
    getfields,
    getfields_df,
    getvaluecounts,
)

TESTJSON = {"count": 500, "maxRecordCount": 100}


def test_wherevarinlist():
    assert where_var_in_list("STATE", ["FL", "GA"]) == "STATE In ('FL', 'GA')"
    assert where_var_in_list("OBJECTID", [1, 2]) == "OBJECTID In (1, 2)"


# def mock_session_post(*args, **kwargs):
#     class MockResponse:
#         def __init__(self, json_data):
#             self.json_data = json_data
#
#         def json(self):
#             return self.json_data
#
#     return MockResponse(TESTJSON)


def mock_session_post(*args, **kwargs):
    class MockResponse:
        def __init__(self, json_data):
            self.json_data = json_data
            self.content_type = "application/json"

        async def json(
            self,
            content_type: str = "application/json",
        ):  # make this method async
            return self.json_data

    future = asyncio.Future()  # create a Future object
    future.set_result(MockResponse(TESTJSON))  # set the result of the future
    return future  # return the future


def mock_uniquevalues_post(*args, **kwargs):
    class MockResponse:
        def __init__(self, json_data):
            self.json_data = json_data
            self.content_type = "application/json"

        async def json(self, content_type: str = "application/json"):
            return self.json_data

    future = asyncio.Future()
    future.set_result(
        MockResponse(
            {
                "features": [
                    {"attributes": {"CITY": "C"}},
                    {"attributes": {"CITY": "A"}},
                    {"attributes": {"CITY": "B"}},
                ],
            },
        ),
    )
    return future


@pytest.mark.asyncio
@patch(
    "restgdf.utils.getinfo.ClientSession.post",
    side_effect=mock_session_post,
)
async def test_get_json_dict(mock_response):
    async with ClientSession() as s:
        assert await get_metadata("test", session=s) == TESTJSON


@pytest.mark.asyncio
@patch(
    "restgdf.utils.getinfo.ClientSession.post",
    side_effect=mock_session_post,
)
async def test_get_feature_count(mock_response):
    async with ClientSession() as s:
        assert await get_feature_count("test", session=s) == TESTJSON["count"]
        assert await get_feature_count("test", session=s, data={"where": "test"})
        assert await get_feature_count("test", session=s, data={"token": "test"})
        assert await get_feature_count("test", session=s, data=None)


@patch(
    "restgdf.utils.getinfo.ClientSession.post",
    side_effect=mock_session_post,
)
def test_get_max_record_count(mock_response):
    assert get_max_record_count(TESTJSON) == TESTJSON["maxRecordCount"]


@pytest.mark.asyncio
@patch(
    "restgdf.utils.getinfo.ClientSession.post",
    side_effect=mock_session_post,
)
async def test_get_offset_range(mock_response):
    async with ClientSession() as s:
        assert await get_offset_range("test", session=s) == range(
            0,
            TESTJSON["count"],
            TESTJSON["maxRecordCount"],
        )


@pytest.mark.asyncio
@patch(
    "restgdf.utils.getinfo.ClientSession.post",
    side_effect=mock_uniquevalues_post,
)
async def test_getuniquevalues_sorts_single_field(mock_response):
    async with ClientSession() as s:
        assert await getuniquevalues("test", "CITY", s, sortby="CITY") == [
            "A",
            "B",
            "C",
        ]


def test_default_data():
    t1 = {}
    t1r = {k: v for k, v in DEFAULTDICT.items()}

    t2 = {"where": "test"}
    t2r = {k: v for k, v in DEFAULTDICT.items()}
    t2r["where"] = "test"

    t3 = {"token": "test"}
    t3r = {k: v for k, v in DEFAULTDICT.items()}
    t3r["token"] = "test"

    for indict, outdict in zip([t1, t2, t3], [t1r, t2r, t3r]):
        assert default_data(indict) == outdict


# ---------------------------------------------------------------------------
# Pure-function regression tests (upgrade baseline)
# These cover functions previously only exercised by live-network tests.
# ---------------------------------------------------------------------------

SAMPLE_METADATA = {
    "name": "Test Layer",
    "type": "Feature Layer",
    "fields": [
        {"name": "FIELD1", "type": "esriFieldTypeString"},
        {"name": "FIELD2", "type": "esriFieldTypeInteger"},
    ],
}


def test_ends_with_num():
    assert ends_with_num("https://example.com/FeatureServer/0")
    assert ends_with_num("https://example.com/FeatureServer/42")
    assert not ends_with_num("https://example.com/FeatureServer")
    assert not ends_with_num("https://example.com/FeatureServer/")


def test_get_name():
    assert get_name({"name": "Test Layer"}) == "Test Layer"
    assert get_name({"Name": "Mixed Case"}) == "Mixed Case"
    with pytest.raises(IndexError):
        get_name({"noname": "x"})


def test_getfields():
    assert getfields(SAMPLE_METADATA) == ["FIELD1", "FIELD2"]
    assert getfields(SAMPLE_METADATA, types=True) == {
        "FIELD1": "String",
        "FIELD2": "Integer",
    }


def test_getfields_df():
    df = getfields_df(SAMPLE_METADATA)
    assert isinstance(df, DataFrame)
    assert list(df.columns) == ["name", "type"]
    assert df.iloc[0]["name"] == "FIELD1"
    assert df.iloc[0]["type"] == "String"
    assert df.iloc[1]["name"] == "FIELD2"
    assert df.iloc[1]["type"] == "Integer"


# ---------------------------------------------------------------------------
# Mocked async tests for pandas-heavy paths (upgrade-sensitive)
# getuniquevalues/getvaluecounts use DataFrame construction patterns that
# may silently change across pandas versions.
# ---------------------------------------------------------------------------

FEATURES_SINGLE_JSON = {
    "features": [
        {"attributes": {"City": "DAYTONA"}},
        {"attributes": {"City": "ORMOND"}},
    ],
}

FEATURES_MULTI_JSON = {
    "features": [
        {"attributes": {"City": "DAYTONA", "Status": "Open"}},
        {"attributes": {"City": "ORMOND", "Status": "Closed"}},
    ],
}

VALUECOUNTS_JSON = {
    "features": [
        {"attributes": {"City": "DAYTONA", "City_count": 5}},
        {"attributes": {"City": "ORMOND", "City_count": 3}},
    ],
}


def _make_mock_post(json_data):
    """Return a mock side_effect callable that yields json_data."""

    def _mock(*args, **kwargs):
        class _MockResponse:
            content_type = "application/json"

            async def json(self, content_type="application/json"):
                return json_data

        future = asyncio.Future()
        future.set_result(_MockResponse())
        return future

    return _mock


@pytest.mark.asyncio
@patch(
    "restgdf.utils.getinfo.ClientSession.post",
    side_effect=_make_mock_post(FEATURES_SINGLE_JSON),
)
async def test_getuniquevalues_single_field(mock_response):
    async with ClientSession() as s:
        result = await getuniquevalues("test", "City", session=s)
    assert result == ["DAYTONA", "ORMOND"]


@pytest.mark.asyncio
@patch(
    "restgdf.utils.getinfo.ClientSession.post",
    side_effect=_make_mock_post(FEATURES_SINGLE_JSON),
)
async def test_getuniquevalues_single_element_tuple(mock_response):
    async with ClientSession() as s:
        result = await getuniquevalues("test", ("City",), session=s)
    assert result == ["DAYTONA", "ORMOND"]


@pytest.mark.asyncio
@patch(
    "restgdf.utils.getinfo.ClientSession.post",
    side_effect=_make_mock_post(FEATURES_MULTI_JSON),
)
async def test_getuniquevalues_multi_field(mock_response):
    """Protect the DataFrame(x).T pattern used for multi-field unique values."""
    async with ClientSession() as s:
        result = await getuniquevalues("test", ("City", "Status"), session=s)
    assert isinstance(result, DataFrame)
    assert list(result.columns) == ["City", "Status"]
    assert len(result) == 2
    assert result.iloc[0]["City"] == "DAYTONA"
    assert result.iloc[1]["City"] == "ORMOND"


@pytest.mark.asyncio
@patch(
    "restgdf.utils.getinfo.ClientSession.post",
    side_effect=_make_mock_post(VALUECOUNTS_JSON),
)
async def test_getvaluecounts_mock(mock_response):
    """Protect the concat(DataFrame(x['attributes'], index=[0])...) pattern."""
    async with ClientSession() as s:
        result = await getvaluecounts("test", "City", session=s)
    assert isinstance(result, DataFrame)
    assert "City" in result.columns
    assert "City_count" in result.columns
    # sorted descending by count
    assert result.iloc[0]["City"] == "DAYTONA"
    assert result.iloc[0]["City_count"] == 5
