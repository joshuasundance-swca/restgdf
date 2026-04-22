"""Red tests for BL-14: get_token DeprecationWarning + SecretStr acceptance."""

from __future__ import annotations

import warnings
from unittest.mock import patch

import pytest
from pydantic import SecretStr

from restgdf.utils.token import get_token


class _FakeResponse:
    def json(self):
        return {"token": "tok", "expires": 9999999999999}


@pytest.fixture()
def _mock_post():
    with patch("restgdf.utils.token.requests.post", return_value=_FakeResponse()) as m:
        yield m


# ── R-14-a: DeprecationWarning on every call ──────────────────────
class TestGetTokenDeprecation:
    def test_emits_deprecation_warning(self, _mock_post):
        """get_token must emit DeprecationWarning."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            get_token("user", "pass")
        deprecations = [x for x in w if issubclass(x.category, DeprecationWarning)]
        assert len(deprecations) >= 1
        assert "deprecated" in str(deprecations[0].message).lower()

    def test_still_returns_dict(self, _mock_post):
        """get_token must still return the JSON dict."""
        with warnings.catch_warnings():
            warnings.simplefilter("always")
            result = get_token("user", "pass")
        assert isinstance(result, dict)
        assert result["token"] == "tok"


# ── R-14-b: SecretStr acceptance ──────────────────────────────────
class TestGetTokenSecretStr:
    def test_accepts_secret_str_password(self, _mock_post):
        """get_token must unwrap SecretStr passwords transparently."""
        secret_pw = SecretStr("s3cret")
        with warnings.catch_warnings():
            warnings.simplefilter("always")
            result = get_token("user", secret_pw)
        assert result["token"] == "tok"
        # Verify the actual POST received the unwrapped string
        call_data = _mock_post.call_args
        assert call_data[1]["data"]["password"] == "s3cret"

    def test_accepts_plain_str_password(self, _mock_post):
        """get_token must continue to accept plain-str passwords."""
        with warnings.catch_warnings():
            warnings.simplefilter("always")
            result = get_token("user", "plain")
        assert result["token"] == "tok"
        call_data = _mock_post.call_args
        assert call_data[1]["data"]["password"] == "plain"
