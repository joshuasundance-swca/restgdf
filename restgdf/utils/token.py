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

import asyncio
import datetime
from dataclasses import dataclass, field

import aiohttp
import requests

from restgdf._models._drift import _parse_response
from restgdf._models.credentials import AGOLUserPass, TokenSessionConfig
from restgdf._models.responses import TokenResponse
from restgdf.utils._http import default_timeout

from restgdf.errors import (
    AuthNotAttachedError,
    AuthenticationError,
    TokenExpiredError,
)

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
    _refresh_lock: asyncio.Lock | None = field(
        default=None,
        init=False,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        if self.config is not None:
            # Caller supplied a validated config -- respect it and sync the
            # legacy dataclass mirror so ``token_needs_update`` stays in step.
            self.credentials = self.config.credentials
            self.token_url = self.config.token_url
            self.verify_ssl = self.config.verify_ssl
            self.token_refresh_threshold = (
                self.config.refresh_leeway_seconds + self.config.clock_skew_seconds
            )
            return
        if self.credentials is not None:
            # Derive the split fields from the dataclass-level
            # ``token_refresh_threshold`` using the same rule the
            # ``TokenSessionConfig`` model-validator applies for the
            # deprecated alias (skew capped at 30, leeway gets the
            # remainder). Passing the new fields directly avoids firing
            # the alias ``DeprecationWarning`` on every construction.
            total = int(self.token_refresh_threshold)
            skew = min(30, total) if total >= 0 else 0
            leeway = max(0, total - skew)
            self.config = _parse_response(
                TokenSessionConfig,
                {
                    "token_url": self.token_url,
                    "credentials": self.credentials,
                    "refresh_leeway_seconds": leeway,
                    "clock_skew_seconds": skew,
                    "verify_ssl": self.verify_ssl,
                },
                context="ArcGISTokenSession",
            )
            self.credentials = self.config.credentials
            self.token_refresh_threshold = (
                self.config.refresh_leeway_seconds + self.config.clock_skew_seconds
            )

    @property
    def token_request_payload(self) -> dict:
        """Return the payload for the token request."""
        if self.credentials is None:
            raise AuthenticationError(
                "Credentials are required to generate a token.",
                model_name="ArcGISTokenSession",
                context="token_request_payload",
                raw=None,
            )
        return {
            "f": "json",
            "client": "requestip",
            "username": self.credentials.username,
            # Unwrap SecretStr only at the HTTP-POST boundary.
            "password": self.credentials.password.get_secret_value(),
        }

    @property
    def _transport(self) -> str:
        """Return the wire transport mode: ``'header'``, ``'body'``, or ``'query'``."""
        if self.config is not None and hasattr(self.config, "transport"):
            return self.config.transport
        return "header"

    @property
    def _header_name(self) -> str:
        """Return the header key for header-mode transport."""
        if self.config is not None and hasattr(self.config, "header_name"):
            return self.config.header_name
        return "X-Esri-Authorization"

    @property
    def auth_headers(self) -> dict[str, str]:
        """Return authentication headers with the token if available."""
        headers: dict[str, str] = {}
        if self.token and self._transport == "header":
            headers[self._header_name] = f"Bearer {self.token}"
        return headers

    def update_headers(self, headers: dict | None = None) -> dict:
        """Return headers merged with the active token."""
        request_headers = dict(headers or {})
        request_headers.update(self.auth_headers)
        return request_headers

    def update_dict(self, input_dict: dict | None = None) -> dict:
        """Return a request payload/query dict merged with the active token."""
        output_dict = dict(input_dict or {})
        if self.token and self._transport in ("body", "query") and "token" not in output_dict:
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
            timeout=default_timeout(),
            ssl=self.verify_ssl,
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
        """Ensure the token is valid and refresh if necessary.

        BL-03: concurrent callers racing on an expired token collapse onto
        a single ``/generateToken`` POST via a lazily-initialized
        per-instance :class:`asyncio.Lock` with a double-checked
        :meth:`token_needs_update` inside the lock (plan.md §3c R-18,
        kickoff phase-1a §10.4). The lock is created here — not in
        ``__post_init__`` — so instances constructed outside a running
        event loop (e.g. at import time or inside a sync test) never
        trigger ``DeprecationWarning: There is no current event loop``.
        """
        if not self.token_needs_update():
            return
        if self._refresh_lock is None:
            self._refresh_lock = asyncio.Lock()
        async with self._refresh_lock:
            if self.token_needs_update():
                await self.update_token()

    async def _call_with_auth_retry(
        self,
        method: str,
        url: str,
        payload_key: str,
        payload: dict | None,
        headers: dict | None,
        **kwargs,
    ) -> aiohttp.ClientResponse:
        """Execute *method* with reactive 498/499 handling.

        * **498** (Invalid Token): single-flight refresh via ``_refresh_lock``,
          then retry exactly once. If the retry also returns 498,
          raise :class:`TokenExpiredError`.
        * **499** (Token Required): raise :class:`AuthNotAttachedError`
          immediately — no refresh, no retry.
        """
        await self.update_token_if_needed()

        has_explicit_token = "token" in (payload or {})
        request_headers = (
            self.update_headers(headers) if not has_explicit_token
            else dict(headers or {})
        )
        request_payload = self.update_dict(payload)
        kwargs.setdefault("timeout", default_timeout())

        session_method = getattr(self.session, method)
        resp = await session_method(
            url, **{payload_key: request_payload}, headers=request_headers, **kwargs,
        )

        status = getattr(resp, "status", 200)

        if status == 499:
            raise AuthNotAttachedError(
                f"499 Token Required from {url}",
                context="response_status",
            )

        if status == 498:
            # Single-flight refresh, then retry exactly once.
            if self._refresh_lock is None:
                self._refresh_lock = asyncio.Lock()
            async with self._refresh_lock:
                await self.update_token()

            # Rebuild auth for the retry.
            request_headers = (
                self.update_headers(headers) if not has_explicit_token
                else dict(headers or {})
            )
            request_payload = self.update_dict(payload)
            resp = await session_method(
                url, **{payload_key: request_payload},
                headers=request_headers, **kwargs,
            )
            if getattr(resp, "status", 200) == 498:
                raise TokenExpiredError(
                    f"Token still invalid after refresh for {url}",
                    context="retry_exhausted",
                    attempt=2,
                )

        return resp

    async def get(
        self,
        url: str,
        params: dict | None = None,
        headers: dict | None = None,
        **kwargs,
    ) -> aiohttp.ClientResponse:
        """Make a GET request to the specified URL with the token."""
        return await self._call_with_auth_retry(
            "get", url, "params", params, headers, **kwargs,
        )

    async def post(
        self,
        url: str,
        data: dict | None = None,
        headers: dict | None = None,
        **kwargs,
    ) -> aiohttp.ClientResponse:
        """Make a POST request to the specified URL with the token."""
        return await self._call_with_auth_retry(
            "post", url, "data", data, headers, **kwargs,
        )

    async def __aenter__(self) -> ArcGISTokenSession:
        """Enter the runtime context related to this object."""
        await self.update_token_if_needed()
        return self

    async def __aexit__(self, exc_type, exc_value, traceback) -> None:
        """Exit the runtime context related to this object."""
        return None
