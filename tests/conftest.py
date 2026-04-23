from __future__ import annotations

import json
from typing import Any

import pytest
import pytest_asyncio
from aiohttp import ClientSession


def pytest_addoption(parser):
    parser.addoption(
        "--run-network",
        action="store_true",
        default=False,
        help="run tests marked as requiring live network access",
    )


def pytest_collection_modifyitems(config, items):
    if config.getoption("--run-network"):
        return

    skip_network = pytest.mark.skip(
        reason="network test; pass --run-network to include live-service checks",
    )
    for item in items:
        if "network" in item.keywords:
            item.add_marker(skip_network)


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
