"""Typed response contracts for ArcGIS REST payloads consumed by restgdf.

These :class:`~typing.TypedDict` definitions describe the shapes returned
by ArcGIS REST endpoints and consumed by the parsers in
:mod:`restgdf.utils._metadata`, :mod:`restgdf.utils._query`, and the
orchestrators in :mod:`restgdf.utils.getinfo`.

Design notes
------------
* ArcGIS responses are loosely-shaped JSON: many keys are optional and
  vary by layer/server version. To match reality without losing useful
  static guarantees, each TypedDict splits into a ``*Required`` base with
  keys the parsers will index unconditionally, and a subclass
  (``total=False``) that adds known-optional keys the parsers touch via
  ``.get(...)``.
* TypedDicts are ordinary :class:`dict` instances at runtime. Parsers
  keep using ``mapping[key]`` / ``mapping.get(key)`` access; the types
  are purely advisory for static analysis.
* ``from __future__ import annotations`` is REQUIRED here for Python 3.9
  runtime compatibility with PEP 604 / 585 syntax used in other modules.
"""

from __future__ import annotations

from typing import TypedDict


class _FieldSpecRequired(TypedDict):
    name: str
    type: str


class FieldSpec(_FieldSpecRequired, total=False):
    """A field descriptor in a layer's ``fields`` list."""

    alias: str
    length: int
    domain: dict | None
    nullable: bool
    editable: bool


class _LayerMetadataRequired(TypedDict):
    """Keys parsers index directly.

    In practice ArcGIS may omit any key on an error response; parsers
    that require a key handle the missing case explicitly (``get_name``
    raises ``FIELDDOESNOTEXIST``). Keeping the required base empty keeps
    the type permissive enough for polymorphic ArcGIS endpoints (service
    root, folder root, layer root) while still documenting common keys
    in the subclass below.
    """


class LayerMetadata(_LayerMetadataRequired, total=False):
    """JSON payload returned by ``GET <layer_url>?f=json`` (or service root).

    ArcGIS REST endpoints are polymorphic: the same endpoint family may
    return per-layer metadata, service-level summaries (with ``services``
    and ``folders``), or sub-layer descriptors (with ``id``). All the
    optional keys below model those variants in a single shape so that
    parsers and orchestrators can accept any ArcGIS JSON response.
    """

    name: str
    id: int
    type: str
    fields: list[FieldSpec]
    maxRecordCount: int
    supportsPagination: bool
    advancedQueryCapabilities: dict
    layers: list[LayerMetadata]
    services: list[dict]
    folders: list[str]
    url: str
    feature_count: int | None


class _ServiceInfoRequired(TypedDict):
    pass


class ServiceInfo(_ServiceInfoRequired, total=False):
    """JSON payload returned by ``GET <services_root>?f=json``."""

    services: list[dict]
    folders: list[str]
    layers: list[LayerMetadata]
    url: str


class CountResponse(TypedDict):
    """JSON payload returned by ``?returnCountOnly=true`` queries."""

    count: int


class ObjectIdsResponse(TypedDict):
    """JSON payload returned by ``?returnIdsOnly=true`` queries."""

    objectIdFieldName: str
    objectIds: list[int]


class _FeatureRequired(TypedDict):
    attributes: dict


class Feature(_FeatureRequired, total=False):
    """A single feature in a ``FeaturesResponse.features`` list."""

    geometry: dict


class FeaturesResponse(TypedDict, total=False):
    """JSON payload for ``?f=json`` feature queries."""

    features: list[Feature]
    fields: list[FieldSpec]
    objectIdFieldName: str


class _ErrorInfoRequired(TypedDict):
    code: int
    message: str


class ErrorInfo(_ErrorInfoRequired, total=False):
    details: list[str]


class ErrorResponse(TypedDict):
    """JSON payload returned by ArcGIS when a request fails.

    Note: not every ArcGIS error surfaces through this shape; some are
    raised as aiohttp exceptions. Consumers that want to detect the JSON
    error envelope should test ``"error" in response``.
    """

    error: ErrorInfo


class _CrawlErrorRequired(TypedDict):
    stage: str
    url: str
    message: str


class CrawlError(_CrawlErrorRequired, total=False):
    """A single failure captured during :func:`restgdf.utils.crawl.safe_crawl`.

    ``stage`` identifies where the failure occurred: ``"base_metadata"``
    for the root ``get_metadata`` call, ``"folder_metadata"`` for a
    per-folder ``get_metadata`` call, and ``"service_metadata"`` for a
    per-service ``service_metadata`` call. ``url`` is the URL whose
    request failed and ``message`` is ``str(exception)`` so the report
    stays JSON-serializable. The original exception is preserved under
    the optional ``exception`` key for callers that want to re-raise.
    """

    exception: BaseException


class _CrawlServiceEntryRequired(TypedDict):
    name: str
    url: str


class CrawlServiceEntry(_CrawlServiceEntryRequired, total=False):
    """A service entry in :attr:`CrawlReport.services`.

    ``metadata`` is the :class:`LayerMetadata` returned by
    ``service_metadata`` for this service. It is absent when the
    ``service_metadata`` call failed; in that case a corresponding
    :class:`CrawlError` is recorded in :attr:`CrawlReport.errors`.
    """

    metadata: LayerMetadata


class _CrawlReportRequired(TypedDict):
    services: list[CrawlServiceEntry]
    errors: list[CrawlError]


class CrawlReport(_CrawlReportRequired, total=False):
    """Aggregated result of a directory crawl.

    Unlike the legacy ``fetch_all_data`` return shape (which short-circuits
    to ``{"error": exc}`` on the first failure), :class:`CrawlReport`
    always returns partial successes alongside captured errors.
    """

    metadata: LayerMetadata


__all__ = [
    "CountResponse",
    "CrawlError",
    "CrawlReport",
    "CrawlServiceEntry",
    "ErrorInfo",
    "ErrorResponse",
    "Feature",
    "FeaturesResponse",
    "FieldSpec",
    "LayerMetadata",
    "ObjectIdsResponse",
    "ServiceInfo",
]
