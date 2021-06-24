from pytest import raises
from restgdf import Rest


def test_rest():
    beachurl = r"https://maps1.vcgov.org/arcgis/rest/services/Beaches/MapServer/6"
    beaches = Rest(beachurl, where="City <> 'fgsfds'")
    assert all(
        "fgsfds" in s for s in (beaches.wherestr, beaches.kwargs["data"]["where"])
    )
    assert len(beaches.getuniquevalues(("City", "Status"), sortby="City")) > 10
    assert "Status" in beaches.where("City LIKE 'DAYTONA%'").fields
    assert str(beaches) == f"Beach Access Points ({beachurl})"

    zipurl = "https://services.arcgis.com/P3ePLMYs2RVChkJx/ArcGIS/rest/services/USA_ZIP_Codes_2016/FeatureServer/0"
    ziprest = Rest(zipurl, where="STATE = 'OH'")
    testkwargs = {k: v for k, v in ziprest.kwargs.items()}
    assert "Cincinnati" in ziprest.getuniquevalues("PO_NAME")
    assert ziprest.getuniquevalues("PO_NAME") == ziprest.getuniquevalues("PO_NAME")
    assert (
        ziprest.getvaluecounts("PO_NAME")
        .set_index("PO_NAME")
        .to_dict()["PO_NAME_count"]["Cincinnati"]
        > 40
    )
    with raises(IndexError):
        assert "Cincinnati" in ziprest.getuniquevalues("zzzzzz")
    with raises(IndexError):
        assert len(ziprest.getnestedcount(("PO_NAME", "ZIP"))) > 900
    assert len(ziprest.getnestedcount(("PO_NAME", "ZIP_CODE"))) > 900
    assert ziprest.count > ziprest.jsondict["maxRecordCount"]
    assert len(ziprest.getgdf()) > ziprest.jsondict["maxRecordCount"]
    assert ziprest.kwargs == testkwargs  # make sure nothing is altering kwargs
