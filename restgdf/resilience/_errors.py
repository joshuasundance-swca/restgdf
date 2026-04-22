"""Retry-After header parsing helper (Q-A12)."""

from __future__ import annotations

import time
from email.utils import parsedate_to_datetime


def _parse_retry_after(value: str) -> float | None:
    """Parse a ``Retry-After`` header value into seconds.

    Supports both integer-seconds (``"120"``) and RFC 7231 HTTP-date
    formats (``"Sun, 06 Nov 1994 08:49:37 GMT"``).

    Returns ``None`` for empty, unparseable, or negative values.
    """
    if not value or not value.strip():
        return None

    value = value.strip()

    # Try integer/float seconds first
    try:
        seconds = float(value)
        if seconds < 0:
            return None
        return seconds
    except ValueError:
        pass

    # Try RFC 7231 HTTP-date
    try:
        dt = parsedate_to_datetime(value)
        delta = dt.timestamp() - time.time()
        return max(0.0, delta)
    except Exception:
        return None
