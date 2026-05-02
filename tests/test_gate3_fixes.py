"""Gate-3 rubber-duck findings: regression guards for v3-followup.

Covers three follow-up-on-follow-up fixes on top of T6–T11:

* **H1 (auth token leakage).** After T8 routes short ArcGIS requests
  through ``_choose_verb``, sessions using ``ArcGISTokenSession(transport=...)``
  with a non-header transport ("body" or "query") would have their
  token serialized into URL query parameters when the chosen verb was
  ``GET``. The fix forces ``POST`` whenever the session (or a wrapped
  inner session) reports a non-header transport.

* **H2 (ResilientSession awaitability).** ``_arcgis_request`` does
  ``await session.get(...) / await session.post(...)`` (matching the
  ``aiohttp.ClientSession`` pattern). ``ResilientSession`` declares it
  satisfies ``AsyncHTTPSession`` but its ``get``/``post`` returned an
  object that was only an async context manager. The fix makes
  ``_RetriedCtx`` both awaitable AND ``async with``-able, mirroring
  ``aiohttp._RequestContextManager``.

* **M1 (advertised_factor gate strictness).** T9's
  ``_advertised_max_record_count_factor`` must reject :class:`bool`
  instances (``True``/``False`` are subclasses of :class:`int`) and
  non-finite floats (``nan`` / ``inf``) so malformed vendor payloads
  fall through to the byte-identical pre-T9 code path.
"""

from __future__ import annotations

import math
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from restgdf import AGOLUserPass


# ---------------------------------------------------------------------------
# H1: ArcGISTokenSession(transport="body") must not take the GET path
# ---------------------------------------------------------------------------


class _FakeAuthSession:
    """Minimal duck-typed stand-in for ArcGISTokenSession."""

    def __init__(self, transport: str) -> None:
        self._transport = transport
        self.get = AsyncMock(return_value=SimpleNamespace(status=200))
        self.post = AsyncMock(return_value=SimpleNamespace(status=200))


@pytest.mark.asyncio
async def test_arcgis_request_forces_post_when_transport_is_body():
    """A short body must NOT be routed via GET when the session injects
    the token into the request payload. Otherwise the token would land
    in the URL query string (credential leak)."""
    from restgdf.utils._http import _arcgis_request

    session = _FakeAuthSession(transport="body")
    tiny_body = {"where": "1=1", "f": "json"}
    await _arcgis_request(session, "https://example/query", tiny_body)

    assert (
        session.post.await_count == 1
    ), "expected POST for body-transport auth session"
    assert session.get.await_count == 0
    # POST must send the body as data=, not params=.
    _, kwargs = session.post.call_args
    assert kwargs.get("data") == tiny_body


@pytest.mark.asyncio
async def test_arcgis_request_forces_post_when_transport_is_query():
    """Query-transport is semantically URL-bound but still a credential;
    pre-T8 behavior was POST (token serialized into body). Preserve that
    to avoid the observable wire shape changing silently."""
    from restgdf.utils._http import _arcgis_request

    session = _FakeAuthSession(transport="query")
    await _arcgis_request(session, "https://example/query", {"f": "json"})

    assert session.post.await_count == 1
    assert session.get.await_count == 0


@pytest.mark.asyncio
async def test_arcgis_request_still_uses_get_for_header_transport():
    """transport='header' is the safe default (token in HTTP header);
    short requests can use GET without leaking credentials."""
    from restgdf.utils._http import _arcgis_request

    session = _FakeAuthSession(transport="header")
    await _arcgis_request(session, "https://example/query", {"f": "json"})

    assert session.get.await_count == 1
    assert session.post.await_count == 0


