# Quickstart

Install ``restgdf`` from PyPI:

```bash
pip install restgdf
```

## Read a FeatureServer into a GeoDataFrame

``restgdf`` reads *all* features past the ``maxRecordCount`` limit, using
``asyncio`` + [`aiohttp`](https://docs.aiohttp.org/) to chunk ``objectIds``
in parallel.

```python
import asyncio

from aiohttp import ClientSession

from restgdf import FeatureLayer


beaches_url = "https://maps1.vcgov.org/arcgis/rest/services/Beaches/MapServer/6"
zipcodes_url = (
    "https://services.arcgis.com/P3ePLMYs2RVChkJx/ArcGIS/rest/services/"
    "USA_ZIP_Codes_2016/FeatureServer/0"
)


async def main():
    async with ClientSession() as session:
        beaches = await FeatureLayer.from_url(beaches_url, session=session)
        beaches_gdf = await beaches.getgdf()

        daytona = await beaches.where("LOWER(City) LIKE 'daytona%'")
        daytona_gdf = await daytona.getgdf()

        oh = await FeatureLayer.from_url(
            zipcodes_url, where="STATE = 'OH'", session=session
        )
        oh_gdf = await oh.getgdf()

    return beaches_gdf, daytona_gdf, oh_gdf


beaches_gdf, daytona_gdf, oh_gdf = asyncio.run(main())
# (243, 10)   (83, 10)   (1026, 8)
```

Keyword arguments to {meth}`~restgdf.FeatureLayer.getgdf` are forwarded to
`aiohttp.ClientSession.post`; include query parameters like ``where`` and
``token`` in the ``data`` dict when you need per-request overrides.

## Typed responses

Every response is a pydantic model. Attribute access replaces dict indexing,
and ``model_dump(by_alias=True)`` round-trips back to ArcGIS camelCase:

```python
fl = await FeatureLayer.from_url(beaches_url, session=session)
md = fl.metadata                      # restgdf.LayerMetadata
md.name                               # was md["name"]
md.max_record_count                   # was md["maxRecordCount"]
md.model_dump(by_alias=True)          # ArcGIS camelCase dict
```

Need a plain dict during a transitional migration? Use
{func}`restgdf.compat.as_dict` — see the {doc}`migration` for the full
rewrite table.

## Crawl a directory

```python
from restgdf import Directory

async def crawl():
    async with ClientSession() as session:
        d = await Directory.from_url(
            "https://services.arcgis.com/P3ePLMYs2RVChkJx/ArcGIS/rest/services",
            session=session,
        )
        report = d.report                      # restgdf.CrawlReport
        for svc in report.services:            # list[CrawlServiceEntry]
            print(svc.name, svc.type)
```

## What next?

- {doc}`authentication` — tokens and ``ArcGISTokenSession``.
- {doc}`models` — every pydantic response model.
- {doc}`restgdf` — the full API reference.
- {doc}`migration` — moving from 1.x.
