from __future__ import annotations

import pytest
import pytest_asyncio
from aiohttp import ClientSession
from geopandas import GeoDataFrame
from shapely.geometry import Point


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
    return GeoDataFrame(
        {
            "OBJECTID": [1, 2],
            "CITY": ["DAYTONA", "ORMOND"],
            "geometry": [Point(0, 0), Point(1, 1)],
        },
        crs="EPSG:4326",
    )
