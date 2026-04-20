"""S-4: Pydantic models for :func:`restgdf.utils.crawl.safe_crawl` output.

``safe_crawl`` aggregates results of a directory crawl and, unlike
``fetch_all_data``, never short-circuits on the first failure. Its return
value is a :class:`CrawlReport` containing:

* :attr:`CrawlReport.services` — a list of :class:`CrawlServiceEntry`
  (one per successfully-discovered service).
* :attr:`CrawlReport.errors` — a list of :class:`CrawlError` capturing
  every recoverable failure, tagged by ``stage``.
* :attr:`CrawlReport.metadata` — the parsed root
  :class:`~restgdf._models.responses.LayerMetadata` (absent when the root
  ``get_metadata`` call itself failed).

All three models are :class:`~restgdf._models._drift.PermissiveModel`
subclasses: ArcGIS servers may emit extra keys at any of these levels,
and missing fields must never raise. :class:`CrawlError` declares
``arbitrary_types_allowed=True`` so that the original
:class:`BaseException` that caused the failure can be preserved under
``exception`` for callers that want to re-raise; the default
:meth:`~pydantic.BaseModel.model_dump` output excludes it so the report
stays JSON-serializable.
"""

from __future__ import annotations


from pydantic import ConfigDict, Field

from restgdf._models._drift import PermissiveModel
from restgdf._models.responses import LayerMetadata


class CrawlError(PermissiveModel):
    """A single failure captured during :func:`safe_crawl`.

    ``stage`` identifies where the failure occurred. Standard stages
    emitted by ``safe_crawl`` are:

    * ``"base_metadata"`` — the root ``get_metadata`` call failed.
    * ``"folder_metadata"`` — a per-folder ``get_metadata`` call failed.
    * ``"service_metadata"`` — a per-service ``service_metadata`` call
      failed.

    ``exception`` preserves the original :class:`BaseException` so
    callers can re-raise; it is excluded from the default
    :meth:`~pydantic.BaseModel.model_dump` output for JSON safety.
    """

    model_config = ConfigDict(
        extra="allow",
        populate_by_name=True,
        arbitrary_types_allowed=True,
    )

    stage: str | None = None
    url: str | None = None
    message: str | None = None
    exception: BaseException | None = Field(default=None, exclude=True)


class CrawlServiceEntry(PermissiveModel):
    """A service entry in :attr:`CrawlReport.services`.

    ``metadata`` is the :class:`~restgdf._models.responses.LayerMetadata`
    returned by ``service_metadata`` for this service. It is ``None``
    when the ``service_metadata`` call failed; in that case a
    corresponding :class:`CrawlError` is recorded in
    :attr:`CrawlReport.errors`.
    """

    name: str | None = None
    url: str | None = None
    type: str | None = None
    metadata: LayerMetadata | None = None


class CrawlReport(PermissiveModel):
    """Aggregated result of a directory crawl.

    Unlike the legacy ``fetch_all_data`` return shape (which
    short-circuits to ``{"error": exc}`` on the first failure),
    :class:`CrawlReport` always returns partial successes alongside
    captured errors.
    """

    services: list[CrawlServiceEntry] = Field(default_factory=list)
    errors: list[CrawlError] = Field(default_factory=list)
    metadata: LayerMetadata | None = None


__all__ = ["CrawlError", "CrawlReport", "CrawlServiceEntry"]
