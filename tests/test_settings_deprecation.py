"""Red-first pins for phase-2a BL-18 deprecation semantics.

Covers:
* ``get_settings()`` emits a ``DeprecationWarning`` (shim contract).
* Old flat env-var aliases (``RESTGDF_TIMEOUT_SECONDS``, ``RESTGDF_TOKEN_URL``,
  ``RESTGDF_REFRESH_THRESHOLD``, ``RESTGDF_USER_AGENT``, ``RESTGDF_LOG_LEVEL``,
  ``RESTGDF_MAX_CONCURRENT_REQUESTS``) still flow to :class:`Config` + emit a
  ``DeprecationWarning`` naming the replacement env-var.
* When both OLD and NEW env-vars are set, NEW wins and the warning notes that
  the OLD value was ignored.
* ``get_settings()`` still returns a Settings-shaped object usable by existing
  callers (``.timeout_seconds``, ``.max_concurrent_requests`` etc.).
"""

from __future__ import annotations

import warnings

import pytest

from restgdf._config import get_config, reset_config_cache
from restgdf._models._settings import Settings, get_settings, reset_settings_cache


@pytest.fixture(autouse=True)
def _clear_caches(monkeypatch: pytest.MonkeyPatch) -> None:
    """Drop cached Config/Settings before and after each test."""
    reset_config_cache()
    reset_settings_cache()
    for key in (
        "RESTGDF_TIMEOUT_SECONDS",
        "RESTGDF_TIMEOUT_TOTAL_S",
        "RESTGDF_TOKEN_URL",
        "RESTGDF_AUTH_TOKEN_URL",
        "RESTGDF_REFRESH_THRESHOLD",
        "RESTGDF_AUTH_REFRESH_THRESHOLD_S",
        "RESTGDF_USER_AGENT",
        "RESTGDF_TRANSPORT_USER_AGENT",
        "RESTGDF_LOG_LEVEL",
        "RESTGDF_TELEMETRY_LOG_LEVEL",
        "RESTGDF_MAX_CONCURRENT_REQUESTS",
        "RESTGDF_CONCURRENCY_MAX_CONCURRENT_REQUESTS",
        "RESTGDF_CHUNK_SIZE",
        "RESTGDF_DEFAULT_HEADERS_JSON",
    ):
        monkeypatch.delenv(key, raising=False)
    yield
    reset_config_cache()
    reset_settings_cache()


def test_get_settings_emits_deprecation_warning() -> None:
    with pytest.warns(DeprecationWarning, match="get_settings"):
        settings = get_settings()
    assert isinstance(settings, Settings)


def test_get_settings_warning_fires_once_per_cache() -> None:
    with pytest.warns(DeprecationWarning):
        first = get_settings()
    # Second call hits the lru_cache; no new warning emitted.
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        second = get_settings()
    assert first is second


def test_old_env_timeout_seconds_alias_emits_warning_and_resolves(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RESTGDF_TIMEOUT_SECONDS", "7.5")
    with pytest.warns(DeprecationWarning, match="RESTGDF_TIMEOUT_TOTAL_S"):
        cfg = get_config()
    assert cfg.timeout.total_s == pytest.approx(7.5)


def test_old_env_token_url_alias_emits_warning_and_resolves(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RESTGDF_TOKEN_URL", "https://example.com/token")
    with pytest.warns(DeprecationWarning, match="RESTGDF_AUTH_TOKEN_URL"):
        cfg = get_config()
    assert cfg.auth.token_url == "https://example.com/token"


def test_old_env_refresh_threshold_alias_emits_warning_and_resolves(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RESTGDF_REFRESH_THRESHOLD", "120")
    with pytest.warns(
        DeprecationWarning, match="RESTGDF_AUTH_REFRESH_THRESHOLD_S",
    ):
        cfg = get_config()
    assert cfg.auth.refresh_threshold_s == pytest.approx(120.0)


def test_old_env_user_agent_alias_emits_warning_and_resolves(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RESTGDF_USER_AGENT", "legacy-agent/1.0")
    with pytest.warns(DeprecationWarning, match="RESTGDF_TRANSPORT_USER_AGENT"):
        cfg = get_config()
    assert cfg.transport.user_agent == "legacy-agent/1.0"


def test_old_env_log_level_alias_emits_warning_and_resolves(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RESTGDF_LOG_LEVEL", "debug")
    with pytest.warns(DeprecationWarning, match="RESTGDF_TELEMETRY_LOG_LEVEL"):
        cfg = get_config()
    assert cfg.telemetry.log_level == "DEBUG"


def test_old_env_max_concurrent_requests_alias_emits_warning_and_resolves(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RESTGDF_MAX_CONCURRENT_REQUESTS", "4")
    with pytest.warns(
        DeprecationWarning,
        match="RESTGDF_CONCURRENCY_MAX_CONCURRENT_REQUESTS",
    ):
        cfg = get_config()
    assert cfg.concurrency.max_concurrent_requests == 4


def test_new_env_var_wins_over_deprecated_alias(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RESTGDF_TIMEOUT_SECONDS", "5.0")
    monkeypatch.setenv("RESTGDF_TIMEOUT_TOTAL_S", "9.0")
    with pytest.warns(DeprecationWarning, match="takes precedence"):
        cfg = get_config()
    assert cfg.timeout.total_s == pytest.approx(9.0)


def test_get_settings_roundtrip_preserves_config_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RESTGDF_TIMEOUT_TOTAL_S", "11.5")
    monkeypatch.setenv("RESTGDF_CONCURRENCY_MAX_CONCURRENT_REQUESTS", "3")
    monkeypatch.setenv("RESTGDF_TRANSPORT_USER_AGENT", "ua/test")
    with pytest.warns(DeprecationWarning):
        settings = get_settings()
    assert settings.timeout_seconds == pytest.approx(11.5)
    assert settings.max_concurrent_requests == 3
    assert settings.user_agent == "ua/test"


def test_get_settings_chunk_size_from_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RESTGDF_CHUNK_SIZE", "250")
    with pytest.warns(DeprecationWarning):
        settings = get_settings()
    assert settings.chunk_size == 250


def test_get_settings_default_headers_json_from_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "RESTGDF_DEFAULT_HEADERS_JSON", '{"x-foo":"bar"}',
    )
    with pytest.warns(DeprecationWarning):
        settings = get_settings()
    assert settings.default_headers_json == '{"x-foo":"bar"}'
