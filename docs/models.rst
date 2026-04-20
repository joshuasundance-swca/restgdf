Pydantic models
===============

restgdf 2.0 exposes every ArcGIS response and config object as a
pydantic ``BaseModel``. These classes are the single source of truth
for payload shape and are re-exported from ``restgdf`` directly.

Response envelopes
------------------

.. autoclass:: restgdf.LayerMetadata
   :members:
   :undoc-members:
   :show-inheritance:

.. autoclass:: restgdf.ServiceInfo
   :members:
   :undoc-members:
   :show-inheritance:

.. autoclass:: restgdf.FieldSpec
   :members:
   :undoc-members:
   :show-inheritance:

.. autoclass:: restgdf.Feature
   :members:
   :undoc-members:
   :show-inheritance:

.. autoclass:: restgdf.FeaturesResponse
   :members:
   :undoc-members:
   :show-inheritance:

.. autoclass:: restgdf.CountResponse
   :members:
   :undoc-members:
   :show-inheritance:

.. autoclass:: restgdf.ObjectIdsResponse
   :members:
   :undoc-members:
   :show-inheritance:

.. autoclass:: restgdf.TokenResponse
   :members:
   :undoc-members:
   :show-inheritance:

.. autoclass:: restgdf.ErrorInfo
   :members:
   :undoc-members:
   :show-inheritance:

.. autoclass:: restgdf.ErrorResponse
   :members:
   :undoc-members:
   :show-inheritance:

Crawl models
------------

.. autoclass:: restgdf.CrawlReport
   :members:
   :undoc-members:
   :show-inheritance:

.. autoclass:: restgdf.CrawlServiceEntry
   :members:
   :undoc-members:
   :show-inheritance:

.. autoclass:: restgdf.CrawlError
   :members:
   :undoc-members:
   :show-inheritance:

Credentials and session config
------------------------------

.. autoclass:: restgdf.AGOLUserPass
   :members:
   :undoc-members:
   :show-inheritance:

.. autoclass:: restgdf.TokenSessionConfig
   :members:
   :undoc-members:
   :show-inheritance:

Runtime settings
----------------

.. autoclass:: restgdf.Settings
   :members:
   :undoc-members:
   :show-inheritance:

.. autofunction:: restgdf.get_settings

Errors
------

.. autoclass:: restgdf.RestgdfResponseError
   :members:
   :undoc-members:
   :show-inheritance:

Migration helpers
-----------------

.. automodule:: restgdf.compat
   :members:
   :undoc-members:
   :show-inheritance:
