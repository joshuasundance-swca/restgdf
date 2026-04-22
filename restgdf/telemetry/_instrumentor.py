"""``RestgdfInstrumentor`` — dynamic subclass of ``AioHttpClientInstrumentor``.

The class is built lazily on first instantiation so that ``import
restgdf.telemetry`` succeeds without any OpenTelemetry packages installed.
If OTel is absent at *construction* time, :class:`~restgdf.errors.OptionalDependencyError`
is raised (R-58).
"""

from __future__ import annotations

from typing import Any

from restgdf.errors import OptionalDependencyError


class RestgdfInstrumentor:
    """Thin restgdf-specific wrapper around ``AioHttpClientInstrumentor``.

    Dynamically rebuilds itself as a subclass of
    ``opentelemetry.instrumentation.aiohttp_client.AioHttpClientInstrumentor``
    at construction time. This deferred approach avoids import-time failures
    on a base install that has no OTel packages.
    """

    _real_cls: type | None = None

    def __new__(cls, *args: Any, **kwargs: Any) -> RestgdfInstrumentor:
        """Build the dynamic subclass on first instantiation."""
        if cls._real_cls is None:
            try:
                from opentelemetry.instrumentation.aiohttp_client import (  # type: ignore[import-untyped]
                    AioHttpClientInstrumentor,
                )
            except ImportError as exc:
                raise OptionalDependencyError(
                    "restgdf[telemetry] requires opentelemetry-instrumentation-aiohttp-client. "
                    "Install it with:  pip install restgdf[telemetry]",
                ) from exc

            # Dynamically create a subclass that inherits from both
            cls._real_cls = type(
                "RestgdfInstrumentor",
                (cls, AioHttpClientInstrumentor),
                {},
            )

        instance: RestgdfInstrumentor = object.__new__(cls._real_cls)
        return instance  # type: ignore[return-value]


__all__ = ["RestgdfInstrumentor"]
