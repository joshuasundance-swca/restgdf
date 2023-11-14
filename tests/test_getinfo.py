import asyncio
from unittest.mock import patch

import pytest
from aiohttp import ClientSession

from restgdf.utils.utils import where_var_in_list
from restgdf.utils.getinfo import (
    DEFAULTDICT,
    default_data,
    get_feature_count,
    get_metadata,
    get_max_record_count,
    get_offset_range,
)

TESTJSON = {"count": 500, "maxRecordCount": 100}


def test_wherevarinlist():
    assert where_var_in_list("STATE", ["FL", "GA"]) == "STATE In ('FL', 'GA')"


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
