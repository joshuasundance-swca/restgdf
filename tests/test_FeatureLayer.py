import json
from typing import Optional
from unittest.mock import patch

import pytest
from aiohttp import ClientSession
from geopandas import GeoDataFrame
from pytest import raises
from shapely.geometry import Point

from restgdf.featurelayer.featurelayer import FeatureLayer
from restgdf.utils.token import AGOLUserPass, ArcGISTokenSession
from restgdf.utils.utils import where_var_in_list


class MockRequestContext:
    def __init__(self, payload: dict):
        self.payload = payload

    def __await__(self):
        async def _response():
            return self

        return _response().__await__()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        return None

    async def json(self, content_type: Optional[str] = None):
        return self.payload

    async def text(self):
        return json.dumps(self.payload)

    def raise_for_status(self):
        return None


class MockArcGISSession:
    def __init__(self):
        self.get_calls: list[tuple[str, dict]] = []
        self.post_calls: list[tuple[str, dict]] = []

    def get(self, url: str, **kwargs):
        self.get_calls.append((url, kwargs))
        return MockRequestContext({"ok": True})

    def post(self, url: str, **kwargs):
        self.post_calls.append((url, kwargs))
        if url.endswith("generateToken"):
            return MockRequestContext(
                {
                    "token": "generated-token",
                    "expires": 32503680000000,
                },
            )
        return MockRequestContext({"ok": True})


class MockFeatureLayerSession:
    def __init__(
        self,
        metadata: dict,
        count: int,
        object_ids: Optional[list[int]] = None,
    ):
        self.metadata = metadata
        self.count = count
        self.object_ids = object_ids or list(range(1, count + 1))
        self.post_calls: list[tuple[str, dict]] = []
        self.get_calls: list[tuple[str, dict]] = []

    def get(self, url: str, **kwargs):
        copied_kwargs = {
            **kwargs,
            "params": dict(kwargs.get("params", {})),
        }
        self.get_calls.append((url, copied_kwargs))
        return MockRequestContext(self.metadata)

    def post(self, url: str, **kwargs):
        copied_kwargs = {
            **kwargs,
            "data": dict(kwargs.get("data", {})),
        }
        self.post_calls.append((url, copied_kwargs))
        data = copied_kwargs["data"]

        if url.endswith("/query"):
            if data.get("returnCountOnly"):
                return MockRequestContext({"count": self.count})
            if data.get("returnIdsOnly"):
                return MockRequestContext(
                    {
                        "objectIdFieldName": "OBJECTID",
                        "objectIds": self.object_ids,
                    },
                )
            return MockRequestContext({"features": []})

        return MockRequestContext(self.metadata)


def _mock_feature_gdf():
    return GeoDataFrame(
        {"OBJECTID": [1], "geometry": [Point(0, 0)]},
        crs="EPSG:4326",
    )


@pytest.mark.asyncio
async def test_arcgistokensession():
    session = MockArcGISSession()
    token_session = ArcGISTokenSession(
        session=session,
        credentials=AGOLUserPass(username="user", password="password"),
    )

    post_response = await token_session.post(
        "https://example.com/query",
        data={"where": "1=1"},
    )
    get_response = await token_session.get(
        "https://example.com/items",
        params={"f": "json"},
    )

    assert await post_response.json() == {"ok": True}
    assert await get_response.json() == {"ok": True}
    assert token_session.token == "generated-token"
    assert session.post_calls[0][0].endswith("generateToken")
    assert session.post_calls[1][1]["data"]["token"] == "generated-token"
    assert session.get_calls[0][1]["params"]["token"] == "generated-token"


def test_featurelayer_accepts_legacy_token_kwarg():
    layer = FeatureLayer(
        "https://example.com/arcgis/rest/services/Secured/FeatureServer/0",
        session=MockArcGISSession(),
        token="legacy-token",
    )

    assert layer.kwargs["data"]["token"] == "legacy-token"


def test_featurelayer_rejects_conflicting_token_sources():
    with pytest.raises(ValueError):
        FeatureLayer(
            "https://example.com/arcgis/rest/services/Secured/FeatureServer/0",
            session=MockArcGISSession(),
            token="legacy-token",
            data={"token": "other-token"},
        )


