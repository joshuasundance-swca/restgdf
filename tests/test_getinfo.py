import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from pandas import DataFrame

from restgdf.utils.utils import ends_with_num, where_var_in_list
from restgdf.utils.getinfo import (
    DEFAULTDICT,
    default_headers,
    default_data,
    get_feature_count,
    get_object_id_field,
    get_object_ids,
    getuniquevalues,
    get_metadata,
    get_max_record_count,
    get_name,
    get_offset_range,
    getfields,
    getfields_df,
    nestedcount,
    service_metadata,
    supports_pagination,
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


def mock_session_get(*args, **kwargs):
    class MockResponse:
        def __init__(self, json_data):
            self.json_data = json_data
            self.content_type = "application/json"

        async def json(
            self,
            content_type: str = "application/json",
        ):
            return self.json_data

    future = asyncio.Future()
    future.set_result(MockResponse(TESTJSON))
    return future


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
    "restgdf.utils.getinfo.ClientSession.get",
    side_effect=mock_session_get,
)
async def test_get_json_dict(mock_response, client_session):
    result = await get_metadata("test", session=client_session)
    assert result.model_dump(by_alias=True, exclude_none=True) == TESTJSON


@pytest.mark.asyncio
@patch(
    "restgdf.utils.getinfo.ClientSession.post",
    side_effect=mock_session_post,
)
async def test_get_feature_count(mock_response, client_session):
    assert await get_feature_count("test", session=client_session) == TESTJSON["count"]
    assert await get_feature_count(
        "test",
        session=client_session,
        data={"where": "test"},
    )
    assert await get_feature_count(
        "test",
        session=client_session,
        data={"token": "test"},
    )
    assert await get_feature_count("test", session=client_session, data=None)


@patch(
    "restgdf.utils.getinfo.ClientSession.post",
    side_effect=mock_session_post,
)
def test_get_max_record_count(mock_response):
    assert get_max_record_count(TESTJSON) == TESTJSON["maxRecordCount"]


@pytest.mark.asyncio
@patch(
    "restgdf.utils.getinfo.ClientSession.get",
    side_effect=mock_session_get,
)
@patch(
    "restgdf.utils.getinfo.ClientSession.post",
    side_effect=mock_session_post,
)
async def test_get_offset_range(mock_post, mock_get, client_session):
    assert await get_offset_range("test", session=client_session) == range(
        0,
        TESTJSON["count"],
        TESTJSON["maxRecordCount"],
    )


@pytest.mark.asyncio
@patch(
    "restgdf.utils.getinfo.ClientSession.post",
    side_effect=mock_uniquevalues_post,
)
async def test_getuniquevalues_sorts_single_field(mock_response, client_session):
    assert await getuniquevalues(
        "test",
        "CITY",
        client_session,
        sortby="CITY",
    ) == ["A", "B", "C"]


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


def test_default_headers():
    assert default_headers({"X-Test": "yes"}) == {
        "Accept": "application/json,text/plain,*/*",
        "User-Agent": "Mozilla/5.0",
        "X-Test": "yes",
    }


def test_supports_pagination_prefers_advanced_query_capabilities():
    assert (
        supports_pagination(
            {"advancedQueryCapabilities": {"supportsPagination": False}},
        )
        is False
    )
    assert supports_pagination({"supportsPagination": False}) is False
    assert supports_pagination({}) is True


def test_get_object_id_field():
    assert (
        get_object_id_field(
            {"fields": [{"name": "OBJECTID", "type": "esriFieldTypeOID"}]},
        )
        == "OBJECTID"
    )

    with pytest.raises(IndexError):
        get_object_id_field({"fields": []})

    with pytest.raises(IndexError):
        get_object_id_field(
            {
                "fields": [
                    {"name": "OBJECTID", "type": "esriFieldTypeOID"},
                    {"name": "ALTID", "type": "esriFieldTypeOID"},
                ],
            },
        )


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
async def test_getuniquevalues_single_field(mock_response, client_session):
    result = await getuniquevalues("test", "City", session=client_session)
    assert result == ["DAYTONA", "ORMOND"]


@pytest.mark.asyncio
@patch(
    "restgdf.utils.getinfo.ClientSession.post",
    side_effect=_make_mock_post(FEATURES_SINGLE_JSON),
)
async def test_getuniquevalues_single_element_tuple(mock_response, client_session):
    result = await getuniquevalues("test", ("City",), session=client_session)
    assert result == ["DAYTONA", "ORMOND"]


@pytest.mark.asyncio
@patch(
    "restgdf.utils.getinfo.ClientSession.post",
    side_effect=_make_mock_post(FEATURES_MULTI_JSON),
)
async def test_getuniquevalues_multi_field(mock_response, client_session):
    """Protect the DataFrame(x).T pattern used for multi-field unique values."""
    result = await getuniquevalues(
        "test",
        ("City", "Status"),
        session=client_session,
    )
    assert isinstance(result, DataFrame)
    assert list(result.columns) == ["City", "Status"]
    assert len(result) == 2
    assert result.iloc[0]["City"] == "DAYTONA"
    assert result.iloc[1]["City"] == "ORMOND"


