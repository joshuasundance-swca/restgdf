"""Red tests for BL-36 error-attribute population (commit 2)."""

from __future__ import annotations

import pytest

from restgdf.errors import (
    RateLimitError,
    RestgdfResponseError,
    RestgdfTimeoutError,
    TransportError,
)


class TestErrorAttributePopulation:
    """BL-36: url, status_code, request_id, timeout_kind are stored on error instances."""

    def test_restgdf_response_error_url_status_code(self) -> None:
        exc = RestgdfResponseError(
            "test",
            url="http://test/FeatureServer/0",
            status_code=500,
        )
        assert exc.url == "http://test/FeatureServer/0"
        assert exc.status_code == 500

    def test_restgdf_response_error_request_id(self) -> None:
        exc = RestgdfResponseError(
            "test",
            request_id="abc-123",
        )
        assert exc.request_id == "abc-123"

    def test_transport_error_url_status_code(self) -> None:
        exc = TransportError(
            "DNS failed",
            url="http://test/FeatureServer/0",
            status_code=None,
        )
        assert exc.url == "http://test/FeatureServer/0"
        assert exc.status_code is None

    def test_timeout_error_timeout_kind(self) -> None:
        exc = RestgdfTimeoutError(
            "connect timed out",
            timeout_kind="connect",
        )
        assert exc.timeout_kind == "connect"

    def test_rate_limit_error_retry_after_and_status_code(self) -> None:
        exc = RateLimitError(
            "rate limited",
            retry_after=30.0,
            url="http://test/query",
            status_code=429,
        )
        assert exc.retry_after == 30.0
        assert exc.status_code == 429
        assert exc.url == "http://test/query"