@pytest.mark.asyncio
async def test_arcgis_request_walks_inner_for_wrapped_auth_session():
    """``ResilientSession(ArcGISTokenSession(..., transport='body'))``
    nests the auth session inside a wrapper. The guard must walk the
    ``_inner`` chain so wrapped token sessions still force POST."""
    from restgdf.utils._http import _arcgis_request

    inner = _FakeAuthSession(transport="body")
    outer = SimpleNamespace(
        _inner=inner,
        get=AsyncMock(return_value=SimpleNamespace(status=200)),
        post=AsyncMock(return_value=SimpleNamespace(status=200)),
    )
    await _arcgis_request(outer, "https://example/query", {"f": "json"})

    assert outer.post.await_count == 1
    assert outer.get.await_count == 0


@pytest.mark.asyncio
async def test_arcgis_request_does_not_loop_forever_on_wrapped_cycle():
    """Defensive guard: a malformed wrapper cycle must terminate rather
    than spinning forever while inspecting the transport chain."""
    from restgdf.utils._http import _arcgis_request

    session = SimpleNamespace(
        _transport=None,
        get=AsyncMock(return_value=SimpleNamespace(status=200)),
        post=AsyncMock(return_value=SimpleNamespace(status=200)),
    )
    session._inner = session

    await _arcgis_request(session, "https://example/query", {"f": "json"})

    assert session.get.await_count == 1
    assert session.post.await_count == 0


@pytest.mark.asyncio
async def test_arcgis_request_ignores_dynamic_mock_attrs_when_transport_missing():
    """AsyncMock sessions fabricate missing attrs via ``__getattr__``.

    Transport inspection must treat missing ``_transport`` / ``_inner``
    as absent instead of traversing synthetic mocks, which can explode
    call history and memory use during equality/comparison checks.
    """
    from restgdf.utils._http import _arcgis_request

    response = SimpleNamespace(status=200)
    session = AsyncMock()
    session.get = AsyncMock(return_value=response)
    session.post = AsyncMock(return_value=response)

    await _arcgis_request(session, "https://example/query", {"f": "json"})

    assert session.get.await_count == 1
    assert session.post.await_count == 0


@pytest.mark.asyncio
async def test_arcgis_request_forces_post_for_real_property_backed_token_session():
    from restgdf._models.credentials import TokenSessionConfig
    from restgdf.utils._http import _arcgis_request
    from restgdf.utils.token import ArcGISTokenSession

    class _InnerSession:
        def __init__(self) -> None:
            self.get = AsyncMock(return_value=SimpleNamespace(status=200))
            self.post = AsyncMock(return_value=SimpleNamespace(status=200))

        @property
        def closed(self) -> bool:
            return False

        async def close(self) -> None:
            return None

    inner = _InnerSession()
    auth_session = ArcGISTokenSession(
        session=inner,
        config=TokenSessionConfig(
            token_url="https://example.com/sharing/rest/generateToken",
            credentials=AGOLUserPass(username="alice", password="hunter2"),
            transport="body",
        ),
        token="secret-token",
        expires=9_999_999_999_999,
    )

    await _arcgis_request(auth_session, "https://example/query", {"f": "json"})

    assert inner.post.await_count == 1
    assert inner.get.await_count == 0


@pytest.mark.asyncio
async def test_arcgis_request_forces_post_for_resilient_wrapped_token_session():
    resilience = pytest.importorskip("restgdf.resilience")
    from restgdf._config import ResilienceConfig
    from restgdf._models.credentials import TokenSessionConfig
    from restgdf.utils._http import _arcgis_request
    from restgdf.utils.token import ArcGISTokenSession

    class _InnerSession:
        def __init__(self) -> None:
            self.get = AsyncMock(return_value=SimpleNamespace(status=200))
            self.post = AsyncMock(return_value=SimpleNamespace(status=200))

        @property
        def closed(self) -> bool:
            return False

        async def close(self) -> None:
            return None

    inner = _InnerSession()
    auth_session = ArcGISTokenSession(
        session=inner,
        config=TokenSessionConfig(
            token_url="https://example.com/sharing/rest/generateToken",
            credentials=AGOLUserPass(username="alice", password="hunter2"),
            transport="body",
        ),
        token="secret-token",
        expires=9_999_999_999_999,
    )
    session = resilience.ResilientSession(
        inner=auth_session,
        config=ResilienceConfig(enabled=True),
    )

    await _arcgis_request(session, "https://example/query", {"f": "json"})

    assert inner.post.await_count == 1
    assert inner.get.await_count == 0


