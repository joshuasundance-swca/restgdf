"""Compat-seam regression: restgdf.telemetry importable without OTel."""

from __future__ import annotations

import importlib
import sys

import pytest


def test_restgdf_telemetry_is_importable_without_otel(monkeypatch):
    """``import restgdf.telemetry`` succeeds even when opentelemetry is absent."""
    # Block opentelemetry at the import level.
    monkeypatch.setitem(sys.modules, "opentelemetry", None)
    monkeypatch.setitem(sys.modules, "opentelemetry.trace", None)
    monkeypatch.setitem(sys.modules, "opentelemetry.instrumentation", None)
    monkeypatch.setitem(
        sys.modules, "opentelemetry.instrumentation.aiohttp_client", None
    )

    # Purge any cached restgdf.telemetry modules so re-import is forced.
    for key in list(sys.modules):
        if key.startswith("restgdf.telemetry"):
            monkeypatch.delitem(sys.modules, key, raising=False)

    mod = importlib.import_module("restgdf.telemetry")
    assert hasattr(mod, "RestgdfInstrumentor")
    assert hasattr(mod, "feature_layer_stream_span")


def test_telemetry_config_importable():
    """TelemetryConfig (phase-2a) is still importable."""
    from restgdf import TelemetryConfig  # noqa: F401


def test_restgdf_logger_outside_span_no_raise(caplog):
    """restgdf.* logging outside a span does not raise."""
    import logging

    with caplog.at_level(logging.INFO, logger="restgdf.transport"):
        logging.getLogger("restgdf.transport").info("msg")
    assert any(r.message == "msg" for r in caplog.records)
