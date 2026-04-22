"""BL-39 scaffold: OpenTelemetry InMemorySpanExporter test fixture.

Reuses the session-scoped ``memory_exporter`` fixture from
``tests/_telemetry_utils.py``. OTel's ``set_tracer_provider`` is a
one-way global install — a function-scoped fixture that shuts down the
provider on teardown permanently breaks span capture for every later
test. The shared ``_telemetry_utils._telemetry_provider`` installs the
provider exactly once per pytest session and ``memory_exporter``
clears the exporter between tests.
"""

from __future__ import annotations

from opentelemetry import trace
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from tests._telemetry_utils import memory_exporter  # noqa: F401  (re-export)


def test_otel_fixture_captures_spans(
    memory_exporter: InMemorySpanExporter,  # noqa: F811
):
    """Sanity test: fixture captures spans emitted during the test."""
    tracer = trace.get_tracer("test")
    with tracer.start_as_current_span("test-span"):
        pass
    spans = memory_exporter.get_finished_spans()
    assert len(spans) == 1
    assert spans[0].name == "test-span"
