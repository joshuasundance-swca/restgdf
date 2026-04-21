restgdf
=======

   *Improved Esri REST I/O for GeoPandas.*

.. image:: https://img.shields.io/pypi/v/restgdf.svg
   :target: https://pypi.org/project/restgdf/
   :alt: PyPI version
.. image:: https://img.shields.io/badge/Python-3.9+-3776AB.svg?style=flat&logo=python&logoColor=white
   :target: https://www.python.org
   :alt: Python versions
.. image:: https://img.shields.io/readthedocs/restgdf
   :target: https://restgdf.readthedocs.io/
   :alt: Read the Docs

``restgdf`` is an async-first wrapper around Esri/ArcGIS REST Feature and Map
services. It reads *all* features past the server's ``maxRecordCount``, returns
validated pydantic models for every response, and hands you a
:class:`geopandas.GeoDataFrame` ready for analysis.

.. code-block:: python

   import asyncio
   from aiohttp import ClientSession
   from restgdf import FeatureLayer

   url = "https://maps1.vcgov.org/arcgis/rest/services/Beaches/MapServer/6"

   async def main():
       async with ClientSession() as session:
           layer = await FeatureLayer.from_url(url, session=session)
           return await layer.getgdf()

   gdf = asyncio.run(main())

--------

Explore the docs
----------------

.. grid:: 1 2 2 2
   :gutter: 3

   .. grid-item-card:: 🚀 Quickstart
      :link: quickstart
      :link-type: doc

      Install, connect to a FeatureServer, and pull a GeoDataFrame in under ten lines.

   .. grid-item-card:: 🔐 Authentication
      :link: authentication
      :link-type: doc

      Pass ArcGIS tokens directly or let ``ArcGISTokenSession`` mint and refresh them for you.

   .. grid-item-card:: 📦 Pydantic models
      :link: models
      :link-type: doc

      Every ArcGIS response is a typed ``BaseModel`` — ``LayerMetadata``, ``FeaturesResponse``, ``CrawlReport``, and more.

   .. grid-item-card:: 📖 API reference
      :link: restgdf
      :link-type: doc

      ``FeatureLayer``, ``Directory``, ``ArcGISTokenSession``, and the migration helpers in ``restgdf.compat``.

   .. grid-item-card:: 🛠 Utilities
      :link: utils
      :link-type: doc

      Low-level crawl, HTTP, token, and GeoDataFrame helpers.

   .. grid-item-card:: 🔁 Migration 1.x → 2.0
      :link: migration
      :link-type: doc

      Upgrading from restgdf 1.x? The breaking-changes table and rewrite recipes live here.

.. toctree::
   :hidden:
   :maxdepth: 2
   :caption: Getting started

   quickstart
   authentication

.. toctree::
   :hidden:
   :maxdepth: 2
   :caption: Reference

   restgdf
   models
   utils

.. toctree::
   :hidden:
   :maxdepth: 1
   :caption: Project

   migration
   changelog

Indices and tables
------------------

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
