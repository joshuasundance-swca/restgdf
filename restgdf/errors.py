"""Canonical exception taxonomy for restgdf 3.0.

This module defines the public exception hierarchy used by every public
entry point in :mod:`restgdf`. All domain-specific exceptions derive from
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
    +-- TransportError(RestgdfError)
    |   +-- RestgdfTimeoutError(TransportError, TimeoutError)
    |   +-- RateLimitError(TransportError)
    +-- OutputConversionError(RestgdfError)
"""

from __future__ import annotations

from typing import Any


class RestgdfError(Exception):
    """Base class for every exception raised by :mod:`restgdf`."""


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
        model_name: str,
        context: str,
        raw: Any,
    ) -> None:
        super().__init__(message)
        self.model_name = model_name
        self.context = context
        self.raw = raw


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


class TransportError(RestgdfError):
    """Raised for network/HTTP transport-layer failures (connection, DNS, ...)."""


class RestgdfTimeoutError(TransportError, TimeoutError):
    """Raised when a request times out.

    Named ``RestgdfTimeoutError`` (not ``TimeoutError``) to avoid shadowing
    the builtin. Multi-inherits :class:`TimeoutError` so
    ``except TimeoutError`` callers continue to match.
    """


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
    ) -> None:
        super().__init__(*args)
        self.retry_after = retry_after


class OutputConversionError(RestgdfError):
    """Raised when converting validated ArcGIS data to a GeoDataFrame / DataFrame fails."""


__all__ = [
    "ArcGISServiceError",
    "AuthenticationError",
    "ConfigurationError",
    "OptionalDependencyError",
    "OutputConversionError",
    "PaginationError",
    "RateLimitError",
    "RestgdfError",
    "RestgdfResponseError",
    "RestgdfTimeoutError",
    "SchemaValidationError",
    "TransportError",
]
