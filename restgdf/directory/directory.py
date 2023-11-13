from __future__ import annotations


import aiohttp

from restgdf.directory._crawl import fetch_all_data


class Directory:
    """A class for interacting with ArcGIS Server directories."""

    def __init__(
        self,
        url: str,
        session: aiohttp.ClientSession,
    ):
        """A class for interacting with ArcGIS Server directories."""
        self.url = url
        self.session = session
        self.data: dict
        self.metadata: dict

    async def prep(self):
        all_data = await fetch_all_data(self.session, self.url)
        self.data = all_data["services"]
        self.metadata = all_data["metadata"]

    @classmethod
    async def from_url(cls, url: str, **kwargs) -> Directory:
        """Create a Directory object from a url."""
        self = cls(url, **kwargs)
        await self.prep()
        return self
