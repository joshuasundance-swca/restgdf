Authentication
==============

restgdf supports secured ArcGIS services in two common ways:

1. Pass an existing ArcGIS token in the request ``data`` payload.
2. Wrap an ``aiohttp.ClientSession`` in ``ArcGISTokenSession`` so tokens are requested and refreshed automatically.

These auth helpers are part of the base ``pip install restgdf`` contract.
Install ``restgdf[geo]`` only when you want the authenticated response as a
GeoDataFrame via :meth:`restgdf.FeatureLayer.get_gdf`.

Direct token usage
------------------

If you already have a valid token, pass it directly when you create the layer:

.. code-block:: python

   import asyncio

   from aiohttp import ClientSession

   from restgdf import FeatureLayer


   async def main():
       async with ClientSession() as session:
           layer = await FeatureLayer.from_url(
               "https://example.com/arcgis/rest/services/Secured/FeatureServer/0",
               session=session,
               token="my-token",
           )
           return await layer.get_gdf()


   secured_gdf = asyncio.run(main())

You can also pass the same value via ``data={"token": "my-token"}`` if you prefer to keep all ArcGIS query params together.

Automatic token management
--------------------------

Use ``ArcGISTokenSession`` when you want the session to mint and refresh ArcGIS Online tokens for you:

.. code-block:: python

   import asyncio

   from aiohttp import ClientSession

   from restgdf import AGOLUserPass, ArcGISTokenSession, FeatureLayer


   async def main():
       async with ClientSession() as base_session:
           token_session = ArcGISTokenSession(
               session=base_session,
               credentials=AGOLUserPass(
                   username="my-username",
                   password="my-password",
               ),
           )
           layer = await FeatureLayer.from_url(
               "https://example.com/arcgis/rest/services/Secured/FeatureServer/0",
               session=token_session,
           )
           return await layer.get_gdf()


   secured_gdf = asyncio.run(main())

Notes
-----

- ``ArcGISTokenSession`` delegates network I/O to the wrapped ``aiohttp.ClientSession``.
- If you provide ``credentials``, the token is refreshed when it is missing or near expiry.
- Existing request kwargs and ``data`` payloads still work; the token session only augments them with auth data.
