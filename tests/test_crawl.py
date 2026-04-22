from __future__ import annotations

from unittest.mock import AsyncMock, call, patch

import pytest

from restgdf.utils.crawl import fetch_all_data


@pytest.mark.asyncio
async def test_fetch_all_data_collects_services_and_folder_services():
    base_url = "https://example.com/arcgis/rest/services"
    session = object()
    metadata_by_url = {
        base_url: {
            "services": [{"name": "Root/Parcels", "type": "FeatureServer"}],
            "folders": ["Utilities"],
        },
        f"{base_url}/Utilities": {
            "services": [{"name": "Utilities/Storm", "type": "MapServer"}],
        },
    }

    async def fake_get_metadata(url, session, token=None):
        return metadata_by_url[url]

    async def fake_service_metadata(
        session,
        service_url,
        token,
        return_feature_count=False,
        _sem=None,
    ):
        return {
            "service_url": service_url,
            "return_feature_count": return_feature_count,
            "token": token,
        }

    with patch(
        "restgdf.utils.crawl.get_metadata",
        side_effect=fake_get_metadata,
    ) as mock_get_metadata, patch(
        "restgdf.utils.crawl.service_metadata",
        side_effect=fake_service_metadata,
    ) as mock_service_metadata:
        result = await fetch_all_data(
            session,
            base_url,
            token="abc123",
            return_feature_count=True,
        )

    assert result["metadata"]["url"] == base_url
    assert result["services"] == [
        {
            "name": "Root/Parcels",
            "url": f"{base_url}/Root/Parcels/FeatureServer",
            "metadata": {
                "service_url": f"{base_url}/Root/Parcels/FeatureServer",
                "return_feature_count": True,
                "token": "abc123",
            },
        },
        {
            "name": "Utilities/Storm",
            "url": f"{base_url}/Utilities/Storm/MapServer",
            "metadata": {
                "service_url": f"{base_url}/Utilities/Storm/MapServer",
                "return_feature_count": True,
                "token": "abc123",
            },
        },
    ]
    assert mock_get_metadata.await_args_list == [
        call(base_url, session, "abc123"),
        call(f"{base_url}/Utilities", session, "abc123"),
    ]
    assert mock_service_metadata.await_count == 2


@pytest.mark.asyncio
async def test_fetch_all_data_returns_base_metadata_error():
    error = RuntimeError("boom")

    with patch(
        "restgdf.utils.crawl.get_metadata",
        new=AsyncMock(side_effect=error),
    ):
        result = await fetch_all_data(object(), "https://example.com/services")

    assert result == {"error": error}


@pytest.mark.asyncio
async def test_fetch_all_data_returns_folder_metadata_error():
    base_url = "https://example.com/arcgis/rest/services"
    error = RuntimeError("folder failure")

    async def fake_get_metadata(url, session, token=None):
        if url == base_url:
            return {"services": [], "folders": ["Utilities"]}
        raise error

    with patch(
        "restgdf.utils.crawl.get_metadata",
        side_effect=fake_get_metadata,
    ):
        result = await fetch_all_data(object(), base_url)

    assert result == {"error": error}


@pytest.mark.asyncio
async def test_fetch_all_data_wraps_service_metadata_failures():
    base_url = "https://example.com/arcgis/rest/services"

    with patch(
        "restgdf.utils.crawl.get_metadata",
        new=AsyncMock(
            side_effect=[
                {
                    "services": [{"name": "Root/Parcels", "type": "FeatureServer"}],
                    "folders": [],
                },
            ],
        ),
    ), patch(
        "restgdf.utils.crawl.service_metadata",
        new=AsyncMock(side_effect=KeyError("missing")),
    ):
        result = await fetch_all_data(object(), base_url)

    assert isinstance(result["services"][0]["metadata"]["error"], KeyError)
