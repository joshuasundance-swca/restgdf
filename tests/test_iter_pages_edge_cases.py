"""Edge-case coverage for `_iter_pages_raw` validation and split irreducibility."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from restgdf.errors import RestgdfResponseError
from restgdf.utils import getgdf as getgdf_mod
from restgdf.utils.getgdf import _fetch_page_dict, _iter_pages_raw


@pytest.mark.asyncio
async def test_iter_pages_raw_rejects_invalid_order() -> None:
    agen = _iter_pages_raw("https://x/FeatureServer/0", object(), order="bogus")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="order must be"):
        await agen.__anext__()


@pytest.mark.asyncio
async def test_iter_pages_raw_rejects_invalid_on_truncation() -> None:
    agen = _iter_pages_raw(
        "https://x/FeatureServer/0",
        object(),  # type: ignore[arg-type]
        on_truncation="nope",  # type: ignore[arg-type]
    )
    with pytest.raises(ValueError, match="on_truncation must be"):
        await agen.__anext__()


@pytest.mark.asyncio
async def test_iter_pages_raw_rejects_invalid_max_concurrent_pages() -> None:
    agen = _iter_pages_raw(
        "https://x/FeatureServer/0",
        object(),  # type: ignore[arg-type]
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
        agen = _iter_pages_raw(url, object(), on_truncation="split")  # type: ignore[arg-type]
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
            object(),  # type: ignore[arg-type]
            on_truncation="split",
            max_split_depth=1,
        )
        with pytest.raises(RestgdfResponseError, match="reached max depth"):
            async for _ in agen:
                pass


@pytest.mark.asyncio
async def test_iter_pages_raw_does_not_eagerly_schedule_all_batches_when_bounded() -> None:
    url = "https://x/FeatureServer/0"
    gate = asyncio.Event()
    created: list[asyncio.Task] = []
    orig_create_task = asyncio.create_task

    async def fake_fetch(*_a, **_kw):
        await gate.wait()
        return {"features": []}

    def spy_create_task(coro):
        task = orig_create_task(coro)
        created.append(task)
        return task

    with (
        patch.object(
            getgdf_mod,
            "get_query_data_batches",
            AsyncMock(return_value=[{"resultOffset": i} for i in range(25)]),
        ),
        patch.object(getgdf_mod, "_fetch_page_dict", side_effect=fake_fetch),
        patch("asyncio.create_task", new=spy_create_task),
    ):
        agen = _iter_pages_raw(url, object(), max_concurrent_pages=2)  # type: ignore[arg-type]
        consumer = orig_create_task(agen.__anext__())
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert len(created) == 2
        gate.set()
        await consumer
        await agen.aclose()


@pytest.mark.asyncio
async def test_iter_pages_raw_rejects_non_mapping_page_payload() -> None:
    url = "https://x/FeatureServer/0"

    response = AsyncMock()
    response.json = AsyncMock(return_value=[])

    with patch.object(getgdf_mod, "_arcgis_request", AsyncMock(return_value=response)):
        with pytest.raises(RestgdfResponseError, match="non-object JSON payload"):
            await _fetch_page_dict(url, object(), {"where": "1=1"})  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# W4-3 (PAGINATION-03): bound the split path's OID IN-lists and reuse the
# parent's materialized slice instead of re-calling get_object_ids per node.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resolve_page_split_reuses_parent_oid_slice_across_two_levels() -> None:
    """A 2-level split calls get_object_ids only once (at the root)."""
    url = "https://x/FeatureServer/0"
    truncated = {"features": [], "exceededTransferLimit": True}
    resolved_page = {"features": [{"attributes": {}}], "exceededTransferLimit": False}
    fetch_calls: list[dict] = []

    async def fake_fetch(_url, _session, query_data, **_kw):
        fetch_calls.append(dict(query_data))
        # Root fetch (#1) and the first-half sub-fetch (#2) both still
        # report truncation, forcing a second bisection level; every
        # fetch after that resolves cleanly.
        if len(fetch_calls) in (1, 2):
            return truncated
        return resolved_page

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
            AsyncMock(return_value=("OBJECTID", [1, 2, 3, 4, 5, 6, 7, 8])),
        ) as mock_get_object_ids,
    ):
        agen = _iter_pages_raw(url, object(), on_truncation="split")  # type: ignore[arg-type]
        results = [page async for page in agen]

    # root fetch + half([1,2,3,4]) fetch + its two sub-halves + half([5..8]).
    assert len(fetch_calls) == 5
    assert len(results) == 3
    # The child nodes reused the parent's held OID slice -- no re-fetch.
    mock_get_object_ids.assert_awaited_once()


@pytest.mark.asyncio
async def test_resolve_page_split_caps_oversized_inlist_and_recurses() -> None:
    """A half exceeding the IN-list cap is bisected further, not emitted whole."""
    url = "https://x/FeatureServer/0"
    big_oid_list = list(range(1, 3001))  # 3000 OIDs -> each 1500-element half > cap
    truncated = {"features": [], "exceededTransferLimit": True}
    resolved_page = {"features": [{"attributes": {}}], "exceededTransferLimit": False}
    fetch_calls: list[dict] = []

    async def fake_fetch(_url, _session, query_data, **_kw):
        fetch_calls.append(dict(query_data))
        if len(fetch_calls) == 1:
            return truncated
        return resolved_page

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
            AsyncMock(return_value=("OBJECTID", big_oid_list)),
        ),
    ):
        agen = _iter_pages_raw(url, object(), on_truncation="split")  # type: ignore[arg-type]
        results = [page async for page in agen]

    sub_fetches = fetch_calls[1:]
    # Each 1500-element half is bisected once more into two 750-element
    # chunks (1000-element cap) instead of one 1500-element IN-list.
    assert len(sub_fetches) == 4
    assert len(results) == 4
    for query_data in sub_fetches:
        element_count = query_data["where"].count(",") + 1
        assert element_count == 750
        assert element_count <= 1000
