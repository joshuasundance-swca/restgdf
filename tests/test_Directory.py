from unittest.mock import AsyncMock, patch

import pytest

from restgdf.directory.directory import Directory


@pytest.mark.asyncio
@pytest.mark.network
async def test_directory(client_session):
    directory = await Directory.from_url(
        "https://maps1.vcgov.org/arcgis/rest/services",
        session=client_session,
    )
    services = await directory.crawl()
    assert directory.services == services
    first_service_with_layers = None
    for service in services:
        service_layers = service.get("metadata", {}).get("layers", [])
        if service_layers:
            first_service_with_layers = service
            break
    first_service_layers = first_service_with_layers.get("metadata", {}).get(
        "layers",
        [],
    )
    assert len(first_service_layers) > 0
    assert isinstance(first_service_layers[0], dict)
    assert len(directory.metadata) > 0
    assert len(directory.rasters()) > 0
    assert len(directory.feature_layers()) > 0


@pytest.mark.asyncio
async def test_directory_crawl_caches_feature_count_variant_separately():
    directory = Directory("https://example.com/arcgis/rest/services", session=object())
    without_count = {"services": [{"name": "base"}]}
    with_count = {
        "services": [{"name": "with-count", "metadata": {"feature_count": 1}}],
    }

    with patch(
        "restgdf.directory.directory.fetch_all_data",
        new=AsyncMock(side_effect=[without_count, with_count]),
    ) as mock_fetch:
        first = await directory.crawl(return_feature_count=False)
        second = await directory.crawl(return_feature_count=True)

    assert first == without_count["services"]
    assert second == with_count["services"]
    assert mock_fetch.await_count == 2
