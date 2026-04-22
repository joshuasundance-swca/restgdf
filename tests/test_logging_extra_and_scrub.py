"""Tests for ``build_log_extra`` and the private ``_scrub_url`` helper (BL-26)."""

from __future__ import annotations

import logging

import pytest

from restgdf._logging import (
    LOG_EXTRA_KEYS,
    _scrub_url,
    build_log_extra,
    get_logger,
)


def test_scrub_url_strips_token_param() -> None:
    assert (
        _scrub_url("https://host/rest/generateToken?f=json&token=SECRET")
        == "https://host/rest/generateToken?f=json&token=***"
    )


def test_scrub_url_case_insensitive_key() -> None:
    scrubbed = _scrub_url("https://host/x?Token=SECRET")
    assert scrubbed is not None
    assert "Token=***" in scrubbed
    assert "SECRET" not in scrubbed


def test_scrub_url_preserves_ordering() -> None:
    assert _scrub_url("https://host/x?a=1&token=X&b=2") == (
        "https://host/x?a=1&token=***&b=2"
    )


def test_scrub_url_preserves_untouched_params_byte_stable() -> None:
    url = "https://host/x?a=hello%20world&token=X&b=c+d"
    expected = "https://host/x?a=hello%20world&token=***&b=c+d"
    out = _scrub_url(url)
    assert out == expected
    assert out is not None
    assert out.encode("utf-8") == expected.encode("utf-8")


def test_scrub_url_without_token_is_unchanged() -> None:
    url = "https://host/x?a=1&b=2"
    assert _scrub_url(url) == url


def test_scrub_url_none_and_empty() -> None:
    assert _scrub_url(None) is None
    assert _scrub_url("") == ""


def test_scrub_url_fragment_is_preserved() -> None:
    assert (
        _scrub_url("https://host/x#frag?token=SECRET")
        == "https://host/x#frag?token=SECRET"
    )


def test_scrub_url_empty_token_value() -> None:
    assert _scrub_url("https://host/x?token=") == "https://host/x?token=***"


def test_scrub_url_empty_token_with_next_param() -> None:
    assert (
        _scrub_url("https://host/x?token=&next=x") == "https://host/x?token=***&next=x"
    )


def test_scrub_url_does_not_mutate_nested_query_in_other_param() -> None:
    url = "https://host/x?a=1&token=SECRET&b=2"
    assert _scrub_url(url) == "https://host/x?a=1&token=***&b=2"


def test_build_log_extra_drops_none_keys() -> None:
    extra = build_log_extra(
        service_root="https://host/rest",
        operation="query",
    )
    assert set(extra.keys()) == {"service_root", "operation"}


def test_build_log_extra_full_envelope_keys_match_contract() -> None:
    extra = build_log_extra(
        service_root="https://host/rest",
        layer_id=0,
        operation="query",
        page_index=1,
        page_size=2000,
        retry_attempt=0,
        retry_delay_s=0.5,
        limiter_wait_s=0.01,
        timeout_category="read",
        result_count=42,
        exception_type="TimeoutError",
    )
    assert set(extra.keys()) == set(LOG_EXTRA_KEYS)


def test_build_log_extra_scrubs_service_root() -> None:
    extra = build_log_extra(service_root="https://host/x?token=X")
    assert "token=***" in extra["service_root"]
    assert "token=X" not in extra["service_root"]


def test_build_log_extra_caplog_roundtrip(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.INFO, logger="restgdf.pagination"):
        get_logger("pagination").info(
            "msg",
            extra=build_log_extra(
                page_index=3,
                page_size=10,
                operation="query",
            ),
        )
    assert caplog.records[0].page_index == 3
    assert caplog.records[0].page_size == 10
    assert caplog.records[0].operation == "query"
