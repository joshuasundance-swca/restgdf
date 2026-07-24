"""W4-2 (PAGINATION-02): explicit offset/count pagination must default
``orderByFields`` to the layer's resolved OID field so multi-page traversal is
deterministic.

ArcGIS does not guarantee a stable row order across separate
``resultOffset``/``resultRecordCount`` requests unless ``orderByFields`` is
supplied, so without it a feature can be duplicated across adjacent pages or
dropped between page boundaries. These tests pin that both explicit-pagination
sub-branches (caller ``resultRecordCount`` and the planner) now inject the OID,
that a caller-supplied sort (any case) is never clobbered, and that an
unresolvable OID degrades gracefully (skip injection, never break the happy
path). The OID-chunked WHERE fallback branch is deliberately untouched.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from restgdf.utils.getgdf import get_query_data_batches


_OID_METADATA = {
    "maxRecordCount": 2,
    "advancedQueryCapabilities": {"supportsPagination": True},
    "fields": [
        {"name": "OBJECTID", "type": "esriFieldTypeOID"},
        {"name": "NAME", "type": "esriFieldTypeString"},
    ],
}

# Two OID-typed fields -> get_object_id_field raises FieldDoesNotExistError.
_AMBIGUOUS_OID_METADATA = {
    "maxRecordCount": 2,
    "advancedQueryCapabilities": {"supportsPagination": True},
    "fields": [
        {"name": "OBJECTID", "type": "esriFieldTypeOID"},
        {"name": "FID", "type": "esriFieldTypeOID"},
    ],
}


@pytest.mark.asyncio
async def test_planner_branch_injects_orderby_oid() -> None:
    """Planner sub-branch (no caller resultRecordCount): every batch carries
    orderByFields=<OID>."""
    with patch(
        "restgdf.utils.getgdf.get_feature_count",
        new=AsyncMock(return_value=5),
    ), patch(
        "restgdf.utils.getgdf.get_metadata",
        new=AsyncMock(return_value=_OID_METADATA),
    ):
        batches = await get_query_data_batches(
            "https://example.com/layer/0",
            object(),
            data={"where": "1=1"},
        )

    assert len(batches) == 3
    assert all(batch["orderByFields"] == "OBJECTID" for batch in batches)
    # Offsets/counts are still the planner's; injection is additive.
    assert [(b["resultOffset"], b["resultRecordCount"]) for b in batches] == [
        (0, 2),
        (2, 2),
        (4, 1),
    ]


@pytest.mark.asyncio
async def test_caller_result_record_count_branch_injects_orderby_oid() -> None:
    """Caller-resultRecordCount sub-branch: every batch carries the OID sort."""
    with patch(
        "restgdf.utils.getgdf.get_feature_count",
        new=AsyncMock(return_value=5),
    ), patch(
        "restgdf.utils.getgdf.get_metadata",
        new=AsyncMock(return_value=_OID_METADATA),
    ):
        batches = await get_query_data_batches(
            "https://example.com/layer/0",
            object(),
            data={"where": "1=1", "resultRecordCount": 2},
        )

    assert len(batches) == 3
    assert all(batch["orderByFields"] == "OBJECTID" for batch in batches)


@pytest.mark.asyncio
async def test_caller_orderby_is_not_clobbered_case_insensitive() -> None:
    """A caller-supplied sort (differently cased key) is preserved and the OID
    is NOT injected on top."""
    with patch(
        "restgdf.utils.getgdf.get_feature_count",
        new=AsyncMock(return_value=5),
    ), patch(
        "restgdf.utils.getgdf.get_metadata",
        new=AsyncMock(return_value=_OID_METADATA),
    ):
        batches = await get_query_data_batches(
            "https://example.com/layer/0",
            object(),
            data={"where": "1=1", "orderbyfields": "NAME DESC"},
        )

    assert len(batches) == 3
    for batch in batches:
        assert batch["orderbyfields"] == "NAME DESC"
        assert "orderByFields" not in batch


@pytest.mark.asyncio
async def test_unresolvable_oid_degrades_gracefully() -> None:
    """An ambiguous/unresolvable OID must NOT break the happy path: batches are
    produced without orderByFields and no exception escapes."""
    with patch(
        "restgdf.utils.getgdf.get_feature_count",
        new=AsyncMock(return_value=5),
    ), patch(
        "restgdf.utils.getgdf.get_metadata",
        new=AsyncMock(return_value=_AMBIGUOUS_OID_METADATA),
    ):
        batches = await get_query_data_batches(
            "https://example.com/layer/0",
            object(),
            data={"where": "1=1"},
        )

    assert len(batches) == 3
    assert all("orderByFields" not in batch for batch in batches)
    # Still a valid offset/count plan.
    assert [(b["resultOffset"], b["resultRecordCount"]) for b in batches] == [
        (0, 2),
        (2, 2),
        (4, 1),
    ]
