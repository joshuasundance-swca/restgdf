# restgdf

lightweight async Esri REST client with optional GeoPandas extras


<!-- Package -->
[![PyPI version](https://img.shields.io/pypi/v/restgdf.svg)](https://pypi.org/project/restgdf/)
[![Python versions](https://img.shields.io/pypi/pyversions/restgdf.svg)](https://pypi.org/project/restgdf/)
[![Downloads](https://static.pepy.tech/badge/restgdf/month)](https://pepy.tech/project/restgdf)
[![License](https://img.shields.io/github/license/joshuasundance-swca/restgdf.svg)](https://github.com/joshuasundance-swca/restgdf/blob/main/LICENSE)

<!-- Build & coverage -->
[![CI](https://img.shields.io/github/actions/workflow/status/joshuasundance-swca/restgdf/pytest.yml?event=pull_request&label=CI&logo=github)](https://github.com/joshuasundance-swca/restgdf/actions/workflows/pytest.yml)
[![Publish to PyPI](https://github.com/joshuasundance-swca/restgdf/actions/workflows/publish_on_pypi.yml/badge.svg)](https://github.com/joshuasundance-swca/restgdf/actions/workflows/publish_on_pypi.yml)
[![coverage](https://raw.githubusercontent.com/joshuasundance-swca/restgdf/main/coverage.svg)](https://github.com/joshuasundance-swca/restgdf/blob/main/COVERAGE.md)

<!-- Docs & discovery -->
[![Read the Docs](https://img.shields.io/readthedocs/restgdf)](https://restgdf.readthedocs.io/en/latest/)
[![llms.txt](https://img.shields.io/badge/llms.txt-green)](https://restgdf.readthedocs.io/en/latest/llms.txt)
[![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/joshuasundance-swca/restgdf)

<!-- Built with & code quality -->
[![Pydantic v2](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/pydantic/pydantic/main/docs/badge/v2.json)](https://docs.pydantic.dev/latest/contributing/#badges)
[![pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit&logoColor=white)](https://github.com/pre-commit/pre-commit)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v1.json)](https://github.com/astral-sh/ruff)
[![Checked with mypy](https://www.mypy-lang.org/static/mypy_badge.svg)](https://mypy-lang.org/)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![security: bandit](https://img.shields.io/badge/security-bandit-yellow.svg)](https://github.com/PyCQA/bandit)

## What's new in 2.0

restgdf 2.0 is a **major release** built on [pydantic 2.13](https://docs.pydantic.dev/).
See [`MIGRATION.md`](https://github.com/joshuasundance-swca/restgdf/blob/main/MIGRATION.md) for the full breaking-changes table and
code-rewrite recipes.

- **Typed responses.** `FeatureLayer.metadata`, `Directory.metadata` /
  `.services` / `.report`, and helpers like `get_metadata`, `safe_crawl`
  now return pydantic models instead of raw dicts.
- **Validated envelopes.** `get_feature_count`, `get_object_ids`, and
  token refresh surface malformed ArcGIS payloads as a typed
  `RestgdfResponseError` (with `model_name`, `context`, `raw`).
- **Schema-drift observability.** Vendor variance in permissive payloads
  (metadata, crawl) is logged through the opt-in `restgdf.schema_drift`
  logger instead of silently `KeyError`-ing.
- **Redacted credentials.** `AGOLUserPass.password` is a
  `pydantic.SecretStr` so passwords are never in `repr()` or logs.
- **Centralized settings.** `Settings` / `get_settings()` reads
  `RESTGDF_*` environment variables (chunk size, timeout, user agent,
  token URL, refresh threshold, etc.).
- **Migration helpers.** `restgdf.compat.as_dict` and `as_json_dict`
  convert any returned model back to a plain dict during a transitional
  upgrade window.
- **Deprecated shim.** `restgdf._types.*` still imports the legacy
  `TypedDict` names, but they now re-export the pydantic classes and
  emit `DeprecationWarning`. The shim will be removed in 3.x.
- **Dependency bump.** `pydantic>=2.13.3,<3` is a new required
  dependency.

`gpd.read_file(url, driver="ESRIJSON")` does not account for max record count
limitations, so large services get truncated at the server's
`maxRecordCount`.

restgdf uses asyncio to read *all* features from a service, not just the first
page, while letting you choose between a light-core install and an optional
GeoPandas extra.

# Installation

Install the lightweight core package when you want typed metadata, query
helpers, crawl/auth utilities, or raw feature rows without pulling in
`pandas`, `geopandas`, or `pyogrio`:

```bash
pip install restgdf
```

Base-install capabilities include:

- typed pydantic response models like `LayerMetadata` and `CrawlReport`
- `FeatureLayer.from_url`, `.metadata`, `.count`, and `.get_oids()`
- single-field `get_unique_values()` queries
- raw feature dictionaries via `FeatureLayer.row_dict_generator()`
- `Directory` crawling and `ArcGISTokenSession` authentication helpers

Install the geo extra for GeoDataFrame and pandas-backed workflows:

```bash
pip install "restgdf[geo]"
```

`restgdf[geo]` adds:

- `FeatureLayer.get_gdf()` / deprecated `getgdf()`
- `FeatureLayer.sample_gdf()` and `head_gdf()`
- `FeatureLayer.fieldtypes`
- pandas-backed helpers like `get_value_counts()` and `get_nested_count()`
- low-level `restgdf.utils.getgdf` helpers

## Light-core usage

```python
import asyncio

from aiohttp import ClientSession

from restgdf import FeatureLayer


beaches_url = r"https://maps1.vcgov.org/arcgis/rest/services/Beaches/MapServer/6"


async def main():
    async with ClientSession() as session:
        beaches = await FeatureLayer.from_url(beaches_url, session=session)
        cities = await beaches.get_unique_values("CITY")

        first_rows = []
        async for row in beaches.row_dict_generator(data={"outFields": "CITY,STATE"}):
            first_rows.append(row)
            if len(first_rows) == 2:
                break

    return beaches.count, beaches.metadata.max_record_count, cities[:3], first_rows


count, max_record_count, cities, first_rows = asyncio.run(main())

print(count, max_record_count)
print(cities)
print(first_rows[0])
```

## GeoDataFrame workflows (`restgdf[geo]`)

```python
import asyncio

from aiohttp import ClientSession

from restgdf import FeatureLayer


beaches_url = r"https://maps1.vcgov.org/arcgis/rest/services/Beaches/MapServer/6"

zipcodes_url = "https://services.arcgis.com/P3ePLMYs2RVChkJx/ArcGIS/rest/services/USA_ZIP_Codes_2016/FeatureServer/0"


async def main():
    async with ClientSession() as session:
        beaches = await FeatureLayer.from_url(beaches_url, session=session)
        beaches_gdf = await beaches.get_gdf()

        daytona = await beaches.where("LOWER(City) LIKE 'daytona%'")
        daytona_gdf = await daytona.get_gdf()

        oh_zipcodes = await FeatureLayer.from_url(
            zipcodes_url,
            where="STATE = 'OH'",
            session=session,
        )
        oh_zipcodes_gdf = await oh_zipcodes.get_gdf()

    return beaches_gdf, daytona_gdf, oh_zipcodes_gdf


beaches_gdf, daytona_gdf, oh_zipcodes_gdf = asyncio.run(main())

print(beaches_gdf.shape)
# (243, 10)

print(daytona_gdf.shape)
# (83, 10)

print(oh_zipcodes_gdf.shape)
# (1026, 8)
```

Keyword arguments to `FeatureLayer.get_gdf()` are passed on to
`aiohttp.ClientSession.post`; include query parameters like `where` and `token`
in the `data` dict when needed.

## Token authentication

Token helpers are available in the base install. The GeoDataFrame example below
requires `restgdf[geo]` because it calls `get_gdf()`.

```python
import asyncio

from aiohttp import ClientSession

from restgdf import AGOLUserPass, ArcGISTokenSession, FeatureLayer


secured_url = "https://example.com/arcgis/rest/services/Secured/FeatureServer/0"


async def main():
    async with ClientSession() as base_session:
        token_session = ArcGISTokenSession(
            session=base_session,
            credentials=AGOLUserPass(
                username="my-username",
                password="my-password",
            ),
        )
        layer = await FeatureLayer.from_url(secured_url, session=token_session)
        return await layer.get_gdf()


secured_gdf = asyncio.run(main())
```

If you already have a token, you can pass it with `token="..."` or `data={"token": "..."}`.

## Typed responses

Typed responses are part of the base `pip install restgdf` surface.

Every response is a pydantic model. Attribute access replaces dict
indexing, and `model_dump(by_alias=True)` round-trips back to ArcGIS
camelCase:

```python
import asyncio

from aiohttp import ClientSession

from restgdf import FeatureLayer


async def main():
    async with ClientSession() as session:
        fl = await FeatureLayer.from_url(beaches_url, session=session)
        md = fl.metadata                      # restgdf.LayerMetadata
        return md.name, md.max_record_count, md.model_dump(by_alias=True)


name, max_record_count, arcgis_dict = asyncio.run(main())
```

Need a plain dict during a transitional migration? Use
`restgdf.compat.as_dict(md)`. See [`MIGRATION.md`](https://github.com/joshuasundance-swca/restgdf/blob/main/MIGRATION.md) for
the full 1.x → 2.0 rewrite table.

# Documentation

Full docs live at **<https://restgdf.readthedocs.io/>** (hosted by Read the Docs).

## Docs for humans *and* LLMs

Every page is published in three formats so you can feed it to a teammate
*or* to a language model without any preprocessing:

| Format                  | URL                                                                                                      |
| ----------------------- | -------------------------------------------------------------------------------------------------------- |
| Rendered HTML           | <https://restgdf.readthedocs.io/en/latest/>                                                              |
| Plain Markdown (per page) | append `.md` to any page — e.g. <https://restgdf.readthedocs.io/en/latest/quickstart.html.md>            |
| [llms.txt][llmstxt] index | <https://restgdf.readthedocs.io/en/latest/llms.txt>                                                      |
| llms-full.txt (all pages) | <https://restgdf.readthedocs.io/en/latest/llms-full.txt>                                                 |
| Ask DeepWiki           | <https://deepwiki.com/joshuasundance-swca/restgdf>                                                       |

[llmstxt]: https://llmstxt.org/

Point your coding agent or RAG pipeline at `llms-full.txt` for the entire
reference in a single file, or at `llms.txt` for a concise table of
contents.

# Uses

- [restgdf_api](https://github.com/joshuasundance-swca/restgdf_api)
- [govgis_nov2023](https://huggingface.co/datasets/joshuasundance/govgis_nov2023)
