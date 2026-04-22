"""MRO / isinstance contracts for the canonical exception taxonomy (BL-06).

These tests lock the class-hierarchy shape documented in ``restgdf/errors.py``.
Every multi-inheritance class has an explicit MRO assertion so that
accidental base-tuple reordering (which would silently break
``except ValueError`` / ``except ImportError`` / ``except TimeoutError``
callers) fails loudly in CI.
"""

from __future__ import annotations

import pytest

from restgdf.errors import (
    ArcGISServiceError,
    AuthenticationError,
    ConfigurationError,
    OptionalDependencyError,
    OutputConversionError,
    PaginationError,
    RateLimitError,
    RestgdfError,
    RestgdfResponseError,
    RestgdfTimeoutError,
    SchemaValidationError,
    TransportError,
)


def test_restgdf_error_is_base_exception() -> None:
    assert issubclass(RestgdfError, Exception)
    assert RestgdfError.__mro__ == (RestgdfError, Exception, BaseException, object)


def test_configuration_error_mro_and_isinstance() -> None:
    assert issubclass(ConfigurationError, RestgdfError)
    assert issubclass(ConfigurationError, ValueError)
    assert ConfigurationError.__mro__ == (
        ConfigurationError,
        RestgdfError,
        ValueError,
        Exception,
        BaseException,
        object,
    )
    err = ConfigurationError("bad config")
    assert isinstance(err, RestgdfError)
    assert isinstance(err, ValueError)


def test_optional_dependency_error_mro_and_catches() -> None:
    assert issubclass(OptionalDependencyError, ConfigurationError)
    assert issubclass(OptionalDependencyError, ModuleNotFoundError)
    assert issubclass(OptionalDependencyError, ImportError)
    assert issubclass(OptionalDependencyError, ValueError)
    assert OptionalDependencyError.__mro__ == (
        OptionalDependencyError,
        ConfigurationError,
        RestgdfError,
        ValueError,
        ModuleNotFoundError,
        ImportError,
        Exception,
        BaseException,
        object,
    )
    err = OptionalDependencyError("pandas missing")
    with pytest.raises(ModuleNotFoundError):
        raise err
    with pytest.raises(ImportError):
        raise err


def test_restgdf_response_error_mro_and_signature() -> None:
    assert issubclass(RestgdfResponseError, RestgdfError)
    assert issubclass(RestgdfResponseError, ValueError)
    assert RestgdfResponseError.__mro__ == (
        RestgdfResponseError,
        RestgdfError,
        ValueError,
        Exception,
        BaseException,
        object,
    )
    err = RestgdfResponseError(
        "bad envelope",
        model_name="CountResponse",
        context="https://example/arcgis",
        raw={"foo": 1},
    )
    assert err.model_name == "CountResponse"
    assert err.context == "https://example/arcgis"
    assert err.raw == {"foo": 1}
    assert isinstance(err, ValueError)


def test_schema_validation_error_not_indexerror() -> None:
    # R-02: SchemaValidationError must not multi-inherit IndexError.
    assert issubclass(SchemaValidationError, RestgdfResponseError)
    assert issubclass(SchemaValidationError, ValueError)
    assert not issubclass(SchemaValidationError, IndexError)
    assert SchemaValidationError.__mro__ == (
        SchemaValidationError,
        RestgdfResponseError,
        RestgdfError,
        ValueError,
        Exception,
        BaseException,
        object,
    )


def test_arcgis_service_error_mro() -> None:
    assert issubclass(ArcGISServiceError, RestgdfResponseError)
    assert ArcGISServiceError.__mro__ == (
        ArcGISServiceError,
        RestgdfResponseError,
        RestgdfError,
        ValueError,
        Exception,
        BaseException,
        object,
    )


