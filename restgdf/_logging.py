"""Logging scaffolding for the pydantic-powered schema-drift pipeline.

Usage
-----
Library code that wants to record ArcGIS response variance should call
:func:`get_drift_logger` rather than instantiating its own logger. The
returned logger is shared by every slice and attaches a :class:`NullHandler`
so library users opt in to output (``logging.getLogger("restgdf.schema_drift")
.addHandler(logging.StreamHandler())`` or equivalent).

The logger name ``restgdf.schema_drift`` is part of the restgdf 2.x public
contract. Tests assert against it via ``caplog``.
"""

from __future__ import annotations

import logging

SCHEMA_DRIFT_LOGGER_NAME = "restgdf.schema_drift"


def get_drift_logger() -> logging.Logger:
    """Return the restgdf schema-drift logger.

    The logger is created lazily on first access and is guaranteed to have
    a :class:`~logging.NullHandler` attached so libraries importing restgdf
    do not emit warnings to the root logger by default.
    """
    logger = logging.getLogger(SCHEMA_DRIFT_LOGGER_NAME)
    if not any(isinstance(h, logging.NullHandler) for h in logger.handlers):
        logger.addHandler(logging.NullHandler())
    return logger


__all__ = ["SCHEMA_DRIFT_LOGGER_NAME", "get_drift_logger"]
