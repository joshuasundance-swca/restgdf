"""Typed runtime errors raised by validated ArcGIS response parsing.

:class:`RestgdfResponseError` is the single exception type raised when a
response fails strict-tier validation or when a permissive parse receives an
explicit top-level ArcGIS ``{"error": {...}}`` envelope. Ordinary
metadata/crawl drift still logs through :mod:`restgdf._models._drift`
instead of raising.
"""

from __future__ import annotations

from typing import Any


class RestgdfResponseError(ValueError):
    """Raised when validated ArcGIS response handling must fail fast.

    Attributes
    ----------
    model_name
        The pydantic model class name associated with the failed parse (for
        example ``"CountResponse"`` or ``"LayerMetadata"``).
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
