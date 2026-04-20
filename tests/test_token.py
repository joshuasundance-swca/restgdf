from __future__ import annotations

import datetime
from unittest.mock import AsyncMock, Mock, patch

import pytest

from restgdf.utils.token import AGOLUserPass, ArcGISTokenSession, get_token


class MockRequestContext:
    def __init__(self, payload: dict):
        self.payload = payload

    def __await__(self):
        async def _response():
            return self

        return _response().__await__()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        return None

    async def json(self):
        return self.payload

    def raise_for_status(self):
        return None


class RecordingTokenSession:
    def __init__(self):
        self.get_calls: list[tuple[str, dict]] = []
        self.post_calls: list[tuple[str, dict]] = []

    def get(self, url: str, **kwargs):
        self.get_calls.append((url, kwargs))
        return MockRequestContext({"ok": True})

    def post(self, url: str, **kwargs):
        self.post_calls.append((url, kwargs))
        if url.endswith("generateToken"):
            return MockRequestContext(
                {
                    "token": "generated-token",
                    "expires": 32503680000000,
                },
            )
        return MockRequestContext({"ok": True})


def test_get_token_uses_requests_post():
    response = Mock()
    response.json.return_value = {"token": "sync-token"}

    with patch("restgdf.utils.token.requests.post", return_value=response) as mock_post:
        result = get_token("user", "password")

    assert result == {"token": "sync-token"}
    mock_post.assert_called_once_with(
        "https://www.arcgis.com/sharing/rest/generateToken",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "f": "json",
            "client": "requestip",
            "username": "user",
            "password": "password",
        },
        timeout=30,
    )


def test_token_request_payload_requires_credentials():
    token_session = ArcGISTokenSession(session=RecordingTokenSession())

    with pytest.raises(ValueError):
        _ = token_session.token_request_payload


def test_update_headers_and_dict_respect_existing_values():
    token_session = ArcGISTokenSession(
        session=RecordingTokenSession(),
        token="abc123",
        expires=32503680000000,
    )

    assert token_session.auth_headers == {"Authorization": "Bearer abc123"}
    assert token_session.update_headers({"X-Test": "yes"}) == {
        "X-Test": "yes",
        "Authorization": "Bearer abc123",
    }
    assert token_session.update_dict({"where": "1=1"}) == {
        "where": "1=1",
        "token": "abc123",
    }
    assert token_session.update_dict({"token": "explicit"}) == {"token": "explicit"}


def test_token_needs_update_branching():
    token_session = ArcGISTokenSession(session=RecordingTokenSession())
    assert token_session.token_needs_update() is False

    token_session = ArcGISTokenSession(
        session=RecordingTokenSession(),
        credentials=AGOLUserPass("user", "password"),
    )
    assert token_session.token_needs_update() is True

    future = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(
        minutes=5,
    )
    token_session.token = "abc123"
    token_session.expires = future.timestamp()
    assert token_session.token_needs_update() is False

    soon = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(
        seconds=30,
    )
    token_session.expires = soon.timestamp() * 1000
    assert token_session.token_needs_update() is True


@pytest.mark.asyncio
async def test_update_token_if_needed_only_refreshes_when_required():
    token_session = ArcGISTokenSession(
        session=RecordingTokenSession(),
        credentials=AGOLUserPass("user", "password"),
        token="abc123",
        expires=32503680000000,
    )

    with patch.object(
        token_session,
        "update_token",
        new=AsyncMock(),
    ) as mock_update_token, patch.object(
        token_session,
        "token_needs_update",
        return_value=False,
    ):
        await token_session.update_token_if_needed()

    mock_update_token.assert_not_awaited()


@pytest.mark.asyncio
async def test_arcgistokensession_refreshes_and_injects_auth():
    session = RecordingTokenSession()
    token_session = ArcGISTokenSession(
        session=session,
        credentials=AGOLUserPass(username="user", password="password"),
    )

    post_response = await token_session.post(
        "https://example.com/query",
        data={"where": "1=1"},
    )
    get_response = await token_session.get(
        "https://example.com/items",
        params={"f": "json"},
    )

    assert await post_response.json() == {"ok": True}
    assert await get_response.json() == {"ok": True}
    assert token_session.token == "generated-token"
    assert session.post_calls[0][0].endswith("generateToken")
    assert session.post_calls[1][1]["data"]["token"] == "generated-token"
    assert session.get_calls[0][1]["params"]["token"] == "generated-token"


@pytest.mark.asyncio
async def test_arcgistokensession_context_manager_updates_token():
    token_session = ArcGISTokenSession(
        session=RecordingTokenSession(),
        credentials=AGOLUserPass("user", "password"),
    )

    async with token_session as active_session:
        assert active_session is token_session
        assert active_session.token == "generated-token"

    assert await token_session.__aexit__(None, None, None) is None


@pytest.mark.asyncio
async def test_arcgistokensession_respects_explicit_token_in_request():
    session = RecordingTokenSession()
    token_session = ArcGISTokenSession(
        session=session,
        credentials=AGOLUserPass("user", "password"),
    )

    await token_session.post(
        "https://example.com/query",
        data={"token": "explicit", "where": "1=1"},
        headers={"X-Test": "yes"},
    )
    await token_session.get(
        "https://example.com/items",
        params={"token": "explicit"},
        headers={"X-Test": "yes"},
    )

    assert session.post_calls[-1][1]["headers"] == {"X-Test": "yes"}
    assert session.post_calls[-1][1]["data"]["token"] == "explicit"
    assert session.get_calls[-1][1]["headers"] == {"X-Test": "yes"}
    assert session.get_calls[-1][1]["params"]["token"] == "explicit"
