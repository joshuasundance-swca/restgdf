# Changelog

All notable changes to restgdf are documented here. This project follows
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- `restgdf.utils._concurrency.bounded_gather(*aws, semaphore)` — internal
  helper that caps concurrent fan-out via an `asyncio.BoundedSemaphore`
  while preserving `asyncio.gather` result ordering and
  `return_exceptions` semantics (BL-01).
- `Settings.max_concurrent_requests: int = 8` (field) +
  `RESTGDF_MAX_CONCURRENT_REQUESTS` env-var coercion. Caps the in-flight
  HTTP fan-out inside every top-level restgdf orchestration call. Default
  matches aiohttp `TCPConnector` pool size (BL-01).
- Private `restgdf.utils._http._choose_verb(url, body=None)` seam
  returning `"POST"` for `/query` and `/queryRelatedRecords`, `"GET"`
  for bare service/layer metadata URLs, and `"POST"` as the
  conservative default. Call sites unchanged; forward-compatible stub
  for BL-50's future ~1800-byte GET→POST auto-switch (BL-20).

### Changed

- `restgdf.utils.getinfo.service_metadata`,
  `restgdf.utils.crawl.fetch_all_data`, and
  `restgdf.utils.crawl.safe_crawl` now route their internal
  `asyncio.gather` fan-out through `bounded_gather` with a per-call
  `asyncio.BoundedSemaphore`. Saturation semantics = wait (no new
  exception) (BL-01).
- `ArcGISTokenSession.update_token_if_needed` now collapses concurrent
  refresh attempts onto a single `/generateToken` POST via a
  lazily-initialized per-instance `asyncio.Lock` with a double-checked
  `token_needs_update()` inside the lock. The new `_refresh_lock` field
  is `init=False`, `repr=False`, `compare=False` (BL-03).

## [2.0.0] - 2026-04-20

**Major release — pydantic 2.13 integration.** See
[`MIGRATION.md`](./MIGRATION.md) for a complete breaking-changes table and
migration recipes.

### Breaking

- Public return and attribute shapes changed from plain `dict` /
  `TypedDict` to pydantic `BaseModel` classes:
  - `FeatureLayer.metadata` → `LayerMetadata`
  - `Directory.metadata` → `LayerMetadata`
  - `Directory.services`, `Directory.services_with_feature_count`,
    and `Directory.crawl(...)` → `list[CrawlServiceEntry]`
  - `get_metadata(...)` → `LayerMetadata`
  - `safe_crawl(...)` → `CrawlReport`
- `AGOLUserPass.password` is now `pydantic.SecretStr`; call
  `.get_secret_value()` at the HTTP-POST boundary.
- `restgdf._types.*` TypedDicts are replaced by lazy aliases that
  re-export the new pydantic models and emit `DeprecationWarning` on
  import. The shim will be removed in 3.x.

### Added

- `LayerMetadata`, `ServiceInfo`, `FieldSpec`, `Feature`,
  `FeaturesResponse`, `CountResponse`, `ObjectIdsResponse`,
  `TokenResponse`, `ErrorInfo`, `ErrorResponse`, `CrawlReport`,
  `CrawlServiceEntry`, `CrawlError` — pydantic response models.
- `AGOLUserPass`, `TokenSessionConfig` — pydantic credentials / session
  config models.
- `Settings`, `get_settings` — process-wide runtime configuration backed
  by `RESTGDF_*` environment variables (`CHUNK_SIZE`, `TIMEOUT_SECONDS`,
  `USER_AGENT`, `LOG_LEVEL`, `TOKEN_URL`, `REFRESH_THRESHOLD`,
  `DEFAULT_HEADERS_JSON`).
- `RestgdfResponseError` — typed error raised when a strict-tier
  response fails validation; carries `model_name`, `context`, and `raw`
  payload attributes.
- `restgdf.compat.as_dict` / `restgdf.compat.as_json_dict` — migration
  helpers that convert any returned model (or passthrough any non-model)
  to a plain dict.
- `restgdf.schema_drift` logger — opt-in observability for vendor
  variance; `NullHandler` by default.
- `Directory.report` — the full `CrawlReport` (services, errors,
  root metadata) from the most recent `.crawl()` call.

### Dependencies

- Added `pydantic>=2.13.3,<3`.

## 1.x

Earlier releases were not formally tracked here. See the
[Git tag history](https://github.com/joshuasundance-swca/restgdf/tags) and
[PyPI release notes](https://pypi.org/project/restgdf/#history) for pre-2.0
changes.
