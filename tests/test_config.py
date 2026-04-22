"""Tests for restgdf._config — phase-2a BL-18 (additive / tests-with-code)."""

from __future__ import annotations

import warnings
from collections.abc import Iterator

import pytest
from pydantic import BaseModel, ValidationError

from restgdf._config import (
    AuthConfig,
    ConcurrencyConfig,
    Config,
    LimiterConfig,
    RetryConfig,
    TelemetryConfig,
    TimeoutConfig,
    TransportConfig,
    _parse_bool,
    get_config,
    reset_config_cache,
)
from restgdf._models._errors import RestgdfResponseError
from restgdf._models._settings import reset_settings_cache


_ENV_KEYS = (
    "RESTGDF_TRANSPORT_VERIFY_SSL",
    "RESTGDF_TRANSPORT_USER_AGENT",
    "RESTGDF_TIMEOUT_CONNECT_S",
    "RESTGDF_TIMEOUT_READ_S",
    "RESTGDF_TIMEOUT_TOTAL_S",
    "RESTGDF_TIMEOUT_SECONDS",
    "RESTGDF_RETRY_ENABLED",
    "RESTGDF_RETRY_MAX_ATTEMPTS",
    "RESTGDF_RETRY_MAX_DELAY_S",
    "RESTGDF_LIMITER_ENABLED",
    "RESTGDF_LIMITER_RATE_PER_HOST",
    "RESTGDF_CONCURRENCY_MAX_CONCURRENT_REQUESTS",
    "RESTGDF_MAX_CONCURRENT_REQUESTS",
    "RESTGDF_AUTH_TOKEN_URL",
    "RESTGDF_AUTH_REFRESH_THRESHOLD_S",
    "RESTGDF_TOKEN_URL",
    "RESTGDF_REFRESH_THRESHOLD",
    "RESTGDF_USER_AGENT",
    "RESTGDF_LOG_LEVEL",
    "RESTGDF_TELEMETRY_ENABLED",
    "RESTGDF_TELEMETRY_SERVICE_NAME",
    "RESTGDF_TELEMETRY_LOG_LEVEL",
)


