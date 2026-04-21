from __future__ import annotations

import json
from pathlib import Path

from restgdf._models._drift import _parse_response
from restgdf._models.responses import ErrorResponse

FIXTURES_DIR = Path(__file__).with_name("error_format_fixtures")


def read_error_format_fixture(name: str) -> str:
    return (FIXTURES_DIR / name).read_text(encoding="utf-8")


def load_error_format_json(name: str) -> dict:
    return json.loads(read_error_format_fixture(name))


def test_html_response_fixture_is_small_and_stable() -> None:
    html = read_error_format_fixture("generate_token_default_html_response.html")

    assert "<!DOCTYPE html>" in html
    assert "<title>ArcGIS REST Services Directory: Generate Token</title>" in html
    assert '<textarea name="token">q1w2e3r4t5-demo-token</textarea>' in html


def test_text_plain_json_fixture_round_trips_as_json() -> None:
    payload = load_error_format_json("count_response_text_plain.txt")

    assert payload == {"count": 42}


def test_token_error_fixture_matches_arcgis_error_envelope() -> None:
    payload = load_error_format_json("generate_token_invalid_credentials_error.json")

    envelope = _parse_response(
        ErrorResponse,
        payload,
        context="generate-token-fixture",
    )

    assert envelope.error.code == 400
    assert envelope.error.message == "Unable to generate token."
    assert envelope.error.details == ["Invalid username or password."]
    assert payload["error"]["messageCode"] == "GWM_0003"
