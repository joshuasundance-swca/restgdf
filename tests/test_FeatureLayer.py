import pytest
from aiohttp import ClientSession
from pytest import raises

from restgdf.featurelayer.featurelayer import FeatureLayer
from restgdf.utils.token import AGOLUserPass, ArcGISTokenSession


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

    async def json(self, content_type: str | None = None):
        return self.payload

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