@pytest.fixture(autouse=True)
def _clear_caches_and_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Scrub config-related env vars and drop caches before each test."""
    reset_config_cache()
    reset_settings_cache()
    for key in _ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    yield
    reset_config_cache()
    reset_settings_cache()


# ---- frozen-model tests ---------------------------------------------------


@pytest.mark.parametrize(
    "model_cls",
    [
        TransportConfig,
        TimeoutConfig,
        RetryConfig,
        LimiterConfig,
        ConcurrencyConfig,
        AuthConfig,
        TelemetryConfig,
    ],
)
def test_subconfig_is_frozen(model_cls: type[BaseModel]) -> None:
    instance = model_cls()
    first_field = next(iter(model_cls.model_fields))
    with pytest.raises(ValidationError):
        setattr(instance, first_field, getattr(instance, first_field))


def test_config_slot_assignment_is_frozen() -> None:
    cfg = Config()
    with pytest.raises(ValidationError):
        cfg.transport = TransportConfig()


def test_config_nested_field_assignment_is_frozen() -> None:
    cfg = Config()
    with pytest.raises(ValidationError):
        cfg.transport.verify_ssl = False


# ---- defaults -------------------------------------------------------------


def test_config_defaults_match_spec() -> None:
    cfg = Config()
    assert cfg.transport.verify_ssl is True
    assert cfg.transport.user_agent.startswith("restgdf/")
    assert cfg.timeout.connect_s is None
    assert cfg.timeout.read_s is None
    assert cfg.timeout.total_s == 30.0
    assert cfg.retry.enabled is False
    assert cfg.retry.max_attempts == 5
    assert cfg.retry.max_delay_s == 60.0
    assert cfg.limiter.enabled is False
    assert cfg.limiter.rate_per_host is None
    assert cfg.concurrency.max_concurrent_requests == 8
    assert cfg.auth.token_url is None
    assert cfg.auth.refresh_threshold_s == 60.0
    assert cfg.telemetry.enabled is False
    assert cfg.telemetry.service_name == "restgdf"
    assert cfg.telemetry.log_level == "WARNING"


# ---- get_config caching ---------------------------------------------------


def test_get_config_caches_identity() -> None:
    first = get_config()
    second = get_config()
    assert first is second


def test_reset_config_cache_produces_fresh_instance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = get_config()
    assert first.timeout.total_s == 30.0
    monkeypatch.setenv("RESTGDF_TIMEOUT_TOTAL_S", "42.5")
    reset_config_cache()
    second = get_config()
    assert second.timeout.total_s == pytest.approx(42.5)
    assert first is not second


def test_reset_config_cache_is_idempotent() -> None:
    reset_config_cache()
    reset_config_cache()  # second call is a no-op, must not raise.


# ---- new env-var surface --------------------------------------------------


@pytest.mark.parametrize(
    ("env_key", "env_value", "dotted", "expected"),
    [
        ("RESTGDF_TRANSPORT_VERIFY_SSL", "false", "transport.verify_ssl", False),
        ("RESTGDF_TRANSPORT_USER_AGENT", "ua/1", "transport.user_agent", "ua/1"),
        ("RESTGDF_TIMEOUT_CONNECT_S", "2.5", "timeout.connect_s", 2.5),
        ("RESTGDF_TIMEOUT_READ_S", "6.25", "timeout.read_s", 6.25),
        ("RESTGDF_TIMEOUT_TOTAL_S", "45", "timeout.total_s", 45.0),
        ("RESTGDF_RETRY_ENABLED", "yes", "retry.enabled", True),
        ("RESTGDF_RETRY_MAX_ATTEMPTS", "10", "retry.max_attempts", 10),
        ("RESTGDF_RETRY_MAX_DELAY_S", "15.5", "retry.max_delay_s", 15.5),
        ("RESTGDF_LIMITER_ENABLED", "on", "limiter.enabled", True),
        ("RESTGDF_LIMITER_RATE_PER_HOST", "3.3", "limiter.rate_per_host", 3.3),
        (
            "RESTGDF_CONCURRENCY_MAX_CONCURRENT_REQUESTS",
            "2",
            "concurrency.max_concurrent_requests",
            2,
        ),
        (
            "RESTGDF_AUTH_TOKEN_URL",
            "https://example.com/t",
            "auth.token_url",
            "https://example.com/t",
        ),
        (
            "RESTGDF_AUTH_REFRESH_THRESHOLD_S",
            "90",
            "auth.refresh_threshold_s",
            90.0,
        ),
        ("RESTGDF_TELEMETRY_ENABLED", "1", "telemetry.enabled", True),
        (
            "RESTGDF_TELEMETRY_SERVICE_NAME",
            "svc-x",
            "telemetry.service_name",
            "svc-x",
        ),
        (
            "RESTGDF_TELEMETRY_LOG_LEVEL",
            "debug",
            "telemetry.log_level",
            "DEBUG",
        ),
    ],
)
def test_new_env_var_resolves(
    monkeypatch: pytest.MonkeyPatch,
    env_key: str,
    env_value: str,
    dotted: str,
    expected: object,
) -> None:
    monkeypatch.setenv(env_key, env_value)
    cfg = get_config()
    section, field_name = dotted.split(".", 1)
    actual = getattr(getattr(cfg, section), field_name)
    if isinstance(expected, float):
        assert actual == pytest.approx(expected)
    else:
        assert actual == expected


# ---- validator errors -----------------------------------------------------


def test_from_env_wraps_validation_error_preserves_cause(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RESTGDF_CONCURRENCY_MAX_CONCURRENT_REQUESTS", "0")
    with pytest.raises(RestgdfResponseError) as exc_info:
        get_config()
    assert isinstance(exc_info.value.__cause__, ValidationError)
    assert exc_info.value.context == "Config.from_env"


def test_telemetry_log_level_rejects_bogus_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RESTGDF_TELEMETRY_LOG_LEVEL", "BOGUS")
    with pytest.raises(RestgdfResponseError):
        get_config()


def test_auth_token_url_rejects_bad_scheme(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RESTGDF_AUTH_TOKEN_URL", "javascript:alert(1)")
    with pytest.raises(RestgdfResponseError):
        get_config()


def test_auth_token_url_none_is_accepted() -> None:
    cfg = get_config()
    assert cfg.auth.token_url is None


def test_from_env_coerce_type_error_wraps(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RESTGDF_TIMEOUT_TOTAL_S", "not-a-float")
    with pytest.raises(RestgdfResponseError) as exc_info:
        get_config()
    assert "RESTGDF_TIMEOUT_TOTAL_S" in str(exc_info.value)


def test_parse_bool_invalid_raises_through_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RESTGDF_RETRY_ENABLED", "maybe")
    with pytest.raises(RestgdfResponseError) as exc_info:
        get_config()
    assert "RESTGDF_RETRY_ENABLED" in str(exc_info.value)


@pytest.mark.parametrize("raw", ["1", "true", "TRUE", "Yes", "on"])
def test_parse_bool_truthy(raw: str) -> None:
    assert _parse_bool(raw) is True


@pytest.mark.parametrize("raw", ["0", "false", "no", "OFF"])
def test_parse_bool_falsy(raw: str) -> None:
    assert _parse_bool(raw) is False


def test_parse_bool_invalid_direct() -> None:
    with pytest.raises(ValueError):
        _parse_bool("perhaps")


# ---- alias precedence (additional assertions; warning-focused tests live
# in test_settings_deprecation.py) -----------------------------------------


def test_new_wins_over_deprecated_alias_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RESTGDF_TIMEOUT_SECONDS", "5.0")
    monkeypatch.setenv("RESTGDF_TIMEOUT_TOTAL_S", "9.0")
    with pytest.warns(DeprecationWarning, match="takes precedence"):
        cfg = get_config()
    assert cfg.timeout.total_s == pytest.approx(9.0)


def test_from_env_accepts_explicit_mapping() -> None:
    cfg = Config.from_env(env={"RESTGDF_TIMEOUT_TOTAL_S": "13.0"})
    assert cfg.timeout.total_s == pytest.approx(13.0)


def test_from_env_empty_mapping_uses_defaults() -> None:
    cfg = Config.from_env(env={})
    assert cfg.timeout.total_s == 30.0
    assert cfg.concurrency.max_concurrent_requests == 8


# ---- gate-2: log_level aliases (WARN/FATAL) -------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("WARN", "WARNING"),
        ("warn", "WARNING"),
        ("Warn", "WARNING"),
        ("FATAL", "CRITICAL"),
        ("fatal", "CRITICAL"),
    ],
)
def test_telemetry_log_level_accepts_stdlib_aliases(raw: str, expected: str) -> None:
    cfg = TelemetryConfig(log_level=raw)
    assert cfg.log_level == expected


def test_telemetry_log_level_alias_via_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RESTGDF_TELEMETRY_LOG_LEVEL", "WARN")
    cfg = get_config()
    assert cfg.telemetry.log_level == "WARNING"


# ---- gate-2: HttpUrl-based token_url validation ---------------------------


@pytest.mark.parametrize(
    "bad_url",
    [
        "https://",
        "not-a-url",
        "ftp://example.com/token",
        "javascript:alert(1)",
        "",
    ],
)
def test_auth_token_url_rejects_invalid_urls(bad_url: str) -> None:
    with pytest.raises(ValidationError):
        AuthConfig(token_url=bad_url)


@pytest.mark.parametrize(
    "good_url",
    [
        "https://example.com/token",
        "http://enterprise.example.com/sharing/rest/generateToken",
        "https://arcgis.com/sharing/rest/generateToken",
    ],
)
def test_auth_token_url_accepts_valid_urls(good_url: str) -> None:
    cfg = AuthConfig(token_url=good_url)
    assert cfg.token_url == good_url


# ---- gate-2: cache-cascade (both directions) ------------------------------


def test_reset_config_cache_also_invalidates_get_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Clearing the Config cache must also drop the cached Settings shim."""
    from restgdf._models._settings import get_settings

    monkeypatch.setenv("RESTGDF_TIMEOUT_TOTAL_S", "11.5")
    with pytest.warns(DeprecationWarning):
        first = get_settings()
    assert first.timeout_seconds == pytest.approx(11.5)

    monkeypatch.setenv("RESTGDF_TIMEOUT_TOTAL_S", "17.25")
    reset_config_cache()  # only the Config cache is cleared explicitly
    with pytest.warns(DeprecationWarning):
        second = get_settings()
    assert second.timeout_seconds == pytest.approx(17.25)
    assert first is not second


