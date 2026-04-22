"""BL-05: ``ArcGISTokenSession.verify_ssl`` must plumb into token POST.

Before this change, ``ArcGISTokenSession.update_token`` issued the
``/generateToken`` POST without forwarding the session's ``verify_ssl``
flag. Users who instantiated ``ArcGISTokenSession(..., verify_ssl=False)``
to hit ArcGIS Enterprise deployments behind self-signed certs would
still see TLS verification failures because the token refresh call
ignored the flag.

These tests assert that the flag reaches ``aiohttp`` as ``ssl=<bool>``
on the POST keyword arguments.
"""

from __future__ import annotations

from typing import Any

import pytest

from restgdf.utils.token import AGOLUserPass, ArcGISTokenSession


class _RecordingPostContext:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    async def __aenter__(self) -> _RecordingPostContext:
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def json(self) -> dict[str, Any]:
        return self._payload

    def raise_for_status(self) -> None:
        return None


class _RecordingSession:
    def __init__(self) -> None:
        self.post_kwargs: dict[str, Any] = {}
        self.post_url: str | None = None

    def post(self, url: str, **kwargs: Any) -> _RecordingPostContext:
        self.post_url = url
        self.post_kwargs = kwargs
        return _RecordingPostContext(
            {"token": "tok", "expires": 32503680000000},
        )


@pytest.mark.asyncio
async def test_verify_ssl_false_forwards_to_token_post() -> None:
    session = _RecordingSession()
    creds = AGOLUserPass(username="u", password="p")
    token_session = ArcGISTokenSession(
        session=session,
        credentials=creds,
        verify_ssl=False,
    )

    await token_session.update_token()

    assert "ssl" in session.post_kwargs
    assert session.post_kwargs["ssl"] is False


@pytest.mark.asyncio
async def test_verify_ssl_true_forwards_to_token_post() -> None:
    session = _RecordingSession()
    creds = AGOLUserPass(username="u", password="p")
    token_session = ArcGISTokenSession(
        session=session,
        credentials=creds,
        verify_ssl=True,
    )

    await token_session.update_token()

    assert "ssl" in session.post_kwargs
    assert session.post_kwargs["ssl"] is True