def test_coerce_params_for_get_normalizes_bool_none_and_preserves_other_values():
    """Direct unit coverage for the GET-param normalization helper.

    ArcGIS request bodies can include bools from DEFAULTDICT and explicit
    ``None`` values. The helper must only normalize those two cases and
    leave all other scalar / sequence values untouched.
    """
    from restgdf.utils._http import _coerce_params_for_get

    result = _coerce_params_for_get(
        {
            "where": "1=1",
            "returnGeometry": True,
            "returnCountOnly": False,
            "outFields": None,
            "resultRecordCount": 1000,
            "objectIds": [1, 2, 3],
        },
    )

    assert result == {
        "where": "1=1",
        "returnGeometry": "true",
        "returnCountOnly": "false",
        "outFields": "",
        "resultRecordCount": 1000,
        "objectIds": [1, 2, 3],
    }


@pytest.mark.asyncio
async def test_arcgis_request_get_path_uses_normalized_params():
    """Short GET-routed requests must use the normalized param payload."""
    from restgdf.utils._http import _arcgis_request

    session = _FakeAuthSession(transport="header")
    await _arcgis_request(
        session,
        "https://example/query",
        {
            "returnGeometry": True,
            "returnCountOnly": False,
            "outFields": None,
            "f": "json",
        },
    )

    assert session.get.await_count == 1
    _, kwargs = session.get.call_args
    assert kwargs["params"] == {
        "returnGeometry": "true",
        "returnCountOnly": "false",
        "outFields": "",
        "f": "json",
    }


# ---------------------------------------------------------------------------
# H2: ResilientSession.get/post() must be both awaitable and async-ctxmgr
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resilient_session_get_is_awaitable():
    """``_arcgis_request`` does ``await session.get(url, ...)``. That
    pattern must work against :class:`ResilientSession` exactly like it
    works against :class:`aiohttp.ClientSession` and
    :class:`ArcGISTokenSession`."""
    resilience = pytest.importorskip("restgdf.resilience")
    from restgdf._config import ResilienceConfig

    response = SimpleNamespace(status=200, headers={}, read=AsyncMock(return_value=b""))

    class _Inner:
        closed = False

        async def close(self) -> None:
            return None

        def get(self, url, **kwargs):
            class _Ctx:
                async def __aenter__(_self):
                    return response

                async def __aexit__(_self, *args):
                    return None

                def __await__(_self):
                    async def _coro():
                        return response

                    return _coro().__await__()

            return _Ctx()

        post = get

    session = resilience.ResilientSession(
        inner=_Inner(),
        config=ResilienceConfig(enabled=True),
    )
    result = await session.get("http://test/query")
    assert result is response


@pytest.mark.asyncio
async def test_resilient_session_get_still_works_as_context_manager():
    """The pre-existing ``async with session.get(...) as resp:`` pattern
    must continue to work — adding ``__await__`` must not break it."""
    resilience = pytest.importorskip("restgdf.resilience")
    from restgdf._config import ResilienceConfig

    response = SimpleNamespace(status=200, headers={}, read=AsyncMock(return_value=b""))

    class _Inner:
        closed = False

        async def close(self) -> None:
            return None

        def get(self, url, **kwargs):
            class _Ctx:
                async def __aenter__(_self):
                    return response

                async def __aexit__(_self, *args):
                    return None

                def __await__(_self):
                    async def _coro():
                        return response

                    return _coro().__await__()

            return _Ctx()

        post = get

    session = resilience.ResilientSession(
        inner=_Inner(),
        config=ResilienceConfig(enabled=True),
    )
    async with session.get("http://test/query") as resp:
        assert resp is response


