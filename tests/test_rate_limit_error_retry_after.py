"""Red tests for RateLimitError.retry_after population (Q-A12, commit 2)."""

from __future__ import annotations


class TestRateLimitErrorRetryAfter:
    """Q-A12: RateLimitError.retry_after population from _parse_retry_after."""

    def test_retry_after_integer_header(self) -> None:
        from restgdf.resilience._errors import _parse_retry_after

        result = _parse_retry_after("120")
        assert result == 120.0

    def test_retry_after_http_date_header(self) -> None:
        from restgdf.resilience._errors import _parse_retry_after

        # RFC 7231 date: Sun, 06 Nov 1994 08:49:37 GMT
        result = _parse_retry_after("Sun, 06 Nov 1994 08:49:37 GMT")
        assert isinstance(result, float)

    def test_retry_after_none_on_garbage(self) -> None:
        from restgdf.resilience._errors import _parse_retry_after

        assert _parse_retry_after("not-a-number-or-date") is None

    def test_retry_after_none_on_empty(self) -> None:
        from restgdf.resilience._errors import _parse_retry_after

        assert _parse_retry_after("") is None

    def test_retry_after_clamps_negative_to_zero(self) -> None:
        from restgdf.resilience._errors import _parse_retry_after

        result = _parse_retry_after("-5")
        assert result is None or result >= 0.0
