"""R-71: ArcGISTokenSession must satisfy AsyncHTTPSession Protocol.

These tests lock in that :class:`~restgdf.utils.token.ArcGISTokenSession`
exposes ``close()`` and ``closed`` mirroring its underlying
:class:`aiohttp.ClientSession`, and that the Protocol is
``runtime_checkable`` so adapter classes can be validated via
``isinstance``.
"""

from __future__ import annotations

import aiohttp
import pytest

from restgdf._client._protocols import AsyncHTTPSession
from restgdf.utils.token import ArcGISTokenSession


def test_protocol_is_runtime_checkable() -> None:
    """AsyncHTTPSession must be decorated @runtime_checkable."""
    # _is_runtime_protocol is set by typing.runtime_checkable
    assert getattr(AsyncHTTPSession, "_is_runtime_protocol", False) is True


@pytest.mark.asyncio
async def test_arcgis_token_session_is_asynchttpsession() -> None:
    """ArcGISTokenSession instances must pass isinstance(AsyncHTTPSession)."""
    async with aiohttp.ClientSession() as inner:
        tok = ArcGISTokenSession(session=inner)
        assert isinstance(tok, AsyncHTTPSession)


@pytest.mark.asyncio
async def test_arcgis_token_session_closed_mirrors_inner() -> None:
    """``.closed`` must delegate to the underlying aiohttp.ClientSession."""
    inner = aiohttp.ClientSession()
    tok = ArcGISTokenSession(session=inner)
    assert tok.closed is False
    await inner.close()
    assert tok.closed is True


@pytest.mark.asyncio
async def test_arcgis_token_session_close_closes_inner() -> None:
    """``await .close()`` must close the underlying aiohttp.ClientSession."""
    inner = aiohttp.ClientSession()
    tok = ArcGISTokenSession(session=inner)
    assert inner.closed is False
    await tok.close()
    assert inner.closed is True
    assert tok.closed is True


@pytest.mark.asyncio
async def test_aiohttp_client_session_still_satisfies_protocol() -> None:
    """Regression: aiohttp.ClientSession itself must still match the Protocol."""
    async with aiohttp.ClientSession() as s:
        assert isinstance(s, AsyncHTTPSession)
