restgdf
=======

   *Improved Esri REST I/O for GeoPandas.*

.. Package
.. image:: https://img.shields.io/pypi/v/restgdf.svg
   :target: https://pypi.org/project/restgdf/
   :alt: PyPI version
.. image:: https://img.shields.io/pypi/pyversions/restgdf.svg
   :target: https://pypi.org/project/restgdf/
   :alt: Python versions
.. image:: https://static.pepy.tech/badge/restgdf/month
   :target: https://pepy.tech/project/restgdf
   :alt: Downloads
.. image:: https://img.shields.io/github/license/joshuasundance-swca/restgdf.svg
   :target: https://github.com/joshuasundance-swca/restgdf/blob/main/LICENSE
   :alt: License

.. Build & coverage
.. image:: https://img.shields.io/github/actions/workflow/status/joshuasundance-swca/restgdf/pytest.yml?event=pull_request&label=CI&logo=github
   :target: https://github.com/joshuasundance-swca/restgdf/actions/workflows/pytest.yml
   :alt: CI
.. image:: https://github.com/joshuasundance-swca/restgdf/actions/workflows/publish_on_pypi.yml/badge.svg
   :target: https://github.com/joshuasundance-swca/restgdf/actions/workflows/publish_on_pypi.yml
   :alt: Publish to PyPI
.. image:: https://raw.githubusercontent.com/joshuasundance-swca/restgdf/main/coverage.svg
   :target: https://github.com/joshuasundance-swca/restgdf/blob/main/COVERAGE.md
   :alt: coverage

.. Docs & discovery (RTD badge omitted -- you're reading RTD)
.. image:: https://img.shields.io/badge/llms.txt-green
   :target: https://restgdf.readthedocs.io/en/latest/llms.txt
   :alt: llms.txt
.. image:: https://deepwiki.com/badge.svg
   :target: https://deepwiki.com/joshuasundance-swca/restgdf
   :alt: Ask DeepWiki

.. Built with
.. image:: https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/pydantic/pydantic/main/docs/badge/v2.json
   :target: https://docs.pydantic.dev/latest/contributing/#badges
   :alt: Pydantic v2

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

   .. grid-item-card:: 🤖 Docs for LLMs
      :link: https://restgdf.readthedocs.io/en/latest/llms.txt
      :link-type: url

      Every page is also published as plain Markdown (append ``.md`` to any URL),
      plus ``llms.txt`` / ``llms-full.txt`` indexes for RAG pipelines and coding agents.

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
