"""Layered runtime configuration for restgdf (phase-2a BL-18).

Eight frozen pydantic 2.x sub-configs mirror the plan-obs §3 taxonomy:
:class:`TransportConfig`, :class:`TimeoutConfig`, :class:`RetryConfig`,
:class:`LimiterConfig`, :class:`ConcurrencyConfig`, :class:`AuthConfig`,
:class:`TelemetryConfig`, :class:`ResilienceConfig`. The aggregate
:class:`Config` is resolved lazily via
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
from typing import Any, Literal
from collections.abc import Callable

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


class InertConfigWarning(UserWarning):
    """A ``RESTGDF_*`` env var is set but does not affect runtime.

    Emitted once (per :func:`Config.from_env` resolution) when a caller sets
    a validated-but-inert knob -- the **deprecated** ``RESTGDF_RETRY_*`` /
    ``RESTGDF_LIMITER_*`` values (superseded in 3.3 by the live
    ``RESTGDF_RESILIENCE_*`` knobs on :class:`ResilienceConfig`; see the
    deprecation notes on :class:`RetryConfig` / :class:`LimiterConfig`) or
    ``RESTGDF_AUTH_REFRESH_THRESHOLD_S`` (token sessions do not read
    ``AuthConfig``; see :class:`AuthConfig`). The value still validates into
    :class:`Config`, but nothing consumes it (the RETRY/LIMITER knobs are
    removed in 4.0). Silence it with
    ``warnings.filterwarnings("ignore", category=restgdf._config.InertConfigWarning)``.
    """


# ``RESTGDF_*`` env keys that validate into :class:`Config` but that no live
# code path reads (verified 2026-07-24: the resilience executor reads its
# retry/limiter policy from ``config.resilience`` (:class:`ResilienceConfig`)
# and never reads ``config.retry``/``config.limiter``; the ``RESTGDF_RETRY_*``
# / ``RESTGDF_LIMITER_*`` knobs are deprecated in 3.3 and superseded by the
# ``RESTGDF_RESILIENCE_*`` replacements. ``AuthConfig.refresh_threshold_s`` is
# surfaced only through the deprecated ``Settings`` shim, never applied to a
# token session). Kept intact as a back-compat seam (tests pin them); the
# deprecated RETRY/LIMITER knobs are removed in 4.0 (W2-13/AUTH-04).
_INERT_ENV_KEYS: tuple[str, ...] = (
    "RESTGDF_RETRY_ENABLED",
    "RESTGDF_RETRY_MAX_ATTEMPTS",
    "RESTGDF_RETRY_MAX_DELAY_S",
    "RESTGDF_LIMITER_ENABLED",
    "RESTGDF_LIMITER_RATE_PER_HOST",
    "RESTGDF_AUTH_REFRESH_THRESHOLD_S",
)

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
    """HTTP transport knobs (TLS, user agent).

    Single source of truth for the **library-owned data-request** transport.
    These two fields are the one place a caller sets the data-path TLS and
    User-Agent behavior. The application seams that carry them into requests
    -- the ``restgdf.utils._http`` request layer and the ``getgdf`` TLS
    connector -- are the *designated* consumers: they read from these fields
    (rather than any hardcoded value or separate flag) so a single change
    here governs the whole data path. Those seams own the wiring; this
    config only fixes where they read from.

    * ``verify_ssl`` is the authoritative TLS-verification flag for
      library-owned data-request sessions. It is deliberately **distinct**
      from
      :attr:`restgdf._models.credentials.TokenSessionConfig.verify_ssl`,
      which is an explicit per-session override applied to the
      ``/generateToken`` POST and token-attached data requests. The two are
      NOT defaulted from one another: ``TokenSessionConfig`` never implicitly
      reads ``get_config().transport.verify_ssl`` (that would make a
      session-scoped knob follow a process-wide singleton). To harmonize
      them, pass the same value to both explicitly.
    * ``user_agent`` is the source the data-path request headers default
      from. Do NOT re-introduce a hardcoded ``User-Agent`` at a leaf call
      site -- change the default here (or ``RESTGDF_TRANSPORT_USER_AGENT``)
      instead.
    """

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
    """Retry policy holder (validated but inert; see the deprecation note).

    .. deprecated:: 3.3
        ``max_attempts`` and ``max_delay_s`` are inert and superseded by the
        live :class:`ResilienceConfig` retry knobs -- ``max_attempts`` maps to
        ``ResilienceConfig.max_attempts`` and ``max_delay_s`` to
        ``ResilienceConfig.retry_budget_s`` (the total wall-clock budget). The
        resilience executor reads only :class:`ResilienceConfig`; these two
        fields (and their ``RESTGDF_RETRY_MAX_ATTEMPTS`` /
        ``RESTGDF_RETRY_MAX_DELAY_S`` env keys) validate but change nothing.
        They stay wired as a back-compat seam and emit
        :class:`InertConfigWarning` when set; both are removed in 4.0.
    """

    model_config = _FROZEN

    enabled: bool = False
    max_attempts: int = Field(default=5, ge=1)
    max_delay_s: float = Field(default=60.0, gt=0)


class LimiterConfig(BaseModel):
    """Rate-limiter configuration holder (validated but inert).

    .. deprecated:: 3.3
        ``rate_per_host`` is inert and superseded by the live
        :class:`ResilienceConfig` rate limiter: set
        ``ResilienceConfig.rate_per_service_root_per_second`` together with
        ``ResilienceConfig.limiter_key = "host"`` for per-host rate limiting.
        The resilience executor reads only :class:`ResilienceConfig`; this
        field (and its ``RESTGDF_LIMITER_RATE_PER_HOST`` env key) validates but
        changes nothing. It stays wired as a back-compat seam and emits
        :class:`InertConfigWarning` when set; it is removed in 4.0.
    """

    model_config = _FROZEN

    enabled: bool = False
    rate_per_host: float | None = Field(default=None, gt=0)


class ConcurrencyConfig(BaseModel):
    """Bounded-semaphore ceiling for top-level orchestration calls."""

    model_config = _FROZEN

    max_concurrent_requests: int = Field(default=8, ge=1)


class AuthConfig(BaseModel):
    """ArcGIS token-session defaults (validated ``RESTGDF_AUTH_*`` namespace).

    .. versionchanged:: 3.0
        Default *transport* flipped from ``"body"`` to ``"header"``; default
        *header_name* is ``"X-Esri-Authorization"``.  Pass
        ``allow_query_transport=True`` to enable ``transport="query"``.

    **Not auto-applied to token sessions (AUTH-04 / CONFIG-02).**
    ``AuthConfig`` is a *validated namespace* for the ``RESTGDF_AUTH_*``
    environment variables; it is **not** auto-applied to any
    :class:`~restgdf.utils.token.ArcGISTokenSession`. In particular the three
    refresh knobs -- ``refresh_threshold_s``, ``refresh_leeway_s`` and
    ``clock_skew_s`` -- are config *holders*, exactly like the
    :class:`RetryConfig`/``LimiterConfig`` inert notes above: reading them off
    ``get_config().auth`` changes nothing about a live session's refresh
    timing on its own. The library never constructs the token session for
    you, and ``ArcGISTokenSession.__post_init__`` deliberately never reads
    ``get_config()`` -- a process-wide singleton flip must not silently change
    transport/refresh timing for every session in the process.

    To make these values take effect, construct a
    :class:`~restgdf._models.credentials.TokenSessionConfig` explicitly and
    pass it to ``ArcGISTokenSession`` -- e.g. via the opt-in
    ``TokenSessionConfig.from_auth_config(get_config().auth)`` /
    ``ArcGISTokenSession.from_config(...)`` hand-off (W2-11). Only that
    explicit hand-off threads ``AuthConfig`` into a running session.

    Default split to be aware of: a bare ``TokenSessionConfig`` derives its
    refresh window from ``refresh_leeway_seconds (120) + clock_skew_seconds
    (30) = 150`` s, whereas a bare ``ArcGISTokenSession`` uses the dataclass
    default ``token_refresh_threshold = 60`` s. A caller migrating from the
    dataclass argument to a config-driven session should expect ``150`` s,
    not ``60`` s; the ``from_auth_config`` path is internally consistent.
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

    Controls the optional stamina-based retry wrapper and token-bucket rate
    limiter used by :class:`restgdf.resilience.ResilientSession`. Disabled by
    default; callers opt in via ``RESTGDF_RESILIENCE_ENABLED=1`` or by
    constructing explicitly. ``enabled`` is the **sole** gate for the retry
    executor -- the retry-tuning fields below never re-gate an
    already-enabled session; they only shape its behaviour.

    Rate-limit granularity (``limiter_key``)
    ----------------------------------------
    ``limiter_key`` selects the key the single token bucket (and the shared
    429 cooldown) is keyed on:

    * ``"service_root"`` (default, behaviour-preserving) -- one bucket per
      ArcGIS service root (truncated at ``FeatureServer``/``MapServer``/...),
      so ``rate_per_service_root_per_second`` is enforced *per service*.
    * ``"host"`` -- one bucket per ``scheme://host``, so the same rate is
      enforced across every service on that host. This is the polite default
      when many independent services sit behind one government host; the
      configured rate then applies **per host** rather than per service root.

    Both granularities share the one ``rate_per_service_root_per_second``
    value and one registry -- the field name is historical; read it as
    "the configured rate, enforced at ``limiter_key`` granularity". Sub-1.0
    rates (e.g. ``0.5`` req/s -- the natural polite setting) are valid.

    Retry attempts / backoff / budget
    ---------------------------------
    The stamina executor reads ``max_attempts``, ``retry_budget_s``,
    ``wait_initial_s``, ``wait_max_s`` and ``wait_jitter_s`` directly from this
    config (defaults preserve the historical hardcoded policy exactly). These
    supersede the inert :class:`RetryConfig` knobs (deprecated in 3.3).

    Budget / cooldown coherence (H1-N3)
    -----------------------------------
    A 429 ``Retry-After`` cooldown sleep happens *inside* a retried attempt and
    ``retry_budget_s`` is a **total** wall-clock budget, so in-attempt cooldown
    sleeps count against it: honouring a ``Retry-After`` at or above
    ``retry_budget_s`` collapses the whole retry loop to roughly a single
    cooldown cycle before giving up. ``respect_retry_after_max_s`` caps how
    long a single honoured ``Retry-After`` may be; setting it at or above
    ``retry_budget_s`` therefore lets one cooldown consume the entire budget.
    Keep ``respect_retry_after_max_s`` below ``retry_budget_s`` if you want
    more than one real retry after a 429 (the defaults are deliberately equal
    at ``60.0`` -- one honoured max-length cooldown, then give up).

    .. deprecated:: 3.3
        ``backend`` is dead config -- ``"stamina"`` is the only implementation
        and the executor never reads the field. Setting
        ``RESTGDF_RESILIENCE_BACKEND`` emits a :class:`DeprecationWarning`; the
        field stays reachable (default ``"stamina"``) for back-compat and is
        removed in 4.0.
    """

    model_config = _FROZEN

    enabled: bool = False
    rate_per_service_root_per_second: float | None = Field(default=None, gt=0)
    limiter_key: Literal["service_root", "host"] = "service_root"
    respect_retry_after_max_s: float = Field(default=60.0, gt=0)
    fallback_retry_after_seconds: float = Field(default=5.0, gt=0)
    max_attempts: int = Field(default=5, ge=1)
    retry_budget_s: float = Field(default=60.0, gt=0)
    wait_initial_s: float = Field(default=0.5, ge=0)
    wait_max_s: float = Field(default=10.0, gt=0)
    wait_jitter_s: float = Field(default=1.0, ge=0)
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
    ("RESTGDF_RESILIENCE_LIMITER_KEY", "resilience.limiter_key", str),
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
    ("RESTGDF_RESILIENCE_MAX_ATTEMPTS", "resilience.max_attempts", int),
    ("RESTGDF_RESILIENCE_RETRY_BUDGET_S", "resilience.retry_budget_s", float),
    ("RESTGDF_RESILIENCE_WAIT_INITIAL_S", "resilience.wait_initial_s", float),
    ("RESTGDF_RESILIENCE_WAIT_MAX_S", "resilience.wait_max_s", float),
    ("RESTGDF_RESILIENCE_WAIT_JITTER_S", "resilience.wait_jitter_s", float),
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

    **Not request-path-injectable (CONFIG-03).**
    A freshly built ``Config(...)`` instance is **test-only**: it is *not*
    threaded into the runtime request path. Every library consumer
    (``utils._http``, ``utils.getgdf``, ``utils.getinfo``, ``utils.crawl``,
    ``telemetry._spans``) resolves configuration through the no-arg
    process-global :func:`get_config`; there is no public API that accepts an
    explicit ``Config`` and honors it below the public constructor. Passing a
    ``Config`` instance somewhere and expecting it to override the process
    global would silently do nothing. To change resolved configuration, set
    the ``RESTGDF_*`` environment variables (then call
    ``reset_config_cache``) -- the single documented precedence is
    constructor/aiohttp kwargs > env vars > model defaults, resolved
    process-globally. The separate, intentionally session-scoped
    ``ArcGISTokenSession(config=...)`` / ``TokenSessionConfig`` injection is
    *not* a global ``Config`` override -- do not conflate the two.
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

        # R5: ``backend`` is dead config -- "stamina" is the only backend and
        # the resilience executor never reads the field. It shipped as a public
        # field in 3.2.0, so it cannot be removed in a minor; deprecate the
        # env-var path here (mirroring the _DEPRECATED_ALIASES precedent above)
        # and remove the field + this warning in 4.0. Field *construction* is
        # intentionally NOT deprecated -- Field(deprecated=True) warns on every
        # attribute read and would trip the restgdf.* DeprecationWarning
        # escalation (judge-R5 footgun note).
        if "RESTGDF_RESILIENCE_BACKEND" in source:
            warnings.warn(
                "RESTGDF_RESILIENCE_BACKEND is deprecated and has no effect "
                "('stamina' is the only backend); it is removed in 4.0.",
                DeprecationWarning,
                stacklevel=_warn_stacklevel,
            )

        # W2-13 (TRANSPORT-01 / AUTH-04): a validated-but-inert knob is a
        # silent lie -- the caller set it expecting an effect it never has.
        # Emit ONE consolidated warning naming every inert key that is set.
        # ``get_config`` is LRU-cached size-1, so in production this resolves
        # (and warns) at most once per process; the knobs + env aliases stay
        # wired (tests pin them). Real executor/session wiring is deferred.
        inert_present = [key for key in _INERT_ENV_KEYS if key in source]
        if inert_present:
            warnings.warn(
                "These RESTGDF_* environment variables are set but are inert -- "
                "they validate into Config yet do not affect runtime behavior: "
                f"{', '.join(sorted(inert_present))}. The RESTGDF_RETRY_* and "
                "RESTGDF_LIMITER_* knobs are deprecated (removed in 4.0); use "
                "their live RESTGDF_RESILIENCE_* replacements instead -- "
                "RESTGDF_RESILIENCE_MAX_ATTEMPTS, "
                "RESTGDF_RESILIENCE_RETRY_BUDGET_S, and "
                "RESTGDF_RESILIENCE_RATE_PER_SERVICE_ROOT_PER_SECOND with "
                "RESTGDF_RESILIENCE_LIMITER_KEY=host. "
                "RESTGDF_AUTH_REFRESH_THRESHOLD_S is still not read by token "
                "sessions (construct TokenSessionConfig explicitly). "
                "See AUTH-04 / TRANSPORT-01.",
                InertConfigWarning,
                stacklevel=_warn_stacklevel,
            )

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
    "InertConfigWarning",
    "LimiterConfig",
    "ResilienceConfig",
    "RetryConfig",
    "TelemetryConfig",
    "TimeoutConfig",
    "TransportConfig",
    "get_config",
    "reset_config_cache",
]
