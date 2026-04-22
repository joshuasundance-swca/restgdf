"""Span-context helpers for external loggers.

:func:`span_context_fields` is the public convenience for non-restgdf loggers
that want trace/span IDs without depending on ``_SpanContextFilter``.
"""

from __future__ import annotations


def span_context_fields() -> dict[str, str]:
    """Return ``{trace_id, span_id}`` from the current OTel span, or ``{}``.

    Safe to call even when ``opentelemetry`` is not installed — returns an
    empty dict.
    """
    try:
        from opentelemetry import trace  # type: ignore[import-untyped]
    except ImportError:
        return {}

    span = trace.get_current_span()
    ctx = span.get_span_context()
    if ctx is None or not ctx.is_valid:
        return {}
    return {
        "trace_id": format(ctx.trace_id, "032x"),
        "span_id": format(ctx.span_id, "016x"),
    }


__all__ = ["span_context_fields"]
