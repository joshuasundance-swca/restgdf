from typing import Optional

from restgdf._client._protocols import AsyncHTTPSession
from restgdf._models.crawl import CrawlReport, CrawlServiceEntry
from restgdf._models.responses import LayerMetadata
from restgdf.utils.getinfo import get_metadata
from restgdf.utils.crawl import fetch_all_data, safe_crawl  # noqa: F401


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
        session: AsyncHTTPSession,
        token: Optional[str] = None,
    ):
        """Initialize a Directory instance.

        Prefer :meth:`from_url` for most use-cases — it calls :meth:`prep`
        automatically so metadata is immediately available.

        Parameters
        ----------
        url : str
            ArcGIS Server directory endpoint URL (e.g.
            ``"https://server/arcgis/rest/services"``).
        session : AsyncHTTPSession
            An aiohttp-compatible async HTTP session used for transport.
        token : str or None, optional
            Optional ArcGIS token for secured services.

        See Also
        --------
        from_url : Recommended async constructor that also calls :meth:`prep`.
        """
        self.url = url
        self.session = session
        self.token = token
        self.services: Optional[list[CrawlServiceEntry]] = None
        self.services_with_feature_count: Optional[list[CrawlServiceEntry]] = None
        self.metadata: Optional[LayerMetadata] = None
        self.report: Optional[CrawlReport] = None

    async def prep(self):
        """Fetch and validate directory metadata from the server.

        Populates :attr:`metadata` with a :class:`~restgdf.LayerMetadata`
        instance.  Must be called before accessing metadata unless the
        instance was created via :meth:`from_url`.
        """
        raw = await get_metadata(self.url, self.session, self.token)
        self.metadata = (
            raw if isinstance(raw, LayerMetadata) else LayerMetadata.model_validate(raw)
        )

    @classmethod
    async def from_url(cls, url: str, **kwargs) -> "Directory":
        """Create a prepared Directory from a URL.

        This is the recommended constructor.  It instantiates the class and
        calls :meth:`prep` so metadata is immediately available.

        Parameters
        ----------
        url : str
            ArcGIS Server directory endpoint URL.
        **kwargs
            Forwarded to :meth:`__init__` — accepts ``session`` and
            ``token``.

        Returns
        -------
        Directory
            A fully prepared instance with metadata loaded.
        """
        self = cls(url, **kwargs)
        await self.prep()
        return self

    async def crawl(
        self,
        return_feature_count: bool = False,
    ) -> list[CrawlServiceEntry]:
        """Discover all services under this directory recursively.

        Results are cached — subsequent calls with the same
        *return_feature_count* value return the cached list without
        additional HTTP traffic.

        Parameters
        ----------
        return_feature_count : bool, default False
            When ``True``, also fetches the feature count for each
            discovered layer (requires extra HTTP requests per layer).

        Returns
        -------
        list[CrawlServiceEntry]
            List of discovered service entries, each carrying ``name``,
            ``url``, ``type``, and parsed ``metadata``.

        Notes
        -----
        After a successful call, the following instance attributes are
        populated:

        * :attr:`services` — the returned list.
        * :attr:`report` — the full :class:`~restgdf.CrawlReport`.
        * :attr:`services_with_feature_count` — same as *services* when
          *return_feature_count* was ``True``.
        """
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
        """Filter discovered layers by type.

        Parameters
        ----------
        layer_type : str
            The layer type string to match (e.g. ``"Feature Layer"``,
            ``"Raster Layer"``).

        Returns
        -------
        list[LayerMetadata]
            Metadata entries for layers whose ``type`` matches
            *layer_type*.

        Raises
        ------
        ValueError
            If :meth:`crawl` has not been called yet.

        See Also
        --------
        feature_layers : Shortcut for ``filter_directory_layers("Feature Layer")``.
        rasters : Shortcut for ``filter_directory_layers("Raster Layer")``.
        """
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
        """Return all Feature Layer metadata from the crawl.

        Convenience wrapper around
        ``filter_directory_layers("Feature Layer")``.

        Returns
        -------
        list[LayerMetadata]
            Metadata for every discovered Feature Layer.
        """
        return self.filter_directory_layers("Feature Layer")

    def rasters(self) -> list[LayerMetadata]:
        """Return all Raster Layer metadata from the crawl.

        Convenience wrapper around
        ``filter_directory_layers("Raster Layer")``.

        Returns
        -------
        list[LayerMetadata]
            Metadata for every discovered Raster Layer.
        """
        return self.filter_directory_layers("Raster Layer")
