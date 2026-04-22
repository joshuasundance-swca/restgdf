"""Layered runtime configuration for restgdf (phase-2a BL-18).

Seven frozen pydantic 2.x sub-configs mirror the plan-obs §3 taxonomy:
:class:`TransportConfig`, :class:`TimeoutConfig`, :class:`RetryConfig`,
:class:`LimiterConfig`, :class:`ConcurrencyConfig`, :class:`AuthConfig`,
:class:`TelemetryConfig`. The aggregate :class:`Config` is resolved lazily via
:func:`get_config` (LRU-cached size-1; reset with :func:`reset_config_cache`).

Env-var naming
--------------

New names follow ``RESTGDF_<CATEGORY>_<FIELD>`` (uppercased field name). The
following flat legacy names stay wired as deprecated aliases:

* ``RESTGDF_TIMEOUT_SECONDS``              → ``RESTGDF_TIMEOUT_TOTAL_S``
* ``RESTGDF_TOKEN_URL``                    → ``RESTGDF_AUTH_TOKEN_URL``
* ``RESTGDF_REFRESH_THRESHOLD``            → ``RESTGDF_AUTH_REFRESH_THRESHOLD_S``
* ``RESTGDF_USER_AGENT``                   → ``RESTGDF_TRANSPORT_USER_AGENT``
* ``RESTGDF_LOG_LEVEL``                    → ``RESTGDF_TELEMETRY_LOG_LEVEL``
* ``RESTGDF_MAX_CONCURRENT_REQUESTS``      →
  ``RESTGDF_CONCURRENCY_MAX_CONCURRENT_REQUESTS``

Precedence: new name wins over old alias wins over model defaults. When the
old alias is set a :class:`DeprecationWarning` names its replacement. When
both the old alias and its preferred new name are set, the new name wins and
the deprecation warning notes that the old value was ignored. See MIGRATION.md
for the full migration guide.

The legacy :class:`restgdf.Settings` model and :func:`restgdf.get_settings`
remain as deprecated shims delegating here; see
:mod:`restgdf._models._settings`.
"""

from __future__ import annotations

import functools
import os
import warnings
from collections.abc import Mapping
from typing import Any, Callable, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    SecretStr,
    TypeAdapter,
    ValidationError,
    field_validator,
    model_validator,
)

from restgdf._models._errors import RestgdfResponseError
from restgdf._models._settings import _VALID_LOG_LEVELS, _default_user_agent


_FROZEN = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

# pydantic HttpUrl-based validator for ``token_url`` strings. We keep the
# public field type as ``str`` so consumers (e.g. TokenSessionConfig) that
# expect plain strings do not break, but we reuse pydantic's URL parser for
# validation so we reject malformed inputs consistently.
_HTTP_URL_ADAPTER: TypeAdapter[HttpUrl] = TypeAdapter(HttpUrl)

# Logging aliases we accept in addition to the canonical level names. The
# stdlib logging module treats ``WARN`` as a synonym for ``WARNING`` and
# ``FATAL`` as a synonym for ``CRITICAL``; we normalize both here so
# ``RESTGDF_TELEMETRY_LOG_LEVEL=WARN`` does not raise.
_LOG_LEVEL_ALIASES: Mapping[str, str] = {"WARN": "WARNING", "FATAL": "CRITICAL"}


class TransportConfig(BaseModel):
    """HTTP transport knobs (TLS, user agent)."""

    model_config = _FROZEN

    verify_ssl: bool = True
    user_agent: str = Field(default_factory=_default_user_agent, min_length=1)


class TimeoutConfig(BaseModel):
    """HTTP timeout budget (total + optional connect/read splits)."""

    model_config = _FROZEN

    connect_s: float | None = Field(default=None, gt=0)
    read_s: float | None = Field(default=None, gt=0)
    total_s: float = Field(default=30.0, gt=0)


class RetryConfig(BaseModel):
    """Retry policy (disabled by default; phase-3a wires the executor)."""

    model_config = _FROZEN

    enabled: bool = False
    max_attempts: int = Field(default=5, ge=1)
    max_delay_s: float = Field(default=60.0, gt=0)


class LimiterConfig(BaseModel):
    """Rate-limiter configuration (disabled by default)."""

    model_config = _FROZEN

    enabled: bool = False
    rate_per_host: float | None = Field(default=None, gt=0)


