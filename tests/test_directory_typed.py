"""S-6: verify Directory exposes typed CrawlReport / CrawlServiceEntry models."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from restgdf._models.crawl import CrawlReport, CrawlServiceEntry
from restgdf._models.responses import LayerMetadata
from restgdf.directory.directory import Directory


@pytest.mark.asyncio
async def test_directory_crawl_returns_typed_entries_and_stores_report():
    directory = Directory(
        "https://example.com/arcgis/rest/services",
        session=object(),
    )
    report = CrawlReport(
        services=[
            CrawlServiceEntry(
                name="svc-a",
                url="https://example.com/svc-a",
                type="FeatureServer",
                metadata=LayerMetadata(
                    layers=[LayerMetadata(id=0, type="Feature Layer")],
                ),
            ),
        ],
        errors=[],
        metadata=LayerMetadata(current_version=11.3),
    )

    with patch(
        "restgdf.directory.directory.safe_crawl",
        new=AsyncMock(return_value=report),
    ):
        services = await directory.crawl()

    assert isinstance(directory.report, CrawlReport)
    assert directory.report is report
    assert len(services) == 1
    assert isinstance(services[0], CrawlServiceEntry)
    assert services[0].metadata is not None
    assert isinstance(services[0].metadata, LayerMetadata)
    assert services[0].metadata.layers is not None
    assert isinstance(services[0].metadata.layers[0], LayerMetadata)
