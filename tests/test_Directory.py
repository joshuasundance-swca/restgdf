from unittest.mock import AsyncMock, patch

import pytest

from restgdf._models.crawl import CrawlReport, CrawlServiceEntry
from restgdf._models.responses import LayerMetadata
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
        service_layers = (
            service.metadata.layers if service.metadata is not None else None
        ) or []
        if service_layers:
            first_service_with_layers = service
            break
    first_service_layers = (
        first_service_with_layers.metadata.layers
        if first_service_with_layers is not None
        else []
    ) or []
    assert len(first_service_layers) > 0
    assert isinstance(first_service_layers[0], LayerMetadata)
    assert directory.metadata is not None
    assert len(directory.rasters()) > 0
    assert len(directory.feature_layers()) > 0


@pytest.mark.asyncio
async def test_directory_crawl_caches_feature_count_variant_separately():
    directory = Directory("https://example.com/arcgis/rest/services", session=object())
    without_count = CrawlReport(
        services=[CrawlServiceEntry(name="base", url="https://example.com/base")],
    )
    with_count = CrawlReport(
        services=[
            CrawlServiceEntry(
                name="with-count",
                url="https://example.com/with-count",
                metadata=LayerMetadata(feature_count=1),
            ),
        ],
    )

    with patch(
        "restgdf.directory.directory.safe_crawl",
        new=AsyncMock(side_effect=[without_count, with_count]),
    ) as mock_crawl:
        first = await directory.crawl(return_feature_count=False)
        second = await directory.crawl(return_feature_count=True)

    assert first == without_count.services
    assert second == with_count.services
    assert mock_crawl.await_count == 2
    assert directory.report is with_count


@pytest.mark.asyncio
async def test_directory_prep_stores_metadata():
    session = object()
    metadata = {"currentVersion": 11.3}
    directory = Directory(
        "https://example.com/arcgis/rest/services",
        session=session,
        token="secret-token",
    )

    with patch(
        "restgdf.directory.directory.get_metadata",
        new=AsyncMock(return_value=metadata),
    ) as mock_get_metadata:
        await directory.prep()

    assert isinstance(directory.metadata, LayerMetadata)
    assert directory.metadata.model_dump(by_alias=True, exclude_none=True) == metadata
    mock_get_metadata.assert_awaited_once_with(
        "https://example.com/arcgis/rest/services",
        session,
        "secret-token",
    )


@pytest.mark.asyncio
async def test_directory_from_url_calls_prep():
    with patch.object(Directory, "prep", new=AsyncMock()) as mock_prep:
        directory = await Directory.from_url(
            "https://example.com/arcgis/rest/services",
            session=object(),
        )

    assert isinstance(directory, Directory)
    mock_prep.assert_awaited_once()


@pytest.mark.asyncio
async def test_directory_crawl_reuses_cached_services():
    directory = Directory("https://example.com/arcgis/rest/services", session=object())
    cached_services = [CrawlServiceEntry(name="cached", url="https://example.com/c")]
    directory.services = cached_services

    with patch(
        "restgdf.directory.directory.safe_crawl",
        new=AsyncMock(),
    ) as mock_crawl:
        result = await directory.crawl()

    assert result is cached_services
    mock_crawl.assert_not_awaited()


def test_filter_directory_layers_requires_crawl():
    directory = Directory("https://example.com/arcgis/rest/services", session=object())

    with pytest.raises(ValueError, match="call \\.crawl"):
        directory.filter_directory_layers("Feature Layer")


def test_filter_directory_layers_selects_matching_types():
    directory = Directory("https://example.com/arcgis/rest/services", session=object())
    directory.services = [
        CrawlServiceEntry(
            name="svc-with-layers",
            url="https://example.com/svc-with-layers",
            metadata=LayerMetadata(
                layers=[
                    LayerMetadata(id=0, type="Feature Layer"),
                    LayerMetadata(id=1, type="Raster Layer"),
                ],
            ),
        ),
        CrawlServiceEntry(
            name="svc-empty-metadata",
            url="https://example.com/svc-empty-metadata",
            metadata=LayerMetadata(),
        ),
        CrawlServiceEntry(
            name="svc-no-metadata",
            url="https://example.com/svc-no-metadata",
            metadata=None,
        ),
    ]

    feature_layers = directory.feature_layers()
    rasters = directory.rasters()

    assert len(feature_layers) == 1
    assert feature_layers[0].id == 0
    assert feature_layers[0].type == "Feature Layer"

    assert len(rasters) == 1
    assert rasters[0].id == 1
    assert rasters[0].type == "Raster Layer"