class ConcurrencyConfig(BaseModel):
    """Bounded-semaphore ceiling for top-level orchestration calls."""

    model_config = _FROZEN

    max_concurrent_requests: int = Field(default=8, ge=1)


class AuthConfig(BaseModel):
    """ArcGIS token-session defaults.

    .. versionchanged:: 3.0
        Default *transport* flipped from ``"body"`` to ``"header"``; default
        *header_name* is ``"X-Esri-Authorization"``.  Pass
        ``allow_query_transport=True`` to enable ``transport="query"``.
    """

    model_config = _FROZEN

    token_url: str | None = None
    transport: Literal["header", "body", "query"] = "header"
    header_name: str = Field(default="X-Esri-Authorization", min_length=1)
    referer: str | None = None

    refresh_threshold_s: float = Field(default=60.0, ge=0)
    refresh_leeway_s: float = Field(default=120.0, ge=0.0, le=600.0)
    clock_skew_s: float = Field(default=30.0, ge=0.0, le=120.0)

    username: SecretStr | None = None
    password: SecretStr | None = None
    token: SecretStr | None = None

    allow_query_transport: bool = False

    @field_validator("token_url")
    @classmethod
    def _check_token_url_scheme(cls, value: str | None) -> str | None:
        if value is None:
            return value
        try:
            _HTTP_URL_ADAPTER.validate_python(value)
        except ValidationError as exc:
            raise ValueError(
                f"token_url must be a valid http(s) URL: {value!r} ({exc})",
            ) from exc
        return value

    @model_validator(mode="after")
    def _reject_query_without_flag(self) -> AuthConfig:
        """R-13 strict: ``transport='query'`` without ``allow_query_transport`` → error."""
        if self.transport == "query" and not self.allow_query_transport:
            raise ValueError(
                "transport='query' is insecure and requires "
                "allow_query_transport=True at AuthConfig construction.",
            )
        return self


class TelemetryConfig(BaseModel):
    """Optional telemetry + legacy ``schema_drift`` log-level routing."""

    model_config = _FROZEN

    enabled: bool = False
    service_name: str = Field(default="restgdf", min_length=1)
    log_level: str = Field(default="WARNING")

    @field_validator("log_level")
    @classmethod
    def _normalize_log_level(cls, value: str) -> str:
        upper = value.upper()
        upper = _LOG_LEVEL_ALIASES.get(upper, upper)
        if upper not in _VALID_LOG_LEVELS:
            raise ValueError(
                f"log_level must be one of {sorted(_VALID_LOG_LEVELS)!r}",
            )
        return upper


class ResilienceConfig(BaseModel):
    """Resilience adapter configuration (BL-31).

    Controls the optional stamina-based retry wrapper and per-service-root
    token-bucket rate limiter. Disabled by default; callers opt in via
    ``RESTGDF_RESILIENCE_ENABLED=1`` or by constructing explicitly.
    """

    model_config = _FROZEN

    enabled: bool = False
    rate_per_service_root_per_second: float | None = Field(default=None, gt=0)
    respect_retry_after_max_s: float = Field(default=60.0, gt=0)
    fallback_retry_after_seconds: float = Field(default=5.0, gt=0)
    backend: str = "stamina"


_Caster = Callable[[str], Any]


def _parse_bool(raw: str) -> bool:
    s = raw.strip().lower()
    if s in {"1", "true", "yes", "on"}:
        return True
    if s in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"not a boolean: {raw!r}")


