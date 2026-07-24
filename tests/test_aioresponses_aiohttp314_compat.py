"""Regression: aioresponses must serve mocked responses under aiohttp 3.14.

aiohttp 3.14 added a required keyword-only ``stream_writer`` argument to
``ClientResponse.__init__``. aioresponses 0.7.9 constructs its response
double without it, so before the ``tests/conftest.py`` shim every mocked
request raised, verbatim::

    TypeError: ClientResponse.__init__() missing 1 required keyword-only
    argument: 'stream_writer'

(raised at ``aioresponses/core.py`` ``RequestMatch._build_response`` ->
``resp = response_class(method, url, **kwargs)``), reached from restgdf's
real consumer path ``restgdf.utils._http._arcgis_request``.

These tests drive that real path -- ``aioresponses`` payload mock ->
``_arcgis_request`` (both the GET and the POST verb it selects) -> parsed
JSON round-trip. If the conftest shim is removed while aiohttp>=3.14 is
installed, the aioresponses construction fails and these tests error with the
``stream_writer`` ``TypeError`` above. Under aiohttp<3.14 the argument does
not exist, the shim is a no-op, and these tests pass unchanged.
"""

from __future__ import annotations

import inspect
import re

import pytest
from aiohttp import ClientResponse, ClientSession
from aioresponses import aioresponses

from restgdf.utils._http import _ARCGIS_URL_BODY_LIMIT, _arcgis_request, _choose_verb

# Match the base query URL with or without an encoded query string, so the
# GET path (which appends ``?f=json&...``) is matched the same as POST.
_QUERY_URL = "https://svc.example/arcgis/rest/services/Demo/FeatureServer/0/query"
_QUERY_URL_RE = re.compile(re.escape(_QUERY_URL) + r"(\?.*)?$")


def _aiohttp_requires_stream_writer() -> bool:
    param = inspect.signature(ClientResponse.__init__).parameters.get("stream_writer")
    return param is not None and param.default is inspect.Parameter.empty


@pytest.mark.asyncio
async def test_arcgis_request_get_round_trips_through_aioresponses():
    """Short body -> GET verb -> aioresponses payload round-trips intact."""
    body = {"f": "json", "returnCountOnly": True, "where": "1=1"}
    # Guard the premise: this body must actually route to GET so the test
    # exercises the GET construction path (not POST).
    assert _choose_verb(_QUERY_URL, body=body) == "GET"

    async with ClientSession() as session:
        with aioresponses() as m:
            m.get(_QUERY_URL_RE, payload={"count": 42}, repeat=True)
            resp = await _arcgis_request(session, _QUERY_URL, body)
            data = await resp.json(content_type=None)

    assert data == {"count": 42}


@pytest.mark.asyncio
async def test_arcgis_request_post_round_trips_through_aioresponses():
    """Oversized body -> POST verb -> aioresponses payload round-trips intact."""
    # A where clause past the URL/body ceiling forces the POST branch of
    # ``_arcgis_request`` (the length-based router picks POST for >8k bodies).
    body = {"f": "json", "where": "x" * (_ARCGIS_URL_BODY_LIMIT + 1)}
    assert _choose_verb(_QUERY_URL, body=body) == "POST"

    async with ClientSession() as session:
        with aioresponses() as m:
            m.post(_QUERY_URL, payload={"count": 7}, repeat=True)
            resp = await _arcgis_request(session, _QUERY_URL, body)
            data = await resp.json(content_type=None)

    assert data == {"count": 7}


def test_stream_writer_shim_is_active_exactly_when_aiohttp_requires_it():
    """The conftest shim must be installed iff aiohttp requires ``stream_writer``.

    Proves both directions of the inertness contract from a single assertion:
    * aiohttp>=3.14 (argument required) -> aioresponses' response class is the
      shim subclass installed by conftest;
    * aiohttp<3.14 (argument absent) -> the class is left untouched.
    """
    import aioresponses.core as core

    if _aiohttp_requires_stream_writer():
        assert core.ClientResponse.__name__ == "_StreamWriterShimResponse"
        assert issubclass(core.ClientResponse, ClientResponse)
    else:
        # No-op path: conftest must not have repointed the class.
        assert core.ClientResponse is ClientResponse
