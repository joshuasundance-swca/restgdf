# Changelog

All notable changes to restgdf are documented here. This project follows
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

#### Streaming (BL-24, Q-A11, R-61, R-65)

- `FeatureLayer.iter_pages` — low-level async generator yielding raw
  ArcGIS query-page envelopes with `order` (`"request"` default /
  `"completion"`), `max_concurrent_pages` (optional semaphore bound),
  and `on_truncation` (`"raise"` default / `"ignore"` / `"split"`). The
  `"split"` strategy bisects the predicate's OID list via
  `get_object_ids` and recurses up to depth 32 before raising.
  Truncated pages under `"ignore"` log a structured warning on the
  `restgdf.pagination` logger and continue.
- `FeatureLayer.iter_features` / `FeatureLayer.stream_features` —
  flatten `iter_pages` into individual feature dicts. Deliberate
  aliases: `stream_features` is the canonical public entrypoint,
  `iter_features` the lower-level primitive.
- `FeatureLayer.stream_feature_batches` — yields one `list[feature_dict]`
  per page, mirroring `iter_pages` boundaries.
- `FeatureLayer.stream_rows` — yields row-shaped dicts (`attributes`
  merged with raw `geometry`). Pandas/GeoPandas-free; safe on a base
  install.
- `FeatureLayer.stream_gdf_chunks` — yields `GeoDataFrame` chunks over
  the optional geo stack; each chunk inherits
  `attrs["spatial_reference"]`.
- `iter_pages` now emits **exactly one** `feature_layer.stream`
  INTERNAL parent span wrapping the per-page loop when telemetry is
  enabled; no restgdf-owned per-page spans are emitted. No-op when
  `RESTGDF_TELEMETRY_ENABLED` is unset. Constructed inside
  `restgdf.utils.getgdf._iter_pages_raw`.
- Spatial-reference propagation: `restgdf.utils.getgdf.get_gdf`,
  `FeatureLayer.get_gdf`, `FeatureLayer.sample_gdf`,
  `FeatureLayer.head_gdf`, and `chunk_generator` /
  `FeatureLayer.stream_gdf_chunks` all stamp
  `gdf.attrs["spatial_reference"]` with the raw dict from the layer's
  metadata envelope (`extent.spatialReference` preferred, top-level
  `spatialReference` fallback). Normalization uses
  `restgdf.utils._metadata.normalize_spatial_reference`.

#### Adapters + tabular output (BL-34, Q-S6)

- `restgdf.adapters` subpackage (lazy-loaded via PEP 562): four
  submodules covering dict / stream / pandas / geopandas shapes. All
  submodules are base-install safe at import time; pandas and
  geopandas are required only at call time and raise
  `OptionalDependencyError` when missing.
  - `restgdf.adapters.dict` — `feature_to_row`, `features_to_rows`,
    plus `as_dict` / `as_json_dict` re-exports.
  - `restgdf.adapters.stream` — `iter_feature_batches`, `iter_rows`,
    `iter_gdf_chunks`.
  - `restgdf.adapters.pandas` — `rows_to_dataframe` (sync) +
    `arows_to_dataframe` (async).
  - `restgdf.adapters.geopandas` — `rows_to_geodataframe` +
    `arows_to_geodataframe`.
- `FeatureLayer.get_df()` — async pandas-first tabular accessor.
  Sibling to `get_gdf()` that returns a `pandas.DataFrame` from the
  same row stream and does **not** require the geo extra.

#### Configuration (BL-18)

- `restgdf.Config` — frozen pydantic 2.x aggregate of seven frozen
  sub-configs (`TransportConfig`, `TimeoutConfig`, `RetryConfig`,
  `LimiterConfig`, `ConcurrencyConfig`, `AuthConfig`,
  `TelemetryConfig`) plus `Config.from_env(env=None)` classmethod.
  Sub-configs and the aggregate are immutable at both slot and
  nested-field level.
- `restgdf.get_config()` — process-wide cached `Config` accessor
  (`functools.lru_cache(maxsize=1)`).
- `restgdf.reset_config_cache()` — clears the cache; cascades
  bidirectionally with the existing `reset_settings_cache` so tests
  can refresh all configuration with a single call regardless of
  which accessor they use.
