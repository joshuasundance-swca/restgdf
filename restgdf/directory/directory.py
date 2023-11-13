from __future__ import annotations


import aiohttp

from restgdf.utils.getinfo import get_metadata
from restgdf.utils.crawl import fetch_all_data


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
        self.services: dict | None = None
        self.metadata: dict | None = None

    async def prep(self):
        self.metadata = await get_metadata(self.url, self.session)

    async def crawl(self):
        if self.services is None:
            all_data = await fetch_all_data(self.session, self.url)
            self.services = all_data["services"]
        return self.services

    @classmethod
    async def from_url(cls, url: str, **kwargs) -> Directory:
        """Create a Directory object from a url."""
        self = cls(url, **kwargs)
        await self.prep()
        return self