_NEW_ENV_SPEC: tuple[tuple[str, str, _Caster], ...] = (
    ("RESTGDF_TRANSPORT_VERIFY_SSL", "transport.verify_ssl", _parse_bool),
    ("RESTGDF_TRANSPORT_USER_AGENT", "transport.user_agent", str),
    ("RESTGDF_TIMEOUT_CONNECT_S", "timeout.connect_s", float),
    ("RESTGDF_TIMEOUT_READ_S", "timeout.read_s", float),
    ("RESTGDF_TIMEOUT_TOTAL_S", "timeout.total_s", float),
    ("RESTGDF_RETRY_ENABLED", "retry.enabled", _parse_bool),
    ("RESTGDF_RETRY_MAX_ATTEMPTS", "retry.max_attempts", int),
    ("RESTGDF_RETRY_MAX_DELAY_S", "retry.max_delay_s", float),
    ("RESTGDF_LIMITER_ENABLED", "limiter.enabled", _parse_bool),
    ("RESTGDF_LIMITER_RATE_PER_HOST", "limiter.rate_per_host", float),
    (
        "RESTGDF_CONCURRENCY_MAX_CONCURRENT_REQUESTS",
        "concurrency.max_concurrent_requests",
        int,
    ),
    ("RESTGDF_AUTH_TOKEN_URL", "auth.token_url", str),
    ("RESTGDF_AUTH_REFRESH_THRESHOLD_S", "auth.refresh_threshold_s", float),
    ("RESTGDF_TELEMETRY_ENABLED", "telemetry.enabled", _parse_bool),
    ("RESTGDF_TELEMETRY_SERVICE_NAME", "telemetry.service_name", str),
    ("RESTGDF_TELEMETRY_LOG_LEVEL", "telemetry.log_level", str),
    ("RESTGDF_RESILIENCE_ENABLED", "resilience.enabled", _parse_bool),
    (
        "RESTGDF_RESILIENCE_RATE_PER_SERVICE_ROOT_PER_SECOND",
        "resilience.rate_per_service_root_per_second",
        float,
    ),
    (
        "RESTGDF_RESILIENCE_RESPECT_RETRY_AFTER_MAX_S",
        "resilience.respect_retry_after_max_s",
        float,
    ),
    (
        "RESTGDF_RESILIENCE_FALLBACK_RETRY_AFTER_SECONDS",
        "resilience.fallback_retry_after_seconds",
        float,
    ),
    ("RESTGDF_RESILIENCE_BACKEND", "resilience.backend", str),
)


_DEPRECATED_ALIASES: tuple[tuple[str, str, str, _Caster], ...] = (
    (
        "RESTGDF_TIMEOUT_SECONDS",
        "RESTGDF_TIMEOUT_TOTAL_S",
        "timeout.total_s",
        float,
    ),
    ("RESTGDF_TOKEN_URL", "RESTGDF_AUTH_TOKEN_URL", "auth.token_url", str),
    (
        "RESTGDF_REFRESH_THRESHOLD",
        "RESTGDF_AUTH_REFRESH_THRESHOLD_S",
        "auth.refresh_threshold_s",
        float,
    ),
    (
        "RESTGDF_USER_AGENT",
        "RESTGDF_TRANSPORT_USER_AGENT",
        "transport.user_agent",
        str,
    ),
    (
        "RESTGDF_LOG_LEVEL",
        "RESTGDF_TELEMETRY_LOG_LEVEL",
        "telemetry.log_level",
        str,
    ),
    (
        "RESTGDF_MAX_CONCURRENT_REQUESTS",
        "RESTGDF_CONCURRENCY_MAX_CONCURRENT_REQUESTS",
        "concurrency.max_concurrent_requests",
        int,
    ),
)


