"""BL-15 red tests: structured auth.refresh.* log events.

RED-first — these fail until feat(BL-15) emits the events.
"""

from __future__ import annotations

import logging

import pytest

from restgdf._models.credentials import AGOLUserPass


class TestAuthRefreshLogEvents:
    """update_token must emit auth.refresh.start / .success / .failure events."""

    @pytest.mark.asyncio
    async def test_refresh_start_event_logged(self, caplog):
        from tests.test_token import RecordingTokenSession

        from restgdf.utils.token import ArcGISTokenSession

        session = RecordingTokenSession()
        ts = ArcGISTokenSession(
            session=session,
            credentials=AGOLUserPass(username="user", password="password"),
        )

        with caplog.at_level(logging.DEBUG, logger="restgdf.auth"):
            await ts.update_token()

        messages = [r.message for r in caplog.records if "restgdf.auth" in r.name]
        assert any(
            "auth.refresh.start" in m for m in messages
        ), f"Expected 'auth.refresh.start' in auth log, got: {messages}"

    @pytest.mark.asyncio
    async def test_refresh_success_event_logged(self, caplog):
        from tests.test_token import RecordingTokenSession

        from restgdf.utils.token import ArcGISTokenSession

        session = RecordingTokenSession()
        ts = ArcGISTokenSession(
            session=session,
            credentials=AGOLUserPass(username="user", password="password"),
        )

        with caplog.at_level(logging.DEBUG, logger="restgdf.auth"):
            await ts.update_token()

        messages = [r.message for r in caplog.records if "restgdf.auth" in r.name]
        assert any(
            "auth.refresh.success" in m for m in messages
        ), f"Expected 'auth.refresh.success' in auth log, got: {messages}"

    @pytest.mark.asyncio
    async def test_refresh_failure_event_logged(self, caplog):
        from tests.test_token import RecordingTokenSession

        from restgdf.utils.token import ArcGISTokenSession

        session = RecordingTokenSession()
        ts = ArcGISTokenSession(
            session=session,
            credentials=AGOLUserPass(username="user", password="password"),
        )
        # Force a failure by removing credentials after construction
        ts.credentials = None

        with caplog.at_level(logging.DEBUG, logger="restgdf.auth"):
            try:
                await ts.update_token()
            except Exception:
                pass

        messages = [r.message for r in caplog.records if "restgdf.auth" in r.name]
        assert any(
            "auth.refresh.failure" in m for m in messages
        ), f"Expected 'auth.refresh.failure' in auth log, got: {messages}"