def test_reset_settings_cache_also_invalidates_get_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Clearing the Settings cache must also drop the cached Config."""
    from restgdf._models._settings import reset_settings_cache as _rsc

    first = get_config()
    assert first.timeout.total_s == 30.0

    monkeypatch.setenv("RESTGDF_TIMEOUT_TOTAL_S", "21.5")
    _rsc()  # only the Settings cache is cleared explicitly
    second = get_config()
    assert second.timeout.total_s == pytest.approx(21.5)
    assert first is not second


# ---- gate-2: stacklevel attribution ---------------------------------------


def test_config_from_env_direct_warning_attributes_to_caller(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Direct ``Config.from_env()`` call — warning points at this test file."""
    monkeypatch.setenv("RESTGDF_TIMEOUT_SECONDS", "5.0")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        Config.from_env()
    dep = [w for w in caught if issubclass(w.category, DeprecationWarning)]
    assert dep, "expected a DeprecationWarning"
    assert dep[0].filename == __file__, (
        f"expected attribution to test file {__file__!r}, " f"got {dep[0].filename!r}"
    )


def test_get_config_warning_attributes_to_caller(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``get_config()`` call — warning points at this test file, not get_config."""
    monkeypatch.setenv("RESTGDF_TIMEOUT_SECONDS", "5.0")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        get_config()
    dep = [w for w in caught if issubclass(w.category, DeprecationWarning)]
    assert dep, "expected a DeprecationWarning"
    assert dep[0].filename == __file__, (
        f"expected attribution to test file {__file__!r}, " f"got {dep[0].filename!r}"
    )
