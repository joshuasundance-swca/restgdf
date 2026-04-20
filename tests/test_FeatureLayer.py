import json
from typing import Optional
from unittest.mock import AsyncMock, patch

import pytest
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


def test_featurelayer_requires_url_to_end_with_numeric_layer_id():
    with pytest.raises(ValueError, match="must end with a number"):
        FeatureLayer(
            "https://example.com/arcgis/rest/services/Secured/FeatureServer",
            session=MockArcGISSession(),
        )


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

    async def fake_get_unique_values(fields, sortby=None):
        assert fields == "OBJECTID"
        assert sortby is None
        return [1, 2, 3]

    layer.get_unique_values = fake_get_unique_values

    assert await layer.get_oids() == [1, 2, 3]


@pytest.mark.asyncio
async def test_featurelayer_prep_populates_metadata_fields(feature_layer_metadata):
    session = MockFeatureLayerSession(metadata=feature_layer_metadata, count=7)
    layer = FeatureLayer(
        "https://example.com/arcgis/rest/services/Secured/FeatureServer/0",
        session=session,
        token="saved-token",
    )

    await layer.prep()

    assert layer.metadata == feature_layer_metadata
    assert layer.name == "Test Layer"
    assert layer.fields == ["OBJECTID", "CITY", "STATUS"]
    assert layer.object_id_field == "OBJECTID"
    assert layer.count == 7
    assert session.get_calls[0][1]["params"]["token"] == "saved-token"


@pytest.mark.asyncio
@pytest.mark.parametrize("metadata", [{"type": "Map Server"}, {}])
async def test_featurelayer_prep_rejects_non_feature_layers(metadata):
    session = MockFeatureLayerSession(metadata=metadata, count=0)
    layer = FeatureLayer(
        "https://example.com/arcgis/rest/services/Secured/FeatureServer/0",
        session=session,
    )

    with pytest.raises(ValueError, match="FeatureLayer"):
        await layer.prep()


@pytest.mark.asyncio
async def test_featurelayer_from_url_calls_prep():
    with patch.object(FeatureLayer, "prep", new=AsyncMock()) as mock_prep:
        layer = await FeatureLayer.from_url(
            "https://example.com/arcgis/rest/services/Secured/FeatureServer/0",
            session=MockArcGISSession(),
        )

    assert isinstance(layer, FeatureLayer)
    mock_prep.assert_awaited_once()


@pytest.mark.asyncio
async def test_featurelayer_samplegdf_uses_random_subset():
    layer = FeatureLayer(
        "https://example.com/arcgis/rest/services/Secured/FeatureServer/0",
        session=MockArcGISSession(),
    )
    layer.object_id_field = "OBJECTID"
    layer.fields = ("OBJECTID",)

    sampled_layer = AsyncMock()
    sampled_layer.get_gdf = AsyncMock(return_value="sampled-gdf")

    with patch(
        "restgdf.featurelayer.featurelayer.get_unique_values",
        new=AsyncMock(return_value=[1, 2, 3]),
    ), patch(
        "restgdf.featurelayer.featurelayer.random.sample",
        return_value=[3, 1],
    ) as mock_sample, patch.object(
        layer,
        "where",
        new=AsyncMock(return_value=sampled_layer),
    ) as mock_where:
        result = await layer.sample_gdf(10)

    assert result == "sampled-gdf"
    mock_sample.assert_called_once_with([1, 2, 3], 3)
    mock_where.assert_awaited_once_with(where_var_in_list("OBJECTID", [3, 1]))


@pytest.mark.asyncio
async def test_featurelayer_headgdf_uses_first_ids():
    layer = FeatureLayer(
        "https://example.com/arcgis/rest/services/Secured/FeatureServer/0",
        session=MockArcGISSession(),
    )
    layer.object_id_field = "OBJECTID"
    layer.fields = ("OBJECTID",)

    head_layer = AsyncMock()
    head_layer.get_gdf = AsyncMock(return_value="head-gdf")

    with patch(
        "restgdf.featurelayer.featurelayer.get_unique_values",
        new=AsyncMock(return_value=[1, 2, 3, 4]),
    ), patch.object(
        layer,
        "where",
        new=AsyncMock(return_value=head_layer),
    ) as mock_where:
        result = await layer.head_gdf(2)

    assert result == "head-gdf"
    mock_where.assert_awaited_once_with(where_var_in_list("OBJECTID", [1, 2]))


@pytest.mark.asyncio
async def test_featurelayer_getgdf_caches_result(sample_feature_gdf):
    layer = FeatureLayer(
        "https://example.com/arcgis/rest/services/Secured/FeatureServer/0",
        session=MockArcGISSession(),
    )

    with patch(
        "restgdf.featurelayer.featurelayer.get_gdf",
        new=AsyncMock(return_value=sample_feature_gdf),
    ) as mock_get_gdf:
        first = await layer.get_gdf()
        second = await layer.get_gdf()

    assert first.equals(sample_feature_gdf)
    assert second.equals(sample_feature_gdf)
    mock_get_gdf.assert_awaited_once()


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

    async def fake_get_unique_values(url, fields, session, sortby=None, **kwargs):
        return [sortby]

    with patch(
        "restgdf.featurelayer.featurelayer.get_unique_values",
        side_effect=fake_get_unique_values,
    ) as mock_get_unique_values:
        first = await layer.get_unique_values(("CITY", "STATE"), sortby="CITY")
        second = await layer.get_unique_values(("CITY", "STATE"), sortby="STATE")

    assert first == ["CITY"]
    assert second == ["STATE"]
    assert mock_get_unique_values.await_count == 2


