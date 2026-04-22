"""Tests for :mod:`restgdf._models.credentials`.

TDD-first: this file is authored before the module it exercises.
"""

from __future__ import annotations

import pytest
from pydantic import SecretStr

from restgdf._models import RestgdfResponseError
from restgdf._models._drift import StrictModel, _parse_response
from restgdf._models.credentials import AGOLUserPass, TokenSessionConfig


# ---------------------------------------------------------------------------
# Tier + SecretStr behavior
# ---------------------------------------------------------------------------


def test_agoluserpass_is_strict_tier():
    assert issubclass(AGOLUserPass, StrictModel)


def test_tokensessionconfig_is_strict_tier():
    assert issubclass(TokenSessionConfig, StrictModel)


def test_agoluserpass_password_is_secretstr_and_redacted_in_str():
    creds = AGOLUserPass(username="u", password="p")
    assert isinstance(creds.password, SecretStr)
    rendered = str(creds)
    assert "p" not in rendered or "password" in rendered
    # Stronger: the literal secret value must not appear in str/repr.
    rendered_repr = repr(creds)
    assert "p" not in _strip_known_noise(rendered_repr)


def test_agoluserpass_get_secret_value_returns_real_password():
    creds = AGOLUserPass(username="u", password="supersecret")
    assert creds.password.get_secret_value() == "supersecret"


def _strip_known_noise(text: str) -> str:
    """Remove tokens that legitimately contain ``p`` from a repr for the
    'password value is redacted' assertion (field names like ``password``
    and the ``AGOLUserPass`` class name are expected to contain ``p``)."""
    for noise in ("AGOLUserPass", "password", "SecretStr", "expiration"):
        text = text.replace(noise, "")
    return text


# ---------------------------------------------------------------------------
# Validation via _parse_response (strict tier contract)
# ---------------------------------------------------------------------------


def test_agoluserpass_empty_username_raises_via_parse_response():
    with pytest.raises(RestgdfResponseError):
        _parse_response(
            AGOLUserPass,
            {"username": "", "password": "p"},
            context="test",
        )


def test_agoluserpass_missing_password_raises_via_parse_response():
    with pytest.raises(RestgdfResponseError):
        _parse_response(AGOLUserPass, {"username": "u"}, context="test")


def test_agoluserpass_defaults():
    creds = AGOLUserPass(username="u", password="p")
    assert creds.expiration == 60
    assert creds.referer is None


# ---------------------------------------------------------------------------
# TokenSessionConfig: ArcGIS Enterprise HTTP compat
# ---------------------------------------------------------------------------


def _creds() -> AGOLUserPass:
    return AGOLUserPass(username="u", password="p")


def test_tokensessionconfig_accepts_https_url():
    cfg = TokenSessionConfig(
        token_url="https://www.arcgis.com/sharing/rest/generateToken",
        credentials=_creds(),
    )
    assert cfg.token_url.startswith("https://")


def test_tokensessionconfig_accepts_http_enterprise_url():
    # CRITICAL compat test: ArcGIS Enterprise frequently runs plain http
    # on internal networks. Rejecting http:// would break real users.
    cfg = TokenSessionConfig(
        token_url="http://enterprise.example.com/sharing/rest/generateToken",
        credentials=_creds(),
    )
    assert cfg.token_url.startswith("http://")


@pytest.mark.parametrize(
    "bad_url",
    ["ftp://example.com/token", "file:///etc/passwd", "javascript:alert(1)", ""],
)
def test_tokensessionconfig_rejects_non_http_schemes(bad_url: str):
    with pytest.raises(RestgdfResponseError):
        _parse_response(
            TokenSessionConfig,
            {
                "token_url": bad_url,
                "credentials": {"username": "u", "password": "p"},
            },
            context="test",
        )


def test_tokensessionconfig_defaults():
    cfg = TokenSessionConfig(
        token_url="https://example.com/sharing/rest/generateToken",
        credentials=_creds(),
    )
    assert cfg.refresh_leeway_seconds == 60
    assert cfg.clock_skew_seconds == 30
    assert cfg.verify_ssl is True


def test_tokensessionconfig_nested_credentials_preserve_secretstr():
    cfg = TokenSessionConfig(
        token_url="https://example.com/sharing/rest/generateToken",
        credentials={"username": "u", "password": "p"},
    )
    assert isinstance(cfg.credentials, AGOLUserPass)
    assert cfg.credentials.password.get_secret_value() == "p"


def test_tokensessionconfig_parse_response_roundtrip():
    import warnings as _warnings

    with _warnings.catch_warnings():
        _warnings.simplefilter("ignore", DeprecationWarning)
        cfg = _parse_response(
            TokenSessionConfig,
            {
                "token_url": "https://example.com/sharing/rest/generateToken",
                "credentials": {"username": "u", "password": "p"},
                "refresh_threshold_seconds": 120,
                "verify_ssl": False,
            },
            context="test",
        )
    assert cfg.clock_skew_seconds == 30
    assert cfg.refresh_leeway_seconds == 90
    with _warnings.catch_warnings():
        _warnings.simplefilter("ignore", DeprecationWarning)
        assert cfg.refresh_threshold_seconds == 120
    assert cfg.verify_ssl is False