- Nested env-var surface `RESTGDF_<CATEGORY>_<FIELD>` wired through
  `Config.from_env` for every sub-config field
  (`RESTGDF_TRANSPORT_USER_AGENT`, `RESTGDF_TIMEOUT_TOTAL_S`,
  `RESTGDF_RETRY_ENABLED`, `RESTGDF_LIMITER_RATE_PER_HOST`,
  `RESTGDF_CONCURRENCY_MAX_CONCURRENT_REQUESTS`,
  `RESTGDF_AUTH_TOKEN_URL`, `RESTGDF_TELEMETRY_LOG_LEVEL`, …).
  Invalid coercions and validator rejections raise
  `RestgdfResponseError` with the underlying
  `pydantic.ValidationError` preserved as `__cause__`.
- `Settings.max_concurrent_requests: int = 8` (field) +
  `RESTGDF_MAX_CONCURRENT_REQUESTS` env-var coercion (BL-01). Default
  matches aiohttp `TCPConnector` pool size.

#### Errors (BL-06, BL-10, BL-36)

- `restgdf.errors` module exposing the canonical exception taxonomy:
  `RestgdfError`, `ConfigurationError`, `OptionalDependencyError`,
  `TransportError`, `RestgdfTimeoutError`, `RateLimitError`,
  `ArcGISServiceError`, `PaginationError`, `FieldDoesNotExistError`,
  `SchemaValidationError`, `AuthenticationError`, and
  `OutputConversionError`. All re-exported from the top-level
  `restgdf` package via the lazy-import hook.
- `PaginationError.batch_index` / `.page_size` attributes carry
  pagination context when cursor-based iteration fails.
- `RateLimitError.retry_after` attribute carries the optional
  seconds-until-retry hint, populated from the server's `Retry-After`
  header (integer seconds or RFC 7231 HTTP-date) by the resilience
  wrapper (Q-A12). New helper `_parse_retry_after` in
  `restgdf.resilience._errors`.
- Error-attribute population: `RestgdfResponseError` now carries
  optional `url`, `status_code`, and `request_id` attributes (kw-only,
  default `None`). `TransportError` gains `url` and `status_code`.
  `RestgdfTimeoutError` gains `timeout_kind` (`"total"`, `"connect"`,
  `"read"`). `RateLimitError` gains `url` and `status_code` alongside
  existing `retry_after`. All new attrs are backward-compatible —
  existing call sites that omit them get `None` defaults.
- Five `AuthenticationError` subclasses —
  `InvalidCredentialsError`, `TokenExpiredError`,
  `TokenRequiredError`, `TokenRefreshFailedError`,
  `AuthNotAttachedError`. All carry `.context`, `.attempt`, `.cause`
  attributes with `SecretStr` auto-redaction.

#### Auth runtime (BL-12, BL-15, BL-16, R-15)

- `TokenSessionConfig.refresh_leeway_seconds` (default `60`) +
  `TokenSessionConfig.clock_skew_seconds` (default `30`) — explicit
  integer fields (`ge=0`) replacing the implicit semantics of the
  previous single `refresh_threshold_seconds` knob (BL-04).
- `ArcGISTokenSession.expires_at` — tz-aware UTC `datetime` property
  computed from the epoch-ms `expires` field.
- `_utc_now()` shim for deterministic wall-clock test control.
- Structured `auth.refresh.start` / `.success` / `.failure` log
  events at DEBUG level on the `restgdf.auth` logger.
- Bounded `/generateToken` retry — transient errors retried up to 3×
  with exponential backoff; deterministic errors propagate
  immediately. After exhaustion raises `TokenRefreshFailedError`.
- Referer binding — `token_request_payload` honours `config.referer`
  and switches ArcGIS `client` to `"referer"` when set.

#### Normalization (BL-23, BL-28, BL-54)

- `restgdf._models.responses.NormalizedGeometry`,
  `NormalizedFeature`, and `iter_normalized_features(response, *,
  oid_field=None, sr=None)` — typed intermediate models plus iterator
  over `FeaturesResponse.features`. Wire-level `features: list[dict]`
  stays for perf; normalization is opt-in. Geometry `type` is
  heuristically inferred from shape; `object_id` is `int`-coerced
  from `attributes[oid_field]`.
- `restgdf._models.responses.AdvancedQueryCapabilities` — typed
  `PermissiveModel` companion for the ArcGIS
  `advancedQueryCapabilities` sub-object, with camelCase / snake_case
  `AliasChoices` wiring and permissive `extra="allow"` preservation
  of unknown keys (BL-21).