@pytest.mark.asyncio
async def test_getoids_uses_objectid_field():
    layer = FeatureLayer(
        "https://example.com/arcgis/rest/services/Secured/FeatureServer/0",
        session=MockArcGISSession(),
    )
    layer.fields = ["OBJECTID"]

    async def fake_getuniquevalues(fields, sortby=None):
        assert fields == "OBJECTID"
        assert sortby is None
        return [1, 2, 3]

    layer.getuniquevalues = fake_getuniquevalues

    assert await layer.getoids() == [1, 2, 3]


@pytest.mark.asyncio
async def test_row_dict_generator_merges_data_kwargs():
    layer = FeatureLayer(
        "https://example.com/arcgis/rest/services/Secured/FeatureServer/0",
        session=MockArcGISSession(),
        where="CITY = 'DAYTONA'",
        token="saved-token",
    )

    async def fake_row_dict_generator(url, session, **kwargs):
        assert kwargs["data"]["where"] == "CITY = 'DAYTONA'"
        assert kwargs["data"]["token"] == "saved-token"
        assert kwargs["data"]["outFields"] == "CITY"
        yield {"ok": True}

    with patch(
        "restgdf.featurelayer.featurelayer.row_dict_generator",
        side_effect=fake_row_dict_generator,
    ):
        rows = [
            row async for row in layer.row_dict_generator(data={"outFields": "CITY"})
        ]

    assert rows == [{"ok": True}]


@pytest.mark.asyncio
async def test_getuniquevalues_cache_includes_sortby():
    layer = FeatureLayer(
        "https://example.com/arcgis/rest/services/Secured/FeatureServer/0",
        session=MockArcGISSession(),
    )
    layer.fields = ("CITY", "STATE")

    async def fake_getuniquevalues(url, fields, session, sortby=None, **kwargs):
        return [sortby]

    with patch(
        "restgdf.featurelayer.featurelayer.getuniquevalues",
        side_effect=fake_getuniquevalues,
    ) as mock_getuniquevalues:
        first = await layer.getuniquevalues(("CITY", "STATE"), sortby="CITY")
        second = await layer.getuniquevalues(("CITY", "STATE"), sortby="STATE")

    assert first == ["CITY"]
    assert second == ["STATE"]
    assert mock_getuniquevalues.await_count == 2


@pytest.mark.asyncio
async def test_getgdf_avoids_result_offset_when_pagination_is_unsupported():
    session = MockFeatureLayerSession(
        metadata={
            "name": "Unsupported Pagination Layer",
            "type": "Feature Layer",
            "fields": [{"name": "OBJECTID", "type": "esriFieldTypeOID"}],
            "maxRecordCount": 100,
            "advancedQueryCapabilities": {"supportsPagination": False},
        },
        count=3,
    )

    with patch(
        "restgdf.utils.getgdf.read_file",
        side_effect=lambda *args, **kwargs: _mock_feature_gdf(),
    ):
        layer = await FeatureLayer.from_url(
            "https://example.com/arcgis/rest/services/Test/FeatureServer/0",
            session=session,
        )
        await layer.getgdf()

    feature_queries = [
        call_kwargs["data"]
        for url, call_kwargs in session.post_calls
        if url.endswith("/query")
        and not call_kwargs["data"].get("returnCountOnly")
        and not call_kwargs["data"].get("returnIdsOnly")
    ]

    assert len(feature_queries) == 1
    assert "resultOffset" not in feature_queries[0]


