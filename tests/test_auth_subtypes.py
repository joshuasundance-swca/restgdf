"""BL-10: Auth subtype identity, MRO, and SecretStr redaction tests."""

from __future__ import annotations

import pytest
from pydantic import SecretStr

from restgdf.errors import (
    AuthenticationError,
    AuthNotAttachedError,
    InvalidCredentialsError,
    RestgdfResponseError,
    TokenExpiredError,
    TokenRefreshFailedError,
    TokenRequiredError,
)


class TestAuthSubtypeHierarchy:
    """Verify each subtype inherits from AuthenticationError + PermissionError."""

    @pytest.mark.parametrize(
        "cls",
        [
            InvalidCredentialsError,
            TokenExpiredError,
            TokenRequiredError,
            TokenRefreshFailedError,
            AuthNotAttachedError,
        ],
    )
    def test_is_subclass_of_authentication_error(self, cls):
        assert issubclass(cls, AuthenticationError)

    @pytest.mark.parametrize(
        "cls",
        [
            InvalidCredentialsError,
            TokenExpiredError,
            TokenRequiredError,
            TokenRefreshFailedError,
            AuthNotAttachedError,
        ],
    )
    def test_isinstance_permission_error(self, cls):
        exc = cls("test")
        assert isinstance(exc, PermissionError)

    @pytest.mark.parametrize(
        "cls",
        [
            InvalidCredentialsError,
            TokenExpiredError,
            TokenRequiredError,
            TokenRefreshFailedError,
            AuthNotAttachedError,
        ],
    )
    def test_isinstance_restgdf_response_error(self, cls):
        exc = cls("test")
        assert isinstance(exc, RestgdfResponseError)


class TestTokenExpiredErrorCode:
    """TokenExpiredError carries code=498 by default."""

    def test_default_code_is_498(self):
        exc = TokenExpiredError()
        assert exc.code == 498

    def test_custom_code(self):
        exc = TokenExpiredError("custom", code=498)
        assert exc.code == 498


class TestContextAttemptCause:
    """All subtypes carry context, attempt, cause attrs."""

    @pytest.mark.parametrize(
        "cls",
        [
            InvalidCredentialsError,
            TokenExpiredError,
            TokenRequiredError,
            TokenRefreshFailedError,
            AuthNotAttachedError,
        ],
    )
    def test_attrs_present(self, cls):
        cause = RuntimeError("inner")
        if cls is TokenExpiredError:
            exc = cls("msg", context="ctx", attempt=3, cause=cause)
        else:
            exc = cls("msg", context="ctx", attempt=3, cause=cause)
        assert exc.context == "ctx"
        assert exc.attempt == 3
        assert exc.cause is cause
        assert exc.__cause__ is cause

    @pytest.mark.parametrize(
        "cls",
        [
            InvalidCredentialsError,
            TokenRequiredError,
            TokenRefreshFailedError,
            AuthNotAttachedError,
        ],
    )
    def test_defaults_are_none(self, cls):
        exc = cls("msg")
        assert exc.context is None
        assert exc.attempt is None
        assert exc.cause is None


class TestSecretStrRedaction:
    """__repr__ and __str__ MUST NOT leak SecretStr values (R-17)."""

    @pytest.mark.parametrize(
        "cls",
        [
            InvalidCredentialsError,
            TokenExpiredError,
            TokenRequiredError,
            TokenRefreshFailedError,
            AuthNotAttachedError,
        ],
    )
    def test_repr_redacts_secret(self, cls):
        secret = SecretStr("hunter2-very-secret")
        cause = RuntimeError(str(secret))
        if cls is TokenExpiredError:
            exc = cls("msg", context="ctx", attempt=1, cause=cause)
        else:
            exc = cls("msg", context="ctx", attempt=1, cause=cause)
        assert "hunter2-very-secret" not in repr(exc)
        assert "hunter2-very-secret" not in str(exc)

    @pytest.mark.parametrize(
        "cls",
        [
            InvalidCredentialsError,
            TokenExpiredError,
            TokenRequiredError,
            TokenRefreshFailedError,
            AuthNotAttachedError,
        ],
    )
    def test_str_redacts_secretstr_cause(self, cls):
        secret = SecretStr("my-password-123")
        if cls is TokenExpiredError:
            exc = cls("fail", cause=secret)
        else:
            exc = cls("fail", cause=secret)
        assert "my-password-123" not in str(exc)
        assert "**********" in str(exc)


class TestValueErrorRetarget:
    """BL-10: ValueError('Credentials are required ...') → AuthenticationError."""

    def test_token_request_payload_raises_authentication_error(self):
        from restgdf.utils.token import ArcGISTokenSession

        session = ArcGISTokenSession(
            session=object(),  # type: ignore[arg-type]
            token="abc",
            expires=9999999999999,
        )
        session.credentials = None
        with pytest.raises(AuthenticationError, match="Credentials are required"):
            _ = session.token_request_payload