@pytest.mark.asyncio
async def test_resilient_session_async_with_calls_inner_aexit():
    resilience = pytest.importorskip("restgdf.resilience")
    from restgdf._config import ResilienceConfig

    response = SimpleNamespace(status=200, headers={}, read=AsyncMock(return_value=b""))
    exited = False

    class _Ctx:
        async def __aenter__(self):
            return response

        async def __aexit__(self, *args):
            nonlocal exited
            exited = True

    class _Inner:
        closed = False

        async def close(self) -> None:
            return None

        def get(self, url, **kwargs):
            return _Ctx()

        post = get

    session = resilience.ResilientSession(
        inner=_Inner(),
        config=ResilienceConfig(enabled=True),
    )
    async with session.get("http://test/query") as resp:
        assert resp is response
    assert exited is True


# ---------------------------------------------------------------------------
# M1: _advertised_max_record_count_factor must reject bool/nan/inf
# ---------------------------------------------------------------------------


def test_advertised_factor_rejects_bool_true():
    """``True`` is an ``int`` subclass; treating it as a numeric factor
    would silently wire ``advertised_factor=1.0`` and deviate from the
    pre-T9 byte-identical code path. Must return ``None``."""
    from restgdf.utils.getgdf import _advertised_max_record_count_factor

    metadata = {"advancedQueryCapabilities": {"maxRecordCountFactor": True}}
    assert _advertised_max_record_count_factor(metadata) is None


def test_advertised_factor_rejects_bool_false():
    from restgdf.utils.getgdf import _advertised_max_record_count_factor

    metadata = {"advancedQueryCapabilities": {"maxRecordCountFactor": False}}
    assert _advertised_max_record_count_factor(metadata) is None


def test_advertised_factor_rejects_missing_advanced_query_capabilities():
    from restgdf.utils.getgdf import _advertised_max_record_count_factor

    assert _advertised_max_record_count_factor({}) is None


def test_advertised_factor_rejects_nan_string():
    """``float('nan')`` is parseable but nonsensical as a factor."""
    from restgdf.utils.getgdf import _advertised_max_record_count_factor

    metadata = {"advancedQueryCapabilities": {"maxRecordCountFactor": "nan"}}
    assert _advertised_max_record_count_factor(metadata) is None


def test_advertised_factor_rejects_inf_string():
    from restgdf.utils.getgdf import _advertised_max_record_count_factor

    metadata = {"advancedQueryCapabilities": {"maxRecordCountFactor": "inf"}}
    assert _advertised_max_record_count_factor(metadata) is None


def test_advertised_factor_rejects_nan_float():
    from restgdf.utils.getgdf import _advertised_max_record_count_factor

    metadata = {"advancedQueryCapabilities": {"maxRecordCountFactor": math.nan}}
    assert _advertised_max_record_count_factor(metadata) is None


def test_advertised_factor_rejects_zero_and_negative_values():
    from restgdf.utils.getgdf import _advertised_max_record_count_factor

    for raw in (0, 0.0, -1, -0.5):
        metadata = {"advancedQueryCapabilities": {"maxRecordCountFactor": raw}}
        assert _advertised_max_record_count_factor(metadata) is None


def test_advertised_factor_still_accepts_normal_positive_values():
    """Regression guard: the hardening must not reject legitimate
    positive numeric values."""
    from restgdf.utils.getgdf import _advertised_max_record_count_factor

    for raw in (1, 2, 5, 10, 2.5, "4.0"):
        metadata = {"advancedQueryCapabilities": {"maxRecordCountFactor": raw}}
        result = _advertised_max_record_count_factor(metadata)
        assert result is not None and result > 0


def test_advertised_factor_accepts_typed_layer_metadata() -> None:
    from restgdf._models.responses import LayerMetadata
    from restgdf.utils.getgdf import _advertised_max_record_count_factor

    metadata = LayerMetadata(
        maxRecordCount=2000,
        advancedQueryCapabilities={"maxRecordCountFactor": 5},
    )

    assert _advertised_max_record_count_factor(metadata) == 5