@pytest.mark.asyncio
@patch(
    "restgdf.utils.getinfo.ClientSession.post",
    side_effect=_make_mock_post(FEATURES_MULTI_JSON),
)
async def test_getuniquevalues_multi_field_sorts_dataframe(
    mock_response,
    client_session,
):
    result = await getuniquevalues(
        "test",
        ("City", "Status"),
        session=client_session,
        sortby="City",
    )

    assert result.iloc[0]["City"] == "DAYTONA"
    assert result.iloc[1]["City"] == "ORMOND"


@pytest.mark.asyncio
@patch(
    "restgdf.utils.getinfo.ClientSession.post",
    side_effect=_make_mock_post(VALUECOUNTS_JSON),
)
async def test_getvaluecounts_mock(mock_response, client_session):
    """Protect the concat(DataFrame(x['attributes'], index=[0])...) pattern."""
    result = await getvaluecounts("test", "City", session=client_session)
    assert isinstance(result, DataFrame)
    assert "City" in result.columns
    assert "City_count" in result.columns
    # sorted descending by count
    assert result.iloc[0]["City"] == "DAYTONA"
    assert result.iloc[0]["City_count"] == 5


@pytest.mark.asyncio
@patch(
    "restgdf.utils.getinfo.ClientSession.post",
    side_effect=_make_mock_post(
        {
            "objectIdFieldName": "OBJECTID",
            "objectIds": [1, 2, 3],
        },
    ),
)
async def test_get_object_ids_passes_through_where_and_token(
    mock_response,
    client_session,
):
    field_name, object_ids = await get_object_ids(
        "test",
        client_session,
        data={"where": "CITY = 'DAYTONA'", "token": "abc123"},
        headers={"X-Test": "yes"},
    )

    assert field_name == "OBJECTID"
    assert object_ids == [1, 2, 3]


@pytest.mark.asyncio
@patch(
    "restgdf.utils.getinfo.ClientSession.post",
    side_effect=_make_mock_post(
        {
            "features": [
                {
                    "attributes": {
                        "City": "DAYTONA",
                        "Status": "Open",
                        "City_count": 2,
                        "Status_count": 2,
                    },
                },
                {
                    "attributes": {
                        "City": "DAYTONA",
                        "Status": "Closed",
                        "City_count": 1,
                        "Status_count": 1,
                    },
                },
                {
                    "attributes": {
                        "City": "ORMOND",
                        "Status": "Closed",
                        "City_count": 1,
                        "Status_count": 1,
                    },
                },
            ],
        },
    ),
)
async def test_nestedcount_shapes_output(mock_response, client_session):
    result = await nestedcount(
        "test",
        ("City", "Status"),
        client_session,
    )

    assert list(result.columns) == ["City", "Status", "Count"]
    assert result.iloc[0]["City"] == "DAYTONA"
    assert result.iloc[0]["Count"] >= result.iloc[1]["Count"]


@pytest.mark.asyncio
async def test_service_metadata_fetches_layers_and_feature_counts():
    metadata_by_url = {
        "https://example.com/service": {
            "layers": [{"id": 0}, {"id": 1}],
        },
        "https://example.com/service/0": {
            "type": "Feature Layer",
            "name": "Parcels",
        },
        "https://example.com/service/1": {
            "type": "Raster Layer",
            "name": "Imagery",
        },
    }

    async def fake_get_metadata(url, session, token=None):
        return dict(metadata_by_url[url])

    async def fake_get_feature_count(url, session, **kwargs):
        return 12

    with (
        patch(
            "restgdf.utils.getinfo.get_metadata",
            side_effect=fake_get_metadata,
        ),
        patch(
            "restgdf.utils.getinfo.get_feature_count",
            side_effect=fake_get_feature_count,
        ) as mock_get_feature_count,
    ):
        result = await service_metadata(
            object(),
            "https://example.com/service",
            token="abc123",
            return_feature_count=True,
        )

    assert result.layers[0].url == "https://example.com/service/0"
    assert result.layers[0].feature_count == 12
    assert result.layers[1].feature_count is None
    mock_get_feature_count.assert_awaited_once()


@pytest.mark.asyncio
async def test_service_metadata_sets_feature_count_none_when_count_lookup_fails():
    async def fake_get_metadata(url, session, token=None):
        if url.endswith("/0"):
            return {"type": "Feature Layer"}
        return {"layers": [{"id": 0}]}

    with (
        patch(
            "restgdf.utils.getinfo.get_metadata",
            side_effect=fake_get_metadata,
        ),
        patch(
            "restgdf.utils.getinfo.get_feature_count",
            new=AsyncMock(side_effect=KeyError("count")),
        ),
    ):
        result = await service_metadata(
            object(),
            "https://example.com/service",
            return_feature_count=True,
        )

    assert result.layers[0].feature_count is None
