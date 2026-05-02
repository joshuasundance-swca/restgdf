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

## Release highlights

restgdf 2.0.0 includes the following major additions alongside the core
typed-model migration described below.

- **Streaming APIs.** `FeatureLayer.stream_features`,
  `stream_feature_batches`, and `stream_rows` expose ArcGIS
  pagination as async generators with
  `on_truncation="raise" | "ignore" | "split"`,
  `order="request" | "completion"`, and `max_concurrent_pages` knobs,
  plus an R-61 `feature_layer.stream` parent span when telemetry is
  enabled. `stream_gdf_chunks` is the legacy `GeoDataFrame`-per-page
  shape (requires `restgdf[geo]`, completion-order only, no shared
  knobs). `stream_rows` works on the base install.
- **Pandas-first output.** `FeatureLayer.get_df()` returns a
  `pandas.DataFrame` without requiring the geo extra, sibling to
  `get_gdf()`.
- **Output adapters.** `restgdf.adapters.{dict,stream,pandas,geopandas}`
  compose the streaming primitives into tabular shapes.
- **Nested config.** `restgdf.Config` / `restgdf.get_config()` replace
  the flat `Settings` object with eight frozen sub-configs and
  `RESTGDF_<CATEGORY>_<FIELD>` env vars. The old flat variables keep
  working with a `DeprecationWarning`.
- **Error taxonomy.** `restgdf.errors` exposes `RestgdfError`,
  `ConfigurationError`, `OptionalDependencyError`, `TransportError`,
  `RestgdfTimeoutError`, `RateLimitError`, `ArcGISServiceError`,
  `PaginationError`, `FieldDoesNotExistError`, `SchemaValidationError`,
  `AuthenticationError`, and `OutputConversionError` — all with URL,
  status-code, and retry-after context populated where applicable.
