"""BL-16 red tests: tz-aware UTC wall-clock expires_at.

RED-first — these fail until feat(BL-16) stores datetime expiry.
"""

from __future__ import annotations

import datetime


from restgdf._models.credentials import AGOLUserPass


class TestUTCWallClockExpiry:
    """token_needs_update must use tz-aware UTC datetime, not epoch floats."""

    def test_expires_at_stored_as_utc_datetime(self):
        """After update_token, expires_at should be a tz-aware UTC datetime."""
        from restgdf.utils.token import ArcGISTokenSession

        from tests.test_token import RecordingTokenSession

        session = RecordingTokenSession()
        ts = ArcGISTokenSession(
            session=session,
            credentials=AGOLUserPass(username="user", password="password"),
            token="abc",
            expires=32503680000000,  # ~year 3000 in ms
        )

        assert hasattr(ts, "expires_at"), "ArcGISTokenSession must have expires_at attr"
        assert isinstance(
            ts.expires_at,
            datetime.datetime,
        ), f"expires_at must be datetime, got {type(ts.expires_at)}"
        assert ts.expires_at.tzinfo is not None, "expires_at must be tz-aware"
        assert ts.expires_at.tzinfo == datetime.timezone.utc

    def test_utc_now_shim_exists(self):
        """A _utc_now() shim must exist for test monkeypatching."""
        from restgdf.utils.token import _utc_now

        now = _utc_now()
        assert isinstance(now, datetime.datetime)
        assert now.tzinfo is not None
        assert now.tzinfo == datetime.timezone.utc

    def test_token_needs_update_uses_expires_at(self):
        """token_needs_update should compare against expires_at, not raw epoch."""
        from restgdf.utils.token import ArcGISTokenSession

        from tests.test_token import RecordingTokenSession

        session = RecordingTokenSession()
        # Set expires far in the future
        ts = ArcGISTokenSession(
            session=session,
            credentials=AGOLUserPass(username="user", password="password"),
            token="abc",
            expires=32503680000000,
        )
        # Should NOT need update — far future
        assert ts.token_needs_update() is False

    def test_token_needs_update_expired_token(self):
        """token_needs_update returns True for past expires."""
        from restgdf.utils.token import ArcGISTokenSession

        from tests.test_token import RecordingTokenSession

        session = RecordingTokenSession()
        ts = ArcGISTokenSession(
            session=session,
            credentials=AGOLUserPass(username="user", password="password"),
            token="abc",
            expires=1000000,  # epoch 1000 — way in the past
        )
        assert ts.token_needs_update() is True
