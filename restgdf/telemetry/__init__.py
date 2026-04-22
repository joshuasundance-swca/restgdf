"""``restgdf.telemetry`` — optional OpenTelemetry integration (BL-32).

This package is importable on a *base* install (no OTel). Functions that
need OTel at runtime raise :class:`~restgdf.errors.OptionalDependencyError`
when the SDK is absent and telemetry is enabled.

Quick-start::

    pip install restgdf[telemetry]

    from restgdf.telemetry import RestgdfInstrumentor, feature_layer_stream_span
"""

from __future__ import annotations

from restgdf.errors import OptionalDependencyError
from restgdf.telemetry._correlation import span_context_fields
from restgdf.telemetry._instrumentor import RestgdfInstrumentor
from restgdf.telemetry._spans import feature_layer_stream_span

__all__ = [
    "OptionalDependencyError",
    "RestgdfInstrumentor",
    "feature_layer_stream_span",
    "span_context_fields",
]