def test_pagination_error_mro_and_attributes() -> None:
    assert issubclass(PaginationError, ArcGISServiceError)
    assert issubclass(PaginationError, RestgdfResponseError)
    assert issubclass(PaginationError, IndexError)
    assert PaginationError.__mro__ == (
        PaginationError,
        ArcGISServiceError,
        RestgdfResponseError,
        RestgdfError,
        ValueError,
        IndexError,
        LookupError,
        Exception,
        BaseException,
        object,
    )
    err = PaginationError("cursor exhausted", batch_index=4, page_size=1000)
    assert err.batch_index == 4
    assert err.page_size == 1000
    with pytest.raises(IndexError):
        raise err
    default = PaginationError("no ctx")
    assert default.batch_index is None
    assert default.page_size is None


def test_authentication_error_mro() -> None:
    assert issubclass(AuthenticationError, RestgdfResponseError)
    assert issubclass(AuthenticationError, PermissionError)
    assert AuthenticationError.__mro__ == (
        AuthenticationError,
        RestgdfResponseError,
        RestgdfError,
        ValueError,
        PermissionError,
        OSError,
        Exception,
        BaseException,
        object,
    )
    # The auth class carries the RRE signature; smoke-test it.
    err = AuthenticationError(
        "token expired",
        model_name="TokenResponse",
        context="generateToken",
        raw={"error": {"code": 498}},
    )
    assert err.model_name == "TokenResponse"
    with pytest.raises(PermissionError):
        raise err


def test_transport_error_mro() -> None:
    assert issubclass(TransportError, RestgdfError)
    assert TransportError.__mro__ == (
        TransportError,
        RestgdfError,
        Exception,
        BaseException,
        object,
    )


def test_restgdf_timeout_error_mro_and_catches() -> None:
    assert issubclass(RestgdfTimeoutError, TransportError)
    assert issubclass(RestgdfTimeoutError, TimeoutError)
    assert RestgdfTimeoutError.__mro__ == (
        RestgdfTimeoutError,
        TransportError,
        RestgdfError,
        TimeoutError,
        OSError,
        Exception,
        BaseException,
        object,
    )
    err = RestgdfTimeoutError("slow service")
    with pytest.raises(TimeoutError):
        raise err


def test_rate_limit_error_mro_and_retry_after() -> None:
    assert issubclass(RateLimitError, TransportError)
    assert RateLimitError.__mro__ == (
        RateLimitError,
        TransportError,
        RestgdfError,
        Exception,
        BaseException,
        object,
    )
    err = RateLimitError("slow down", retry_after=2.5)
    assert err.retry_after == pytest.approx(2.5)
    default = RateLimitError("no hint")
    assert default.retry_after is None


def test_output_conversion_error_mro() -> None:
    assert issubclass(OutputConversionError, RestgdfError)
    assert OutputConversionError.__mro__ == (
        OutputConversionError,
        RestgdfError,
        Exception,
        BaseException,
        object,
    )


def test_module_lists_full_public_api() -> None:
    import restgdf.errors as errors_module

    exported = set(errors_module.__all__)
    expected = {
        "ArcGISServiceError",
        "AuthNotAttachedError",
        "AuthenticationError",
        "ConfigurationError",
        "FieldDoesNotExistError",
        "InvalidCredentialsError",
        "OptionalDependencyError",
        "OutputConversionError",
        "PaginationError",
        "RateLimitError",
        "RestgdfError",
        "RestgdfResponseError",
        "RestgdfTimeoutError",
        "SchemaValidationError",
        "TokenExpiredError",
        "TokenRefreshFailedError",
        "TokenRequiredError",
        "TransportError",
    }
    assert exported == expected


# ---------------------------------------------------------------------------
# BL-09: FieldDoesNotExistError MRO
# ---------------------------------------------------------------------------
from restgdf.errors import FieldDoesNotExistError  # noqa: E402


def test_fde_mro_chain() -> None:
    assert FieldDoesNotExistError.__mro__ == (
        FieldDoesNotExistError,
        SchemaValidationError,
        RestgdfResponseError,
        RestgdfError,
        ValueError,
        Exception,
        BaseException,
        object,
    )


def test_fde_is_not_indexerror() -> None:
    """R-02 hard break: IndexError shim is removed."""
    assert not issubclass(FieldDoesNotExistError, IndexError)
    exc = FieldDoesNotExistError("test")
    assert not isinstance(exc, IndexError)
