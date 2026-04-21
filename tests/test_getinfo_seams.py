"""Patch-seam invariants for ``restgdf.utils.getinfo``.

These tests pin a compatibility promise: callers (and the test suite) patch
helper functions on the ``restgdf.utils.getinfo`` module expecting the
orchestrators (``service_metadata``, ``get_offset_range``) to resolve sibling
calls through that module's namespace. Phase 2 splits ``getinfo.py`` into
private submodules; the orchestrators MUST keep looking up their callees via
``getinfo``'s globals so these patches continue to intercept.

If any of these tests fail, the split has broken a public patch seam even if
imports still succeed.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from restgdf.utils.getinfo import get_offset_range, service_metadata


@pytest.mark.compat
@pytest.mark.asyncio
async def test_service_metadata_uses_getinfo_get_metadata_seam():
    """Patching ``restgdf.utils.getinfo.get_metadata`` must intercept calls
    made from ``service_metadata``."""

    async def fake_get_metadata(url, session, token=None):
        if url.endswith("/0"):
            return {"type": "Feature Layer"}
        return {"layers": [{"id": 0}]}

    with patch(
        "restgdf.utils.getinfo.get_metadata",
        side_effect=fake_get_metadata,
    ) as mock_gm:
        result = await service_metadata(object(), "https://example.com/svc")

    assert mock_gm.await_count >= 1
    assert result.layers[0].url == "https://example.com/svc/0"


@pytest.mark.compat
@pytest.mark.asyncio
async def test_service_metadata_uses_getinfo_get_feature_count_seam():
    """Patching ``restgdf.utils.getinfo.get_feature_count`` must intercept
    calls made from ``service_metadata``."""

    async def fake_get_metadata(url, session, token=None):
        if url.endswith("/0"):
            return {"type": "Feature Layer"}
        return {"layers": [{"id": 0}]}

    with (
        patch(
            "restgdf.utils.getinfo.get_metadata",
            side_effect=fake_get_metadata,
        ),
        patch(
            "restgdf.utils.getinfo.get_feature_count",
            new=AsyncMock(return_value=7),
        ) as mock_gfc,
    ):
        result = await service_metadata(
            object(),
            "https://example.com/svc",
            return_feature_count=True,
        )

    mock_gfc.assert_awaited()
    assert result.layers[0].feature_count == 7


@pytest.mark.compat
@pytest.mark.asyncio
async def test_get_offset_range_uses_getinfo_get_feature_count_seam():
    """Patching ``restgdf.utils.getinfo.get_feature_count`` must intercept
    calls made from ``get_offset_range``."""

    with (
        patch(
            "restgdf.utils.getinfo.get_feature_count",
            new=AsyncMock(return_value=250),
        ) as mock_gfc,
        patch(
            "restgdf.utils.getinfo.get_metadata",
            new=AsyncMock(return_value={"maxRecordCount": 100}),
        ),
    ):
        result = await get_offset_range("https://example.com/svc/0", object())

    mock_gfc.assert_awaited_once()
    assert list(result) == [0, 100, 200]


@pytest.mark.compat
@pytest.mark.asyncio
async def test_get_offset_range_uses_getinfo_get_metadata_seam():
    """Patching ``restgdf.utils.getinfo.get_metadata`` must intercept calls
    made from ``get_offset_range``."""

    with (
        patch(
            "restgdf.utils.getinfo.get_feature_count",
            new=AsyncMock(return_value=10),
        ),
        patch(
            "restgdf.utils.getinfo.get_metadata",
            new=AsyncMock(return_value={"maxRecordCount": 5}),
        ) as mock_gm,
    ):
        result = await get_offset_range("https://example.com/svc/0", object())

    mock_gm.assert_awaited_once()
    assert list(result) == [0, 5]


@pytest.mark.compat
@pytest.mark.asyncio
async def test_get_offset_range_uses_getinfo_get_max_record_count_seam():
    """Patching ``restgdf.utils.getinfo.get_max_record_count`` must intercept
    calls made from ``get_offset_range``."""

    with (
        patch(
            "restgdf.utils.getinfo.get_feature_count",
            new=AsyncMock(return_value=30),
        ),
        patch(
            "restgdf.utils.getinfo.get_metadata",
            new=AsyncMock(return_value={}),
        ),
        patch(
            "restgdf.utils.getinfo.get_max_record_count",
            return_value=10,
        ) as mock_gmrc,
    ):
        result = await get_offset_range("https://example.com/svc/0", object())

    mock_gmrc.assert_called_once()
    assert list(result) == [0, 10, 20]
