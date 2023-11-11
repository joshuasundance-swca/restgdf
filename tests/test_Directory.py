import pytest
from aiohttp import ClientSession

from restgdf.directory.directory import Directory


@pytest.mark.asyncio
async def test_directory():
    async with ClientSession() as s:
        directory = await Directory.from_url(
            "https://maps1.vcgov.org/arcgis/rest/services",
            session=s,
        )
        assert len(directory.data) > 0
