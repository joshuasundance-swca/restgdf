"""Alias shim re-exporting :class:`restgdf.errors.RestgdfResponseError`.

The canonical class definition lives in :mod:`restgdf.errors` as of phase-1c
(BL-06). This module remains to preserve the legacy import path
``from restgdf._models._errors import RestgdfResponseError`` and the
``from restgdf._models import RestgdfResponseError`` chain. Class identity
is preserved: ``restgdf._models._errors.RestgdfResponseError is
restgdf.errors.RestgdfResponseError``.
"""

from __future__ import annotations

from restgdf.errors import RestgdfResponseError as RestgdfResponseError

__all__ = ["RestgdfResponseError"]
