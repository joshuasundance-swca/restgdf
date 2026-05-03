Pydantic models
===============

The base ``pip install restgdf`` install exposes every ArcGIS response and config object as a
pydantic :class:`~pydantic.BaseModel`. These classes are the single source of
truth for payload shape and are re-exported from ``restgdf`` directly. Use
:func:`restgdf.compat.as_dict` if you need a plain dict during a migration.

Model relationships
-------------------

The models nest in a natural hierarchy that mirrors the ArcGIS REST API
response structure:

.. code-block:: text

   FeatureLayer.metadata → LayerMetadata
   │                        ├── .fields → list[FieldSpec]
   │                        ├── .extent → dict (raw spatial extent)
   │                        └── .advanced_query_capabilities → AdvancedQueryCapabilities
   │
   FeatureLayer.get_gdf() internally parses → FeaturesResponse
   │                                          ├── .features → list[Feature]
   │                                          └── .exceeded_transfer_limit → bool
   │
   Directory.crawl() → list[CrawlServiceEntry]
   │                    ├── .metadata → LayerMetadata | None
   │                    └── .name, .url, .type
   │
   Directory.report → CrawlReport
                      ├── .services → list[CrawlServiceEntry]
                      └── .errors → list[CrawlError]

Use ``model.model_dump(by_alias=True)`` to round-trip any model back to ArcGIS
camelCase JSON. Use :func:`restgdf.compat.as_dict` for a plain ``dict`` during
migration.

Response envelopes
------------------

.. autopydantic_model:: restgdf.LayerMetadata
   :model-show-json: false
   :model-show-config-summary: false

.. autopydantic_model:: restgdf.ServiceInfo
   :model-show-json: false
   :model-show-config-summary: false

.. autopydantic_model:: restgdf.FieldSpec
   :model-show-json: false
   :model-show-config-summary: false

.. autopydantic_model:: restgdf.Feature
   :model-show-json: false
   :model-show-config-summary: false

.. autopydantic_model:: restgdf.FeaturesResponse
   :model-show-json: false
   :model-show-config-summary: false

.. autopydantic_model:: restgdf.CountResponse
   :model-show-json: false
   :model-show-config-summary: false

.. autopydantic_model:: restgdf.ObjectIdsResponse
   :model-show-json: false
   :model-show-config-summary: false

.. autopydantic_model:: restgdf.TokenResponse
   :model-show-json: false
   :model-show-config-summary: false

.. autopydantic_model:: restgdf.ErrorInfo
   :model-show-json: false
   :model-show-config-summary: false

.. autopydantic_model:: restgdf.ErrorResponse
   :model-show-json: false
   :model-show-config-summary: false

Crawl models
------------

.. autopydantic_model:: restgdf.CrawlReport
   :model-show-json: false
   :model-show-config-summary: false

.. autopydantic_model:: restgdf.CrawlServiceEntry
   :model-show-json: false
   :model-show-config-summary: false

.. autopydantic_model:: restgdf.CrawlError
   :model-show-json: false
   :model-show-config-summary: false

Credentials and session config
------------------------------

.. autopydantic_model:: restgdf.AGOLUserPass
   :model-show-json: false
   :model-show-config-summary: false
   :noindex:

.. autopydantic_model:: restgdf.TokenSessionConfig
   :model-show-json: false
   :model-show-config-summary: false
   :noindex:

Runtime settings
----------------

.. autopydantic_model:: restgdf.Settings
   :model-show-json: false
   :model-show-config-summary: false
