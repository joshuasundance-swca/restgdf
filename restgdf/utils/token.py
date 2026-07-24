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
import importlib
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import aiohttp

from restgdf._logging import get_logger
from restgdf._models._drift import _parse_response
from restgdf._models.credentials import AGOLUserPass, TokenSessionConfig
from restgdf._models.responses import TokenResponse
from restgdf.utils._http import default_timeout

from restgdf._compat import _warn_deprecated
from restgdf.errors import (
    AuthNotAttachedError,
    AuthenticationError,
    InvalidCredentialsError,
    RestgdfError,
    RestgdfResponseError,
    TokenExpiredError,
    TokenRefreshFailedError,
)

from pydantic import SecretStr

if TYPE_CHECKING:
    from restgdf._config import AuthConfig

_auth_logger = get_logger("auth")

_MAX_TOKEN_RETRIES: int = 3  # Max /generateToken POST attempts

_BASE_BACKOFF_S: float = 0.5  # Initial retry sleep; doubles each attempt

_RETRYABLE_ERRORS = (OSError, asyncio.TimeoutError, ConnectionError)


class _LazyRequestsModule:
    """Load ``requests`` only when the deprecated sync helper is touched."""

    def _module(self):
        return importlib.import_module("requests")

    def __getattr__(self, name: str):
        return getattr(self._module(), name)

    def __setattr__(self, name: str, value) -> None:
        setattr(self._module(), name, value)

    def __delattr__(self, name: str) -> None:
        delattr(self._module(), name)


requests = _LazyRequestsModule()


def _utc_now() -> datetime.datetime:
    """Return the current tz-aware UTC datetime.

    Exposed as a module-level function so tests can monkeypatch it
    to control wall-clock time without freezing the real clock.
    """
    return datetime.datetime.now(datetime.UTC)


__all__ = [
    "AGOLUserPass",
    "ArcGISTokenSession",
    "TokenSessionConfig",
    "get_token",
]


