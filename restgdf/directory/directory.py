import aiohttp
from typing import Optional, Union

from restgdf._models.crawl import CrawlReport, CrawlServiceEntry
from restgdf._models.responses import LayerMetadata
from restgdf.utils.getinfo import get_metadata
from restgdf.utils.crawl import fetch_all_data, safe_crawl  # noqa: F401
from restgdf.utils.token import ArcGISTokenSession


class Directory:
    """A class for interacting with ArcGIS Server directories.

    Attributes
    ----------
    metadata : Optional[restgdf.LayerMetadata]
        Pydantic-validated root metadata populated by :meth:`prep`.
        ``None`` until ``prep`` (or :meth:`from_url`) has run.
    services : Optional[list[restgdf.CrawlServiceEntry]]
        Services discovered by the most recent :meth:`crawl` call.
        Each entry carries ``name``, ``url``, ``type``, and a parsed
        ``metadata`` (``LayerMetadata`` or ``None`` if that service's
        metadata call failed).
    services_with_feature_count : Optional[list[restgdf.CrawlServiceEntry]]
        Same as ``services`` but populated with feature counts when
        :meth:`crawl` was invoked with ``return_feature_count=True``.
    report : Optional[restgdf.CrawlReport]
        The full crawl report (services + per-stage errors + root
        metadata) from the most recent :meth:`crawl` call. Use this
        when you need to inspect failures that were silently captured
        instead of raised.
    """

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
        self.services: Optional[list[CrawlServiceEntry]] = None
        self.services_with_feature_count: Optional[list[CrawlServiceEntry]] = None
        self.metadata: Optional[LayerMetadata] = None
        self.report: Optional[CrawlReport] = None

    async def prep(self):
        raw = await get_metadata(self.url, self.session, self.token)
        self.metadata = (
            raw if isinstance(raw, LayerMetadata) else LayerMetadata.model_validate(raw)
        )

    @classmethod
    async def from_url(cls, url: str, **kwargs) -> "Directory":
        """Create a Directory object from a url."""
        self = cls(url, **kwargs)
        await self.prep()
        return self

    async def crawl(
        self,
        return_feature_count: bool = False,
    ) -> list[CrawlServiceEntry]:
        if return_feature_count:
            if self.services_with_feature_count is None:
                report = await safe_crawl(
                    self.session,
                    self.url,
                    self.token,
                    return_feature_count=True,
                )
                self.report = report
                self.services_with_feature_count = report.services
            self.services = self.services_with_feature_count
            return self.services_with_feature_count

        if self.services is None:
            report = await safe_crawl(
                self.session,
                self.url,
                self.token,
                return_feature_count=False,
            )
            self.report = report
            self.services = report.services
        return self.services

    def filter_directory_layers(self, layer_type: str) -> list[LayerMetadata]:
        if self.services is None:
            raise ValueError("You must call .crawl() before filtering layers.")
        matched: list[LayerMetadata] = []
        for service in self.services:
            service_metadata = service.metadata
            if service_metadata is None:
                continue
            for layer in service_metadata.layers or []:
                if layer.type == layer_type:
                    matched.append(layer)
        return matched

    def feature_layers(self) -> list[LayerMetadata]:
        return self.filter_directory_layers("Feature Layer")

    def rasters(self) -> list[LayerMetadata]:
        return self.filter_directory_layers("Raster Layer")
