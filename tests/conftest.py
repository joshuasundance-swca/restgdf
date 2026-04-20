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
