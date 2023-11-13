import pytest
from aiohttp import ClientSession

from restgdf.directory.directory import Directory
from restgdf.directory._crawl import fetch_all_data


@pytest.mark.asyncio
async def test_directory():
    async with ClientSession() as s:
        directory = await Directory.from_url(
            "https://maps1.vcgov.org/arcgis/rest/services",
            session=s,
        )
    assert len(directory.data) > 0
    assert len(directory.metadata) > 0


@pytest.mark.asyncio
async def test_fetch_all_data():
    testurl = "https://ocgis4.ocfl.net/arcgis/rest/services"
    async with ClientSession() as s:
        data = await fetch_all_data(s, testurl)
    first_key = list(data["services"].keys())[0]
    first_key_layers = data["services"][first_key]["layers"]
    assert len(first_key_layers) > 0
    assert len(data["metadata"]) > 0
    return data
