"""Tests for BL-12: bounded /generateToken retry with backoff."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import SecretStr

from restgdf.errors import TokenRefreshFailedError
from restgdf.utils.token import (
    ArcGISTokenSession,
    _BASE_BACKOFF_S,
    _MAX_TOKEN_RETRIES,
)


def _make_session(*, post_side_effect=None, post_return=None):
    """Build a minimal ArcGISTokenSession with a mock aiohttp session."""
    from restgdf._models.credentials import AGOLUserPass

    creds = AGOLUserPass(username="u", password=SecretStr("p"))
    mock_session = MagicMock()

    if post_side_effect is not None:
        ctx = AsyncMock()
        ctx.__aenter__ = AsyncMock(side_effect=post_side_effect)
        ctx.__aexit__ = AsyncMock(return_value=False)
        mock_session.post = MagicMock(return_value=ctx)
    elif post_return is not None:
        resp_mock = AsyncMock()
        resp_mock.raise_for_status = MagicMock()
        resp_mock.json = AsyncMock(return_value=post_return)
        ctx = AsyncMock()
        ctx.__aenter__ = AsyncMock(return_value=resp_mock)
        ctx.__aexit__ = AsyncMock(return_value=False)
        mock_session.post = MagicMock(return_value=ctx)

    return ArcGISTokenSession(session=mock_session, credentials=creds)


class TestBoundedRetryConstants:
    def test_max_retries_is_3(self):
        assert _MAX_TOKEN_RETRIES == 3

    def test_base_backoff_is_half_second(self):
        assert _BASE_BACKOFF_S == 0.5


class TestBoundedRetrySuccess:
    @pytest.mark.asyncio
    async def test_succeeds_on_first_try(self):
        ts = _make_session(
            post_return={"token": "tok1", "expires": 9999999999999},
        )
        await ts.update_token()
        assert ts.token == "tok1"

    @pytest.mark.asyncio
    async def test_succeeds_on_second_try(self):
        """First POST fails, second succeeds — total 2 attempts."""
        call_count = 0

        async def side_effect():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ConnectionError("transient")
            resp = AsyncMock()
            resp.raise_for_status = MagicMock()
            resp.json = AsyncMock(
                return_value={"token": "tok2", "expires": 9999999999999},
            )
            return resp

        ts = _make_session(post_side_effect=side_effect)
        with patch("restgdf.utils.token.asyncio.sleep", new_callable=AsyncMock):
            await ts.update_token()
        assert ts.token == "tok2"


class TestBoundedRetryExhaustion:
    @pytest.mark.asyncio
    async def test_raises_token_refresh_failed_after_max(self):
        """All retries exhausted → TokenRefreshFailedError."""

        async def always_fail():
            raise ConnectionError("permanent")

        ts = _make_session(post_side_effect=always_fail)
        with patch("restgdf.utils.token.asyncio.sleep", new_callable=AsyncMock):
            with pytest.raises(TokenRefreshFailedError) as exc_info:
                await ts.update_token()

        assert exc_info.value.attempt == _MAX_TOKEN_RETRIES
        assert exc_info.value.context == ts.token_url

    @pytest.mark.asyncio
    async def test_backoff_delays_are_exponential(self):
        """Verify asyncio.sleep is called with exponential delays."""

        async def always_fail():
            raise ConnectionError("fail")

        ts = _make_session(post_side_effect=always_fail)
        with patch(
            "restgdf.utils.token.asyncio.sleep",
            new_callable=AsyncMock,
        ) as mock_sleep:
            with pytest.raises(TokenRefreshFailedError):
                await ts.update_token()

        # With 3 retries, sleep is called between attempts 1→2 and 2→3
        assert mock_sleep.call_count == _MAX_TOKEN_RETRIES - 1
        delays = [call.args[0] for call in mock_sleep.call_args_list]
        expected = [_BASE_BACKOFF_S * (2**i) for i in range(_MAX_TOKEN_RETRIES - 1)]
        assert delays == expected

    @pytest.mark.asyncio
    async def test_last_exception_is_chained(self):
        """The final exception's __cause__ should be the last real error."""

        async def always_fail():
            raise ConnectionError("the-cause")

        ts = _make_session(post_side_effect=always_fail)
        with patch("restgdf.utils.token.asyncio.sleep", new_callable=AsyncMock):
            with pytest.raises(TokenRefreshFailedError) as exc_info:
                await ts.update_token()

        assert exc_info.value.__cause__ is not None
        assert "the-cause" in str(exc_info.value.__cause__)
