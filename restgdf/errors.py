"""Canonical exception taxonomy for restgdf 3.0.

This module defines the public exception hierarchy used by every public
entry point in ``restgdf``. All domain-specific exceptions derive from
:class:`RestgdfError` so callers can catch "any restgdf failure" with a
single ``except RestgdfError`` block while still being able to discriminate
between transport, schema, auth, pagination, configuration, and conversion
failures via the more specific subclasses.

Several classes multi-inherit from a builtin exception in addition to their
restgdf-specific parent. This is deliberate and preserves backward-compat:

* ``ConfigurationError(RestgdfError, ValueError)`` keeps
  ``except ValueError`` callers working while restgdf 3.x stabilizes (R-09).
* ``OptionalDependencyError(ConfigurationError, ModuleNotFoundError)``
  keeps ``except ImportError`` / ``except ModuleNotFoundError`` working
  when optional pandas/geopandas/pyogrio dependencies are missing.
* ``RestgdfResponseError(RestgdfError, ValueError)`` keeps the 2.x
  ``except ValueError`` contract around typed response validation.
* ``PaginationError(ArcGISServiceError, IndexError)`` preserves the 2.x
  "looks like an IndexError" contract around cursor exhaustion.
* ``AuthenticationError(RestgdfResponseError, PermissionError)`` lets
  callers treat auth failures as ``PermissionError`` when appropriate.
* ``RestgdfTimeoutError(TransportError, TimeoutError)`` keeps
  ``except TimeoutError`` callers working on request timeouts without
  shadowing the builtin ``TimeoutError`` symbol.

Hierarchy::

    RestgdfError(Exception)
    +-- ConfigurationError(RestgdfError, ValueError)
    |   +-- OptionalDependencyError(ConfigurationError, ModuleNotFoundError)
    +-- RestgdfResponseError(RestgdfError, ValueError)
    |   +-- SchemaValidationError(RestgdfResponseError)
    |   +-- ArcGISServiceError(RestgdfResponseError)
    |   |   +-- PaginationError(ArcGISServiceError, IndexError)
    |   +-- AuthenticationError(RestgdfResponseError, PermissionError)
    |       +-- InvalidCredentialsError(AuthenticationError)
    |       +-- TokenExpiredError(AuthenticationError)
    |       +-- TokenRequiredError(AuthenticationError)
    |       +-- TokenRefreshFailedError(AuthenticationError)
    |       +-- AuthNotAttachedError(AuthenticationError)
    +-- TransportError(RestgdfError)
    |   +-- RestgdfTimeoutError(TransportError, TimeoutError)
    |   +-- RateLimitError(TransportError)
    +-- OutputConversionError(RestgdfError)
"""

from __future__ import annotations

from typing import Any


class RestgdfError(Exception):
    """Base class for every exception raised by ``restgdf``."""


class ConfigurationError(RestgdfError, ValueError):
    """Raised when restgdf configuration (env vars, Settings, kwargs) is invalid.

    Multi-inherits :class:`ValueError` through 3.x so existing
    ``except ValueError`` callers continue to catch misconfiguration. The
    ``ValueError`` base will be dropped in 3.1+.
    """


class OptionalDependencyError(ConfigurationError, ModuleNotFoundError):
    """Raised when an optional dependency (pandas/geopandas/pyogrio) is absent.

    Multi-inherits :class:`ModuleNotFoundError` so existing
    ``except ImportError`` / ``except ModuleNotFoundError`` call sites keep
    working when ``restgdf[geo]`` is not installed.
    """