def get_token(username: str, password: str | SecretStr) -> dict:
    """Synchronously request an ArcGIS Online token.

    .. deprecated:: 3.0
        Use :class:`ArcGISTokenSession` instead for async token lifecycle.
    """
    _warn_deprecated(
        "get_token() is deprecated; use ArcGISTokenSession for async token management.",
    )
    url = "https://www.arcgis.com/sharing/rest/generateToken"
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    pw = password.get_secret_value() if isinstance(password, SecretStr) else password
    data = {
        "f": "json",
        "client": "requestip",
        "username": username,
        "password": pw,
        "expiration": 60,
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

    ``__post_init__`` never reads the process-global
    ``get_config``: a plain
    ``ArcGISTokenSession(session, credentials)`` keeps its dataclass
    defaults (e.g. ``token_refresh_threshold=60``). The
    ``AuthConfig`` refresh knobs are config
    holders, not auto-applied; opt in explicitly with
    :meth:`from_config` when you want the ``RESTGDF_AUTH_*`` namespace to
    drive a session's refresh timing / transport.
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
                    "referer": self.credentials.referer,
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

    @classmethod
    def from_config(
        cls,
        session: aiohttp.ClientSession,
        credentials: AGOLUserPass,
        *,
        config: AuthConfig | None = None,
    ) -> ArcGISTokenSession:
        """Build a token session from an ``AuthConfig`` (opt-in).

        W3-3 (CONFIG-02, hybrid decision): this classmethod is the ONLY
        sanctioned path by which an ``AuthConfig`` namespace flows into a
        session. It is strictly opt-in — nothing constructs a session this
        way implicitly, and ``__post_init__`` never reaches into the
        process-global config.

        When *config* is ``None`` the process-global ``get_config().auth`` is
        read, but **only here at call time**, never at import time. The
        ``AuthConfig`` refresh knobs are projected onto a validated
        :class:`~restgdf._models.credentials.TokenSessionConfig` via
        :meth:`~restgdf._models.credentials.TokenSessionConfig.from_auth_config`,
        so the effective refresh window is ``refresh_leeway_s + clock_skew_s``
        (default ``150``), not the bare dataclass default of ``60``.
        """
        if config is None:
            from restgdf._config import get_config

            config = get_config().auth
        token_session_config = TokenSessionConfig.from_auth_config(config, credentials)
        return cls(session=session, config=token_session_config)

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
        if self.config is not None:
            referer = self.config.referer
        else:
            referer = getattr(self.credentials, "referer", None)
        payload = {
            "f": "json",
            "client": "referer" if referer else "requestip",
            "username": self.credentials.username,
            # Unwrap SecretStr only at the HTTP-POST boundary.
            "password": self.credentials.password.get_secret_value(),
            "expiration": self.credentials.expiration,
        }
        if referer:
            payload["referer"] = referer
        return payload

    @property
    def expires_at(self) -> datetime.datetime | None:
        """Return the token expiry as a tz-aware UTC :class:`~datetime.datetime`.

        ArcGIS returns ``expires`` in either seconds or milliseconds
        since the Unix epoch — values above ``1e11`` are treated as
        milliseconds and divided by 1000.  Returns ``None`` when no
        expiry is set.
        """
        if self.expires is None:
            return None
        epoch = self.expires / 1000 if self.expires > 1e11 else self.expires
        return datetime.datetime.fromtimestamp(epoch, tz=datetime.UTC)

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
    def _referer(self) -> str | None:
        """Return the referer this session's token is bound to, if any.

        Resolved with the same precedence as
        :attr:`token_request_payload` (config referer wins over the
        credential's referer) so a request-time ``Referer`` header matches
        the referer sent at mint time. ``None`` for a ``client="requestip"``
        (non-referer) token or a credential-less session.
        """
        if self.config is not None:
            return self.config.referer
        return getattr(self.credentials, "referer", None)

    @property
    def auth_headers(self) -> dict[str, str]:
        """Return authentication headers with the token if available.

        For a **referer-bound** session (``AGOLUserPass(referer=...)`` /
        ``TokenSessionConfig.referer``) a matching ``Referer`` header is
        attached so the ``client="referer"`` token is honoured on data
        requests, not only at mint time (#175 NOTE-1). No ``Referer`` is
        attached for a ``client="requestip"`` token (no referer leak).
        """
        headers: dict[str, str] = {}
        if self.token and self._transport == "header":
            headers[self._header_name] = f"Bearer {self.token}"
        referer = self._referer
        if referer:
            headers["Referer"] = referer
        return headers

    def update_headers(self, headers: dict | None = None) -> dict:
        """Return headers merged with the active token."""
        request_headers = dict(headers or {})
        request_headers.update(self.auth_headers)
        return request_headers

    def update_dict(self, input_dict: dict | None = None) -> dict:
        """Return a request payload/query dict merged with the active token."""
        output_dict = dict(input_dict or {})
        if (
            self.token
            and self._transport in ("body", "query")
            and "token" not in output_dict
        ):
            output_dict["token"] = self.token
        return output_dict

    async def update_token(self) -> None:
        """Update the token by making a request to the token URL.

        The ``/generateToken`` payload is validated against
        :class:`~restgdf._models.responses.TokenResponse` (strict tier)
        so malformed/error envelopes raise
        :class:`~restgdf._models.RestgdfResponseError` instead of
        ``KeyError`` deep in caller code paths.

        Retries up to ``_MAX_TOKEN_RETRIES`` times with exponential
        backoff (base ``_BASE_BACKOFF_S``) on transient network
        errors.  Deterministic errors (bad credentials, content-type
        mismatches, validation failures) are re-raised immediately.
        After exhausting retries, raises
        :class:`~restgdf.errors.TokenRefreshFailedError`.

        Emits structured log events:
        * ``auth.refresh.start`` — before the POST
        * ``auth.refresh.success`` — after successful token update
        * ``auth.refresh.failure`` — on any exception
        """
        last_exc: Exception | None = None
        for attempt in range(1, _MAX_TOKEN_RETRIES + 1):
            _auth_logger.debug(
                "auth.refresh.start url=%s attempt=%d/%d",
                self.token_url,
                attempt,
                _MAX_TOKEN_RETRIES,
            )
            try:
                async with self.session.post(
                    self.token_url,
                    data=self.token_request_payload,
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                    timeout=default_timeout(),
                    ssl=self.verify_ssl,
                ) as resp:
                    # W2-2 (AUTH-02/ERRTAX-01): a true-HTTP 4xx from
                    # /generateToken must not escape as a raw
                    # aiohttp.ClientResponseError. Map credential-rejection
                    # statuses to InvalidCredentialsError and every other
                    # non-2xx to RestgdfResponseError, both under the
                    # RestgdfError umbrella, chained from the aiohttp error.
                    # Scope this to the raise_for_status edge only: the
                    # HTTP-200 JSON-error-envelope path is left to the strict
                    # TokenResponse tier below (raise_for_status no-ops on 200).
                    try:
                        resp.raise_for_status()
                    except aiohttp.ClientResponseError as exc:
                        if exc.status in (400, 401, 403):
                            raise InvalidCredentialsError(
                                f"{exc.status} credential rejection from "
                                f"{self.token_url}",
                                context=self.token_url,
                                cause=exc,
                            ) from exc
                        raise RestgdfResponseError(
                            f"{exc.status} non-2xx from {self.token_url}",
                            context=self.token_url,
                            status_code=exc.status,
                        ) from exc
                    data = await resp.json()
                envelope = _parse_response(TokenResponse, data, context=self.token_url)
                self.token = envelope.token
                self.expires = envelope.expires
                _auth_logger.debug("auth.refresh.success url=%s", self.token_url)
                return
            except RestgdfError:
                # W2-3 (ERRTAX-02): restgdf's own deterministic errors
                # co-inherit OSError via PermissionError
                # (AuthenticationError -> PermissionError -> OSError). Without
                # this guard placed BEFORE `except _RETRYABLE_ERRORS`, the
                # None-credentials AuthenticationError from
                # token_request_payload, the W2-2 InvalidCredentialsError, and
                # the TokenResponse parse RestgdfResponseError would all be
                # swept into the OSError retry bucket and mislabeled
                # TokenRefreshFailedError. The match is by real exception
                # instance (MRO), never by class name. Nothing raised inside
                # the try that is a RestgdfError is a retryable transient, so
                # it propagates immediately (no backoff). It is still a refresh
                # failure, so it emits the documented auth.refresh.failure event.
                _auth_logger.debug(
                    "auth.refresh.failure url=%s attempt=%d/%d",
                    self.token_url,
                    attempt,
                    _MAX_TOKEN_RETRIES,
                )
                raise
            except _RETRYABLE_ERRORS as exc:
                last_exc = exc
                _auth_logger.debug(
                    "auth.refresh.failure url=%s attempt=%d/%d",
                    self.token_url,
                    attempt,
                    _MAX_TOKEN_RETRIES,
                )
                if attempt < _MAX_TOKEN_RETRIES:
                    delay = _BASE_BACKOFF_S * (2 ** (attempt - 1))
                    await asyncio.sleep(delay)
            except Exception:
                _auth_logger.debug(
                    "auth.refresh.failure url=%s attempt=%d/%d",
                    self.token_url,
                    attempt,
                    _MAX_TOKEN_RETRIES,
                )
                raise

        raise TokenRefreshFailedError(
            f"Failed to refresh token after {_MAX_TOKEN_RETRIES} attempts",
            context=self.token_url,
            attempt=_MAX_TOKEN_RETRIES,
            cause=last_exc,
        )

    def token_needs_update(self) -> bool:
        """Check if the token needs to be updated."""
        if self.credentials is None:
            return False
        if not self.token or not self.expires:
            return True
        ea = self.expires_at
        if ea is None:
            return True
        return (ea - _utc_now()).total_seconds() < self.token_refresh_threshold

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

        W2-5 (ERRTAX-03) — **deferred, documented HTTP-status-only scope.**
        Detection reads ``resp.status`` only; the common ArcGIS in-body
        envelope shape (HTTP 200 carrying ``{"error": {"code": 498|499}}``)
        is intentionally NOT inspected here. Reading the body in this retry
        helper would consume the response stream that every downstream caller
        re-reads, so in-body detection cannot live at this seam — it requires
        lifting the refresh/retry decision into the parse layer
        (``_models/_drift._parse_response``, W5-owned). This is a low-severity
        resilience/ergonomics enhancement, not a correctness gap: an in-body
        499 already surfaces as :class:`~restgdf.errors.RestgdfResponseError`
        via the strict parse tier, so no data is silently lost; only callers
        catching :class:`~restgdf.errors.TokenExpiredError` /
        :class:`~restgdf.errors.AuthNotAttachedError` *specifically* miss the
        in-body shape. **Owner:** a future reactive-auth-detection design pass
        coordinated with the ``_drift.py`` owner. **Trigger to revisit:** a
        maintainer go decision to change the documented status-only contract
        (CHANGELOG BL-11 / MIGRATION R-14 / ARCHITECTURE "HTTP 498/499"), or
        field reports of ArcGIS servers returning 498/499 as HTTP-200
        envelopes causing silent auth failures for such callers.
        """
        await self.update_token_if_needed()

        has_explicit_token = "token" in (payload or {})
        request_headers = (
            self.update_headers(headers)
            if not has_explicit_token
            else dict(headers or {})
        )
        request_payload = self.update_dict(payload)
        kwargs.setdefault("timeout", default_timeout())
        # W2-10 (CONFIG-01/AUTH-03): forward the token session's own
        # verify_ssl to token-attached data requests, mirroring the
        # /generateToken POST. setdefault so a caller-supplied ssl= wins;
        # it also carries into the 498-retry call below (shared **kwargs).
        kwargs.setdefault("ssl", self.verify_ssl)

        session_method = getattr(self.session, method)
        # W2-4 (ASYNC-01): snapshot the token BEFORE issuing the request so
        # concurrent 498s collapse onto a single refresh (see the 498 branch).
        tok_before = self.token
        resp = await session_method(
            url,
            **{payload_key: request_payload},
            headers=request_headers,
            **kwargs,
        )

        status = getattr(resp, "status", 200)

        if status == 499:
            raise AuthNotAttachedError(
                f"499 Token Required from {url}",
                context="response_status",
            )

        if status == 498:
            # Single-flight refresh, then retry exactly once. Under N
            # concurrent 498s every task serializes on the lock; only the
            # first (whose snapshot still matches self.token) mints. Later
            # winners observe self.token != tok_before and skip the redundant
            # /generateToken, then retry with the freshly minted token. This
            # mirrors the proactive update_token_if_needed double-check; do
            # NOT gate on token_needs_update() -- after a server-side
            # invalidation the local token still looks valid.
            if self._refresh_lock is None:
                self._refresh_lock = asyncio.Lock()
            async with self._refresh_lock:
                if self.token == tok_before:
                    await self.update_token()

            # Rebuild auth for the retry.
            request_headers = (
                self.update_headers(headers)
                if not has_explicit_token
                else dict(headers or {})
            )
            request_payload = self.update_dict(payload)
            resp = await session_method(
                url,
                **{payload_key: request_payload},
                headers=request_headers,
                **kwargs,
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
            "get",
            url,
            "params",
            params,
            headers,
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
        return await self._call_with_auth_retry(
            "post",
            url,
            "data",
            data,
            headers,
            **kwargs,
        )

    @property
    def closed(self) -> bool:
        """Return ``True`` when the underlying :class:`aiohttp.ClientSession` is closed.

        Delegating lets :class:`ArcGISTokenSession` satisfy the
        internal ``AsyncHTTPSession`` transport Protocol uniformly with
        ``aiohttp.ClientSession`` (R-71).
        """
        return bool(self.session.closed)

    async def close(self) -> None:
        """Close the underlying :class:`aiohttp.ClientSession`.

        Mirrors :meth:`aiohttp.ClientSession.close` so token sessions and
        raw aiohttp sessions are interchangeable through the
        internal ``AsyncHTTPSession`` transport Protocol. Idempotent:
        closing an already-closed session is a no-op.
        """
        if not self.session.closed:
            await self.session.close()

    async def __aenter__(self) -> ArcGISTokenSession:
        """Enter the runtime context related to this object."""
        await self.update_token_if_needed()
        return self

    async def __aexit__(self, exc_type, exc_value, traceback) -> None:
        """Exit the runtime context related to this object."""
        return None
