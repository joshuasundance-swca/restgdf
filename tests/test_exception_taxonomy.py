"""Public surface / docstring sentinels for the canonical exception taxonomy."""

from __future__ import annotations

import pytest


def test_public_errors_importable_from_restgdf() -> None:
    import restgdf

    for name in (
        "ArcGISServiceError",
        "AuthenticationError",
        "ConfigurationError",
        "OptionalDependencyError",
        "OutputConversionError",
        "PaginationError",
        "RateLimitError",
        "RestgdfError",
        "RestgdfResponseError",
        "RestgdfTimeoutError",
        "SchemaValidationError",
        "TransportError",
    ):
        assert hasattr(restgdf, name), f"restgdf.{name} must be importable"
        assert name in restgdf.__all__


def test_errors_module_docstring_lists_taxonomy() -> None:
    import restgdf.errors as errors_module

    assert errors_module.__doc__ is not None
    assert "RestgdfError" in errors_module.__doc__
    assert "TransportError" in errors_module.__doc__
    assert "PaginationError" in errors_module.__doc__


def test_optional_dependency_error_caught_as_modulenotfound() -> None:
    from restgdf.errors import OptionalDependencyError

    with pytest.raises(ModuleNotFoundError):
        raise OptionalDependencyError("pandas missing")


def test_configuration_error_caught_as_valueerror() -> None:
    from restgdf.errors import ConfigurationError

    with pytest.raises(ValueError):
        raise ConfigurationError("bad config")


def test_pagination_error_carries_context() -> None:
    from restgdf.errors import PaginationError

    err = PaginationError("exceeded limit", batch_index=7, page_size=500)
    assert err.batch_index == 7
    assert err.page_size == 500
    assert "exceeded limit" in str(err)


def test_rate_limit_error_retry_after() -> None:
    from restgdf.errors import RateLimitError

    err = RateLimitError("429", retry_after=1.25)
    assert err.retry_after == pytest.approx(1.25)
