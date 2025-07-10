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
    first_service_with_layers = None
    for service in services:
        service_layers = service.get("metadata", {}).get("layers", [])
        if service_layers:
            first_service_with_layers = service
            break
    first_service_layers = first_service_with_layers.get("metadata", {}).get("layers", [])
    assert len(first_service_layers) > 0
    assert isinstance(first_service_layers[0], dict)
    assert len(directory.metadata) > 0
    assert len(directory.rasters()) > 0
    assert len(directory.feature_layers()) > 0
