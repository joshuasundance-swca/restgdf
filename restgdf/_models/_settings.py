"""Process-level runtime settings for restgdf (**deprecated shim**).

Since phase-2a BL-18 this module is a *backwards-compatibility shim* over
:mod:`restgdf._config`. The flat :class:`Settings` model and
:func:`get_settings` remain for existing callers but:

* :func:`get_settings` emits a :class:`DeprecationWarning` on first use and
  constructs its return value from :func:`restgdf.get_config` — the new
  source of truth.
* Deprecated flat env-var names (``RESTGDF_TIMEOUT_SECONDS``,
  ``RESTGDF_TOKEN_URL``, ``RESTGDF_REFRESH_THRESHOLD``, ``RESTGDF_USER_AGENT``,
  ``RESTGDF_LOG_LEVEL``, ``RESTGDF_MAX_CONCURRENT_REQUESTS``) are honoured by
  :class:`restgdf.Config` with their own ``DeprecationWarning``s — see
  ``MIGRATION.md`` ``phase-2a``.

Prefer :func:`restgdf.get_config` / :class:`restgdf.Config` in new code. The
``Settings`` class and ``get_settings`` function will be removed no earlier
than restgdf 3.0.

``Settings.from_env`` is **not** deprecated at the method level — it is the
legacy direct path and keeps its original semantics (reads the flat env-var
set, no alias translation, no deprecation warnings). Callers that invoke
``Settings.from_env()`` directly therefore do **not** receive the new-wins
alias semantics; use :class:`restgdf.Config.from_env` for that contract.
"""

from __future__ import annotations

import functools
import os
import re
import warnings
from collections.abc import Mapping
from importlib.metadata import PackageNotFoundError, version as package_version
from pathlib import Path
from typing import Any, Callable

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
)

from restgdf._models._errors import RestgdfResponseError


_VERSION_RE = re.compile(r"""^__version__\s*=\s*["']([^"']+)["']\s*$""", re.MULTILINE)


@functools.lru_cache(maxsize=1)
def _restgdf_version() -> str:
    """Resolve the installed/package version without importing ``restgdf``."""
    try:
        return package_version("restgdf")
    except PackageNotFoundError:
        init_py = Path(__file__).resolve().parents[1] / "__init__.py"
        match = _VERSION_RE.search(init_py.read_text(encoding="utf-8"))
        if match is None:  # pragma: no cover - defensive fallback
            raise RuntimeError("Could not determine restgdf version")
        return match.group(1)


def _default_user_agent() -> str:
    """Return ``"restgdf/<version>"`` without forcing ``restgdf`` at import."""
    return f"restgdf/{_restgdf_version()}"


_VALID_LOG_LEVELS = frozenset(
    {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG", "NOTSET"},
)


class Settings(BaseModel):
    """Validated runtime configuration for restgdf.

    The model is **frozen**: treat a ``Settings`` instance as immutable. To
    change runtime configuration, mutate the environment (or pass an explicit
    mapping), then call :func:`reset_settings_cache` and re-fetch via
    :func:`get_settings`.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    chunk_size: int = Field(
        default=100,
        gt=0,
        description=(
            "Default batch size for object-id chunking in feature queries. "
            "ArcGIS services advertise their own ``maxRecordCount``; this "
            "value is the library-level fallback."
        ),
    )
    timeout_seconds: float = Field(
        default=30.0,
        gt=0,
        description="Default HTTP request timeout (seconds).",
    )
    user_agent: str = Field(
        default_factory=_default_user_agent,
        min_length=1,
        description="User-Agent header sent on ArcGIS REST requests.",
    )
    log_level: str = Field(
        default="WARNING",
        description=(
            "Log level applied to the ``restgdf.schema_drift`` logger when "
            "consumers opt in."
        ),
    )
    token_url: str = Field(
        default="https://www.arcgis.com/sharing/rest/generateToken",
        description="Default ArcGIS ``generateToken`` endpoint.",
    )
    refresh_threshold_seconds: int = Field(
        default=60,
        ge=0,
        description=(
            "Default token-refresh threshold for "
            ":class:`~restgdf.utils.token.ArcGISTokenSession`."
        ),
    )
    max_concurrent_requests: int = Field(
        default=8,
        ge=1,
        description=(
            "Upper bound on the number of in-flight HTTP requests per "
            "top-level restgdf orchestration call (``service_metadata``, "
            "``fetch_all_data``, ``safe_crawl``). The default of 8 matches "
            "aiohttp's ``TCPConnector`` default connection-pool size; "
            "operators can raise or lower it via "
            "``RESTGDF_MAX_CONCURRENT_REQUESTS``. Saturation semantics = "
            "wait (plan.md §3c R-19)."
        ),
    )
    default_headers_json: str | None = Field(
        default=None,
        description=(
            "Optional JSON-encoded dict merged into default request "
            "headers. Consumers parse this string at the HTTP boundary."
        ),
    )

    @field_validator("log_level")
    @classmethod
    def _normalize_log_level(cls, value: str) -> str:
        upper = value.upper()
        if upper not in _VALID_LOG_LEVELS:
            raise ValueError(
                f"log_level must be one of {sorted(_VALID_LOG_LEVELS)!r}",
            )
        return upper

    @field_validator("token_url")
    @classmethod
    def _check_token_url_scheme(cls, value: str) -> str:
        if not value.startswith(("http://", "https://")):
            raise ValueError(
                "token_url must start with 'http://' or 'https://'",
            )
        return value

    @classmethod
    def from_env(
        cls,
        env: Mapping[str, str] | None = None,
    ) -> Settings:
        """Build :class:`Settings` from environment variables.

        Parameters
        ----------
        env
            Mapping of env-var name to value. Defaults to ``os.environ``.
            Pass an explicit dict (including ``{}``) to bypass the real
            environment — primarily useful for tests.

        Raises
        ------
        RestgdfResponseError
            If any ``RESTGDF_*`` variable contains a malformed value (bad
            cast or failed pydantic validation). The original exception is
            chained via ``__cause__``.
        """
        source: Mapping[str, str] = os.environ if env is None else env
        kwargs: dict[str, Any] = {}

        def _coerce(
            env_key: str,
            field_name: str,
            caster: Callable[[str], Any],
        ) -> None:
            raw = source.get(env_key)
            if raw is None:
                return
            try:
                kwargs[field_name] = caster(raw)
            except (TypeError, ValueError) as exc:
                raise RestgdfResponseError(
                    f"invalid value for {env_key}: {raw!r} ({exc})",
                    model_name=cls.__name__,
                    context=env_key,
                    raw=raw,
                ) from exc

        _coerce("RESTGDF_CHUNK_SIZE", "chunk_size", int)
        _coerce("RESTGDF_TIMEOUT_SECONDS", "timeout_seconds", float)
        _coerce("RESTGDF_REFRESH_THRESHOLD", "refresh_threshold_seconds", int)
        _coerce(
            "RESTGDF_MAX_CONCURRENT_REQUESTS",
            "max_concurrent_requests",
            int,
        )

        for env_key, field_name in (
            ("RESTGDF_USER_AGENT", "user_agent"),
            ("RESTGDF_LOG_LEVEL", "log_level"),
            ("RESTGDF_TOKEN_URL", "token_url"),
            ("RESTGDF_DEFAULT_HEADERS_JSON", "default_headers_json"),
        ):
            raw = source.get(env_key)
            if raw is not None:
                kwargs[field_name] = raw

        try:
            return cls(**kwargs)
        except ValidationError as exc:
            raise RestgdfResponseError(
                f"Settings validation failed: {exc.errors()!r}",
                model_name=cls.__name__,
                context="Settings.from_env",
                raw=dict(kwargs),
            ) from exc


@functools.lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide cached :class:`Settings` instance.

    .. deprecated:: phase-2a
       Use ``restgdf.get_config()`` and ``restgdf.Config``. This shim
       constructs a :class:`Settings` from the cached ``Config`` and
       emits a single :class:`DeprecationWarning` per process.
    """
    warnings.warn(
        "restgdf.get_settings() / restgdf.Settings are deprecated; "
        "use restgdf.get_config() / restgdf.Config instead. See "
        "MIGRATION.md phase-2a.",
        DeprecationWarning,
        stacklevel=2,
    )
    from restgdf._config import get_config

    cfg = get_config()
    shim_kwargs: dict[str, Any] = {
        "timeout_seconds": cfg.timeout.total_s,
        "user_agent": cfg.transport.user_agent,
        "log_level": cfg.telemetry.log_level,
        "token_url": (
            cfg.auth.token_url
            if cfg.auth.token_url is not None
            else Settings.model_fields["token_url"].get_default()
        ),
        "refresh_threshold_seconds": int(cfg.auth.refresh_threshold_s),
        "max_concurrent_requests": cfg.concurrency.max_concurrent_requests,
    }
    raw_chunk = os.environ.get("RESTGDF_CHUNK_SIZE")
    if raw_chunk is not None:
        try:
            shim_kwargs["chunk_size"] = int(raw_chunk)
        except ValueError as exc:
            raise RestgdfResponseError(
                f"invalid value for RESTGDF_CHUNK_SIZE: {raw_chunk!r} ({exc})",
                model_name="Settings",
                context="RESTGDF_CHUNK_SIZE",
                raw=raw_chunk,
            ) from exc
    raw_hdr = os.environ.get("RESTGDF_DEFAULT_HEADERS_JSON")
    if raw_hdr is not None:
        shim_kwargs["default_headers_json"] = raw_hdr
    try:
        return Settings(**shim_kwargs)
    except ValidationError as exc:
        raise RestgdfResponseError(
            f"Settings shim validation failed: {exc.errors()!r}",
            model_name="Settings",
            context="get_settings",
            raw=dict(shim_kwargs),
        ) from exc


def reset_settings_cache() -> None:
    """Clear the :func:`get_settings` cache *and* the new Config cache.

    Bidirectional cascade with ``restgdf.reset_config_cache`` so tests
    and long-lived processes can refresh all configuration with a single
    call regardless of which accessor they use.
    """
    get_settings.cache_clear()
    from restgdf._config import get_config as _gc

    _gc.cache_clear()


__all__ = [
    "Settings",
    "get_settings",
    "reset_settings_cache",
]
