from __future__ import annotations

import inspect
import json
from typing import Any

import aioresponses.core as _aioresponses_core
import pytest
import pytest_asyncio
from aiohttp import ClientResponse as _AiohttpClientResponse
from aiohttp import ClientSession

# ---------------------------------------------------------------------------
# aioresponses x aiohttp 3.14 compatibility shim (TEST DOUBLE ONLY).
#
# aiohttp 3.14 added a required keyword-only ``stream_writer`` argument to
# ``ClientResponse.__init__`` (read to seed ``output_size`` when the request
# was already sent). aioresponses 0.7.9 builds its fake responses without it
# (``resp = response_class(method, url, **kwargs)`` in aioresponses/core.py),
# so under aiohttp>=3.14 every mocked request raises, verbatim:
#     TypeError: ClientResponse.__init__() missing 1 required keyword-only
#     argument: 'stream_writer'
#
# This patches ONLY the aioresponses test double -- never restgdf runtime code
# and never aiohttp itself -- injecting a no-op stream writer when (and only
# when) the installed aiohttp actually requires the argument. aioresponses
# always constructs the double with ``writer=None`` ("request already sent"),
# so ``ClientResponse.__init__`` reads exactly one attribute off it,
# ``stream_writer.output_size``; the stub below supplies that and nothing
# else, leaving every response attribute the tests assert on (status /
# headers / body / json payload -- reified by aioresponses afterwards)
# untouched.
#
# Inertness: detection is by signature introspection, never a version string.
# Under aiohttp<3.14 the ``stream_writer`` parameter is absent, the guard is
# False, and NOTHING below runs -- a complete no-op on the repo's aiohttp
# 3.13 pin.
#
# EXPIRY: remove this shim once aioresponses ships aiohttp-3.14 support
# upstream -- watch https://github.com/pnuckowski/aioresponses -- at which
# point the double stops needing the argument and the guard self-disarms.
# ---------------------------------------------------------------------------


def _client_response_requires_stream_writer() -> bool:
    """Return True iff aiohttp's ``ClientResponse`` requires ``stream_writer``.

    Signature introspection only -- present *and* without a default (i.e.
    aiohttp 3.14+). Never parses a version string, so it disarms the moment
    the argument is no longer required.
    """
    param = inspect.signature(_AiohttpClientResponse.__init__).parameters.get(
        "stream_writer",
    )
    return param is not None and param.default is inspect.Parameter.empty


if _client_response_requires_stream_writer():

    class _NoOpStreamWriter:
        """Minimal stand-in for aiohttp's stream writer in the aioresponses double.

        aioresponses passes ``writer=None`` ("request already sent"), so
        ``ClientResponse.__init__`` reads only ``stream_writer.output_size``.
        Nothing else about a real writer is exercised for a pre-fed fake body.
        """

        output_size = 0

    class _StreamWriterShimResponse(_aioresponses_core.ClientResponse):  # type: ignore[misc,valid-type]
        """aioresponses response double that supplies aiohttp 3.14's ``stream_writer``.

        Base class is bound to the *current* ``aioresponses.core.ClientResponse``
        (the real aiohttp class) at definition time; the module attribute is
        then repointed at this subclass so aioresponses' default response
        construction picks it up via ``__getattr__`` on the module global.
        """

        def __init__(self, *args: object, **kwargs: object) -> None:
            kwargs.setdefault("stream_writer", _NoOpStreamWriter())
            super().__init__(*args, **kwargs)  # type: ignore[arg-type]

    _aioresponses_core.ClientResponse = _StreamWriterShimResponse


def pytest_addoption(parser):
    parser.addoption(
        "--run-network",
        action="store_true",
        default=False,
        help="run tests marked as requiring live network access",
    )
    parser.addoption(
        "--run-stress",
        action="store_true",
        default=False,
        help="run tests marked as resource-intensive or property-based",
    )


def pytest_collection_modifyitems(config, items):
    skip_network = None
    if not config.getoption("--run-network"):
        skip_network = pytest.mark.skip(
            reason="network test; pass --run-network to include live-service checks",
        )

    skip_stress = None
    if not config.getoption("--run-stress"):
        skip_stress = pytest.mark.skip(
            reason="stress test; pass --run-stress to include resource-intensive checks",
        )

    for item in items:
        if skip_network is not None and "network" in item.keywords:
            item.add_marker(skip_network)
        if skip_stress is not None and "stress" in item.keywords:
            item.add_marker(skip_stress)


