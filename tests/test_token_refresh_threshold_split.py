"""Tests for BL-04 refresh_threshold_seconds field split.

Verifies that :class:`TokenSessionConfig` exposes two separate integer
fields (``refresh_leeway_seconds``, default 60; ``clock_skew_seconds``,
default 30, capped at 30 when derived from the alias) while keeping
``refresh_threshold_seconds`` as a deprecation-warning alias whose
read/write paths round-trip through the new fields.
"""

from __future__ import annotations

import warnings

import pytest

from restgdf._models.credentials import AGOLUserPass, TokenSessionConfig


def _creds() -> AGOLUserPass:
    return AGOLUserPass(username="u", password="p")


def test_new_fields_default_to_60_and_30():
    cfg = TokenSessionConfig(
        token_url="https://example.com/generateToken",
        credentials=_creds(),
    )
    assert cfg.refresh_leeway_seconds == 60
    assert cfg.clock_skew_seconds == 30


def test_alias_read_returns_sum_and_warns():
    cfg = TokenSessionConfig(
        token_url="https://example.com/generateToken",
        credentials=_creds(),
    )
    with pytest.warns(DeprecationWarning, match="refresh_threshold_seconds"):
        value = cfg.refresh_threshold_seconds
    assert value == 90


def test_alias_write_roundtrip_small_total():
    with pytest.warns(DeprecationWarning, match="refresh_threshold_seconds"):
        cfg = TokenSessionConfig(
            token_url="https://example.com/generateToken",
            credentials=_creds(),
            refresh_threshold_seconds=45,
        )
    assert cfg.clock_skew_seconds == 30
    assert cfg.refresh_leeway_seconds == 15
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        assert cfg.refresh_threshold_seconds == 45


def test_alias_write_roundtrip_large_total():
    with pytest.warns(DeprecationWarning, match="refresh_threshold_seconds"):
        cfg = TokenSessionConfig(
            token_url="https://example.com/generateToken",
            credentials=_creds(),
            refresh_threshold_seconds=500,
        )
    assert cfg.clock_skew_seconds == 30
    assert cfg.refresh_leeway_seconds == 470
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        assert cfg.refresh_threshold_seconds == 500


def test_alias_write_roundtrip_zero():
    with pytest.warns(DeprecationWarning, match="refresh_threshold_seconds"):
        cfg = TokenSessionConfig(
            token_url="https://example.com/generateToken",
            credentials=_creds(),
            refresh_threshold_seconds=0,
        )
    assert cfg.clock_skew_seconds == 0
    assert cfg.refresh_leeway_seconds == 0
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        assert cfg.refresh_threshold_seconds == 0


def test_alias_write_rejects_negative():
    with pytest.raises(Exception):  # RestgdfResponseError or ValidationError
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            TokenSessionConfig(
                token_url="https://example.com/generateToken",
                credentials=_creds(),
                refresh_threshold_seconds=-1,
            )


def test_new_fields_reject_negative():
    with pytest.raises(Exception):
        TokenSessionConfig(
            token_url="https://example.com/generateToken",
            credentials=_creds(),
            refresh_leeway_seconds=-1,
        )
    with pytest.raises(Exception):
        TokenSessionConfig(
            token_url="https://example.com/generateToken",
            credentials=_creds(),
            clock_skew_seconds=-1,
        )


def test_explicit_new_fields_coexist_without_alias_warning():
    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        cfg = TokenSessionConfig(
            token_url="https://example.com/generateToken",
            credentials=_creds(),
            refresh_leeway_seconds=120,
            clock_skew_seconds=15,
        )
    assert cfg.refresh_leeway_seconds == 120
    assert cfg.clock_skew_seconds == 15