- **Optional telemetry.** `pip install restgdf[telemetry]` unlocks
  `RestgdfInstrumentor` and trace/span log correlation; see the new
  [tracing recipe](https://restgdf.readthedocs.io/en/latest/recipes/tracing.html)
  and [streaming recipe](https://restgdf.readthedocs.io/en/latest/recipes/streaming.html).
- **Header-token default.** Tokens now ride the
  `X-Esri-Authorization` header by default; set
  `AuthConfig.transport="body"` to restore the old behavior.

See [`CHANGELOG.md`](https://github.com/joshuasundance-swca/restgdf/blob/main/CHANGELOG.md)
and [`MIGRATION.md`](https://github.com/joshuasundance-swca/restgdf/blob/main/MIGRATION.md)
for the full release notes and upgrade guidance.

## 2.0 migration changes

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
  emit `DeprecationWarning`. The shim will be removed in a future major release.
- **Dependency bump.** `pydantic>=2.13.3,<3` is a new required
  dependency.

### Resilience extra

For production workloads that need automatic retry with jitter and
per-service-root rate limiting, install the optional resilience extra:

```bash
pip install restgdf[resilience]
```

This adds `stamina` and `aiolimiter`. Wrap any `AsyncHTTPSession` with
`restgdf.resilience.ResilientSession` and configure via
`restgdf.resilience.ResilienceConfig` or `RESTGDF_RESILIENCE_ENABLED=1`.
See [`MIGRATION.md`](MIGRATION.md) for details.

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
- raw feature dictionaries via `FeatureLayer.stream_features()` /
  `stream_rows()` (deprecated `row_dict_generator()` still works)
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

Treat the split above as the stable dependency boundary: geo-enabled
environments should depend on `restgdf[geo]` explicitly. See
[`MIGRATION.md`](https://github.com/joshuasundance-swca/restgdf/blob/main/MIGRATION.md)
for the full 1.x → 2.0 rewrite table and upgrade recipes.

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
        async for row in beaches.stream_rows(data={"outFields": "CITY,STATE"}):
            first_rows.append(row)
            if len(first_rows) == 2:
                break

    return beaches.count, beaches.metadata.max_record_count, cities[:3], first_rows


count, max_record_count, cities, first_rows = asyncio.run(main())

print(count, max_record_count)
print(cities)
print(first_rows[0])
```

## Streaming

`FeatureLayer` exposes ArcGIS pagination as three async generators so
you can process millions of rows without buffering them in memory. The
`on_truncation` knob controls what happens when the server caps a page
at `maxRecordCount`: `"raise"` (default), `"ignore"` (log + continue),
or `"split"` (bisect by object-id and retry, up to depth 32).

```python
import asyncio

from aiohttp import ClientSession

from restgdf import FeatureLayer


zipcodes_url = "https://services.arcgis.com/P3ePLMYs2RVChkJx/ArcGIS/rest/services/USA_ZIP_Codes_2016/FeatureServer/0"


async def main():
    async with ClientSession() as session:
        oh = await FeatureLayer.from_url(
            zipcodes_url,
            where="STATE = 'OH'",
            session=session,
        )

        # 1. Feature dicts, one per row (base install)
        first_feature = None
        async for feature in oh.stream_features(on_truncation="split"):
            first_feature = feature
            break

        # 2. Per-page batches, preserving ArcGIS page boundaries
        page_sizes = []
        async for batch in oh.stream_feature_batches(order="request"):
            page_sizes.append(len(batch))
            if len(page_sizes) == 3:
                break

        # 3. GeoDataFrame chunks (requires `restgdf[geo]`; note that
        # stream_gdf_chunks does *not* accept on_truncation / order /
        # max_concurrent_pages — it yields in completion order).
        chunk_shapes = []
        async for chunk in oh.stream_gdf_chunks():
            chunk_shapes.append(chunk.shape)
            if len(chunk_shapes) == 2:
                break

    return first_feature, page_sizes, chunk_shapes


first_feature, page_sizes, chunk_shapes = asyncio.run(main())
```

See the [streaming recipe](https://restgdf.readthedocs.io/en/latest/recipes/streaming.html)
for the full matrix of `on_truncation`, `order`, and
`max_concurrent_pages` combinations on the `iter_pages`-based shapes
(`stream_features`, `stream_feature_batches`, `stream_rows`).

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

### ArcGIS drift guarantees and limitations

- Strict envelopes (`CountResponse`, `ObjectIdsResponse`, `TokenResponse`) fail
  fast with `RestgdfResponseError` when required keys are missing or malformed.
- Permissive envelopes (`LayerMetadata`, `FeaturesResponse`, crawl/service
  payloads) still tolerate unknown extras and missing optional fields, **but**
  a top-level ArcGIS JSON error envelope (`{"error": {...}}`) now raises
  `RestgdfResponseError` instead of being mistaken for partial metadata or an
  empty feature page.
- Query helpers intentionally call `aiohttp` JSON decoding with
  `content_type=None`, so mislabeled JSON bodies such as `text/plain` still
  parse.
- Non-JSON/HTML bodies are not normalized: malformed query bodies still bubble
  the underlying JSON decoder error, and `ArcGISTokenSession.update_token()`
  still preserves aiohttp's native `ContentTypeError` behavior for HTML token
  pages.

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

## For contributors

- [CONTRIBUTING.md](CONTRIBUTING.md) — local setup, PR checklist,
  commit conventions, gate suite.
- [ARCHITECTURE.md](ARCHITECTURE.md) — module layout, exception
  taxonomy, logger hierarchy, config precedence, session ownership,
  streaming shapes, extras matrix.
- [CHANGELOG.md](CHANGELOG.md) — every user-visible change.
- [MIGRATION.md](MIGRATION.md) — upgrading from 1.x to 2.0.

# Uses

- [restgdf_api](https://github.com/joshuasundance-swca/restgdf_api)
- [govgis_nov2023](https://huggingface.co/datasets/joshuasundance/govgis_nov2023)
