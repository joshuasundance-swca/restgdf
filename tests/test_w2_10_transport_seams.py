"""W2-10 (CONFIG-01 / AUTH-03): user_agent + verify_ssl at the token/_http seams.

Two application-seam wirings land here (part B of the consolidated
verify_ssl/user_agent trio; part A is the ``TransportConfig`` source of truth
in ``restgdf._config``, part C is the ``get_gdf`` connector in ``getgdf``):

1. ``restgdf.utils._http.default_headers`` sources the ``User-Agent`` default
   from ``get_config().transport.user_agent`` (the data-path UA source of
   truth) instead of a hardcoded ``"Mozilla/5.0"``.
2. ``ArcGISTokenSession._call_with_auth_retry`` forwards the token session's
   own ``self.verify_ssl`` to token-attached **data** requests via
   ``setdefault`` (never clobbering a caller-supplied ``ssl=``), mirroring the
   existing ``/generateToken`` POST plumbing (BL-05).

Note on scope: the token session's ``verify_ssl`` is a deliberate *per-session*
override (``TokenSessionConfig.verify_ssl`` / the dataclass field). Per the
W3-1 source-of-truth decision, the token path does NOT read the process-wide
``get_config().transport.verify_ssl`` singleton -- that governs library-owned
bare sessions (the ``get_gdf`` connector, W4-5). So these tests drive
``self.verify_ssl`` directly, not ``RESTGDF_TRANSPORT_VERIFY_SSL``.
"""

from __future__ import annotations

import pytest

from restgdf import get_config, reset_config_cache
from restgdf.utils._http import default_headers
from restgdf.utils.token import AGOLUserPass, ArcGISTokenSession

from tests.test_token import RecordingTokenSession

_FAR_FUTURE_MS = 32503680000000  # year 3000 in epoch-ms; token never "needs update"


# ── user_agent: the _http data-path header seam ──────────────────────


def test_default_headers_uses_configured_user_agent(monkeypatch) -> None:
    """``default_headers`` emits the configured ``transport.user_agent``.

    Real-consumer proof: ``default_headers`` is the function every ArcGIS
    data-path call site (``_query``/``_stats``/``getgdf``) merges to build
    its wire headers.
    """
    monkeypatch.setenv("RESTGDF_TRANSPORT_USER_AGENT", "acme-crawler/9.9")
    reset_config_cache()
    try:
        assert default_headers()["User-Agent"] == "acme-crawler/9.9"
    finally:
        monkeypatch.delenv("RESTGDF_TRANSPORT_USER_AGENT", raising=False)
        reset_config_cache()


def test_default_headers_default_is_config_default_not_mozilla() -> None:
    """The default UA is the ``TransportConfig`` default, not ``Mozilla/5.0``."""
    reset_config_cache()
    expected = get_config().transport.user_agent
    assert default_headers()["User-Agent"] == expected
    assert default_headers()["User-Agent"] != "Mozilla/5.0"


def test_default_headers_caller_user_agent_still_wins() -> None:
    """An explicit caller ``User-Agent`` still overrides the config default."""
    assert (
        default_headers({"User-Agent": "caller/1.0"})["User-Agent"] == "caller/1.0"
    )


def test_default_headers_config_read_at_call_time_not_import_time(
    monkeypatch,
) -> None:
    """The UA is resolved per call (cache-reset semantics), not frozen once.

    Guards against a module-level ``get_config()`` freeze: a fresh env value
    plus ``reset_config_cache()`` must be observed by the very next call.
    """
    reset_config_cache()
    assert default_headers()["User-Agent"] == get_config().transport.user_agent
    monkeypatch.setenv("RESTGDF_TRANSPORT_USER_AGENT", "second-value/2.0")
    reset_config_cache()
    try:
        assert default_headers()["User-Agent"] == "second-value/2.0"
    finally:
        monkeypatch.delenv("RESTGDF_TRANSPORT_USER_AGENT", raising=False)
        reset_config_cache()


# ── verify_ssl: the token-attached data-request seam ─────────────────


def _make_token_session(session, *, verify_ssl: bool) -> ArcGISTokenSession:
    return ArcGISTokenSession(
        session=session,
        credentials=AGOLUserPass(username="u", password="p"),
        token="live-token",
        expires=_FAR_FUTURE_MS,
        verify_ssl=verify_ssl,
    )


@pytest.mark.asyncio
async def test_token_get_data_request_forwards_verify_ssl_false() -> None:
    session = RecordingTokenSession()
    ts = _make_token_session(session, verify_ssl=False)

    await ts.get("https://example.com/layer/0/query", params={"where": "1=1"})

    assert len(session.get_calls) == 1
    _, kwargs = session.get_calls[0]
    assert kwargs.get("ssl") is False


@pytest.mark.asyncio
async def test_token_post_data_request_forwards_verify_ssl_false() -> None:
    session = RecordingTokenSession()
    ts = _make_token_session(session, verify_ssl=False)

    await ts.post("https://example.com/layer/0/query", data={"where": "1=1"})

    assert len(session.post_calls) == 1
    _, kwargs = session.post_calls[0]
    assert kwargs.get("ssl") is False


@pytest.mark.asyncio
async def test_token_data_request_forwards_verify_ssl_true() -> None:
    session = RecordingTokenSession()
    ts = _make_token_session(session, verify_ssl=True)

    await ts.get("https://example.com/layer/0/query", params={"where": "1=1"})

    _, kwargs = session.get_calls[0]
    assert kwargs.get("ssl") is True


@pytest.mark.asyncio
async def test_token_data_request_caller_ssl_not_clobbered() -> None:
    """A caller-supplied ``ssl=`` survives (``setdefault``, not overwrite)."""
    session = RecordingTokenSession()
    ts = _make_token_session(session, verify_ssl=False)

    await ts.get(
        "https://example.com/layer/0/query",
        params={"where": "1=1"},
        ssl=True,
    )

    _, kwargs = session.get_calls[0]
    assert kwargs.get("ssl") is True