- `LayerMetadata.advanced_query_capabilities_typed:
  AdvancedQueryCapabilities | None` — additive typed companion to the
  existing raw `advanced_query_capabilities: dict | None` field.
  Caller-opt-in; the raw dict stays the default representation.
- `restgdf.utils._metadata.normalize_spatial_reference(sr)` — pure
  helper returning `(epsg_int | None, raw_dict | None)` that prefers
  `latestWkid` over `wkid` for EPSG-consuming clients (R-28).
- `concat_gdfs` propagates `GeoDataFrame.attrs["spatial_reference"]`
  across concatenation.
- `restgdf.utils._metadata.normalize_date_fields(features, fields)` —
  converts ArcGIS `esriFieldTypeDate` epoch-ms integers to ISO-8601
  UTC strings. Opt-in via `normalize_dates=True` on the adapter layer.

#### Pagination (BL-22)

- `restgdf.utils._pagination.PaginationPlan` (frozen dataclass) +
  `build_pagination_plan(total_records, max_record_count, *,
  factor=1.0, advertised_factor=None)` — pure-math pagination planner
  re-exported via `restgdf.utils.getinfo`. Emits
  `(resultOffset, resultRecordCount)` tuples byte-identical to the
  previous inline arithmetic in `get_query_data_batches`; clamps
  `factor > advertised_factor` with a warning via
  `get_logger("pagination")`. `get_query_data_batches` is rerouted
  through the planner with no public-signature change and all pinned
  fixtures preserved.

#### Observability (BL-25, BL-26, BL-32, BL-33)

- `restgdf._logging.get_logger(suffix)` library-wide logger factory
  and `build_log_extra` standard `extra=` envelope helper. Existing
  `get_drift_logger` / `restgdf.schema_drift` contract unchanged.
- `restgdf[telemetry]` optional extra — `RestgdfInstrumentor`
  (dynamic subclass of `AioHttpClientInstrumentor`, R-58),
  `feature_layer_stream_span` async context manager (INTERNAL span,
  R-21), `span_context_fields` helper, and `_SpanContextFilter`
  auto-attached to the `restgdf` root logger for trace/span log
  correlation.
- `docs/recipes/tracing.md` — structured observability,
  error-attribute inspection, and OpenTelemetry integration.
- `docs/recipes/streaming.md` — the three streaming shapes,
  `on_truncation` options, `order` variants, and
  `max_concurrent_pages` knob.

#### Resilience (BL-31, BL-52)

- `restgdf.ResilienceConfig` — frozen pydantic sub-config controlling
  the stamina-based retry wrapper and per-service-root token-bucket
  rate limiter. Fields: `enabled`,
  `rate_per_service_root_per_second`, `respect_retry_after_max_s`,
  `fallback_retry_after_seconds`, `backend`. Exposed via
  `restgdf.Config.resilience` and in top-level `__all__`. Disabled by
  default; opt in via `RESTGDF_RESILIENCE_ENABLED=1`.
- `restgdf.resilience.ResilientSession` — retry + rate-limit adapter
  implementing the `AsyncHTTPSession` protocol. Stamina-based retry
  with 429/5xx awareness. Pure pass-through when
  `ResilienceConfig.enabled=False`. Requires
  `pip install restgdf[resilience]`.
- `[project.optional-dependencies] resilience` extra:
  `stamina>=24.2`, `aiolimiter>=1.1`.
- Per-service-root token-bucket rate limiting via `LimiterRegistry`
  and 429-cooldown via `CooldownRegistry` in
  `restgdf.resilience._limiter`. `_service_root(url)` derives the
  rate-limit key by truncating at the first
  `FeatureServer` / `MapServer` / `ImageServer` / `SceneServer` path
  segment.

#### Transport protocols + drift (BL-17, BL-20, BL-27)

- `restgdf._client._protocols.AsyncHTTPSession` —
  `@runtime_checkable` `typing.Protocol` capturing the
  `get` / `post` / `close` / `closed` surface restgdf transport
  sessions rely on; re-exported from `restgdf._client`.
- `restgdf._models._drift.FieldSetDriftObserver` — observer class
  that tracks attribute-key appearance / disappearance across
  feature-page batches and emits deduped
  `field_appeared` / `field_disappeared` records through the existing
  `restgdf.schema_drift` logger.
- Private `restgdf.utils._http._choose_verb(url, body=None)` seam
  returning `"POST"` for `/query` and `/queryRelatedRecords`, `"GET"`
  for bare service/layer metadata URLs, and `"POST"` as the
  conservative default. Call sites unchanged; forward-compatible stub
  for BL-50's future ~1800-byte GET→POST auto-switch.

