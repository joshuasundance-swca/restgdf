from __future__ import annotations

import aiohttp

from restgdf.utils import get_all_services_and_folders


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
        self.services: list[str]

    async def prep(self):
        self.services = get_all_services_and_folders(self.session, self.url)

    @classmethod
    async def from_url(cls, url: str, **kwargs) -> Directory:
        """Create a Directory object from a url."""
        self = cls(url, **kwargs)
        await self.prep()
        return self
