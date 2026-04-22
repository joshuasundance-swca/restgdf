"""Edge-case coverage for `_iter_pages_raw` validation and split irreducibility."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from restgdf.errors import RestgdfResponseError
from restgdf.utils import getgdf as getgdf_mod
from restgdf.utils.getgdf import _iter_pages_raw


@pytest.mark.asyncio
async def test_iter_pages_raw_rejects_invalid_order() -> None:
    agen = _iter_pages_raw("https://x/FeatureServer/0", object(), order="bogus")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="order must be"):
        await agen.__anext__()


@pytest.mark.asyncio
async def test_iter_pages_raw_rejects_invalid_on_truncation() -> None:
    agen = _iter_pages_raw(
        "https://x/FeatureServer/0",
        object(),
        on_truncation="nope",  # type: ignore[arg-type]
    )
    with pytest.raises(ValueError, match="on_truncation must be"):
        await agen.__anext__()


@pytest.mark.asyncio
async def test_iter_pages_raw_rejects_invalid_max_concurrent_pages() -> None:
    agen = _iter_pages_raw(
        "https://x/FeatureServer/0",
        object(),
        max_concurrent_pages=0,
    )
    with pytest.raises(ValueError, match="max_concurrent_pages"):
        await agen.__anext__()


@pytest.mark.asyncio
async def test_iter_pages_raw_split_single_oid_raises() -> None:
    """Bisection cannot subdivide a 1-OID predicate; must raise."""
    url = "https://x/FeatureServer/0"
    truncated = {"features": [], "exceededTransferLimit": True}

    async def fake_fetch(*_a, **_kw):
        return truncated

    with (
        patch.object(
            getgdf_mod,
            "get_query_data_batches",
            AsyncMock(return_value=[{"where": "1=1"}]),
        ),
        patch.object(getgdf_mod, "_fetch_page_dict", side_effect=fake_fetch),
        patch.object(
            getgdf_mod,
            "get_object_ids",
            AsyncMock(return_value=("OBJECTID", [42])),
        ),
    ):
        agen = _iter_pages_raw(url, object(), on_truncation="split")
        with pytest.raises(RestgdfResponseError, match="could not bisect"):
            async for _ in agen:
                pass


@pytest.mark.asyncio
async def test_iter_pages_raw_split_exceeds_max_depth() -> None:
    """When every recursion still reports exceeded, we hit max_split_depth."""
    url = "https://x/FeatureServer/0"
    truncated = {"features": [], "exceededTransferLimit": True}

    async def fake_fetch(*_a, **_kw):
        return truncated

    with (
        patch.object(
            getgdf_mod,
            "get_query_data_batches",
            AsyncMock(return_value=[{"where": "1=1"}]),
        ),
        patch.object(getgdf_mod, "_fetch_page_dict", side_effect=fake_fetch),
        patch.object(
            getgdf_mod,
            "get_object_ids",
            AsyncMock(return_value=("OBJECTID", [1, 2, 3, 4])),
        ),
    ):
        agen = _iter_pages_raw(
            url,
            object(),
            on_truncation="split",
            max_split_depth=1,
        )
        with pytest.raises(RestgdfResponseError, match="reached max depth"):
            async for _ in agen:
                pass
