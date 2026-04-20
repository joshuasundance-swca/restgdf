# restgdf

improved esri rest io for geopandas


[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/license/bsd-3-clause/)
[![python](https://img.shields.io/badge/Python-3.9+-3776AB.svg?style=flat&logo=python&logoColor=white)](https://www.python.org)
[![dev python](https://img.shields.io/badge/Dev%2FCI%20Python-3.14-3776AB.svg?style=flat&logo=python&logoColor=white)](https://www.python.org)

[![Publish to PyPI](https://github.com/joshuasundance-swca/restgdf/actions/workflows/publish_on_pypi.yml/badge.svg)](https://github.com/joshuasundance-swca/restgdf/actions/workflows/publish_on_pypi.yml)
![GitHub tag (with filter)](https://img.shields.io/github/v/tag/joshuasundance-swca/restgdf)
[![Read the Docs](https://img.shields.io/readthedocs/restgdf)](https://restgdf.readthedocs.io/en/latest/)

![Code Climate maintainability](https://img.shields.io/codeclimate/maintainability/joshuasundance-swca/restgdf)
![Code Climate issues](https://img.shields.io/codeclimate/issues/joshuasundance-swca/restgdf)
![Code Climate technical debt](https://img.shields.io/codeclimate/tech-debt/joshuasundance-swca/restgdf)
[![coverage](coverage.svg)](./COVERAGE.md)

[![pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit&logoColor=white)](https://github.com/pre-commit/pre-commit)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/charliermarsh/ruff/main/assets/badge/v1.json)](https://github.com/charliermarsh/ruff)
[![Checked with mypy](http://www.mypy-lang.org/static/mypy_badge.svg)](http://mypy-lang.org/)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

[![security: bandit](https://img.shields.io/badge/security-bandit-yellow.svg)](https://github.com/PyCQA/bandit)
![Known Vulnerabilities](https://snyk.io/test/github/joshuasundance-swca/restgdf/badge.svg)

## What's new in 2.0

restgdf 2.0 is a **major release** built on [pydantic 2.13](https://docs.pydantic.dev/).
See [`MIGRATION.md`](./MIGRATION.md) for the full breaking-changes table and
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

`gpd.read_file(url, driver="ESRIJSON")` does not account for max record count limitations

so if you read a service with 100000 features but there's a limit of 1000 records per query, then your gdf will only have 1000 features

these functions use asyncio to read all features from a service, not limited by max record count

keyword arguments to `FeatureLayer.getgdf` are passed on to `aiohttp.ClientSession.post`; include query parameters like `where` and `token` in the `data` dict when needed

this enables enhanced control over queries and supports either direct `data={"token": "..."}` usage or a reusable `ArcGISTokenSession`

# Usage

```bash
pip install restgdf
```

```python
import asyncio

from aiohttp import ClientSession

from restgdf import FeatureLayer


beaches_url = r"https://maps1.vcgov.org/arcgis/rest/services/Beaches/MapServer/6"

zipcodes_url = "https://services.arcgis.com/P3ePLMYs2RVChkJx/ArcGIS/rest/services/USA_ZIP_Codes_2016/FeatureServer/0"

async def main():
    async with ClientSession() as session:
        beaches = await FeatureLayer.from_url(beaches_url, session=session)
        beaches_gdf = await beaches.getgdf()

        daytona = await beaches.where("LOWER(City) LIKE 'daytona%'")
        daytona_gdf = await daytona.getgdf()

        oh_zipcodes = await FeatureLayer.from_url(zipcodes_url, where="STATE = 'OH'", session=session)
        oh_zipcodes_gdf = await oh_zipcodes.getgdf()

    return beaches_gdf, daytona_gdf, oh_zipcodes_gdf


beaches_gdf, daytona_gdf, oh_zipcodes_gdf = asyncio.run(main())

print(beaches_gdf.shape)
# (243, 10)

print(daytona_gdf.shape)
# (83, 10)

print(oh_zipcodes_gdf.shape)
# (1026, 8)
```

## Token authentication

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
        return await layer.getgdf()


secured_gdf = asyncio.run(main())
```

If you already have a token, you can pass it with `token="..."` or `data={"token": "..."}`.

## Typed responses

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
`restgdf.compat.as_dict(md)`. See [`MIGRATION.md`](./MIGRATION.md) for
the full 1.x → 2.0 rewrite table.

# Documentation

https://restgdf.readthedocs.io/

# Uses

- [restgdf_api](https://github.com/joshuasundance-swca/restgdf_api)
- [govgis_nov2023](https://huggingface.co/datasets/joshuasundance/govgis_nov2023)
