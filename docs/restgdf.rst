API reference
=============

This page documents the public surface exposed at the top of the ``restgdf``
namespace: the :class:`~restgdf.FeatureLayer` and :class:`~restgdf.Directory`
entry points, the :class:`~restgdf.ArcGISTokenSession` wrapper, and the
migration helpers in :mod:`restgdf.compat`.

The pydantic response models (``LayerMetadata``, ``FeaturesResponse``,
``CrawlReport`` and friends) live on :doc:`models`. Internal utility modules
are on :doc:`utils`.

The base ``pip install restgdf`` surface covers metadata/query helpers,
raw-row iteration, crawl/auth utilities, and all pydantic models. Install
``restgdf[geo]`` for GeoDataFrame and pandas-backed APIs such as
``FeatureLayer.get_gdf()``, ``sample_gdf()``, ``head_gdf()``, ``fieldtypes``,
``get_value_counts()``, and ``get_nested_count()``.

FeatureLayer
------------

.. autoclass:: restgdf.FeatureLayer
   :members:
   :undoc-members:
   :show-inheritance:

Directory
---------

.. autoclass:: restgdf.Directory
   :members:
   :undoc-members:
   :show-inheritance:

Token session
-------------

.. autoclass:: restgdf.ArcGISTokenSession
   :members:
   :undoc-members:
   :show-inheritance:

Errors
------

.. autoexception:: restgdf.RestgdfResponseError
   :members:
   :show-inheritance:

Runtime settings
----------------

See :doc:`models` for the :class:`~restgdf.Settings` model; the helpers below
read it from the environment.

.. autofunction:: restgdf.get_settings

Migration helpers
-----------------

.. automodule:: restgdf.compat
   :members:
   :undoc-members:
   :show-inheritance:
