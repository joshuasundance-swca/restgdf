"""Process-level runtime settings for restgdf.

A single :class:`Settings` pydantic model centralizes every runtime knob
(HTTP timeouts, user-agent, chunk size, token-session defaults, drift-logger
level). The library does **not** depend on ``pydantic-settings`` — that
package requires Python 3.10+ and restgdf supports 3.9. Instead,
:meth:`Settings.from_env` reads ``os.environ`` (or a caller-supplied mapping,
for tests) and safely coerces each value.

Values are resolved lazily via :func:`get_settings`, which caches a single
``Settings`` instance per process. Tests and long-lived processes that need
to reconfigure at runtime call :func:`reset_settings_cache` to drop the
cached instance; the next :func:`get_settings` call re-reads the environment.

This module only provides the infrastructure. Consumer migration (wiring
``get_settings()`` into the HTTP helpers and token session) happens in
later slices so it does not conflict with parallel work.
"""

from __future__ import annotations

import functools
import os
import re
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
    """Return the process-wide cached :class:`Settings` instance."""
    return Settings.from_env()


def reset_settings_cache() -> None:
    """Clear the :func:`get_settings` cache.

    Useful for tests (force a re-read of ``os.environ``) and for
    long-running processes that change configuration at runtime.
    """
    get_settings.cache_clear()


__all__ = [
    "Settings",
    "get_settings",
    "reset_settings_cache",
]
