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


# ---------------------------------------------------------------------------
# Runtime wiring: ArcGISTokenSession must actually honor the split fields.
# ---------------------------------------------------------------------------


def _expires_in_seconds(seconds: float) -> float:
    import datetime as _dt

    return (
        _dt.datetime.now(_dt.timezone.utc) + _dt.timedelta(seconds=seconds)
    ).timestamp()


def test_ts_config_split_fields_drive_refresh_threshold():
    """Explicit split fields must be honored by ``token_needs_update``."""
    from restgdf.utils.token import ArcGISTokenSession

    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        cfg = TokenSessionConfig(
            token_url="https://example.com/generateToken",
            credentials=_creds(),
            refresh_leeway_seconds=90,
            clock_skew_seconds=30,
        )

    class _Sess:
        pass

    ts = ArcGISTokenSession(
        session=_Sess(),  # type: ignore[arg-type]
        credentials=_creds(),
        config=cfg,
        token="existing",
        expires=_expires_in_seconds(80),
    )
    # Effective threshold must be 120s (90 + 30), so 80s-to-expiry needs refresh.
    assert ts.token_needs_update() is True


def test_dataclass_token_refresh_threshold_drives_runtime():
    """``AGTS(token_refresh_threshold=120)`` must drive refresh at 80s left."""
    from restgdf.utils.token import ArcGISTokenSession

    class _Sess:
        pass

    ts = ArcGISTokenSession(
        session=_Sess(),  # type: ignore[arg-type]
        credentials=_creds(),
        token_refresh_threshold=120,
        token="existing",
        expires=_expires_in_seconds(80),
    )
    assert ts.token_needs_update() is True


def test_ts_config_legacy_alias_drives_runtime():
    """Legacy ``refresh_threshold_seconds=120`` alias path must still wire."""
    from restgdf.utils.token import ArcGISTokenSession

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        cfg = TokenSessionConfig(
            token_url="https://example.com/generateToken",
            credentials=_creds(),
            refresh_threshold_seconds=120,
        )

    class _Sess:
        pass

    ts = ArcGISTokenSession(
        session=_Sess(),  # type: ignore[arg-type]
        credentials=_creds(),
        config=cfg,
        token="existing",
        expires=_expires_in_seconds(80),
    )
    assert ts.token_needs_update() is True


# ---------------------------------------------------------------------------
# Warning-surface guards: no spurious DeprecationWarnings at construction.
# ---------------------------------------------------------------------------


def test_plain_arcgis_token_session_construction_is_silent():
    """Constructing ``ArcGISTokenSession`` must not emit any deprecation."""
    from restgdf.utils.token import ArcGISTokenSession

    class _Sess:
        pass

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        ArcGISTokenSession(
            session=_Sess(),  # type: ignore[arg-type]
            credentials=_creds(),
        )
    deprecations = [w for w in caught if issubclass(w.category, DeprecationWarning)]
    assert deprecations == [], (
        "ArcGISTokenSession construction fired DeprecationWarning(s): "
        f"{[str(w.message) for w in deprecations]}"
    )


def test_refresh_threshold_seconds_read_warns_from_caller_frame():
    """Reading the alias must blame the caller's line (stacklevel=2)."""
    cfg = TokenSessionConfig(
        token_url="https://example.com/generateToken",
        credentials=_creds(),
    )
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        _ = cfg.refresh_threshold_seconds
    deprecations = [w for w in caught if issubclass(w.category, DeprecationWarning)]
    assert len(deprecations) == 1
    assert deprecations[0].filename.endswith("test_token_refresh_threshold_split.py")
