"""Referer rider (#175 review NOTE-1): request-time Referer propagation.

Before 3.1, `AGOLUserPass(referer=...)` was honoured only at token-mint time
(the ArcGIS `client` field switches to `"referer"` and `referer=<url>` joins
the `/generateToken` payload), but restgdf never sent a matching `Referer`
HTTP header on the *subsequent data requests*. ArcGIS binds a
`client="referer"` token to that referer and can reject queries whose
`Referer` header does not match (498/499), so a referer-bound session was
incoherent end-to-end.

These tests assert that a referer-bound token session attaches a matching
`Referer` header on its data requests (through the token session's
header-injection seam) -- and, critically, that a requestip (non-referer)
session attaches NO `Referer` header (no referer leak).
"""

from __future__ import annotations

import pytest

from restgdf.utils.token import AGOLUserPass, ArcGISTokenSession

from tests.test_token import RecordingTokenSession

_FAR_FUTURE_MS = 32503680000000  # token never "needs update"
_REFERER = "https://myapp.example.com"


def _session(recording, *, referer: str | None) -> ArcGISTokenSession:
    return ArcGISTokenSession(
        session=recording,
        credentials=AGOLUserPass(username="u", password="p", referer=referer),
        token="live-token",
        expires=_FAR_FUTURE_MS,
    )


@pytest.mark.asyncio
async def test_referer_bound_session_sends_referer_header_on_get() -> None:
    recording = RecordingTokenSession()
    ts = _session(recording, referer=_REFERER)

    await ts.get("https://example.com/layer/0/query", params={"where": "1=1"})

    _, kwargs = recording.get_calls[0]
    assert kwargs["headers"].get("Referer") == _REFERER


@pytest.mark.asyncio
async def test_referer_bound_session_sends_referer_header_on_post() -> None:
    recording = RecordingTokenSession()
    ts = _session(recording, referer=_REFERER)

    await ts.post("https://example.com/layer/0/query", data={"where": "1=1"})

    _, kwargs = recording.post_calls[0]
    assert kwargs["headers"].get("Referer") == _REFERER


@pytest.mark.asyncio
async def test_referer_header_matches_mint_referer() -> None:
    """The data-request Referer matches the referer sent at mint time."""
    recording = RecordingTokenSession()
    ts = _session(recording, referer=_REFERER)

    await ts.get("https://example.com/layer/0/query", params={"where": "1=1"})

    _, kwargs = recording.get_calls[0]
    assert kwargs["headers"].get("Referer") == ts.token_request_payload["referer"]


@pytest.mark.asyncio
async def test_requestip_session_sends_no_referer_header() -> None:
    """A non-referer (client='requestip') session leaks NO Referer header."""
    recording = RecordingTokenSession()
    ts = _session(recording, referer=None)

    await ts.get("https://example.com/layer/0/query", params={"where": "1=1"})

    _, kwargs = recording.get_calls[0]
    assert "Referer" not in kwargs["headers"]


@pytest.mark.asyncio
async def test_credentialless_token_session_sends_no_referer_header() -> None:
    """A bare token session (no credentials) attaches no Referer header."""
    recording = RecordingTokenSession()
    ts = ArcGISTokenSession(
        session=recording,
        token="live-token",
        expires=_FAR_FUTURE_MS,
    )

    await ts.get("https://example.com/layer/0/query", params={"where": "1=1"})

    _, kwargs = recording.get_calls[0]
    assert "Referer" not in kwargs["headers"]
