from __future__ import annotations

import aiohttp
from typing import Optional, Union

from restgdf.utils.getinfo import get_metadata
from restgdf.utils.crawl import fetch_all_data
from restgdf.utils.token import ArcGISTokenSession


class Directory:
    """A class for interacting with ArcGIS Server directories."""

    def __init__(
        self,
        url: str,
        session: Union[aiohttp.ClientSession, ArcGISTokenSession],
        token: Optional[str] = None,
    ):
        """A class for interacting with ArcGIS Server directories."""
        self.url = url
        self.session = session
        self.token = token
        self.services: Optional[list[dict]] = None
        self.services_with_feature_count: Optional[list[dict]] = None
        self.metadata: Optional[dict] = None

    async def prep(self):
        self.metadata = await get_metadata(self.url, self.session, self.token)

    @classmethod
    async def from_url(cls, url: str, **kwargs) -> Directory:
        """Create a Directory object from a url."""
        self = cls(url, **kwargs)
        await self.prep()
        return self

    async def crawl(self, return_feature_count: bool = False) -> list[dict]:
        if return_feature_count:
            if self.services_with_feature_count is None:
                all_data = await fetch_all_data(
                    self.session,
                    self.url,
                    self.token,
                    return_feature_count=True,
                )
                self.services_with_feature_count = all_data["services"]
            self.services = self.services_with_feature_count
            return self.services_with_feature_count

        if self.services is None:
            all_data = await fetch_all_data(
                self.session,
                self.url,
                self.token,
                return_feature_count=False,
            )
            self.services = all_data["services"]
        return self.services

    def filter_directory_layers(self, layer_type: str) -> list[dict]:
        if self.services is None:
            raise ValueError("You must call .crawl() before filtering layers.")
        return [
            layer
            for service in self.services
            for layer in service.get("metadata", {}).get("layers", [])
            if layer["type"] == layer_type
        ]

    def feature_layers(self) -> list[dict]:
        return self.filter_directory_layers("Feature Layer")

    def rasters(self) -> list[dict]:
        return self.filter_directory_layers("Raster Layer")
