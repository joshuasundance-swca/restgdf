"""Span helpers for restgdf telemetry.

:func:`feature_layer_stream_span` is the async context-manager that opens an
INTERNAL ``feature_layer.stream`` span (R-21). It is *not* wired into
production call-sites by this phase — that happens in phase-4A.

:func:`start_feature_layer_stream_span` is the generator-safe companion used
by the streaming primitive (``_iter_pages_raw``). It starts a NON-current
span (no asyncio Context token is attached) so that it can be ended from a
``finally:`` block that spans ``yield`` boundaries without tripping OTel's
"Failed to detach context" error on early break / ``aclose()`` / cancellation.
"""

from __future__ import annotations

import re
from contextlib import asynccontextmanager
from typing import Any
from collections.abc import AsyncIterator

from restgdf._config import get_config
from restgdf._logging import _scrub_url
from restgdf.errors import OptionalDependencyError


def _service_root_for_telemetry(url: str) -> str:
    """Scrub token params and strip trailing ``/<layer-id>`` from *url*."""
    from urllib.parse import urlsplit, urlunsplit

    scrubbed = _scrub_url(url) or url
    parts = urlsplit(scrubbed)
    # Strip trailing /<digits> from the path component
    clean_path = re.sub(r"/\d+/?$", "", parts.path)
    # Rebuild without query/fragment for a clean service root
    return urlunsplit((parts.scheme, parts.netloc, clean_path, "", ""))


def _build_stream_span_attrs(
    *,
    layer_url: str,
    layer_id: int | None,
    out_fields: str | None,
    where: str | None,
    order: str | None,
    extra_attrs: dict[str, Any] | None,
) -> dict[str, Any]:
    attrs: dict[str, Any] = {
        "restgdf.service_root": _service_root_for_telemetry(layer_url),
    }
    if layer_id is not None:
        attrs["restgdf.layer_id"] = layer_id
    if out_fields is not None:
        attrs["restgdf.out_fields"] = out_fields
    if where is not None:
        attrs["restgdf.where"] = where
    if order is not None:
        attrs["restgdf.order"] = order
    if extra_attrs:
        attrs.update(extra_attrs)
    return attrs


def start_feature_layer_stream_span(
    *,
    layer_url: str,
    layer_id: int | None = None,
    out_fields: str | None = None,
    where: str | None = None,
    order: str | None = None,
    extra_attrs: dict[str, Any] | None = None,
) -> Any:
    """Start a non-current ``feature_layer.stream`` span (R-21, generator-safe).

    Returns the opened :class:`~opentelemetry.trace.Span`, or ``None`` when
    telemetry is disabled. The caller owns the span lifetime and **must**
    call :meth:`Span.end` (typically from a ``finally:`` block).

    Unlike :func:`feature_layer_stream_span`, this helper does **not** attach
    the span to the asyncio ``contextvars`` Context. This is required for
    async-generator callers where ``yield`` boundaries can suspend/resume in
    different Contexts — using ``start_as_current_span`` there triggers
    OTel's "Failed to detach context" / "Token was created in a different
    Context" errors on early break / ``aclose()`` / cancellation.
    """
    cfg = get_config()
    if not cfg.telemetry.enabled:
        return None

    try:
        from opentelemetry import trace  # type: ignore[import-untyped]
    except ImportError as exc:
        raise OptionalDependencyError(
            "restgdf[telemetry] requires opentelemetry-api. "
            "Install it with:  pip install restgdf[telemetry]",
        ) from exc

    tracer = trace.get_tracer("restgdf", tracer_provider=trace.get_tracer_provider())
    attrs = _build_stream_span_attrs(
        layer_url=layer_url,
        layer_id=layer_id,
        out_fields=out_fields,
        where=where,
        order=order,
        extra_attrs=extra_attrs,
    )
    return tracer.start_span(
        "feature_layer.stream",
        kind=trace.SpanKind.INTERNAL,
        attributes=attrs,
    )


@asynccontextmanager
async def feature_layer_stream_span(
    *,
    layer_url: str,
    layer_id: int | None = None,
    out_fields: str | None = None,
    where: str | None = None,
    order: str | None = None,
    extra_attrs: dict[str, Any] | None = None,
) -> AsyncIterator[Any]:
    """Open an INTERNAL ``feature_layer.stream`` span (R-21).

    Parameters
    ----------
    layer_url:
        Full service URL (will be scrubbed).
    layer_id:
        ArcGIS layer ID.
    out_fields:
        Value of the ``outFields`` parameter, if any.
    where:
        Value of the ``where`` parameter, if any.
    order:
        Pagination order hint (``"request"`` or ``"completion"``).
    extra_attrs:
        Additional span attributes (must already be namespaced).

    Yields
    ------
    span | None
        The opened :class:`~opentelemetry.trace.Span`, or ``None`` when
        telemetry is disabled.

    Notes
    -----
    This helper attaches the span to the current asyncio Context via
    ``start_as_current_span``. It is **not** safe to wrap an async-generator
    body whose ``yield`` can suspend across the ``__aexit__`` boundary —
    use :func:`start_feature_layer_stream_span` + manual ``span.end()``
    in those callers instead.
    """
    cfg = get_config()
    if not cfg.telemetry.enabled:
        yield None
        return

    try:
        from opentelemetry import trace  # type: ignore[import-untyped]
    except ImportError as exc:
        raise OptionalDependencyError(
            "restgdf[telemetry] requires opentelemetry-api. "
            "Install it with:  pip install restgdf[telemetry]",
        ) from exc

    tracer = trace.get_tracer("restgdf", tracer_provider=trace.get_tracer_provider())
    attrs = _build_stream_span_attrs(
        layer_url=layer_url,
        layer_id=layer_id,
        out_fields=out_fields,
        where=where,
        order=order,
        extra_attrs=extra_attrs,
    )

    with tracer.start_as_current_span(
        "feature_layer.stream",
        kind=trace.SpanKind.INTERNAL,
        attributes=attrs,
    ) as span:
        yield span


__all__ = ["feature_layer_stream_span", "start_feature_layer_stream_span"]
