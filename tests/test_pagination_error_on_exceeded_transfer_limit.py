"""BL-08 red tests: exceededTransferLimit=true emits PaginationError with context.

These tests pin the emitted-context shape (``batch_index`` / ``page_size``)
and the user-visible break from ``RuntimeError``. The type-flip itself is
pinned via retargeted ``pytest.raises`` calls in ``tests/test_getgdf.py``.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from restgdf.errors import PaginationError
from restgdf.utils.getgdf import _feature_batch_generator, _get_sub_features
from tests.pagination_fixtures import load_pagination_fixture


class JsonSession:
    """Minimal ArcGIS session double: POST returns the next queued JSON payload."""

    def __init__(self, payloads: list[dict]):
        self.payloads = list(payloads)
        self.post_calls: list[tuple[str, dict]] = []

    async def post(self, url: str, **kwargs):
        self.post_calls.append((url, kwargs))

        class Response:
            def __init__(self, payload: dict):
                self._payload = payload

            async def json(self, content_type=None):
                return self._payload

        return Response(self.payloads.pop(0))


@pytest.mark.asyncio
async def test_pagination_error_carries_page_size():
    """Direct ``_get_sub_features`` call: page_size derives from query_data; batch_index stays None."""
    session = JsonSession(
        [load_pagination_fixture("query_exceeded_transfer_limit_empty_features.json")],
    )

    with pytest.raises(PaginationError, match="exceededTransferLimit") as exc_info:
        await _get_sub_features(
            "https://example.com/layer/0",
            session,
            query_data={"resultOffset": 10, "resultRecordCount": 10},
        )

    assert exc_info.value.page_size == 10
    assert exc_info.value.batch_index is None


@pytest.mark.asyncio
async def test_feature_batch_generator_threads_batch_index():
    """Drive ``_feature_batch_generator`` through a 25-row / page-size-10 layer.

    The 3rd batch (offset=20, resultRecordCount=5) returns
    ``exceededTransferLimit=true``. batch_index must be 2 (zero-based, the
    index into ``query_data_batches``), not ``20 // 5 == 4``.
    """
    batches = [
        {"resultOffset": 0, "resultRecordCount": 10},
        {"resultOffset": 10, "resultRecordCount": 10},
        {"resultOffset": 20, "resultRecordCount": 5},
    ]
    session = JsonSession(
        [
            {"features": [{"attributes": {"OBJECTID": i}} for i in range(1, 11)]},
            {"features": [{"attributes": {"OBJECTID": i}} for i in range(11, 21)]},
            load_pagination_fixture(
                "query_exceeded_transfer_limit_empty_features.json",
            ),
        ],
    )

    with patch(
        "restgdf.utils.getgdf.get_query_data_batches",
        new=AsyncMock(return_value=batches),
    ), pytest.raises(PaginationError, match="exceededTransferLimit") as exc_info:
        async for _ in _feature_batch_generator(
            "https://example.com/layer/0",
            session,
        ):
            pass

    assert exc_info.value.batch_index == 2
    assert exc_info.value.page_size == 5


@pytest.mark.asyncio
async def test_pagination_error_is_not_runtimeerror():
    """User-visible break: ``except RuntimeError`` no longer catches this."""
    session = JsonSession(
        [load_pagination_fixture("query_exceeded_transfer_limit_empty_features.json")],
    )

    with pytest.raises(PaginationError) as exc_info:
        await _get_sub_features(
            "https://example.com/layer/0",
            session,
            query_data={"resultOffset": 10, "resultRecordCount": 10},
        )

    assert not isinstance(exc_info.value, RuntimeError)
