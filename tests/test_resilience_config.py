"""Red tests for ResilienceConfig (BL-31, commit 1)."""

from __future__ import annotations


import pytest
from pydantic import ValidationError

from restgdf._config import Config, ResilienceConfig, get_config, reset_config_cache
from restgdf.errors import ConfigurationError, RestgdfResponseError


class TestResilienceConfig:
    """ResilienceConfig shape and defaults."""

    def test_resilience_config_default_disabled(self) -> None:
        cfg = ResilienceConfig()
        assert cfg.enabled is False

    def test_resilience_config_frozen(self) -> None:
        cfg = ResilienceConfig()
        with pytest.raises(ValidationError):
            cfg.enabled = True  # type: ignore[misc]

    def test_resilience_config_on_config_default_factory_instance(self) -> None:
        a = Config()
        b = Config()
        assert a.resilience is not b.resilience
        assert a.resilience == b.resilience

    def test_resilience_env_var_enables(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("RESTGDF_RESILIENCE_ENABLED", "1")
        reset_config_cache()
        try:
            cfg = get_config()
            assert cfg.resilience.enabled is True
        finally:
            reset_config_cache()

    def test_resilience_rate_env_var_coerces_float(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("RESTGDF_RESILIENCE_RATE_PER_SERVICE_ROOT_PER_SECOND", "5.5")
        reset_config_cache()
        try:
            cfg = get_config()
            assert cfg.resilience.rate_per_service_root_per_second == 5.5
        finally:
            reset_config_cache()

    def test_resilience_rate_env_var_rejects_nonpositive(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("RESTGDF_RESILIENCE_RATE_PER_SERVICE_ROOT_PER_SECOND", "0")
        reset_config_cache()
        try:
            with pytest.raises((ConfigurationError, RestgdfResponseError)):
                get_config()
        finally:
            reset_config_cache()

    # ---- R1: limiter_key granularity selector -----------------------------

    def test_limiter_key_defaults_to_service_root(self) -> None:
        assert ResilienceConfig().limiter_key == "service_root"

    def test_limiter_key_accepts_host(self) -> None:
        assert ResilienceConfig(limiter_key="host").limiter_key == "host"

    def test_limiter_key_rejects_unknown_value(self) -> None:
        with pytest.raises(ValidationError):
            ResilienceConfig(limiter_key="region")  # type: ignore[arg-type]

    def test_limiter_key_env_var_resolves(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("RESTGDF_RESILIENCE_LIMITER_KEY", "host")
        reset_config_cache()
        try:
            assert get_config().resilience.limiter_key == "host"
        finally:
            reset_config_cache()

    def test_limiter_key_env_var_rejects_bad_value(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("RESTGDF_RESILIENCE_LIMITER_KEY", "planet")
        reset_config_cache()
        try:
            with pytest.raises((ConfigurationError, RestgdfResponseError)):
                get_config()
        finally:
            reset_config_cache()

    # ---- R2: retry knobs on ResilienceConfig ------------------------------

    def test_retry_knob_defaults_preserve_hardcoded_policy(self) -> None:
        cfg = ResilienceConfig()
        assert cfg.max_attempts == 5
        assert cfg.retry_budget_s == 60.0
        assert cfg.wait_initial_s == 0.5
        assert cfg.wait_max_s == 10.0
        assert cfg.wait_jitter_s == 1.0

    def test_max_attempts_env_var_resolves(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("RESTGDF_RESILIENCE_MAX_ATTEMPTS", "2")
        reset_config_cache()
        try:
            assert get_config().resilience.max_attempts == 2
        finally:
            reset_config_cache()

    def test_retry_budget_env_var_resolves(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("RESTGDF_RESILIENCE_RETRY_BUDGET_S", "12.5")
        reset_config_cache()
        try:
            assert get_config().resilience.retry_budget_s == 12.5
        finally:
            reset_config_cache()

    def test_wait_knob_env_vars_resolve(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("RESTGDF_RESILIENCE_WAIT_INITIAL_S", "0.25")
        monkeypatch.setenv("RESTGDF_RESILIENCE_WAIT_MAX_S", "3.0")
        monkeypatch.setenv("RESTGDF_RESILIENCE_WAIT_JITTER_S", "0")
        reset_config_cache()
        try:
            cfg = get_config().resilience
            assert cfg.wait_initial_s == 0.25
            assert cfg.wait_max_s == 3.0
            assert cfg.wait_jitter_s == 0.0
        finally:
            reset_config_cache()

    def test_max_attempts_rejects_below_one(self) -> None:
        with pytest.raises(ValidationError):
            ResilienceConfig(max_attempts=0)