#### Internal helpers

- `restgdf.utils._concurrency.bounded_gather(*aws, semaphore)` —
  caps concurrent fan-out via an `asyncio.BoundedSemaphore` while
  preserving `asyncio.gather` result ordering and `return_exceptions`
  semantics (BL-01).
- `restgdf.utils.getinfo._feature_count_with_timeout` — inline
  bounded retry around `get_feature_count` with exponential backoff.
  Retries only on `asyncio.TimeoutError`, `TimeoutError`, and
  `aiohttp.ServerTimeoutError`; connection-level failures
  (`aiohttp.ClientConnectionError`) and deterministic errors
  (`RestgdfResponseError`, schema mismatches) propagate on the first
  attempt. Exhausted timeouts raise `RestgdfTimeoutError` with
  `__cause__` preserved (BL-51).
- `Directory.safe_crawl` now routes its per-layer `feature_count`
  probe through a `BoundedSemaphore` sized from
  `ConcurrencyConfig.max_concurrent_requests` (Q-A7).
- `restgdf.__getattr__` now consults a `_REMOVED_EXPORTS` extension
  point before raising `AttributeError`, letting future phases
  register removed top-level names with a `DeprecationWarning` +
  migration message. Mapping empty in this release (BL-57).

#### Tests + tooling

- Taxonomy + observability contract tests
  (`tests/test_taxonomy_contract.py`) asserting `errors.__all__`
  shape and that `get_logger(suffix)` emits a structured record for
  every `LOGGER_SUFFIXES` entry (BL-37).
- Minimal-install contract test (`tests/test_minimal_install.py`)
  guarding against accidental import of `pandas` / `geopandas` /
  `pyogrio` when users install the base package without extras
  (BL-38).
- Streaming-recipe discoverability regression test
  (`tests/test_streaming_recipe_discoverable.py`).
- `hypothesis`, `aioresponses`, and `opentelemetry-sdk` added to the
  `dev` extra. New `tests/test_crawl_property_hypothesis.py` scaffold
  and `tests/_mocks/aioresponses_helpers.py` shared fixtures (BL-39,
  R-62 scope).

### Changed

#### Breaking

- Default token wire transport flipped from `"body"` to `"header"`
  (BL-13). Tokens are now sent via the `X-Esri-Authorization`
  header. Set `transport="body"` in `AuthConfig` /
  `TokenSessionConfig` to restore the old behavior.
- `refresh_leeway_seconds` default raised 60 → 120 (BL-13).
- `getgdf` / `_get_sub_features` now raise
  `restgdf.errors.PaginationError` (not `RuntimeError`) on
  `exceededTransferLimit=true`. `PaginationError` carries
  `batch_index` and `page_size` (BL-08).
- `PaginationError` no longer multi-inherits `RuntimeError` (phase-3d
  consolidation under the BL-06 taxonomy). Callers catching
  `RuntimeError` around `feature_count` / pagination calls must
  widen to `RestgdfError` or narrow to `PaginationError` /
  `ArcGISServiceError` (BL-09, R-02).

#### Non-breaking

- `ArcGISTokenSession.token_needs_update` refactored to use
  `expires_at` and `_utc_now()` instead of inline epoch arithmetic
  (BL-16).
- Reactive 498/499 handling in `_call_with_auth_retry` — HTTP 498
  triggers single-flight refresh + one retry; HTTP 499 raises
  `AuthNotAttachedError` immediately (BL-11).
- `restgdf.utils.getinfo.service_metadata`,
  `restgdf.utils.crawl.fetch_all_data`, and
  `restgdf.utils.crawl.safe_crawl` now route their internal
  `asyncio.gather` fan-out through `bounded_gather` with a per-call
  `asyncio.BoundedSemaphore`. Saturation semantics = wait (no new
  exception) (BL-01).
- `ArcGISTokenSession.update_token_if_needed` now collapses concurrent
  refresh attempts onto a single `/generateToken` POST via a
  lazily-initialized per-instance `asyncio.Lock` with a double-checked
  `token_needs_update()` inside the lock. The new `_refresh_lock`
  field is `init=False`, `repr=False`, `compare=False` (BL-03).
- `RestgdfResponseError` now inherits from
  `restgdf.errors.RestgdfError` in addition to `ValueError`. Class
  identity and the
  `from restgdf._models._errors import RestgdfResponseError` import
  path are preserved; `except ValueError:` call sites keep working
  (BL-06).
