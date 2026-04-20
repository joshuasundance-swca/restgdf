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
  ``token_url``/``refresh_threshold``/``verify_ssl`` knobs so validation
  logic is not scattered across the dataclass.

Both models are ``StrictModel`` subclasses — invalid config is an
operator-visible bug, not schema drift.
"""

from __future__ import annotations


from pydantic import Field, SecretStr, field_validator

from restgdf._models._drift import StrictModel


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
    """

    token_url: str
    credentials: AGOLUserPass
    refresh_threshold_seconds: int = 60
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


__all__ = ["AGOLUserPass", "TokenSessionConfig"]
