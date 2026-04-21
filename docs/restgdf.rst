API reference
=============

This page documents the public surface exposed at the top of the ``restgdf``
namespace: the :class:`~restgdf.FeatureLayer` and :class:`~restgdf.Directory`
entry points, the :class:`~restgdf.ArcGISTokenSession` wrapper, and the
migration helpers in :mod:`restgdf.compat`.

The pydantic response models (``LayerMetadata``, ``FeaturesResponse``,
``CrawlReport`` and friends) live on :doc:`models`. Internal utility modules
are on :doc:`utils`.

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
