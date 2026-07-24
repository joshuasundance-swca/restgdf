"""Credentials and token-session configuration models.

Two pydantic models live here:

* :class:`AGOLUserPass` — ArcGIS Online / Enterprise username + password
  credentials. The password field is a :class:`pydantic.SecretStr` so it
  is redacted from ``str()`` / ``repr()`` / logs; the literal value is
  available via ``creds.password.get_secret_value()`` and is only
  dereferenced at the HTTP-POST boundary in
  :mod:`restgdf.utils.token`.

* :class:`TokenSessionConfig` — validated configuration for
  :class:`restgdf.utils.token.ArcGISTokenSession`. Centralizes the
  ``token_url``/``refresh_leeway_seconds``/``clock_skew_seconds``/
  ``verify_ssl`` knobs so validation logic is not scattered across the
  dataclass.

Both models are ``StrictModel`` subclasses — invalid config is an
operator-visible bug, not schema drift.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from pydantic import Field, SecretStr, field_validator, model_validator

from restgdf._compat import _warn_deprecated
from restgdf._models._drift import StrictModel

if TYPE_CHECKING:
    from restgdf._config import AuthConfig


class AGOLUserPass(StrictModel):
    """ArcGIS Online / Enterprise credentials used to mint tokens.

    ``password`` is stored as :class:`pydantic.SecretStr`. Call
    ``creds.password.get_secret_value()`` only at the HTTP-POST
    boundary; never store or log the unwrapped value.
    """

    username: str = Field(..., min_length=1)
    password: SecretStr
    referer: str | None = None
    expiration: int = 60  # minutes; ArcGIS ``generateToken`` default


class TokenSessionConfig(StrictModel):
    """Validated configuration for :class:`ArcGISTokenSession`.

    ``token_url`` is intentionally a plain :class:`str` with a custom
    validator rather than :class:`pydantic.AnyHttpUrl`. ArcGIS Enterprise
    deployments commonly run plain HTTP on internal networks, and
    ``AnyHttpUrl`` normalizes/rejects real-world URLs (for example it
    appends trailing slashes and may reject edge cases). Accepting any
    ``http://`` or ``https://`` string matches the behavior ArcGIS
    clients need.

    Refresh semantics (BL-04 / R-36, R-37):
      * ``refresh_leeway_seconds`` (default ``120``) — how far in
        advance of the token's expiry the session eagerly refreshes.
      * ``clock_skew_seconds`` (default ``30``, capped at ``30`` when
        derived from the legacy alias) — extra padding for client /
        server clock drift.

    ``refresh_threshold_seconds`` is retained as a
    deprecation-warning alias. Reads return
    ``refresh_leeway_seconds + clock_skew_seconds``; writes via the
    constructor kwarg split the supplied total into
    ``clock_skew_seconds = min(30, total)`` and
    ``refresh_leeway_seconds = total - clock_skew_seconds``.

    The ``AuthConfig`` refresh knobs
    (``refresh_leeway_s``/``clock_skew_s``) are **config holders, never
    auto-applied to a session**. Opt in explicitly via
    ``from_auth_config`` (or :meth:`ArcGISTokenSession.from_config`);
    the library never constructs a token session from the process-global
    config on its own.
    """

    token_url: str
    credentials: AGOLUserPass
    transport: Literal["header", "body", "query"] = "header"
    header_name: str = Field(default="X-Esri-Authorization", min_length=1)
    referer: str | None = None
    token: SecretStr | None = None
    refresh_leeway_seconds: int = Field(default=120, ge=0)
    clock_skew_seconds: int = Field(default=30, ge=0)
    verify_ssl: bool = True

    @field_validator("token_url")
    @classmethod
    def _check_token_url_scheme(cls, value: str) -> str:
        if not isinstance(value, str) or not value.startswith(
            ("http://", "https://"),
        ):
            raise ValueError(
                "token_url must start with 'http://' or 'https://' "
                "(ArcGIS Enterprise frequently uses http on internal networks)",
            )
        return value

    @model_validator(mode="before")
    @classmethod
    def _translate_legacy_refresh_threshold(cls, data: object) -> object:
        """Translate ``refresh_threshold_seconds=N`` into the new field pair.

        ``StrictModel`` is configured with ``extra="ignore"``, so unknown
        keys are silently dropped during normal validation. This
        validator intercepts ``refresh_threshold_seconds`` *before* that
        filtering so the legacy alias keeps working and emits a
        ``DeprecationWarning`` via :func:`restgdf._compat._warn_deprecated`.
        """
        if not isinstance(data, dict):
            return data
        if "refresh_threshold_seconds" not in data:
            return data
        total = data.pop("refresh_threshold_seconds")
        _warn_deprecated(
            "`TokenSessionConfig.refresh_threshold_seconds` is deprecated; "
            "set `refresh_leeway_seconds` and `clock_skew_seconds` "
            "explicitly instead. The alias will be removed in a future "
            "release.",
        )
        if not isinstance(total, int) or isinstance(total, bool):
            # Let pydantic surface a clear type error by leaving the
            # translated fields for the field validators to reject.
            data.setdefault("refresh_leeway_seconds", total)
            return data
        skew = min(30, total)
        leeway = total - skew
        data.setdefault("clock_skew_seconds", skew)
        data.setdefault("refresh_leeway_seconds", leeway)
        return data

    @classmethod
    def from_auth_config(
        cls,
        auth_config: AuthConfig,
        credentials: AGOLUserPass,
    ) -> TokenSessionConfig:
        """Project an ``AuthConfig`` onto a session config (opt-in).

        W2-11 (AUTH-04/CONFIG-02): ``AuthConfig`` is a validated namespace for
        the ``RESTGDF_AUTH_*`` env vars and is **never** auto-applied to a
        session. This factory is the explicit opt-in bridge: it threads
        *auth_config*'s ``transport``/``header_name``/``referer``/``token_url``
        and its ``refresh_leeway_s``/``clock_skew_s`` refresh knobs onto a
        validated :class:`TokenSessionConfig`, pairing them with the
        *credentials* the caller supplies (``AuthConfig`` carries no
        :class:`AGOLUserPass`).

        ``token_url`` falls back to the ArcGIS Online default when the
        ``AuthConfig`` leaves it unset; ``referer`` prefers the ``AuthConfig``
        value, then the credential's own referer. The resulting effective
        refresh window is ``refresh_leeway_seconds + clock_skew_seconds``
        (default ``120 + 30 = 150``), reconciling the split with the bare
        ``ArcGISTokenSession`` dataclass default of ``60``.
        """
        token_url = (
            auth_config.token_url or "https://www.arcgis.com/sharing/rest/generateToken"
        )
        referer = auth_config.referer or credentials.referer
        return cls(
            token_url=token_url,
            credentials=credentials,
            transport=auth_config.transport,
            header_name=auth_config.header_name,
            referer=referer,
            refresh_leeway_seconds=int(auth_config.refresh_leeway_s),
            clock_skew_seconds=int(auth_config.clock_skew_s),
        )

    @property
    def refresh_threshold_seconds(self) -> int:
        """Return the legacy threshold sum (``leeway + skew``) and emit a ``DeprecationWarning``."""
        _warn_deprecated(
            "`TokenSessionConfig.refresh_threshold_seconds` is deprecated; "
            "read `refresh_leeway_seconds` and `clock_skew_seconds` "
            "directly. The alias will be removed in a future release.",
            stacklevel=3,
        )
        return self.refresh_leeway_seconds + self.clock_skew_seconds


__all__ = ["AGOLUserPass", "TokenSessionConfig"]
