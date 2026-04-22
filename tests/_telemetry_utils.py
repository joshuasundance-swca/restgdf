"""Shared OTel test fixtures for phase-3b telemetry tests.

Session-scoped TracerProvider + per-test memory exporter. All OTel-SDK
imports live **inside fixture bodies** so ``tests/test_compat.py``
collection never touches ``opentelemetry``.
"""

from __future__ import annotations

import pytest

from restgdf import reset_config_cache


@pytest.fixture(scope="session")
def _telemetry_provider():
    """Install TracerProvider once per pytest session (OTel is process-global)."""
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory import InMemorySpanExporter

    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    yield exporter


@pytest.fixture()
def memory_exporter(_telemetry_provider):
    """Per-test accessor: clean exporter + fresh config cache."""
    _telemetry_provider.clear()
    reset_config_cache()
    try:
        yield _telemetry_provider
    finally:
        _telemetry_provider.clear()
        reset_config_cache()
