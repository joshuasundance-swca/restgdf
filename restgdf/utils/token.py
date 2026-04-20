"""Token-session helpers for ArcGIS Online / Enterprise.

The :class:`AGOLUserPass` and :class:`TokenSessionConfig` models live in
:mod:`restgdf._models.credentials`. They are re-exported here for
backward compatibility with ``from restgdf.utils.token import
AGOLUserPass`` and with the public ``from restgdf import AGOLUserPass``
surface documented in the README. The legacy frozen dataclass
``AGOLUserPass`` was migrated to a pydantic ``StrictModel`` in v2.0.0;
the import path is unchanged but the constructor is keyword-only.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field

import aiohttp
import requests

from restgdf._models._drift import _parse_response
from restgdf._models.credentials import AGOLUserPass, TokenSessionConfig
from restgdf._models.responses import TokenResponse

__all__ = [
    "AGOLUserPass",
    "ArcGISTokenSession",
    "TokenSessionConfig",
    "get_token",
]


def get_token(username: str, password: str) -> dict:
    """Synchronously request an ArcGIS Online token."""
    url = "https://www.arcgis.com/sharing/rest/generateToken"
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    data = {
        "f": "json",
        "client": "requestip",
        "username": username,
        "password": password,
    }
    return requests.post(url, headers=headers, data=data, timeout=30).json()


@dataclass
class ArcGISTokenSession:
    """Wrap an aiohttp session with ArcGIS token refresh behavior.

    Construction knobs (``token_url``, ``token_refresh_threshold``,
    ``credentials``) are validated via
    :class:`~restgdf._models.credentials.TokenSessionConfig` in
    :meth:`__post_init__` so a bogus scheme or zero-length username
    fails fast with :class:`~restgdf._models.RestgdfResponseError`
    rather than surfacing as a 401 or an ``aiohttp`` error deep in
    the request path.
    """

    session: aiohttp.ClientSession
    credentials: AGOLUserPass | None = None
    token_url: str = "https://www.arcgis.com/sharing/rest/generateToken"
    token_refresh_threshold: int = 60
    token: str | None = None
    expires: int | float | None = None
    verify_ssl: bool = True
    config: TokenSessionConfig | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if self.credentials is not None:
            # Validate config via TokenSessionConfig. Pass the already-
            # validated credentials instance directly; pydantic accepts
            # a model instance for a model-typed field without re-
            # validating the SecretStr password.
            self.config = _parse_response(
                TokenSessionConfig,
                {
                    "token_url": self.token_url,
                    "credentials": self.credentials,
                    "refresh_threshold_seconds": self.token_refresh_threshold,
                    "verify_ssl": self.verify_ssl,
                },
                context="ArcGISTokenSession",
            )
            self.credentials = self.config.credentials

    @property
    def token_request_payload(self) -> dict:
        """Return the payload for the token request."""
        if self.credentials is None:
            raise ValueError("Credentials are required to generate a token.")
        return {
            "f": "json",
            "client": "requestip",
            "username": self.credentials.username,
            # Unwrap SecretStr only at the HTTP-POST boundary.
            "password": self.credentials.password.get_secret_value(),
        }

    @property
    def auth_headers(self) -> dict[str, str]:
        """Return authentication headers with the token if available."""
        headers: dict[str, str] = {}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def update_headers(self, headers: dict | None = None) -> dict:
        """Return headers merged with the active token."""
        request_headers = dict(headers or {})
        request_headers.update(self.auth_headers)
        return request_headers

    def update_dict(self, input_dict: dict | None = None) -> dict:
        """Return a request payload/query dict merged with the active token."""
        output_dict = dict(input_dict or {})
        if self.token and "token" not in output_dict:
            output_dict["token"] = self.token
        return output_dict

    async def update_token(self) -> None:
        """Update the token by making a request to the token URL.

        The ``/generateToken`` payload is validated against
        :class:`~restgdf._models.responses.TokenResponse` (strict tier)
        so malformed/error envelopes raise
        :class:`~restgdf._models.RestgdfResponseError` instead of
        ``KeyError`` deep in caller code paths.
        """
        async with self.session.post(
            self.token_url,
            data=self.token_request_payload,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        ) as resp:
            resp.raise_for_status()
            data = await resp.json()
        envelope = _parse_response(TokenResponse, data, context=self.token_url)
        self.token = envelope.token
        self.expires = envelope.expires

    def token_needs_update(self) -> bool:
        """Check if the token needs to be updated."""
        if self.credentials is None:
            return False
        if not self.token or not self.expires:
            return True
        expires_at = self.expires / 1000 if self.expires > 1e11 else self.expires
        expires_dt = datetime.datetime.fromtimestamp(
            expires_at,
            tz=datetime.timezone.utc,
        )
        now_dt = datetime.datetime.now(datetime.timezone.utc)
        return (expires_dt - now_dt).total_seconds() < self.token_refresh_threshold

    async def update_token_if_needed(self) -> None:
        """Ensure the token is valid and refresh if necessary."""
        if self.token_needs_update():
            await self.update_token()

    async def get(
        self,
        url: str,
        params: dict | None = None,
        headers: dict | None = None,
        **kwargs,
    ) -> aiohttp.ClientResponse:
        """Make a GET request to the specified URL with the token."""
        await self.update_token_if_needed()
        request_headers = (
            self.update_headers(
                headers,
            )
            if "token" not in (params or {})
            else dict(headers or {})
        )
        request_params = self.update_dict(params)
        return await self.session.get(
            url,
            params=request_params,
            headers=request_headers,
            **kwargs,
        )

    async def post(
        self,
        url: str,
        data: dict | None = None,
        headers: dict | None = None,
        **kwargs,
    ) -> aiohttp.ClientResponse:
        """Make a POST request to the specified URL with the token."""
        await self.update_token_if_needed()
        request_headers = (
            self.update_headers(
                headers,
            )
            if "token" not in (data or {})
            else dict(headers or {})
        )
        request_data = self.update_dict(data)
        return await self.session.post(
            url,
            data=request_data,
            headers=request_headers,
            **kwargs,
        )

    async def __aenter__(self) -> ArcGISTokenSession:
        """Enter the runtime context related to this object."""
        await self.update_token_if_needed()
        return self

    async def __aexit__(self, exc_type, exc_value, traceback) -> None:
        """Exit the runtime context related to this object."""
        return None
