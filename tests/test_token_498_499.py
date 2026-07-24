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


class TestSingleFlightRefreshUnderConcurrent498:
    """W2-4 (ASYNC-01): N concurrent 498s → exactly ONE /generateToken.

    Without the snapshot double-check inside the 498 branch, every task that
    won the refresh lock re-mints, so N concurrent 498s produce N mints. The
    fix captures ``tok_before`` before the request and only refreshes when
    ``self.token == tok_before`` under the lock (mirroring the proactive
    ``update_token_if_needed`` double-check).
    """

    @pytest.mark.asyncio
    async def test_n_concurrent_498s_trigger_exactly_one_mint(self):
        from restgdf._models.credentials import AGOLUserPass
        from restgdf.utils.token import ArcGISTokenSession

        from tests.test_token import RecordingTokenSession

        k = 12
        session = RecordingTokenSession()
        ts = ArcGISTokenSession(
            session=session,
            credentials=AGOLUserPass(username="user", password="password"),
            token="tok-0",
            expires=9999999999999,
        )

        resp_498 = _make_response(status=498, json_body={"error": {"code": 498}})
        resp_200 = _make_response(status=200, json_body={"features": []})

        # Barrier: hold every task's FIRST response until all k have issued
        # their first request, so all k capture the same tok_before ("tok-0")
        # and receive 498 *before* any refresh runs. This removes timing luck
        # -- the dedupe must come from the snapshot check, not from tasks
        # arriving after the first refresh already rotated the token.
        arrived = 0
        gate = asyncio.Event()
        first_seen: set[int] = set()

        async def flaky_get(url, **kwargs):
            task_id = id(asyncio.current_task())
            if task_id not in first_seen:
                first_seen.add(task_id)
                nonlocal arrived
                arrived += 1
                if arrived == k:
                    gate.set()
                await gate.wait()
                return resp_498
            return resp_200

        session.get = flaky_get

        mint_count = 0

        async def rotating_update_token():
            nonlocal mint_count
            mint_count += 1
            # Rotate the token so later lock-winners see self.token != tok_before
            # and correctly SKIP the redundant mint.
            ts.token = f"tok-{mint_count}"

        ts.update_token = rotating_update_token

        results = await asyncio.gather(
            *(
                ts.get("https://example.com/query", params={"where": "1=1"})
                for _ in range(k)
            ),
        )

        assert all(r.status == 200 for r in results)
        assert mint_count == 1

    @pytest.mark.asyncio
    async def test_concurrent_498s_all_retry_with_refreshed_token(self):
        """Every concurrent task still completes its retry after the single mint."""
        from restgdf._models.credentials import AGOLUserPass
        from restgdf.utils.token import ArcGISTokenSession

        from tests.test_token import RecordingTokenSession

        k = 8
        session = RecordingTokenSession()
        ts = ArcGISTokenSession(
            session=session,
            credentials=AGOLUserPass(username="user", password="password"),
            token="tok-0",
            expires=9999999999999,
        )

        resp_498 = _make_response(status=498, json_body={"error": {"code": 498}})
        resp_200 = _make_response(status=200, json_body={"features": []})

        arrived = 0
        gate = asyncio.Event()
        first_seen: set[int] = set()

        async def flaky_get(url, **kwargs):
            task_id = id(asyncio.current_task())
            if task_id not in first_seen:
                first_seen.add(task_id)
                nonlocal arrived
                arrived += 1
                if arrived == k:
                    gate.set()
                await gate.wait()
                return resp_498
            return resp_200

        session.get = flaky_get
        ts.update_token = AsyncMock(side_effect=lambda: setattr(ts, "token", "fresh"))

        results = await asyncio.gather(
            *(ts.get("https://example.com/query") for _ in range(k)),
        )

        assert len(results) == k
        assert all(r.status == 200 for r in results)
        assert ts.update_token.await_count == 1
