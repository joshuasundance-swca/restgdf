"""Logging scaffolding for restgdf.

Public contract:
  * ``restgdf.schema_drift`` logger name is a 2.x public contract (tests assert via caplog).
  * ``get_drift_logger`` stays as the historical accessor (thin alias for
    ``get_logger("schema_drift")``).
  * ``get_logger(suffix)`` is the library-wide factory (BL-25). Suffix must be
    ``""`` or one of :data:`LOGGER_SUFFIXES`; unknown suffixes raise ``ValueError``.
  * ``build_log_extra(...)`` builds the standard ``extra=`` envelope (BL-26).

All loggers created via ``get_logger`` have a ``NullHandler`` attached so library
consumers opt in to output.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Final
from urllib.parse import urlsplit, urlunsplit

SCHEMA_DRIFT_LOGGER_NAME: Final[str] = "restgdf.schema_drift"

LOGGER_SUFFIXES: Final[tuple[str, ...]] = (
    "transport",
    "retry",
    "limiter",
    "concurrency",
    "auth",
    "pagination",
    "normalization",
    "schema_drift",
)

LOG_EXTRA_KEYS: Final[tuple[str, ...]] = (
    "service_root",
    "layer_id",
    "operation",
    "page_index",
    "page_size",
    "retry_attempt",
    "retry_delay_s",
    "limiter_wait_s",
    "timeout_category",
    "result_count",
    "exception_type",
)

_TOKEN_PARAM_RE: Final[re.Pattern[str]] = re.compile(
    r"([?&])(token)=[^&#]*",
    flags=re.IGNORECASE,
)
_SCRUB_PLACEHOLDER: Final[str] = "***"


def get_logger(suffix: str = "") -> logging.Logger:
    """Return a named restgdf child logger with a ``NullHandler`` attached.

    ``suffix`` must be either ``""`` (the ``restgdf`` root logger) or one of
    :data:`LOGGER_SUFFIXES`. Unknown suffixes raise :class:`ValueError` so new
    loggers require an explicit ledger entry.

    Handler attachment is idempotent: repeated calls do not stack handlers.
    """
    if not isinstance(suffix, str):
        raise TypeError(
            f"restgdf logger suffix must be str, got {type(suffix).__name__}",
        )
    if suffix != "" and suffix not in LOGGER_SUFFIXES:
        raise ValueError(
            f"unknown restgdf logger suffix {suffix!r}; "
            f"allowed: '' or one of {sorted(LOGGER_SUFFIXES)}",
        )
    name = f"restgdf.{suffix}" if suffix else "restgdf"
    logger = logging.getLogger(name)
    if not any(isinstance(h, logging.NullHandler) for h in logger.handlers):
        logger.addHandler(logging.NullHandler())
    _ensure_span_context_filter(logger)
    return logger


def get_drift_logger() -> logging.Logger:
    """Return the restgdf schema-drift logger.

    Equivalent to :func:`get_logger` with ``suffix="schema_drift"``. The logger
    name ``restgdf.schema_drift`` is a 2.x public contract.
    """
    return get_logger("schema_drift")


def _scrub_url(url: str | None) -> str | None:
    """Return ``url`` with ``token=...`` query-parameter values replaced by ``***``.

    Byte-stable: non-token parts of the URL (scheme, netloc, path, fragment, and
    non-token query params) are returned unchanged. Case-insensitive match on the
    parameter key. ``None`` and empty strings are returned unchanged.
    """
    if not url:
        return url
    parts = urlsplit(url)
    if not parts.query:
        return url
    scrubbed_query = _TOKEN_PARAM_RE.sub(
        lambda m: f"{m.group(1)}{m.group(2)}={_SCRUB_PLACEHOLDER}",
        "?" + parts.query,
    )
    if scrubbed_query.startswith("?"):
        scrubbed_query = scrubbed_query[1:]
    return urlunsplit(parts._replace(query=scrubbed_query))


def build_log_extra(
    *,
    service_root: str | None = None,
    layer_id: int | None = None,
    operation: str | None = None,
    page_index: int | None = None,
    page_size: int | None = None,
    retry_attempt: int | None = None,
    retry_delay_s: float | None = None,
    limiter_wait_s: float | None = None,
    timeout_category: str | None = None,
    result_count: int | None = None,
    exception_type: str | None = None,
) -> dict[str, Any]:
    """Build a normalized ``extra=`` envelope for library log records.

    Only keys with non-``None`` values are included. ``service_root`` is scrubbed
    via :func:`_scrub_url` so ``?token=`` values never reach log handlers. Keys
    are drawn from :data:`LOG_EXTRA_KEYS`; the keyword list is the contract —
    unknown keys raise :class:`TypeError` from the signature.
    """
    raw: dict[str, Any] = {
        "service_root": _scrub_url(service_root),
        "layer_id": layer_id,
        "operation": operation,
        "page_index": page_index,
        "page_size": page_size,
        "retry_attempt": retry_attempt,
        "retry_delay_s": retry_delay_s,
        "limiter_wait_s": limiter_wait_s,
        "timeout_category": timeout_category,
        "result_count": result_count,
        "exception_type": exception_type,
    }
    return {k: v for k, v in raw.items() if v is not None}


__all__ = [
    "LOGGER_SUFFIXES",
    "LOG_EXTRA_KEYS",
    "SCHEMA_DRIFT_LOGGER_NAME",
    "build_log_extra",
    "get_drift_logger",
    "get_logger",
]


# ---------------------------------------------------------------------------
# Span-context correlation filter (BL-32, phase-3b)
# ---------------------------------------------------------------------------


class _SpanContextFilter(logging.Filter):
    """Stamp ``trace_id`` and ``span_id`` on log records when OTel is active.

    Silent no-op when ``opentelemetry`` is not installed — never raises
    :class:`ImportError` or :class:`~restgdf.errors.OptionalDependencyError`.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            from opentelemetry import trace  # type: ignore[import-untyped]
        except ImportError:
            return True

        span = trace.get_current_span()
        ctx = span.get_span_context()
        if ctx is not None and ctx.is_valid:
            record.trace_id = format(ctx.trace_id, "032x")  # type: ignore[attr-defined]
            record.span_id = format(ctx.span_id, "016x")  # type: ignore[attr-defined]
        return True


def _ensure_span_context_filter(logger: logging.Logger) -> None:
    """Attach :class:`_SpanContextFilter` to *logger* if not already present."""
    if not any(isinstance(f, _SpanContextFilter) for f in logger.filters):
        logger.addFilter(_SpanContextFilter())


def _install_span_context_filter() -> None:
    """Attach :class:`_SpanContextFilter` to the ``restgdf`` logger tree."""
    _ensure_span_context_filter(logging.getLogger("restgdf"))
    for suffix in LOGGER_SUFFIXES:
        _ensure_span_context_filter(logging.getLogger(f"restgdf.{suffix}"))


_install_span_context_filter()
