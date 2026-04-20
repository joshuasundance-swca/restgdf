"""Scaffolding tests for the pydantic 2.x model integration (S-0).

These tests pin the public contract of the new shared plumbing:

* ``restgdf._logging.get_drift_logger`` returns the ``restgdf.schema_drift``
  logger with a ``NullHandler`` attached so importing the library is silent
  by default.
* ``restgdf._models.RestgdfResponseError`` is the single strict-tier
  validation exception type, preserves operator-triage context, and
  subclasses ``ValueError`` (so existing ``except ValueError`` handlers
  keep working).

Later slices build on this scaffolding; these tests guard against
accidental renames/moves during the migration.
"""

from __future__ import annotations

import logging

import pytest

from restgdf._logging import SCHEMA_DRIFT_LOGGER_NAME, get_drift_logger
from restgdf._models import RestgdfResponseError


def test_drift_logger_is_named_schema_drift() -> None:
    logger = get_drift_logger()
    assert logger.name == SCHEMA_DRIFT_LOGGER_NAME == "restgdf.schema_drift"


def test_drift_logger_has_null_handler_by_default() -> None:
    logger = get_drift_logger()
    assert any(isinstance(h, logging.NullHandler) for h in logger.handlers)


def test_drift_logger_does_not_stack_null_handlers_on_repeat_access() -> None:
    first = get_drift_logger()
    before = sum(1 for h in first.handlers if isinstance(h, logging.NullHandler))
    second = get_drift_logger()
    after = sum(1 for h in second.handlers if isinstance(h, logging.NullHandler))
    assert first is second
    assert before == after == 1


def test_response_error_subclasses_value_error() -> None:
    with pytest.raises(ValueError):
        raise RestgdfResponseError(
            "boom",
            model_name="CountResponse",
            context="https://example/arcgis/rest/services/Foo/FeatureServer/0/query",
            raw={"count": "not-an-int"},
        )


def test_response_error_preserves_triage_context() -> None:
    raw = {"error": {"code": 498, "message": "Invalid Token"}}
    err = RestgdfResponseError(
        "token invalid",
        model_name="TokenResponse",
        context="token refresh",
        raw=raw,
    )
    assert err.model_name == "TokenResponse"
    assert err.context == "token refresh"
    assert err.raw is raw
    assert str(err) == "token invalid"