@pytest_asyncio.fixture
async def client_session():
    async with ClientSession() as session:
        yield session


@pytest.fixture
def feature_layer_metadata():
    return {
        "name": "Test Layer",
        "type": "Feature Layer",
        "fields": [
            {"name": "OBJECTID", "type": "esriFieldTypeOID"},
            {"name": "CITY", "type": "esriFieldTypeString"},
            {"name": "STATUS", "type": "esriFieldTypeString"},
        ],
        "maxRecordCount": 2,
        "advancedQueryCapabilities": {"supportsPagination": True},
    }


@pytest.fixture
def sample_feature_gdf():
    from geopandas import GeoDataFrame
    from shapely.geometry import Point

    return GeoDataFrame(
        {
            "OBJECTID": [1, 2],
            "CITY": ["DAYTONA", "ORMOND"],
            "geometry": [Point(0, 0), Point(1, 1)],
        },
        crs="EPSG:4326",
    )


# ---------------------------------------------------------------------------
# Shared fake-session helpers (Phase 0 harness).
#
# These consolidate the ad-hoc MockRequestContext / MockArcGISSession /
# MockFeatureLayerSession patterns that currently live inline across test
# modules. New characterization and compatibility tests use these; existing
# inline mocks are left untouched so we avoid churning already-green tests.
# ---------------------------------------------------------------------------


class FakeResponse:
    """Minimal async response supporting the shape used by restgdf helpers."""

    def __init__(self, payload: Any):
        self.payload = payload

    def __await__(self):
        async def _response() -> FakeResponse:
            return self

        return _response().__await__()

    async def __aenter__(self) -> FakeResponse:
        return self

    async def __aexit__(self, exc_type, exc_value, traceback) -> None:
        return None

    async def json(self, content_type: str | None = None):
        return self.payload

    async def text(self) -> str:
        return json.dumps(self.payload)

    def raise_for_status(self) -> None:
        return None


class FakeSession:
    """Record every get/post call and serve a scripted response per call.

    Tests push payloads onto ``post_responses`` / ``get_responses`` queues
    (falling back to the ``default_*`` payload when empty). All call args
    are captured on ``post_calls`` / ``get_calls`` for assertions.
    """

    def __init__(
        self,
        *,
        default_post: Any = None,
        default_get: Any = None,
    ):
        self.default_post = default_post if default_post is not None else {"ok": True}
        self.default_get = default_get if default_get is not None else {"ok": True}
        # T8 (R-74): after the GET/POST length-based routing change, the
        # same logical ArcGIS request may flip between ``session.post`` and
        # ``session.get`` depending on the encoded body size. We unify the
        # recorded-call and scripted-response queues here so pre-existing
        # tests that assert on ``post_calls`` / ``post_responses`` keep
        # working without having to rewrite each call site individually.
        self._responses: list[Any] = []
        self.post_responses = self._responses
        self.get_responses = self._responses
        self._calls: list[tuple[str, dict]] = []
        self.post_calls = self._calls
        self.get_calls = self._calls

    def _snapshot_kwargs(self, kwargs: dict, *, body_key: str) -> dict:
        snapshot: dict = {}
        for key, value in kwargs.items():
            if isinstance(value, dict):
                snapshot[key] = dict(value)
            else:
                snapshot[key] = value
        # Mirror the body under both ``data`` (POST) and ``params`` (GET)
        # so tests written against the legacy POST-only contract keep
        # resolving ``kwargs["data"]`` when a short request now flips to
        # GET (and vice-versa).
        mirror_key = "params" if body_key == "data" else "data"
        if body_key in snapshot and mirror_key not in snapshot:
            snapshot[mirror_key] = snapshot[body_key]
        return snapshot

    def post(self, url: str, **kwargs) -> FakeResponse:
        self._calls.append((url, self._snapshot_kwargs(kwargs, body_key="data")))
        payload = self._responses.pop(0) if self._responses else self.default_post
        return FakeResponse(payload)

    def get(self, url: str, **kwargs) -> FakeResponse:
        self._calls.append((url, self._snapshot_kwargs(kwargs, body_key="params")))
        payload = self._responses.pop(0) if self._responses else self.default_get
        return FakeResponse(payload)


@pytest.fixture
def fake_session() -> FakeSession:
    """Drop-in session fixture for Phase 0+ characterization tests."""

    return FakeSession()


from tests._telemetry_utils import _telemetry_provider  # noqa: E402, F401
from tests._telemetry_utils import memory_exporter  # noqa: E402, F401
