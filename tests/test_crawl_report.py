"""S-4 TDD tests for :func:`restgdf.utils.crawl.safe_crawl`.

Unlike the legacy ``fetch_all_data`` which short-circuits the whole
crawl to ``{"error": exc}`` on the first failure, ``safe_crawl`` must
always return a :class:`CrawlReport` with a ``services`` list (possibly
empty) and an ``errors`` list (possibly empty). Every recoverable
failure is appended to ``errors`` as a typed :class:`CrawlError` entry
tagged by stage so callers can diagnose which request failed.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from restgdf._models import CrawlError, CrawlReport, CrawlServiceEntry
from restgdf._models._drift import reset_drift_cache
from restgdf.utils.crawl import safe_crawl


BASE_URL = "https://example.com/arcgis/rest/services"


@pytest.fixture(autouse=True)
def _reset_drift_cache() -> None:
    reset_drift_cache()


def _metadata_by_url(mapping):
    async def fake_get_metadata(url, session, token=None):
        value = mapping[url]
        if isinstance(value, Exception):
            raise value
        return value

    return fake_get_metadata


@pytest.mark.asyncio
async def test_safe_crawl_returns_crawl_report_model():
    async def fake_get_metadata(url, session, token=None):
        return {"services": [], "folders": []}

    with patch(
        "restgdf.utils.crawl.get_metadata",
        side_effect=fake_get_metadata,
    ):
        report = await safe_crawl(object(), BASE_URL)

    assert isinstance(report, CrawlReport)
    assert report.services == []
    assert report.errors == []


@pytest.mark.asyncio
async def test_safe_crawl_happy_path_collects_services_and_metadata():
    mapping = {
        BASE_URL: {
            "services": [{"name": "Root/Parcels", "type": "FeatureServer"}],
            "folders": ["Utilities"],
        },
        f"{BASE_URL}/Utilities": {
            "services": [{"name": "Utilities/Storm", "type": "MapServer"}],
        },
    }

    async def fake_service_metadata(session, service_url, token, **kwargs):
        return {"name": service_url}

    with (
        patch(
            "restgdf.utils.crawl.get_metadata",
            side_effect=_metadata_by_url(mapping),
        ),
        patch(
            "restgdf.utils.crawl.service_metadata",
            side_effect=fake_service_metadata,
        ),
    ):
        report = await safe_crawl(object(), BASE_URL, token="abc")

    assert report.errors == []
    assert report.metadata is not None
    assert report.metadata.url == BASE_URL
    assert [svc.name for svc in report.services] == [
        "Root/Parcels",
        "Utilities/Storm",
    ]
    assert all(svc.metadata is not None for svc in report.services)
    assert all(isinstance(svc, CrawlServiceEntry) for svc in report.services)


@pytest.mark.asyncio
async def test_safe_crawl_records_base_metadata_error_without_raising():
    boom = RuntimeError("base boom")

    with patch(
        "restgdf.utils.crawl.get_metadata",
        new=AsyncMock(side_effect=boom),
    ):
        report = await safe_crawl(object(), BASE_URL)

    assert report.services == []
    assert len(report.errors) == 1
    error = report.errors[0]
    assert isinstance(error, CrawlError)
    assert error.stage == "base_metadata"
    assert error.url == BASE_URL
    assert error.message == "base boom"
    assert error.exception is boom


@pytest.mark.asyncio
async def test_safe_crawl_records_folder_error_and_keeps_base_services():
    folder_boom = RuntimeError("folder boom")
    mapping = {
        BASE_URL: {
            "services": [{"name": "Root/Parcels", "type": "FeatureServer"}],
            "folders": ["Utilities"],
        },
        f"{BASE_URL}/Utilities": folder_boom,
    }

    async def fake_service_metadata(session, service_url, token, **kwargs):
        return {"name": service_url}

    with (
        patch(
            "restgdf.utils.crawl.get_metadata",
            side_effect=_metadata_by_url(mapping),
        ),
        patch(
            "restgdf.utils.crawl.service_metadata",
            side_effect=fake_service_metadata,
        ),
    ):
        report = await safe_crawl(object(), BASE_URL)

    assert [svc.name for svc in report.services] == ["Root/Parcels"]
    assert all(svc.metadata is not None for svc in report.services)
    assert len(report.errors) == 1
    error = report.errors[0]
    assert error.stage == "folder_metadata"
    assert error.url == f"{BASE_URL}/Utilities"
    assert error.exception is folder_boom


@pytest.mark.asyncio
async def test_safe_crawl_records_service_metadata_errors_per_service():
    mapping = {
        BASE_URL: {
            "services": [
                {"name": "Root/OK", "type": "FeatureServer"},
                {"name": "Root/Bad", "type": "FeatureServer"},
            ],
            "folders": [],
        },
    }
    bad_url = f"{BASE_URL}/Root/Bad/FeatureServer"
    ok_url = f"{BASE_URL}/Root/OK/FeatureServer"
    svc_boom = KeyError("missing")

    async def fake_service_metadata(session, service_url, token, **kwargs):
        if service_url == bad_url:
            raise svc_boom
        return {"name": service_url}

    with (
        patch(
            "restgdf.utils.crawl.get_metadata",
            side_effect=_metadata_by_url(mapping),
        ),
        patch(
            "restgdf.utils.crawl.service_metadata",
            side_effect=fake_service_metadata,
        ),
    ):
        report = await safe_crawl(object(), BASE_URL)

    by_name = {svc.name: svc for svc in report.services}
    assert by_name["Root/OK"].metadata is not None
    assert by_name["Root/Bad"].metadata is None
    assert len(report.errors) == 1
    error = report.errors[0]
    assert error.stage == "service_metadata"
    assert error.url == bad_url
    assert error.exception is svc_boom
    # ok service still fetched
    assert by_name["Root/OK"].metadata.name == ok_url


@pytest.mark.asyncio
async def test_safe_crawl_return_feature_count_propagated_to_service_metadata():
    mapping = {
        BASE_URL: {
            "services": [{"name": "Root/S", "type": "FeatureServer"}],
            "folders": [],
        },
    }
    seen = {}

    async def fake_service_metadata(session, service_url, token, **kwargs):
        seen["return_feature_count"] = kwargs.get("return_feature_count")
        return {}

    with (
        patch(
            "restgdf.utils.crawl.get_metadata",
            side_effect=_metadata_by_url(mapping),
        ),
        patch(
            "restgdf.utils.crawl.service_metadata",
            side_effect=fake_service_metadata,
        ),
    ):
        await safe_crawl(object(), BASE_URL, return_feature_count=True)

    assert seen["return_feature_count"] is True


def test_crawl_error_and_report_models_expose_expected_fields():
    err = CrawlError(stage="base_metadata", url="https://example.com", message="boom")
    report = CrawlReport(errors=[err])
    assert report.errors[0].stage == "base_metadata"
    assert report.services == []
