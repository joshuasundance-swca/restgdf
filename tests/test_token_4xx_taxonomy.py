"""W2-2 / W2-3 (AUTH-02, ERRTAX-01, ERRTAX-02): /generateToken error taxonomy.

W2-2 — a true-HTTP 4xx from ``/generateToken`` must surface through the
``RestgdfError`` umbrella (``InvalidCredentialsError`` for 400/401/403,
``RestgdfResponseError`` for other non-2xx) instead of escaping as a raw
``aiohttp.ClientResponseError``. The HTTP-200 JSON-error-envelope path is
unchanged (still ``RestgdfResponseError`` via the strict ``TokenResponse``
tier). A transient network error during refresh is still retried, never
reclassified as a credential failure.

W2-3 — restgdf's own deterministic errors co-inherit ``OSError`` via
``PermissionError`` (``AuthenticationError`` → ``PermissionError`` →
``OSError``). Without an ``except RestgdfError: raise`` guard placed *before*
``except _RETRYABLE_ERRORS`` they are swept into the ``OSError`` retry bucket
and mislabeled ``TokenRefreshFailedError``. The guard distinguishes error
classes by real exception instances (MRO), not by name.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest
from pydantic import SecretStr

from restgdf.errors import (
    AuthenticationError,
    InvalidCredentialsError,
    RestgdfError,
    RestgdfResponseError,
    TokenRefreshFailedError,
)
from restgdf.utils.token import ArcGISTokenSession


def _creds():
    from restgdf._models.credentials import AGOLUserPass

    return AGOLUserPass(username="u", password=SecretStr("p"))


def _session_raise_for_status(status: int, *, message: str = "err") -> MagicMock:
    """Mock aiohttp session whose ``/generateToken`` POST resp.raise_for_status raises."""
    resp = AsyncMock()
    err = aiohttp.ClientResponseError(
        request_info=MagicMock(),
        history=(),
        status=status,
        message=message,
    )
    resp.raise_for_status = MagicMock(side_effect=err)
    resp.json = AsyncMock(return_value={})
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=resp)
    ctx.__aexit__ = AsyncMock(return_value=False)
    session = MagicMock()
    session.post = MagicMock(return_value=ctx)
    return session


def _session_200_envelope(body: dict) -> MagicMock:
    """Mock session returning HTTP 200 with an in-body ArcGIS error envelope."""
    resp = AsyncMock()
    resp.raise_for_status = MagicMock(return_value=None)
    resp.json = AsyncMock(return_value=body)
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=resp)
    ctx.__aexit__ = AsyncMock(return_value=False)
    session = MagicMock()
    session.post = MagicMock(return_value=ctx)
    return session


class TestW2_2_FourXXMapsToTaxonomy:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("status", [400, 401, 403])
    async def test_4xx_credential_status_raises_invalid_credentials(self, status):
        ts = ArcGISTokenSession(
            session=_session_raise_for_status(status),
            credentials=_creds(),
        )
        with patch("restgdf.utils.token.asyncio.sleep", new_callable=AsyncMock) as sl:
            with pytest.raises(InvalidCredentialsError) as exc_info:
                await ts.update_token()
        # No raw aiohttp escape: it is under the RestgdfError umbrella and
        # catchable as AuthenticationError and PermissionError (MRO).
        assert isinstance(exc_info.value, AuthenticationError)
        assert isinstance(exc_info.value, RestgdfError)
        assert isinstance(exc_info.value, PermissionError)
        # Deterministic: not retried (no backoff sleeps).
        assert sl.await_count == 0
        # Original aiohttp error is chained, not swallowed.
        assert isinstance(exc_info.value.__cause__, aiohttp.ClientResponseError)

    @pytest.mark.asyncio
    async def test_non_credential_4xx_5xx_raises_response_error_not_invalid_creds(self):
        ts = ArcGISTokenSession(
            session=_session_raise_for_status(500),
            credentials=_creds(),
        )
        with patch("restgdf.utils.token.asyncio.sleep", new_callable=AsyncMock):
            with pytest.raises(RestgdfResponseError) as exc_info:
                await ts.update_token()
        assert not isinstance(exc_info.value, InvalidCredentialsError)
        assert isinstance(exc_info.value.__cause__, aiohttp.ClientResponseError)

    @pytest.mark.asyncio
    async def test_no_raw_aiohttp_error_escapes(self):
        """The failure mode this item exists to avoid: raw aiohttp on a 4xx."""
        ts = ArcGISTokenSession(
            session=_session_raise_for_status(401),
            credentials=_creds(),
        )
        with patch("restgdf.utils.token.asyncio.sleep", new_callable=AsyncMock):
            with pytest.raises(RestgdfError):
                await ts.update_token()
        # Prove it is NOT a bare aiohttp error escaping.
        ts2 = ArcGISTokenSession(
            session=_session_raise_for_status(401),
            credentials=_creds(),
        )
        with patch("restgdf.utils.token.asyncio.sleep", new_callable=AsyncMock):
            raised_raw = False
            try:
                await ts2.update_token()
            except aiohttp.ClientResponseError:
                raised_raw = True
            except RestgdfError:
                raised_raw = False
        assert raised_raw is False

    @pytest.mark.asyncio
    async def test_http_200_error_envelope_still_response_error(self):
        """The 200 + {"error": {...}} path is unchanged (strict TokenResponse tier)."""
        ts = ArcGISTokenSession(
            session=_session_200_envelope(
                {"error": {"code": 400, "message": "Invalid username or password."}},
            ),
            credentials=_creds(),
        )
        with pytest.raises(RestgdfResponseError):
            await ts.update_token()


class TestW2_2_TransientStillRetried:
    @pytest.mark.asyncio
    async def test_timeout_during_refresh_still_hits_retry_ladder(self):
        import asyncio

        async def always_timeout():
            raise asyncio.TimeoutError("slow")

        ctx = AsyncMock()
        ctx.__aenter__ = AsyncMock(side_effect=always_timeout)
        ctx.__aexit__ = AsyncMock(return_value=False)
        session = MagicMock()
        session.post = MagicMock(return_value=ctx)
        ts = ArcGISTokenSession(session=session, credentials=_creds())

        with patch(
            "restgdf.utils.token.asyncio.sleep",
            new_callable=AsyncMock,
        ) as sl:
            # A transient error is NEVER reclassified as a credential failure.
            with pytest.raises(TokenRefreshFailedError):
                await ts.update_token()
        assert sl.await_count == 2  # _MAX_TOKEN_RETRIES - 1 backoffs


class TestW2_3_DeterministicAuthNotSwallowed:
    @pytest.mark.asyncio
    async def test_none_credentials_raises_authentication_error_immediately(self):
        """None-cred AuthenticationError (an OSError via PermissionError) must not retry."""
        ts = ArcGISTokenSession(session=MagicMock(), credentials=None)
        with patch("restgdf.utils.token.asyncio.sleep", new_callable=AsyncMock) as sl:
            with pytest.raises(AuthenticationError) as exc_info:
                await ts.update_token()
        # NOT reclassified as TokenRefreshFailedError, and zero backoff sleeps.
        assert not isinstance(exc_info.value, TokenRefreshFailedError)
        assert sl.await_count == 0

    @pytest.mark.asyncio
    async def test_genuine_oserror_still_retries_then_refresh_failed(self):
        """A real socket-layer OSError is still retryable and ends as TokenRefreshFailedError."""

        async def always_oserror():
            raise OSError("connection reset")

        ctx = AsyncMock()
        ctx.__aenter__ = AsyncMock(side_effect=always_oserror)
        ctx.__aexit__ = AsyncMock(return_value=False)
        session = MagicMock()
        session.post = MagicMock(return_value=ctx)
        ts = ArcGISTokenSession(session=session, credentials=_creds())

        with patch(
            "restgdf.utils.token.asyncio.sleep",
            new_callable=AsyncMock,
        ) as sl:
            with pytest.raises(TokenRefreshFailedError):
                await ts.update_token()
        assert sl.await_count == 2
