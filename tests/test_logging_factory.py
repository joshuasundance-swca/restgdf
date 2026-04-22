"""Tests for the restgdf library-wide logger factory (BL-25)."""

from __future__ import annotations

import logging

import pytest

from restgdf._logging import (
    LOGGER_SUFFIXES,
    SCHEMA_DRIFT_LOGGER_NAME,
    get_drift_logger,
    get_logger,
)


def test_get_logger_returns_restgdf_root_when_suffix_empty() -> None:
    logger = get_logger("")
    assert logger.name == "restgdf"


def test_get_logger_returns_named_child() -> None:
    for suffix in LOGGER_SUFFIXES:
        logger = get_logger(suffix)
        assert logger.name == f"restgdf.{suffix}"


def test_get_logger_attaches_single_null_handler() -> None:
    first = get_logger("transport")
    second = get_logger("transport")
    null_handlers = [h for h in first.handlers if isinstance(h, logging.NullHandler)]
    assert len(null_handlers) == 1
    assert first is second


def test_get_logger_is_idempotent() -> None:
    assert get_logger("retry") is get_logger("retry")
    assert get_logger("") is get_logger("")


def test_get_logger_rejects_unknown_suffix() -> None:
    with pytest.raises(ValueError, match="unknown restgdf logger suffix"):
        get_logger("not_a_real_suffix")


def test_get_logger_rejects_non_string_suffix() -> None:
    with pytest.raises(TypeError, match="restgdf logger suffix must be str"):
        get_logger(None)  # type: ignore[arg-type]


def test_drift_alias_returns_same_logger_as_factory() -> None:
    assert get_drift_logger() is get_logger("schema_drift")


def test_drift_logger_name_contract_preserved() -> None:
    assert get_drift_logger().name == SCHEMA_DRIFT_LOGGER_NAME
    assert SCHEMA_DRIFT_LOGGER_NAME == "restgdf.schema_drift"