class RestgdfResponseError(RestgdfError, ValueError):
    """Raised when validated ArcGIS response handling must fail fast.

    Attributes
    ----------
    model_name
        The pydantic model class name associated with the failed parse (for
        example ``"CountResponse"`` or ``"LayerMetadata"``).
    context
        A short identifier describing *where* the response came from
        (for example the request URL or a helper name). Used by operators
        triaging ArcGIS vendor variance.
    raw
        The raw JSON-decoded payload that failed validation. Kept on the
        exception so callers can log or re-raise without re-reading the
        response body.
    """

    def __init__(
        self,
        message: str,
        *,
        model_name: str = "",
        context: str = "",
        raw: Any = None,
        url: str | None = None,
        status_code: int | None = None,
        request_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.model_name = model_name
        self.context = context
        self.raw = raw
        self.url = url
        self.status_code = status_code
        self.request_id = request_id


class SchemaValidationError(RestgdfResponseError):
    """Raised when an ArcGIS response envelope fails schema validation.

    Does **not** multi-inherit :class:`IndexError`: R-02 explicitly forbids
    the transitional ``SchemaValidationError(IndexError, ...)`` shim that
    earlier drafts of the plan proposed.
    """


class ArcGISServiceError(RestgdfResponseError):
    """Raised when the ArcGIS service returns an explicit ``{"error": ...}`` envelope."""


class PaginationError(ArcGISServiceError, IndexError):
    """Raised when cursor-based pagination cannot advance or exceeds limits.

    Multi-inherits :class:`IndexError` so legacy call sites that used
    ``except IndexError`` around pagination exhaustion keep working.

    Attributes
    ----------
    batch_index
        The zero-based batch index at which pagination failed, if known.
    page_size
        The page size in effect when pagination failed, if known.
    """

    def __init__(
        self,
        *args: Any,
        batch_index: int | None = None,
        page_size: int | None = None,
    ) -> None:
        # Bypass the kwarg-only signature on RestgdfResponseError; pagination
        # failures do not carry pydantic model/context/raw metadata.
        Exception.__init__(self, *args)
        self.batch_index = batch_index
        self.page_size = page_size


class AuthenticationError(RestgdfResponseError, PermissionError):
    """Raised when ArcGIS auth (token, creds, scope) is invalid or expired.

    Multi-inherits :class:`PermissionError` so ``except PermissionError``
    in application code can treat restgdf auth failures uniformly with
    local-filesystem permission failures.
    """


def _redact_secret_str(value: object) -> str:
    """Return ``'**********'`` for SecretStr values, ``str(value)`` otherwise."""
    # Avoid importing pydantic at module level just for this guard.
    cls_name = type(value).__name__
    if cls_name == "SecretStr":
        return "**********"
    return str(value)


class _AuthSubtypeBase(AuthenticationError):
    """Internal base for auth subtypes carrying ``context``, ``attempt``, ``cause``.

    All five public auth subtypes below inherit this mixin.  ``__repr__``
    and ``__str__`` redact any :class:`pydantic.SecretStr`-wrapped value
    in *cause* so credential material never leaks to logs / tracebacks.
    """

    def __init__(
        self,
        message: str,
        *,
        context: str | None = None,
        attempt: int | None = None,
        cause: BaseException | None = None,
        model_name: str = "AuthenticationError",
        raw: Any = None,
    ) -> None:
        super().__init__(
            message,
            model_name=model_name,
            context=context or "",
            raw=raw,
        )
        self.context: str = context or ""
        self.attempt = attempt
        self.cause = cause
        if cause is not None and isinstance(cause, BaseException):
            self.__cause__ = cause

    def __str__(self) -> str:
        parts = [super(Exception, self).__str__()]
        if self.context:
            parts.append(f"context={self.context!r}")
        if self.attempt is not None:
            parts.append(f"attempt={self.attempt}")
        if self.cause is not None:
            parts.append(f"cause={_redact_secret_str(self.cause)}")
        return " | ".join(parts)

    def __repr__(self) -> str:
        cls = type(self).__name__
        cause_repr = _redact_secret_str(self.cause) if self.cause is not None else None
        return (
            f"{cls}(context={self.context!r}, "
            f"attempt={self.attempt!r}, cause={cause_repr!r})"
        )


class InvalidCredentialsError(_AuthSubtypeBase):
    """Raised on 400 / bad credentials from ``/generateToken``.

    Inherits :class:`AuthenticationError` → :class:`PermissionError`.
    """


class TokenExpiredError(_AuthSubtypeBase):
    """Raised when ArcGIS returns error code **498** (Invalid Token).

    Attributes
    ----------
    code : int
        Always ``498``.
    """

    def __init__(
        self,
        message: str = "Token expired (Esri 498)",
        *,
        code: int = 498,
        context: str | None = None,
        attempt: int | None = None,
        cause: BaseException | None = None,
    ) -> None:
        super().__init__(
            message,
            context=context,
            attempt=attempt,
            cause=cause,
        )
        self.code = code


class TokenRequiredError(_AuthSubtypeBase):
    """Raised when ArcGIS returns error code **499** (Token Required).

    Semantically: the service demands a token but the request did not
    carry one (or the wrong transport was chosen).
    """


class TokenRefreshFailedError(_AuthSubtypeBase):
    """Raised after the bounded-retry ladder for ``/generateToken`` is exhausted.

    Attributes
    ----------
    attempt : int | None
        The final attempt number at which the refresh was abandoned.
    """


class AuthNotAttachedError(_AuthSubtypeBase):
    """Raised when a 499 is observed — the library did not attach auth to the request.

    Per R-14 no retry is attempted; the error propagates immediately to
    the caller. This is semantically distinct from :class:`TokenExpiredError`
    (498) which *does* trigger a single-flight refresh.
    """


class TransportError(RestgdfError):
    """Raised for network/HTTP transport-layer failures (connection, DNS, ...).

    Attributes
    ----------
    url
        The URL that was being requested when the failure occurred.
    status_code
        The HTTP status code, if one was received before the transport
        failure. ``None`` for pre-connect failures (DNS, refused, …).
    """

    def __init__(
        self,
        *args: Any,
        url: str | None = None,
        status_code: int | None = None,
    ) -> None:
        super().__init__(*args)
        self.url = url
        self.status_code = status_code


class RestgdfTimeoutError(TransportError, TimeoutError):
    """Raised when a request times out.

    Named ``RestgdfTimeoutError`` (not ``TimeoutError``) to avoid shadowing
    the builtin. Multi-inherits :class:`TimeoutError` so
    ``except TimeoutError`` callers continue to match.

    Attributes
    ----------
    timeout_kind
        One of ``"total"``, ``"connect"``, or ``"read"``, indicating which
        timeout budget was exceeded. ``None`` when unknown.
    """

    def __init__(
        self,
        *args: Any,
        url: str | None = None,
        status_code: int | None = None,
        timeout_kind: str | None = None,
    ) -> None:
        super().__init__(*args, url=url, status_code=status_code)
        self.timeout_kind = timeout_kind


class RateLimitError(TransportError):
    """Raised when the ArcGIS service signals a rate limit / throttle.

    Attributes
    ----------
    retry_after
        Optional seconds to wait before retrying, parsed from a
        ``Retry-After`` header or service envelope. ``None`` when the
        service did not supply a hint.
    """

    def __init__(
        self,
        *args: Any,
        retry_after: float | None = None,
        url: str | None = None,
        status_code: int | None = None,
    ) -> None:
        super().__init__(*args, url=url, status_code=status_code)
        self.retry_after = retry_after


class OutputConversionError(RestgdfError):
    """Raised when converting validated ArcGIS data to a GeoDataFrame / DataFrame fails."""


__all__ = [
    "ArcGISServiceError",
    "AuthNotAttachedError",
    "AuthenticationError",
    "ConfigurationError",
    "InvalidCredentialsError",
    "OptionalDependencyError",
    "OutputConversionError",
    "PaginationError",
    "RateLimitError",
    "RestgdfError",
    "RestgdfResponseError",
    "RestgdfTimeoutError",
    "SchemaValidationError",
    "TokenExpiredError",
    "TokenRefreshFailedError",
    "TokenRequiredError",
    "TransportError",
]