@pytest.mark.asyncio
async def test_getgdf_falls_back_to_objectid_chunks_without_pagination():
    session = MockFeatureLayerSession(
        metadata={
            "name": "Unsupported Pagination Layer",
            "type": "Feature Layer",
            "fields": [{"name": "OBJECTID", "type": "esriFieldTypeOID"}],
            "maxRecordCount": 2,
            "advancedQueryCapabilities": {"supportsPagination": False},
        },
        count=5,
        object_ids=[1, 2, 3, 4, 5],
    )

    with patch(
        "restgdf.utils.getgdf.read_file",
        side_effect=lambda *args, **kwargs: _mock_feature_gdf(),
    ):
        layer = await FeatureLayer.from_url(
            "https://example.com/arcgis/rest/services/Test/FeatureServer/0",
            session=session,
        )
        await layer.getgdf()

    query_calls = [
        call_kwargs["data"]
        for url, call_kwargs in session.post_calls
        if url.endswith("/query")
    ]
    feature_queries = [
        data
        for data in query_calls
        if not data.get("returnCountOnly") and not data.get("returnIdsOnly")
    ]

    assert any(data.get("returnIdsOnly") for data in query_calls)
    assert len(feature_queries) == 3
    assert all("resultOffset" not in data for data in feature_queries)
    assert {data["where"] for data in feature_queries} == {
        where_var_in_list("OBJECTID", [1, 2]),
        where_var_in_list("OBJECTID", [3, 4]),
        where_var_in_list("OBJECTID", [5]),
    }


@pytest.mark.asyncio
async def test_featurelayer():
    async with ClientSession() as s:
        # print("testing workflow")
        with pytest.raises(ValueError):
            await FeatureLayer.from_url(
                "https://maps1.vcgov.org/arcgis/rest/services/Beaches/MapServer",
                session=s,
            )
        with pytest.raises(ValueError):
            await FeatureLayer.from_url(
                "https://maps1.vcgov.org/arcgis/rest/services/Aerials/MapServer/4",
                session=s,
            )
        beachurl = r"https://maps1.vcgov.org/arcgis/rest/services/Beaches/MapServer/6"
        beaches = await FeatureLayer.from_url(
            beachurl,
            session=s,
            where="City <> 'fgsfds'",
        )
        beaches_gdf = await beaches.getgdf()
        assert len(await beaches.samplegdf(2)) == 2
        assert len(await beaches.headgdf(2)) == 2
        assert len(beaches_gdf) > 0

        # test row_dict_generator
        row_gen = beaches.row_dict_generator()
        beaches_row_gen_count = 0
        async for row in row_gen:
            assert isinstance(row, dict)
            beaches_row_gen_count += 1
        assert beaches_row_gen_count == len(beaches_gdf)

        assert all(
            "fgsfds" in s for s in (beaches.wherestr, beaches.kwargs["data"]["where"])
        )
        assert len(await beaches.getuniquevalues(("City", "Status"), sortby="City")) > 1
        daytona = await beaches.where("City LIKE 'DAYTONA%'")
        assert "Status" in daytona.fields
        assert str(beaches) == f"Beach Access Points ({beachurl})"

        zipurl = "https://services.arcgis.com/P3ePLMYs2RVChkJx/ArcGIS/rest/services/USA_ZIP_Codes_2016/FeatureServer/0"
        ziprest = await FeatureLayer.from_url(zipurl, where="STATE = 'OH'", session=s)
        testkwargs = {k: v for k, v in ziprest.kwargs.items()}
        assert "Cincinnati" in await ziprest.getuniquevalues("PO_NAME")
        assert await ziprest.getuniquevalues(
            "PO_NAME",
        ) == await ziprest.getuniquevalues(
            "PO_NAME",
        )
        assert (await ziprest.getvaluecounts("PO_NAME")).set_index("PO_NAME").to_dict()[
            "PO_NAME_count"
        ]["Cincinnati"] > 40
        with raises(IndexError):
            assert "Cincinnati" in await ziprest.getuniquevalues("zzzzzz")
        with raises(IndexError):
            assert len(await ziprest.getnestedcount(("PO_NAME", "ZIP"))) > 900
        assert len(await ziprest.getnestedcount(("PO_NAME", "ZIP_CODE"))) > 900
        assert ziprest.count > ziprest.metadata["maxRecordCount"]
        assert len(await ziprest.getgdf()) > ziprest.metadata["maxRecordCount"]
        assert ziprest.kwargs == testkwargs  # make sure nothing is altering kwargs
