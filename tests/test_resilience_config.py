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
