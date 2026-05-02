from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from restgdf._models._drift import _parse_response
from restgdf._models.responses import FeaturesResponse
from restgdf.utils.getgdf import get_query_data_batches
from restgdf.utils.getinfo import supports_pagination
from tests.pagination_fixtures import load_pagination_fixture


def test_supports_pagination_defaults_true_for_vendored_missing_flag_fixture():
    metadata = load_pagination_fixture("metadata_missing_supports_pagination.json")

    assert supports_pagination(metadata) is True


@pytest.mark.asyncio
async def test_missing_pagination_flag_does_not_drive_offset_batching() -> None:
    metadata = load_pagination_fixture("metadata_missing_supports_pagination.json")

    with patch(
        "restgdf.utils.getgdf.get_feature_count",
        new=AsyncMock(return_value=2001),
    ), patch(
        "restgdf.utils.getgdf.get_metadata",
        new=AsyncMock(return_value=metadata),
    ), patch(
        "restgdf.utils.getgdf.get_object_ids",
        new=AsyncMock(return_value=("OBJECTID", list(range(1, 2002)))),
    ):
        batches = await get_query_data_batches(
            "https://example.com/layer/0",
            object(),  # type: ignore[arg-type]
            data={"where": "1=1"},
        )

    assert len(batches) == 3
    assert all("resultOffset" not in batch for batch in batches)


def test_features_response_preserves_truncation_flag_for_empty_fixture() -> None:
    payload = load_pagination_fixture(
        "query_exceeded_transfer_limit_empty_features.json",
    )

    resp = _parse_response(FeaturesResponse, payload, context="fixture")

    assert resp.features == []
    assert resp.exceeded_transfer_limit is True


def test_features_response_preserves_truncation_flag_for_short_page_fixture() -> None:
    payload = load_pagination_fixture(
        "query_exceeded_transfer_limit_short_page.json",
    )

    resp = _parse_response(FeaturesResponse, payload, context="fixture")

    assert len(resp.features) == 2
    assert resp.exceeded_transfer_limit is True
