Pydantic models
===============

restgdf 2.0 exposes every ArcGIS response and config object as a
pydantic :class:`~pydantic.BaseModel`. These classes are the single source of
truth for payload shape and are re-exported from ``restgdf`` directly. Use
:func:`restgdf.compat.as_dict` if you need a plain dict during a migration.

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
