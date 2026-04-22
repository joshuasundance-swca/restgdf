# Changelog

All notable changes to restgdf are documented here. This project follows
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- `restgdf.errors` module exposing the canonical exception taxonomy:
  `RestgdfError`, `ConfigurationError`, `OptionalDependencyError`,
  `TransportError`, `RestgdfTimeoutError`, `RateLimitError`,
  `ArcGISServiceError`, `PaginationError`, `SchemaValidationError`,
  `AuthenticationError`, and `OutputConversionError`. All are
  re-exported from the top-level `restgdf` package via the lazy-import
  hook (BL-06).
- `PaginationError.batch_index` and `.page_size` attributes carry
  pagination context when cursor-based iteration fails (BL-06).
- `RateLimitError.retry_after` attribute carries an optional
  seconds-until-retry hint (BL-06).
- `restgdf.__getattr__` now consults a `_REMOVED_EXPORTS` extension
  point before raising `AttributeError`, letting future phases register
  removed top-level names with a `DeprecationWarning` + migration
  message. Mapping is empty in this release (BL-57).

### Changed

- `RestgdfResponseError` now inherits from `restgdf.errors.RestgdfError`
  in addition to `ValueError`. Class identity and the
  `from restgdf._models._errors import RestgdfResponseError` import
  path are preserved; `except ValueError:` call sites keep working
  (BL-06).
- `restgdf.utils._optional._optional_dependency_error` now returns
  `restgdf.errors.OptionalDependencyError` instead of a bare
  `ModuleNotFoundError`. Existing `except ModuleNotFoundError:` and
  `except ImportError:` handlers still catch the new exception because
  `OptionalDependencyError` multi-inherits `ModuleNotFoundError` (BL-07).

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
