# Changelog

All notable changes to restgdf are documented here. This project follows
[Semantic Versioning](https://semver.org/).

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
