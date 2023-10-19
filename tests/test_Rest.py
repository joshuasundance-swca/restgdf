import pytest
from aiohttp import ClientSession
from pytest import raises
from restgdf import Rest


@pytest.mark.asyncio
async def test_rest():
    async with ClientSession() as s:
        beachurl = r"https://maps1.vcgov.org/arcgis/rest/services/Beaches/MapServer/6"
        beaches = await Rest.from_url(beachurl, session=s, where="City <> 'fgsfds'")
        beaches_gdf = await beaches.getgdf()
        assert len(beaches_gdf) > 0
        assert all(
            "fgsfds" in s for s in (beaches.wherestr, beaches.kwargs["data"]["where"])
        )
        assert (
            len(await beaches.getuniquevalues(("City", "Status"), sortby="City")) > 10
        )
        daytona = await beaches.where("City LIKE 'DAYTONA%'")
        assert "Status" in daytona.fields
        assert str(beaches) == f"Beach Access Points ({beachurl})"

        zipurl = "https://services.arcgis.com/P3ePLMYs2RVChkJx/ArcGIS/rest/services/USA_ZIP_Codes_2016/FeatureServer/0"
        ziprest = await Rest.from_url(zipurl, where="STATE = 'OH'", session=s)
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
        assert ziprest.count > ziprest.jsondict["maxRecordCount"]
        assert len(await ziprest.getgdf()) > ziprest.jsondict["maxRecordCount"]
        assert ziprest.kwargs == testkwargs  # make sure nothing is altering kwargs
