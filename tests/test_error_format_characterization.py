from __future__ import annotations

import json
from json import JSONDecodeError
from pathlib import Path
from typing import Any

import pytest
from aiohttp import ContentTypeError

from restgdf._models._errors import RestgdfResponseError
from restgdf.utils._query import get_feature_count
from restgdf.utils.token import AGOLUserPass, ArcGISTokenSession

pytestmark = pytest.mark.characterization

FIXTURES_DIR = Path(__file__).with_name("error_format_fixtures")


def read_error_format_fixture(name: str) -> str:
    return (FIXTURES_DIR / name).read_text(encoding="utf-8")


def load_error_format_json(name: str) -> dict[str, Any]:
    return json.loads(read_error_format_fixture(name))


class FixtureResponse:
    def __init__(self, body: str, *, content_type: str):
        self.body = body
        self.content_type = content_type

    async def __aenter__(self) -> FixtureResponse:
        return self

    async def __aexit__(self, exc_type, exc_value, traceback) -> None:
        return None

    async def json(self, content_type: str | None = "application/json") -> Any:
        if content_type is not None and not self.content_type.startswith(
            "application/json",
        ):
            raise ContentTypeError(
                None,
                (),
                message=(
                    "Attempt to decode JSON with unexpected mimetype: "
                    f"{self.content_type}"
                ),
            )
        return json.loads(self.body)

    async def text(self) -> str:
        return self.body

    def raise_for_status(self) -> None:
        return None


class ScriptedQuerySession:
    def __init__(self, response: FixtureResponse):
        self.response = response
        self.post_calls: list[tuple[str, dict[str, Any]]] = []

    async def post(self, url: str, **kwargs) -> FixtureResponse:
        self.post_calls.append((url, dict(kwargs)))
        return self.response

    async def get(self, url, **kwargs):
        if "params" in kwargs and "data" not in kwargs:
            kwargs = {**kwargs, "data": kwargs["params"]}
        return await self.post(url, **kwargs)


class ScriptedTokenSession:
    def __init__(self, response: FixtureResponse):
        self.response = response
        self.post_calls: list[tuple[str, dict[str, Any]]] = []

    def post(self, url: str, **kwargs) -> FixtureResponse:
        self.post_calls.append((url, dict(kwargs)))
        return self.response


@pytest.mark.asyncio
async def test_get_feature_count_consumes_text_plain_json_fixture() -> None:
    session = ScriptedQuerySession(
        FixtureResponse(
            read_error_format_fixture("count_response_text_plain.txt"),
            content_type="text/plain",
        ),
    )

    count = await get_feature_count("https://example.com/service/0", session)  # type: ignore[arg-type]

    assert count == 42
    assert session.post_calls[0][0] == "https://example.com/service/0/query"


@pytest.mark.asyncio
async def test_get_feature_count_html_body_bubbles_json_decode_error() -> None:
    session = ScriptedQuerySession(
        FixtureResponse(
            read_error_format_fixture("generate_token_default_html_response.html"),
            content_type="text/html",
        ),
    )

    with pytest.raises(JSONDecodeError):
        await get_feature_count("https://example.com/service/0", session)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_update_token_invalid_credentials_surfaces_raw_error_envelope() -> None:
    payload = load_error_format_json("generate_token_invalid_credentials_error.json")
    token_session = ArcGISTokenSession(
        session=ScriptedTokenSession(
            FixtureResponse(
                json.dumps(payload),
                content_type="application/json",
            ),
        ),
        credentials=AGOLUserPass(username="user", password="password"),
    )

    with pytest.raises(RestgdfResponseError) as exc_info:
        await token_session.update_token()

    assert exc_info.value.model_name == "TokenResponse"
    assert exc_info.value.context == token_session.token_url
    assert exc_info.value.raw == payload
    assert token_session.token is None


@pytest.mark.asyncio
async def test_update_token_default_html_response_raises_content_type_error() -> None:
    token_session = ArcGISTokenSession(
        session=ScriptedTokenSession(
            FixtureResponse(
                read_error_format_fixture("generate_token_default_html_response.html"),
                content_type="text/html",
            ),
        ),
        credentials=AGOLUserPass(username="user", password="password"),
    )

    with pytest.raises(ContentTypeError):
        await token_session.update_token()

    assert token_session.token is None