@pytest.mark.asyncio
async def test_featurelayer_getuniquevalues_rejects_unknown_fields():
    layer = FeatureLayer(
        "https://example.com/arcgis/rest/services/Secured/FeatureServer/0",
        session=MockArcGISSession(),
    )
    layer.fields = ("CITY", "STATE")

    with pytest.raises(IndexError):
        await layer.get_unique_values("ZIP")

    with pytest.raises(IndexError):
        await layer.get_unique_values(("CITY", "ZIP"))


@pytest.mark.asyncio
async def test_featurelayer_getvaluecounts_caches_and_validates_fields():
    layer = FeatureLayer(
        "https://example.com/arcgis/rest/services/Secured/FeatureServer/0",
        session=MockArcGISSession(),
    )
    layer.fields = ("CITY", "STATE")

    with patch(
        "restgdf.featurelayer.featurelayer.get_value_counts",
        new=AsyncMock(return_value="counts"),
    ) as mock_get_value_counts:
        first = await layer.get_value_counts("CITY")
        second = await layer.get_value_counts("CITY")

    assert first == second == "counts"
    mock_get_value_counts.assert_awaited_once()

    with pytest.raises(IndexError):
        await layer.get_value_counts("ZIP")


@pytest.mark.asyncio
async def test_featurelayer_getnestedcount_caches_and_validates_fields():
    layer = FeatureLayer(
        "https://example.com/arcgis/rest/services/Secured/FeatureServer/0",
        session=MockArcGISSession(),
    )
    layer.fields = ("CITY", "STATE")

    with patch(
        "restgdf.featurelayer.featurelayer.nested_count",
        new=AsyncMock(return_value="nested"),
    ) as mock_nested_count:
        first = await layer.get_nested_count(("CITY", "STATE"))
        second = await layer.get_nested_count(("CITY", "STATE"))

    assert first == second == "nested"
    mock_nested_count.assert_awaited_once()

    with pytest.raises(IndexError):
        await layer.get_nested_count(("CITY", "ZIP"))


@pytest.mark.asyncio
async def test_featurelayer_where_combines_filters_and_preserves_kwargs():
    layer = FeatureLayer(
        "https://example.com/arcgis/rest/services/Secured/FeatureServer/0",
        session=MockArcGISSession(),
        where="CITY = 'DAYTONA'",
        token="saved-token",
    )

    with patch(
        "restgdf.featurelayer.featurelayer.FeatureLayer.from_url",
        new=AsyncMock(return_value="filtered-layer"),
    ) as mock_from_url:
        result = await layer.where("STATUS = 'Open'")

    assert result == "filtered-layer"
    mock_from_url.assert_awaited_once_with(
        "https://example.com/arcgis/rest/services/Secured/FeatureServer/0",
        session=layer.session,
        where="CITY = 'DAYTONA' AND STATUS = 'Open'",
        data=layer.kwargs["data"],
    )


@pytest.mark.asyncio
async def test_featurelayer_where_leaves_default_where_unwrapped():
    layer = FeatureLayer(
        "https://example.com/arcgis/rest/services/Secured/FeatureServer/0",
        session=MockArcGISSession(),
    )

    with patch(
        "restgdf.featurelayer.featurelayer.FeatureLayer.from_url",
        new=AsyncMock(return_value="filtered-layer"),
    ) as mock_from_url:
        await layer.where("STATUS = 'Open'")

    mock_from_url.assert_awaited_once_with(
        "https://example.com/arcgis/rest/services/Secured/FeatureServer/0",
        session=layer.session,
        where="STATUS = 'Open'",
        data=layer.kwargs["data"],
    )


def test_featurelayer_repr_and_str():
    layer = FeatureLayer(
        "https://example.com/arcgis/rest/services/Secured/FeatureServer/0",
        session=MockArcGISSession(),
        where="CITY = 'DAYTONA'",
        token="saved-token",
    )
    layer.name = "Beach Access Points"

    representation = repr(layer)

    assert "Rest(" in representation
    assert "CITY = 'DAYTONA'" in representation
    assert str(layer) == (
        "Beach Access Points "
        "(https://example.com/arcgis/rest/services/Secured/FeatureServer/0)"
    )


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
@pytest.mark.network
async def test_featurelayer(client_session):
    with pytest.raises(ValueError):
        await FeatureLayer.from_url(
            "https://maps1.vcgov.org/arcgis/rest/services/Beaches/MapServer",
            session=client_session,
        )
    with pytest.raises(ValueError):
        await FeatureLayer.from_url(
            "https://maps1.vcgov.org/arcgis/rest/services/Aerials/MapServer/4",
            session=client_session,
        )
    beachurl = r"https://maps1.vcgov.org/arcgis/rest/services/Beaches/MapServer/6"
    beaches = await FeatureLayer.from_url(
        beachurl,
        session=client_session,
        where="City <> 'fgsfds'",
    )
    beaches_gdf = await beaches.getgdf()
    assert len(await beaches.samplegdf(2)) == 2
    assert len(await beaches.headgdf(2)) == 2
    assert len(beaches_gdf) > 0

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
    ziprest = await FeatureLayer.from_url(
        zipurl,
        where="STATE = 'OH'",
        session=client_session,
    )
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
