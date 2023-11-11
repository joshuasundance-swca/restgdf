from __future__ import annotations


import aiohttp

from restgdf.utils import fetch_all_data


class Directory:
    """A class for interacting with ArcGIS Server directories."""

    def __init__(
        self,
        url: str,
        session: aiohttp.ClientSession,
        token: str | None = None,
    ):
        """A class for interacting with ArcGIS Server directories."""
        self.url = url
        self.session = session
        self.data: dict
        self.token = token

    async def prep(self):
        self.data = await fetch_all_data(self.session, self.url, self.token)

    @classmethod
    async def from_url(cls, url: str, token: str | None = None, **kwargs) -> Directory:
        """Create a Directory object from a url."""
        self = cls(url, token=token, **kwargs)
        await self.prep()
        return self
