"""Tests for :mod:`restgdf._models._settings`.

TDD-first: this file is authored before the module it exercises (S-7).
"""

from __future__ import annotations

import restgdf._models._settings as settings_mod
import pytest
from pydantic import BaseModel, ValidationError

from restgdf._models import RestgdfResponseError
from restgdf._models._settings import (
    Settings,
    get_settings,
    reset_settings_cache,
)


# ---------------------------------------------------------------------------
# Autouse fixture: isolate cache across tests.
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clear_cache():
    reset_settings_cache()
    yield
    reset_settings_cache()


# ---------------------------------------------------------------------------
# Baseline structure
# ---------------------------------------------------------------------------


def test_settings_is_basemodel():
    assert issubclass(Settings, BaseModel)


def test_default_values_are_sensible():
    s = Settings()
    assert isinstance(s.chunk_size, int) and s.chunk_size > 0
    assert isinstance(s.timeout_seconds, float) and s.timeout_seconds > 0
    # default user_agent derives from restgdf.__version__
    assert s.user_agent.startswith("restgdf/")
    assert s.log_level == "WARNING"
    assert s.token_url.startswith("https://")
    assert isinstance(s.refresh_threshold_seconds, int)
    assert s.default_headers_json is None


def test_from_env_empty_mapping_equals_defaults():
    assert Settings.from_env({}).model_dump() == Settings().model_dump()


def test_restgdf_version_falls_back_to_package_init_when_metadata_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings_mod._restgdf_version.cache_clear()

    def _raise_package_not_found(_: str) -> str:
        raise settings_mod.PackageNotFoundError

    monkeypatch.setattr(settings_mod, "package_version", _raise_package_not_found)
    monkeypatch.setattr(
        settings_mod.Path,
        "read_text",
        lambda self, encoding="utf-8": '__version__ = "9.9.9"\n',
    )

    try:
        assert settings_mod._restgdf_version() == "9.9.9"
    finally:
        settings_mod._restgdf_version.cache_clear()


# ---------------------------------------------------------------------------
# Env var parsing
# ---------------------------------------------------------------------------


def test_from_env_reads_os_environ_by_default(monkeypatch):
    monkeypatch.setenv("RESTGDF_CHUNK_SIZE", "777")
    s = Settings.from_env()
    assert s.chunk_size == 777


def test_from_env_chunk_size_coerced_to_int():
    s = Settings.from_env({"RESTGDF_CHUNK_SIZE": "500"})
    assert s.chunk_size == 500


def test_from_env_chunk_size_bad_value_raises_response_error():
    with pytest.raises(RestgdfResponseError) as excinfo:
        Settings.from_env({"RESTGDF_CHUNK_SIZE": "not_a_number"})
    assert excinfo.value.model_name == "Settings"
    assert "RESTGDF_CHUNK_SIZE" in str(excinfo.value)


def test_from_env_timeout_coerced_to_float():
    s = Settings.from_env({"RESTGDF_TIMEOUT_SECONDS": "5.5"})
    assert s.timeout_seconds == 5.5


def test_from_env_timeout_bad_value_raises():
    with pytest.raises(RestgdfResponseError):
        Settings.from_env({"RESTGDF_TIMEOUT_SECONDS": "abc"})


def test_from_env_refresh_threshold_coerced_to_int():
    s = Settings.from_env({"RESTGDF_REFRESH_THRESHOLD": "120"})
    assert s.refresh_threshold_seconds == 120


def test_from_env_refresh_threshold_bad_value_raises():
    with pytest.raises(RestgdfResponseError):
        Settings.from_env({"RESTGDF_REFRESH_THRESHOLD": "nope"})


def test_from_env_user_agent_override():
    s = Settings.from_env({"RESTGDF_USER_AGENT": "my-agent/1.0"})
    assert s.user_agent == "my-agent/1.0"


def test_from_env_token_url_override():
    s = Settings.from_env({"RESTGDF_TOKEN_URL": "https://example.com/token"})
    assert s.token_url == "https://example.com/token"


def test_from_env_log_level_override():
    s = Settings.from_env({"RESTGDF_LOG_LEVEL": "DEBUG"})
    assert s.log_level == "DEBUG"


def test_from_env_default_headers_json_passthrough():
    raw = '{"X-Foo": "bar"}'
    s = Settings.from_env({"RESTGDF_DEFAULT_HEADERS_JSON": raw})
    assert s.default_headers_json == raw


# ---------------------------------------------------------------------------
# Case sensitivity — env keys must match exactly (uppercase RESTGDF_ prefix).
# ---------------------------------------------------------------------------


def test_from_env_is_case_sensitive():
    s = Settings.from_env({"restgdf_chunk_size": "999"})
    # lowercase key must be ignored; defaults apply
    assert s.chunk_size == Settings().chunk_size


# ---------------------------------------------------------------------------
# Validation via pydantic is also wrapped as RestgdfResponseError.
# ---------------------------------------------------------------------------


def test_invalid_field_value_via_direct_construction_raises_validation_error():
    with pytest.raises(ValidationError):
        Settings(chunk_size=-1)


def test_from_env_wraps_validation_error_as_response_error():
    # chunk_size must be positive; supply 0 via env → RestgdfResponseError.
    with pytest.raises(RestgdfResponseError):
        Settings.from_env({"RESTGDF_CHUNK_SIZE": "0"})


def test_invalid_log_level_rejected():
    with pytest.raises(ValidationError):
        Settings(log_level="LOUD")


def test_log_level_is_normalized_to_upper():
    assert Settings(log_level="debug").log_level == "DEBUG"


def test_invalid_token_url_scheme_rejected():
    with pytest.raises(ValidationError):
        Settings(token_url="ftp://example.com")


# ---------------------------------------------------------------------------
# Immutability — Settings is frozen.
# ---------------------------------------------------------------------------


def test_settings_is_frozen():
    s = Settings()
    with pytest.raises(ValidationError):
        s.chunk_size = 123  # type: ignore[misc]


# ---------------------------------------------------------------------------
# get_settings caching behavior.
# ---------------------------------------------------------------------------


def test_get_settings_returns_cached_instance():
    a = get_settings()
    b = get_settings()
    assert a is b


def test_reset_settings_cache_forces_new_instance(monkeypatch):
    a = get_settings()
    monkeypatch.setenv("RESTGDF_CHUNK_SIZE", "321")
    # Without reset, cached value persists.
    assert get_settings() is a
    reset_settings_cache()
    b = get_settings()
    assert b is not a
    assert b.chunk_size == 321


def test_get_settings_reads_current_env_on_first_call(monkeypatch):
    monkeypatch.setenv("RESTGDF_TRANSPORT_USER_AGENT", "probe/9.9")
    with pytest.warns(DeprecationWarning, match=r"get_settings\(\)"):
        s = get_settings()
    assert s.user_agent == "probe/9.9"
