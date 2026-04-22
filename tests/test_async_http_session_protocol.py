"""Tests for :class:`restgdf._client._protocols.AsyncHTTPSession` (BL-17)."""

from __future__ import annotations

import asyncio

import aiohttp

from restgdf._client import AsyncHTTPSession as AsyncHTTPSessionReexport
from restgdf._client._protocols import AsyncHTTPSession


def test_is_runtime_checkable_protocol() -> None:
    assert getattr(AsyncHTTPSession, "_is_protocol", False) is True
    assert getattr(AsyncHTTPSession, "_is_runtime_protocol", False) is True


def test_aiohttp_client_session_satisfies_protocol() -> None:
    async def _check() -> None:
        async with aiohttp.ClientSession() as session:
            assert isinstance(session, AsyncHTTPSession)

    asyncio.run(_check())


def test_reexport_identity() -> None:
    assert AsyncHTTPSessionReexport is AsyncHTTPSession


def test_empty_object_does_not_satisfy_protocol() -> None:
    class Bare:
        pass

    assert not isinstance(Bare(), AsyncHTTPSession)


def test_duck_typed_fake_satisfies_protocol() -> None:
    class FakeSession:
        closed = False

        async def close(self) -> None:
            return None

        def get(self, url, **kwargs):  # type: ignore[no-untyped-def]
            return None

        def post(self, url, **kwargs):  # type: ignore[no-untyped-def]
            return None

    assert isinstance(FakeSession(), AsyncHTTPSession)


def test_partial_shape_does_not_satisfy_protocol() -> None:
    class PartialSession:
        closed = False

        async def close(self) -> None:
            return None

        # Missing `post` — runtime_checkable Protocol must reject this.
        def get(self, url, **kwargs):  # type: ignore[no-untyped-def]
            return None

    assert not isinstance(PartialSession(), AsyncHTTPSession)
