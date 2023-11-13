import pytest
from aiohttp import ClientSession

from restgdf.directory.directory import Directory


@pytest.mark.asyncio
async def test_directory():
    async with ClientSession() as s:
        directory = await Directory.from_url(
            "https://maps1.vcgov.org/arcgis/rest/services",
            session=s,
        )
        services = await directory.crawl()
    assert directory.services == services
    first_service_layers = services[0]["metadata"]["layers"]
    assert len(first_service_layers) > 0
    assert isinstance(first_service_layers[0], dict)
    assert len(directory.metadata) > 0
    assert len(directory.rasters()) > 0
    assert len(directory.feature_layers()) > 0
