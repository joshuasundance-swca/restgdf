"""BL-11 red tests: 498 single-flight refresh + 499 AuthNotAttachedError.

RED-first — these fail until feat(BL-11) adds _call_with_auth_retry.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import aiohttp
import pytest

from restgdf.errors import AuthNotAttachedError, TokenExpiredError


def _make_response(status: int = 200, json_body: dict | None = None) -> MagicMock:
    """Create a mock aiohttp.ClientResponse with the given status/body."""
    resp = MagicMock(spec=aiohttp.ClientResponse)
    resp.status = status
    body = json_body or {}
    resp.json = AsyncMock(return_value=body)
    resp.text = AsyncMock(return_value=str(body))
    resp.read = AsyncMock(return_value=b"")
    return resp


class TestSingleFlightRefreshOn498:
    """498 → single-flight refresh + exactly one retry."""

    @pytest.mark.asyncio
    async def test_498_triggers_refresh_and_retry(self):
        """A 498 response triggers token refresh and one retry."""
        from restgdf._models.credentials import AGOLUserPass
        from restgdf.utils.token import ArcGISTokenSession

        from tests.test_token import RecordingTokenSession

        session = RecordingTokenSession()
        ts = ArcGISTokenSession(
            session=session,
            credentials=AGOLUserPass(username="user", password="password"),
            token="old-token",
            expires=9999999999999,
        )

        # Mock the first response as 498, second as 200
        resp_498 = _make_response(status=498, json_body={"error": {"code": 498}})
        resp_200 = _make_response(status=200, json_body={"features": []})

        call_count = 0
        original_get = session.get

        async def mock_get(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return resp_498
            return resp_200

        session.get = mock_get
        ts.update_token = AsyncMock()

        result = await ts.get("https://example.com/query", params={"where": "1=1"})
        assert result.status == 200
        ts.update_token.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_498_retries_exactly_once(self):
        """A 498 response that persists after refresh raises TokenExpiredError."""
        from restgdf._models.credentials import AGOLUserPass
        from restgdf.utils.token import ArcGISTokenSession

        from tests.test_token import RecordingTokenSession

        session = RecordingTokenSession()
        ts = ArcGISTokenSession(
            session=session,
            credentials=AGOLUserPass(username="user", password="password"),
            token="old-token",
            expires=9999999999999,
        )

        resp_498 = _make_response(status=498, json_body={"error": {"code": 498}})
        session.get = AsyncMock(return_value=resp_498)
        ts.update_token = AsyncMock()

        with pytest.raises(TokenExpiredError):
            await ts.get("https://example.com/query")


class TestAuthNotAttachedOn499:
    """499 → AuthNotAttachedError, NO retry."""

    @pytest.mark.asyncio
    async def test_499_raises_auth_not_attached(self):
        from restgdf._models.credentials import AGOLUserPass
        from restgdf.utils.token import ArcGISTokenSession

        from tests.test_token import RecordingTokenSession

        session = RecordingTokenSession()
        ts = ArcGISTokenSession(
            session=session,
            credentials=AGOLUserPass(username="user", password="password"),
            token="my-token",
            expires=9999999999999,
        )

        resp_499 = _make_response(status=499, json_body={"error": {"code": 499}})
        session.get = AsyncMock(return_value=resp_499)
        ts.update_token = AsyncMock()

        with pytest.raises(AuthNotAttachedError):
            await ts.get("https://example.com/query")
        ts.update_token.assert_not_awaited()