class Config(BaseModel):
    """Aggregate of the eight sub-configs. Frozen.

    Use :func:`get_config` (process-cached) rather than instantiating directly
    in production code; direct instantiation is useful for tests.
    """

    model_config = _FROZEN

    transport: TransportConfig = Field(default_factory=TransportConfig)
    timeout: TimeoutConfig = Field(default_factory=TimeoutConfig)
    retry: RetryConfig = Field(default_factory=RetryConfig)
    limiter: LimiterConfig = Field(default_factory=LimiterConfig)
    concurrency: ConcurrencyConfig = Field(default_factory=ConcurrencyConfig)
    auth: AuthConfig = Field(default_factory=AuthConfig)
    telemetry: TelemetryConfig = Field(default_factory=TelemetryConfig)
    resilience: ResilienceConfig = Field(default_factory=ResilienceConfig)

    @classmethod
    def from_env(
        cls,
        env: Mapping[str, str] | None = None,
        *,
        _warn_stacklevel: int = 2,
    ) -> Config:
        """Build :class:`Config` from environment variables.

        Parameters
        ----------
        env
            Mapping of env-var name to value. Defaults to ``os.environ``.
            Pass an explicit mapping (including ``{}``) to bypass the real
            environment, primarily for tests.
        _warn_stacklevel
            Internal hook controlling the ``stacklevel`` passed to
            :func:`warnings.warn` for deprecated-alias warnings. Direct
            callers of ``Config.from_env`` get the default (``2``), which
            attributes the warning to the user's call site.
            :func:`get_config` overrides this to ``3`` so the warning
            surfaces past the cached accessor frame. Not part of the
            public API.

        Raises
        ------
        RestgdfResponseError
            If any ``RESTGDF_*`` env var contains a malformed value or fails
            pydantic validation. The original exception chains via
            ``__cause__``.
        """
        source: Mapping[str, str] = os.environ if env is None else env
        sub_kwargs: dict[str, dict[str, Any]] = {
            "transport": {},
            "timeout": {},
            "retry": {},
            "limiter": {},
            "concurrency": {},
            "auth": {},
            "telemetry": {},
            "resilience": {},
        }

        def _assign(dotted: str, value: Any) -> None:
            section, field_name = dotted.split(".", 1)
            sub_kwargs[section][field_name] = value

        def _coerce(env_key: str, dotted: str, caster: _Caster) -> None:
            raw = source.get(env_key)
            if raw is None:
                return
            try:
                _assign(dotted, caster(raw))
            except (TypeError, ValueError) as exc:
                raise RestgdfResponseError(
                    f"invalid value for {env_key}: {raw!r} ({exc})",
                    model_name=cls.__name__,
                    context=env_key,
                    raw=raw,
                ) from exc

        for env_key, dotted, caster in _NEW_ENV_SPEC:
            _coerce(env_key, dotted, caster)

        for old_key, new_key, dotted, caster in _DEPRECATED_ALIASES:
            if old_key not in source:
                continue
            if new_key in source:
                warnings.warn(
                    f"{old_key} is deprecated; {new_key} is set and "
                    f"takes precedence (old value ignored).",
                    DeprecationWarning,
                    stacklevel=_warn_stacklevel,
                )
                continue
            warnings.warn(
                f"{old_key} is deprecated; use {new_key} instead.",
                DeprecationWarning,
                stacklevel=_warn_stacklevel,
            )
            _coerce(old_key, dotted, caster)

        try:
            return cls(
                transport=TransportConfig(**sub_kwargs["transport"]),
                timeout=TimeoutConfig(**sub_kwargs["timeout"]),
                retry=RetryConfig(**sub_kwargs["retry"]),
                limiter=LimiterConfig(**sub_kwargs["limiter"]),
                concurrency=ConcurrencyConfig(**sub_kwargs["concurrency"]),
                auth=AuthConfig(**sub_kwargs["auth"]),
                telemetry=TelemetryConfig(**sub_kwargs["telemetry"]),
                resilience=ResilienceConfig(**sub_kwargs["resilience"]),
            )
        except ValidationError as exc:
            raise RestgdfResponseError(
                f"Config validation failed: {exc.errors()!r}",
                model_name=cls.__name__,
                context="Config.from_env",
                raw=dict(sub_kwargs),
            ) from exc


@functools.lru_cache(maxsize=1)
def get_config() -> Config:
    """Return the process-wide cached :class:`Config` instance.

    Deprecated-alias warnings emitted during env resolution attribute to the
    caller of :func:`get_config` (``stacklevel=3``: one extra frame past the
    :meth:`Config.from_env` default so the warning surfaces at user code).
    """
    return Config.from_env(_warn_stacklevel=3)


def reset_config_cache() -> None:
    """Clear the :func:`get_config` cache *and* the legacy Settings cache.

    Bidirectional cascade avoids stale Settings after env changes: callers
    that reset only the new Config cache still get a fresh Settings shim
    view on the next :func:`restgdf.get_settings` call.
    """
    get_config.cache_clear()
    from restgdf._models._settings import get_settings as _gs

    _gs.cache_clear()


__all__ = [
    "AuthConfig",
    "ConcurrencyConfig",
    "Config",
    "LimiterConfig",
    "ResilienceConfig",
    "RetryConfig",
    "TelemetryConfig",
    "TimeoutConfig",
    "TransportConfig",
    "get_config",
    "reset_config_cache",
]
