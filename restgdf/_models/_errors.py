"""Typed runtime errors raised by validated ArcGIS response parsing.

:class:`RestgdfResponseError` is the single exception type raised when a
response fails strict-tier validation. Permissive (metadata/crawl) models
never raise; they emit structured drift log records instead (see
:mod:`restgdf._models._drift` in a later slice).
"""

from __future__ import annotations

from typing import Any


class RestgdfResponseError(ValueError):
    """Raised when a strict-tier ArcGIS response fails validation.

    Attributes
    ----------
    model_name
        The pydantic model class name that rejected the payload (for example
        ``"CountResponse"``).
    context
        A short identifier describing *where* the response came from
        (for example the request URL or a helper name). Used by operators
        triaging ArcGIS vendor variance.
    raw
        The raw JSON-decoded payload that failed validation. Kept on the
        exception so callers can log or re-raise without re-reading the
        response body.
    """

    def __init__(
        self,
        message: str,
        *,
        model_name: str,
        context: str,
        raw: Any,
    ) -> None:
        super().__init__(message)
        self.model_name = model_name
        self.context = context
        self.raw = raw


__all__ = ["RestgdfResponseError"]
