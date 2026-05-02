"""BL-37: taxonomy + observability contract tests.

For every public exception class exported from :mod:`restgdf.errors`, assert
it is a subclass of :class:`restgdf.errors.RestgdfError`. For every logger
suffix in :data:`restgdf._logging.LOGGER_SUFFIXES`, assert
:func:`restgdf._logging.get_logger` builds a named logger, attaches a
:class:`logging.NullHandler`, and propagates records through ``caplog``.
"""

from __future__ import annotations

import logging

import pytest

from restgdf import errors as errors_module
from restgdf._logging import LOGGER_SUFFIXES, get_logger
from restgdf.errors import PaginationError, PaginationInconsistencyWarning, RestgdfError


def test_every_public_exception_inherits_restgdf_error() -> None:
    # Every name exported by restgdf.errors.__all__ must be a subclass of
    # RestgdfError. This locks the exception taxonomy root per
    # plan-output-exceptions §4 and MASTER-PLAN BL-06.
    for name in errors_module.__all__:
        cls = getattr(errors_module, name)
        assert isinstance(cls, type), f"{name} is not a class"
        if issubclass(cls, Warning):
            continue
        assert issubclass(cls, RestgdfError), f"{name} must inherit RestgdfError"


def test_public_warning_exports_remain_warnings() -> None:
    assert issubclass(PaginationInconsistencyWarning, UserWarning)


def test_exception_taxonomy_is_catchable_as_restgdf_error() -> None:
    # A canonical smoke check that an except-RestgdfError clause catches
    # representative members of the tree (BL-37 "except RestgdfError:
    # coverage on representative paths").
    raised: list[str] = []
    for cls in (PaginationError, errors_module.ConfigurationError):
        try:
            raise cls("ping")
        except RestgdfError as exc:
            raised.append(type(exc).__name__)
    assert raised == ["PaginationError", "ConfigurationError"]


@pytest.mark.parametrize("suffix", LOGGER_SUFFIXES)
def test_every_logger_suffix_has_a_smoke_test(
    suffix: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    # Every suffix in the canonical tuple must round-trip through the
    # factory: named logger, NullHandler attached, caplog captures records.
    # Call sites for some suffixes are not yet wired (they land with
    # phase-3a/3b/3c/3d); this contract asserts the factory surface itself,
    # which is the public API (R-55).
    logger = get_logger(suffix)
    assert logger.name == f"restgdf.{suffix}"
    assert any(isinstance(handler, logging.NullHandler) for handler in logger.handlers)

    caplog.clear()
    with caplog.at_level(logging.INFO, logger=logger.name):
        logger.info("contract-ping-%s", suffix, extra={"operation": "test"})

    records = [record for record in caplog.records if record.name == logger.name]
    assert records, f"no records emitted via {logger.name}"
    assert records[-1].getMessage() == f"contract-ping-{suffix}"


def test_root_logger_factory_round_trips(
    caplog: pytest.LogCaptureFixture,
) -> None:
    logger = get_logger()
    assert logger.name == "restgdf"
    caplog.clear()
    with caplog.at_level(logging.INFO, logger="restgdf"):
        logger.info("root-ping")
    assert any(r.getMessage() == "root-ping" for r in caplog.records)


def test_logger_factory_rejects_unknown_suffix() -> None:
    with pytest.raises(ValueError):
        get_logger("definitely_not_a_real_suffix")