- `restgdf.utils._optional._optional_dependency_error` now returns
  `restgdf.errors.OptionalDependencyError` instead of a bare
  `ModuleNotFoundError`. Existing `except ModuleNotFoundError:` and
  `except ImportError:` handlers still catch the new exception
  because `OptionalDependencyError` multi-inherits
  `ModuleNotFoundError` (BL-07).
- HTTP timeouts are now plumbed through `Settings.timeout_seconds`
  into every library-maintained `session.get` / `session.post` call
  site (`restgdf.utils._query`, `restgdf.utils._stats`,
  `restgdf.utils.getgdf._get_sub_features` / `get_sub_gdf`,
  `ArcGISTokenSession.update_token`, and the
  `ArcGISTokenSession.get` / `.post` wrappers). The new
  `restgdf.utils._http.default_timeout()` helper returns an
  `aiohttp.ClientTimeout` sized from `Settings.timeout_seconds`
  (float, default `30.0`, overridable via `RESTGDF_TIMEOUT_SECONDS`).
  Callers that already pass `timeout=` keep precedence (BL-02).
- `ArcGISTokenSession.__post_init__` now respects a caller-supplied
  `config=TokenSessionConfig(...)` instead of overwriting it, and
  derives the `TokenSessionConfig` split fields from
  `token_refresh_threshold` internally (no longer via the deprecated
  `refresh_threshold_seconds` alias), so plain construction no
  longer fires a `DeprecationWarning`. `token_refresh_threshold` is
  resynced from the validated config after construction.
- `pyproject.toml::[tool.coverage.report].exclude_also` extended with
  `if TYPE_CHECKING:`, `@overload`, and bare-ellipsis stub lines
  (standard coverage.py idioms, pydantic / httpx / attrs precedent).
  Threshold `fail_under=97` unchanged (R-63).

### Deprecated

- `FeatureLayer.row_dict_generator` — use `FeatureLayer.stream_rows`.
  Emits `DeprecationWarning` and continues to delegate to the
  module-level `row_dict_generator` helper for backwards
  compatibility with existing `unittest.mock.patch` call sites.
- `get_token()` — emits `DeprecationWarning` on every call (BL-14).
  Migrate to `ArcGISTokenSession` for async token management.
  `get_token` now also accepts `pydantic.SecretStr` passwords.
- `restgdf.Settings` / `restgdf.get_settings()` — use
  `restgdf.Config` / `restgdf.get_config()`. `get_settings()` emits a
  single `DeprecationWarning` on first call and constructs its return
  value from `get_config()`; existing callers continue to work
  unchanged. Will be removed no earlier than restgdf 3.0 (BL-18).
- Six flat environment variables — `RESTGDF_TIMEOUT_SECONDS`,
  `RESTGDF_TOKEN_URL`, `RESTGDF_REFRESH_THRESHOLD`,
  `RESTGDF_USER_AGENT`, `RESTGDF_LOG_LEVEL`,
  `RESTGDF_MAX_CONCURRENT_REQUESTS` — in favour of their
  `RESTGDF_<CATEGORY>_<FIELD>` replacements. The old names continue
  to work but emit a `DeprecationWarning` when read via
  `Config.from_env` / `get_config`; when both old and new names are
  set the new one wins and the warning notes the override (BL-18).
- `TokenSessionConfig.refresh_threshold_seconds` — a read/write alias
  emitting `DeprecationWarning`. Reads return
  `refresh_leeway_seconds + clock_skew_seconds`; constructor writes
  split the supplied total into
  `clock_skew_seconds = min(30, total)` and
  `refresh_leeway_seconds = total - clock_skew_seconds`. Migrate to
  the explicit field pair.

### Removed

- `restgdf.utils._metadata.FIELDDOESNOTEXIST` sentinel (and its
  re-export via `restgdf.utils.getinfo`). Call sites must now
  `except FieldDoesNotExistError` from the BL-06 taxonomy. Hard break
  — no compat shim (BL-09, R-02).

### Fixed

- `ArcGISTokenSession.update_token` now forwards the session's
  `verify_ssl` flag as `ssl=` on the `/generateToken` POST.
  Previously the flag was honoured for feature / query requests but
  ignored during token refresh, so `verify_ssl=False` sessions could
  still fail TLS verification against self-signed ArcGIS Enterprise
  deployments.


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
