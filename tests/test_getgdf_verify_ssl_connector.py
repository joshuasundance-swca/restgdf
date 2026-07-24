"""W4-5 (CONFIG-01 / AUTH-03 part C): the ``get_gdf`` bare session must be
built with a ``TCPConnector`` whose ``ssl`` policy comes from the configured
``TransportConfig.verify_ssl`` source of truth (W3-1).

Before this change ``get_gdf`` built ``ClientSession()`` with the default
connector (``ssl=True``), so a caller who set
``RESTGDF_TRANSPORT_VERIFY_SSL=false`` (self-signed ArcGIS Enterprise) still
saw TLS verification on the library-owned data-request path. These tests drive
the REAL consumer (``get_gdf`` with ``session=None``) via the env var + cache
reset and introspect the connector the library actually built.

A caller-supplied session is passed through untouched -- its own connector owns
its TLS policy (anti-recommendation: never override a caller connector's SSL).
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any
from unittest.mock import patch

import pytest

from restgdf import reset_config_cache
from restgdf.utils.getgdf import get_gdf


@pytest.fixture
def _reset_config_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Reset the config cache around the test so env overrides take effect
    and do not leak into sibling tests (LRU size-1 singleton)."""
    monkeypatch.delenv("RESTGDF_TRANSPORT_VERIFY_SSL", raising=False)
    reset_config_cache()
    yield
    reset_config_cache()


class _ConnectorSslCapture:
    """gdf_by_concat stand-in that snapshots the session's connector ssl
    policy *at call time* -- get_gdf closes an owned session in its
    ``finally`` block (which nulls ``ClientSession.connector``), so the
    connector must be introspected before get_gdf returns."""

    def __init__(self) -> None:
        self.ssl: Any = "NOT_CALLED"
        self.session: Any = None

    async def __call__(self, url: str, session: Any, **kwargs: Any) -> str:
        self.session = session
        connector = getattr(session, "connector", "NO_CONNECTOR")
        # aiohttp stores the resolved ssl policy on ``TCPConnector._ssl``.
        self.ssl = getattr(connector, "_ssl", "NO_CONNECTOR")
        return "sentinel"


class _PassthroughSession:
    """Caller-supplied session double: records only that it was used as-is."""

    def __init__(self) -> None:
        self._closed = False

    @property
    def closed(self) -> bool:
        return self._closed

    async def close(self) -> None:
        self._closed = True


@pytest.mark.asyncio
async def test_get_gdf_owned_session_connector_honors_env_verify_ssl(
    monkeypatch: pytest.MonkeyPatch,
    _reset_config_env: None,
) -> None:
    """``get_gdf(session=None)`` with ``RESTGDF_TRANSPORT_VERIFY_SSL=false``
    must build a session whose connector carries ``ssl=False``.

    RED before W4-5: the bare ``ClientSession()`` has a default connector
    with ``_ssl is True``, so this assertion fails (no configured connector).
    """
    monkeypatch.setenv("RESTGDF_TRANSPORT_VERIFY_SSL", "false")
    reset_config_cache()

    capture = _ConnectorSslCapture()
    with patch("restgdf.utils.getgdf.gdf_by_concat", new=capture):
        result = await get_gdf("https://example.com/layer/0", session=None)

    assert result == "sentinel"
    # Introspect the REAL aiohttp connector the library built (not a wrapper
    # dict): the configured verify_ssl=False must reach ``TCPConnector.ssl``.
    assert capture.ssl is False


@pytest.mark.asyncio
async def test_get_gdf_owned_session_connector_defaults_verify_ssl_true(
    _reset_config_env: None,
) -> None:
    """With no override, the owned session's connector keeps ``ssl=True``
    (the config default) -- the fix must not silently disable TLS."""
    reset_config_cache()

    capture = _ConnectorSslCapture()
    with patch("restgdf.utils.getgdf.gdf_by_concat", new=capture):
        await get_gdf("https://example.com/layer/0", session=None)

    assert capture.ssl is True


@pytest.mark.asyncio
async def test_get_gdf_passes_caller_session_through_unchanged(
    monkeypatch: pytest.MonkeyPatch,
    _reset_config_env: None,
) -> None:
    """A caller-supplied session is used as-is: no connector override even
    when ``RESTGDF_TRANSPORT_VERIFY_SSL=false`` (the caller connector owns TLS)."""
    monkeypatch.setenv("RESTGDF_TRANSPORT_VERIFY_SSL", "false")
    reset_config_cache()

    supplied = _PassthroughSession()
    capture = _ConnectorSslCapture()
    with patch("restgdf.utils.getgdf.gdf_by_concat", new=capture):
        await get_gdf("https://example.com/layer/0", session=supplied)

    # The exact object is threaded through untouched (no connector rebuilt),
    # and get_gdf did NOT close it (owns_session is False).
    assert capture.session is supplied
    assert supplied.closed is False
