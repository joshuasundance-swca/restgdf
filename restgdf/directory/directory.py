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
        token: str | None = None,
    ):
        """A class for interacting with ArcGIS Server directories."""
        self.url = url
        self.session = session
        self.token = token
        self.services: dict | None = None
        self.metadata: dict | None = None

    async def prep(self):
        self.metadata = await get_metadata(self.url, self.session, self.token)

    @classmethod
    async def from_url(cls, url: str, **kwargs) -> Directory:
        """Create a Directory object from a url."""
        self = cls(url, **kwargs)
        await self.prep()
        return self

    async def crawl(self, return_feature_count: bool = False) -> dict:
        if self.services is None:
            all_data = await fetch_all_data(
                self.session,
                self.url,
                self.token,
                return_feature_count,
            )
            self.services = all_data["services"]
        return self.services

    def filter_directory_layers(self, layer_type: str) -> list[dict]:
        if self.services is None:
            raise ValueError("You must call .crawl() before filtering layers.")
        return [
            layer
            for service in self.services
            for layer in service["metadata"]["layers"]
            if layer["type"] == layer_type
        ]

    def feature_layers(self) -> list[dict]:
        return self.filter_directory_layers("Feature Layer")

    def rasters(self) -> list[dict]:
        return self.filter_directory_layers("Raster Layer")
