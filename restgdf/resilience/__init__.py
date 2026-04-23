"""Resilience adapter for restgdf (BL-31).

Provides :class:`ResilientSession`, a retry + rate-limit wrapper that
implements the :class:`~restgdf._client._protocols.AsyncHTTPSession`
protocol. Requires the ``resilience`` extra (``stamina`` + ``aiolimiter``).

Usage::

    pip install restgdf[resilience]

    from restgdf.resilience import ResilientSession
"""

from __future__ import annotations

try:
    import stamina as _stamina  # noqa: F401
    import aiolimiter as _aiolimiter  # noqa: F401
except ImportError as _exc:
    from restgdf.errors import OptionalDependencyError

    raise OptionalDependencyError(
        "The resilience extra is required: pip install restgdf[resilience]",
    ) from _exc

from restgdf.resilience._bounded_retry import bounded_retry_timeout
from restgdf.resilience._retry import ResilientSession

__all__ = ["ResilientSession", "bounded_retry_timeout"]
