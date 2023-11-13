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
    first_key = list(services.keys())[0]
    first_key_layers = services[first_key]["layers"]
    assert len(first_key_layers) > 0
    assert isinstance(first_key_layers[0], dict)
    assert len(directory.metadata) > 0
