# restgdf migration guide

## Unreleased migration notes

The 3.0 release reshapes install surface, error taxonomy, configuration,
authentication, observability, and streaming on top of the typed
pydantic models that landed in 2.0. Everything below is consolidated
across the phase-1 through phase-4 work tracks — the preserved 1.x → 2.0
guide follows at the bottom unchanged.

### Summary

- **Install surface:** `pip install restgdf` is now a light-core install
  (typed metadata, raw rows, directory crawl, token/session helpers).
  GeoPandas/pandas/pyogrio move behind `pip install "restgdf[geo]"`.
  New optional extras `restgdf[resilience]` (stamina + aiolimiter) and
  `restgdf[telemetry]` (opentelemetry-api + aiohttp client
  instrumentation) opt callers into retry/rate-limiting and
  OpenTelemetry respectively. All extras compose with each other and
  with `restgdf[geo]`.
- **Streaming:** `FeatureLayer` grows three canonical streaming shapes
  on top of `iter_pages` (`stream_features` / `stream_feature_batches`
  / `stream_rows`) with shared `on_truncation` / `order` /
  `max_concurrent_pages` knobs and the R-61 `feature_layer.stream`
  parent span. `stream_gdf_chunks` remains as the legacy
  `GeoDataFrame`-per-page shape (requires `restgdf[geo]`, backed by
  `chunk_generator`, completion-order only, does not take the shared
  knobs). `row_dict_generator` is deprecated in favour of
  `stream_rows`. See `docs/recipes/streaming.md`.
- **Errors:** Single taxonomy rooted at `restgdf.errors.RestgdfError`
  (public). Every class additively multi-inherits the matching builtin
  (`ValueError`, `TimeoutError`, `PermissionError`, `IndexError`,
  `ModuleNotFoundError`) so existing `except` clauses keep catching.
- **Configuration:** `restgdf.Config` (eight frozen sub-configs) now
  supersedes the flat `Settings`. Six `RESTGDF_*` env vars are aliased
  to structured `RESTGDF_<CATEGORY>_<FIELD>` names; the old names still
  work and emit `DeprecationWarning` on read.
- **Authentication:** Default wire transport is now header-based
  (`X-Esri-Authorization`); token refresh is single-flight, bounded-
  retry, reactive on 498/499, and emits structured `restgdf.auth` log
  events. `expires_at` is a tz-aware UTC `datetime`.
- **Observability:** Named loggers under `restgdf.<suffix>`
  (`transport` / `retry` / `limiter` / `concurrency` / `auth` /
  `pagination` / `normalization` / `schema_drift`) each attached with a
  `NullHandler`. Telemetry emits exactly one INTERNAL
  `feature_layer.stream` parent span per `iter_pages` call.
- **Public API additions:** adapters subpackage, pandas-first
  `FeatureLayer.get_df()`, `NormalizedGeometry` / `NormalizedFeature`
  iterator, `AdvancedQueryCapabilities` typed companion,
  `PaginationPlan` / `build_pagination_plan`, pure-helper
  `normalize_spatial_reference` and `normalize_date_fields`, and
  `ResilientSession` / `RestgdfInstrumentor`.
- **Version strings are frozen at `2.0.0`** until the 3.0 cut so the
  taxonomy/contract tests (`tests/test_compat.py`) stay green through
  the rewrite.

### Breaking changes

**Install**

- `pip install restgdf` no longer guarantees that `geopandas`,
  `pandas`, or `pyogrio` are importable.
- GeoDataFrame and pandas-backed helpers — `FeatureLayer.get_gdf()`,
  `sample_gdf()`, `head_gdf()`, `fieldtypes`, `get_fields_frame()`,
  multi-field `get_unique_values()`, `get_value_counts()`,
  `get_nested_count()`, and `restgdf.utils.getgdf` helpers — now require
  `pip install "restgdf[geo]"` and raise `OptionalDependencyError`
  (subclass of `ConfigurationError` / `ModuleNotFoundError`) with an
  install hint when the optional stack is missing.
- Light-core workflows keep working without the geo stack: typed
  response models, `FeatureLayer.from_url`, `.metadata`, `.count`,
  `.get_oids()`, raw row iteration, directory crawling, and token
  helpers.

**Errors**

- `getgdf` / `_get_sub_features` raise
  `restgdf.errors.PaginationError` instead of `RuntimeError` when a
  page reports `exceededTransferLimit=true`. The exception now carries
  `batch_index` and `page_size` attributes. `PaginationError` multi-
  inherits `IndexError` (2.x behavior preserved) but no longer
  multi-inherits `RuntimeError` — migrate `except RuntimeError:` call
  sites to `except PaginationError:` / `except ArcGISServiceError:` /
  `except RestgdfError:`.
- The legacy `FIELDDOESNOTEXIST` sentinel (and its re-export through
  `restgdf.utils.getinfo`) is gone. Call sites must now
  `except FieldDoesNotExistError` (new `SchemaValidationError` subclass).
- Metadata/query/crawl helpers that decode a successful JSON body
  matching the ArcGIS `{"error": {...}}` envelope now raise
  `RestgdfResponseError` immediately with `raw` attached, instead of
  silently treating it as schema drift.

**Auth**

- `ArcGISTokenSession` now defaults to sending the token via the
  `X-Esri-Authorization` header. If your server requires the legacy
  body/query transport, set `AuthConfig(transport="body")` or
  `TokenSessionConfig(transport="body")`.
- `refresh_leeway_seconds` default raised from **60 → 120** — proactive
  token refresh now fires two minutes before expiry instead of one.
- `refresh_threshold_seconds` on `TokenSessionConfig` is retained as a
  deprecation alias; reads/writes emit `DeprecationWarning`. Migrate to
  the explicit `refresh_leeway_seconds` + `clock_skew_seconds` split
  (defaults `60` + `30`, sum preserved).

**Streaming**

- `FeatureLayer.row_dict_generator` emits `DeprecationWarning`. It
  delegates to `stream_rows`; migrate at your convenience.
- All `stream_*` methods default to `on_truncation="raise"`. Callers
  that previously silently ignored `exceededTransferLimit=true` must
  either opt into `on_truncation="ignore"` (warn-and-continue) or
  `on_truncation="split"` (OID-bisect and recurse, up to 32 levels).

### New public APIs

**Errors** (`restgdf.errors`)

```
RestgdfError
├── ConfigurationError(RestgdfError, ValueError)
│   └── OptionalDependencyError(ConfigurationError, ModuleNotFoundError)
├── RestgdfResponseError(RestgdfError, ValueError)
│   ├── SchemaValidationError
│   │   └── FieldDoesNotExistError
│   ├── ArcGISServiceError
│   │   └── PaginationError(ArcGISServiceError, IndexError)  # .batch_index, .page_size
│   └── AuthenticationError(RestgdfResponseError, PermissionError)
│       ├── InvalidCredentialsError        # HTTP 401
│       ├── TokenExpiredError              # HTTP 498 after refresh
│       ├── TokenRequiredError
│       ├── TokenRefreshFailedError        # /generateToken retries exhausted
│       └── AuthNotAttachedError           # HTTP 499
├── TransportError
│   ├── RestgdfTimeoutError(TransportError, TimeoutError)
│   └── RateLimitError(TransportError)     # .retry_after
└── OutputConversionError
```

- All classes re-export from the top-level `restgdf` package.
- `RestgdfResponseError`, `TransportError`, `RestgdfTimeoutError`, and
  `RateLimitError` now accept optional `url`, `status_code`,
  `request_id`, and `timeout_kind` kwargs (all default to `None`).
- `RateLimitError.retry_after` is populated from the server's
  `Retry-After` header (integer seconds or RFC 7231 HTTP-date) by the
  resilience wrapper.

**Streaming** (`FeatureLayer`)

| Method                    | Yields                              | Install        |
| ------------------------- | ----------------------------------- | -------------- |
| `stream_features`         | one raw ArcGIS feature dict         | base           |
| `stream_feature_batches`  | `list[feature_dict]` per page       | base           |
| `stream_rows`             | row-shaped dict (attrs + geometry)  | base           |
| `stream_gdf_chunks`       | `GeoDataFrame` per page             | `restgdf[geo]` |
| `iter_pages` (low-level)  | raw page envelope                   | base           |

`stream_features`, `stream_feature_batches`, `stream_rows`, and
`iter_pages` share these knobs:

- `on_truncation: "raise" | "ignore" | "split"` (default `"raise"`).
- `order: "request" | "completion"` (default `"request"`; `"completion"`
  may interleave pages — do not use for append-ordered downstream
  writers).
- `max_concurrent_pages: int | None` (default `None` — bounded only by
  `ConcurrencyConfig.max_concurrent_requests`).

`stream_gdf_chunks` is backed by the legacy `chunk_generator` pipeline
(pyogrio + ESRIJSON/GeoJSON parsing) rather than `iter_pages`. It
yields chunks in completion order and does **not** accept
`on_truncation`, `order`, or `max_concurrent_pages`, and it does not
emit the R-61 `feature_layer.stream` parent span. For geo output with
the full knob set, compose `stream_rows` or `stream_features` with
your own geometry assembly, or use `get_gdf` / `get_gdf_list`.

Each `GeoDataFrame` yielded by `stream_gdf_chunks` carries the layer's
spatial reference in `gdf.attrs["spatial_reference"]` (R-65).

See `docs/recipes/streaming.md` for copy-pasteable examples.

**Adapters** (`restgdf.adapters`, lazy-loaded via PEP 562)

- `restgdf.adapters.dict` — `feature_to_row`, `features_to_rows`,
  re-exports `as_dict` / `as_json_dict`. Pure-Python, base-install safe.
- `restgdf.adapters.stream` — async iterators `iter_feature_batches`,
  `iter_rows`, `iter_gdf_chunks` wrapping the core generator helpers.
  `iter_gdf_chunks` requires the geo extra at call time.
- `restgdf.adapters.pandas` — `rows_to_dataframe` (sync) +
  `arows_to_dataframe` (async). Calls `require_pandas(...)` before
  materialization; no pandas import at module load.
- `restgdf.adapters.geopandas` — `rows_to_geodataframe` +
  `arows_to_geodataframe`. Calls `require_geo_stack(...)` before
  materialization; no geopandas/pyogrio import at module load.

**Tabular output** (`FeatureLayer.get_df`)

Pandas-first sibling to `get_gdf()`. Returns a `pandas.DataFrame` built
from the same row stream; raises `OptionalDependencyError`
(`extra="pandas"`) if pandas is missing. Geopandas is **not** required.

**Response normalization** (`restgdf._models.responses`)

- `NormalizedGeometry` / `NormalizedFeature` + `iter_normalized_features(
  response, *, oid_field=None, sr=None)`.
- Wire-level `FeaturesResponse.features` stays `list[dict]` for perf;
  normalization is opt-in via the iterator.
- `NormalizedGeometry.type` is inferred heuristically from the geometry
  dict shape (`point` / `multipoint` / `polyline` / `polygon` /
  `envelope` / `None`). `object_id` is hoisted from
  `attributes[oid_field]` via `int(value)` and tolerates unparsable
  values by leaving `object_id=None`.

**Metadata helpers** (`restgdf.utils._metadata`)

- `normalize_spatial_reference(sr)` — pure helper returning
  `(epsg_int | None, raw_dict | None)`. Prefers `latestWkid` over
  `wkid` for EPSG-consuming clients; preserves the original
  `{wkid, latestWkid}` mapping as the raw component for round-trip
  fidelity.
- `normalize_date_fields(features, fields)` — converts ArcGIS
  `esriFieldTypeDate` epoch-ms integers to ISO-8601 UTC strings.
  Defaults preserve the integer representation; opt in with
  `normalize_dates=True` on the adapter layer.
- `GeoDataFrame.attrs["spatial_reference"]` propagation through
  `concat_gdfs` and `stream_gdf_chunks`.

**Pagination** (`restgdf.utils._pagination`, re-exported via
`restgdf.utils.getinfo`)

- Frozen `PaginationPlan` dataclass + sync
  `build_pagination_plan(total_records, max_record_count, *,
  factor=1.0, advertised_factor=None)`. Emits
  `(resultOffset, resultRecordCount)` tuples byte-identical to the
  previous inline arithmetic. When `factor` exceeds
  `advertised_factor` the planner clamps to the advertised value and
  logs a warning via `restgdf.pagination`. Live
  `advancedQueryCapabilities.maxRecordCountFactor` wiring into
  `get_query_data_batches` is a deliberate post-3.0 follow-up.

**Advanced query capabilities** (`restgdf._models.responses`)

- `AdvancedQueryCapabilities` — typed `PermissiveModel` companion for
  the ArcGIS `advancedQueryCapabilities` sub-object (five flags
  restgdf routes on: `supportsPagination`, `supportsQueryByOIDs`,
  `supportsReturnExceededLimitFeatures`,
  `supportsPaginationOnAggregatedQueries`, `maxRecordCountFactor`).
  Unknown keys survive via the permissive tier. Exposed as the
  additive companion
  `LayerMetadata.advanced_query_capabilities_typed: AdvancedQueryCapabilities | None`
  — the raw dict on `advanced_query_capabilities` stays the default
  representation so permissive-tier consumers keep working
  byte-for-byte.

**Transport protocols** (`restgdf._client`)

- `AsyncHTTPSession` — `typing.Protocol` (`@runtime_checkable`)
  capturing the `get` / `post` / `close` / `closed` surface restgdf
  call sites rely on. `isinstance(aiohttp.ClientSession(),
  AsyncHTTPSession)` holds at runtime.

**Drift observation** (`restgdf._models._drift`)

- `FieldSetDriftObserver` — observer class that tracks attribute-key
  appearance/disappearance across feature-page batches. Emits
  `field_appeared` / `field_disappeared` records via the
  `restgdf.schema_drift` logger. Empty pages are skipped.
  Observation-only; never blocking.

**Resilience extra** (`pip install restgdf[resilience]`)

- `restgdf.resilience.ResilientSession` wraps any `AsyncHTTPSession`
  with stamina-based retry (429/5xx awareness, configurable
  max-attempts) and per-service-root token-bucket rate limiting.
- Controlled by `restgdf.ResilienceConfig` (a peer sub-config on
  `Config.resilience`). Disabled by default; opt in via
  `RESTGDF_RESILIENCE_ENABLED=1` or `ResilienceConfig(enabled=True)`.
  When disabled, `ResilientSession` is a zero-overhead pass-through.
- `LimiterRegistry` (backed by `aiolimiter.AsyncLimiter`) and
  `CooldownRegistry` provide per-service-root rate limiting and
  separate 429 back-off. The `_service_root()` helper truncates the
  URL at `FeatureServer` / `MapServer` / `ImageServer` / `SceneServer`
  to derive the rate-limit key. Cooldown is separate from the token
  bucket — 429 back-off does NOT drain tokens.

**Telemetry extra** (`pip install restgdf[telemetry]`)

- `restgdf.telemetry.RestgdfInstrumentor` — dynamic subclass of
  `AioHttpClientInstrumentor` that adds CLIENT spans for every aiohttp
  request.
- `feature_layer_stream_span` — async context manager producing a
  single INTERNAL `feature_layer.stream` parent span (R-21). Now wired
  into `iter_pages` via `_iter_pages_raw` so every `stream_*` call
  emits exactly one parent span. Uses `contextlib.aclosing` to ensure
  span cleanup on early break.
- `span_context_fields()` — convenience for non-restgdf loggers
  wanting the current `trace_id` / `span_id`.
- `_SpanContextFilter` auto-attached to the `restgdf` root logger;
  stamps `trace_id` / `span_id` on every log record when a span is
  active.
- Telemetry is **disabled by default** (`TelemetryConfig.enabled =
  False`). `import restgdf.telemetry` always succeeds; runtime
  functions raise `OptionalDependencyError` when OTel is absent and
  telemetry is enabled.

**Logging surface** (`restgdf._logging`)

- `get_logger(suffix: str = "")` returns a named `restgdf.<suffix>`
  logger with a `NullHandler` attached. `suffix` must be `""` or one
  of `LOGGER_SUFFIXES` (`transport`, `retry`, `limiter`,
  `concurrency`, `auth`, `pagination`, `normalization`,
  `schema_drift`); unknown suffixes raise `ValueError`.
- `build_log_extra(*, service_root=None, layer_id=None,
  operation=None, page_index=None, page_size=None,
  retry_attempt=None, retry_delay_s=None, limiter_wait_s=None,
  timeout_category=None, result_count=None, exception_type=None)`
  returns a normalized `extra=` envelope. Unknown keys raise
  `TypeError`. `service_root` is URL-scrubbed internally so
  `?token=…` values never appear in logs.
- `get_drift_logger` / the `restgdf.schema_drift` logger name remain
  unchanged; `get_drift_logger()` is a thin alias for
  `get_logger("schema_drift")`.

### Deprecations

- `restgdf._types` re-exports (`LayerMetadata`, `ServiceInfo`, etc.)
  — import directly from `restgdf` or `restgdf._models.*`. Alias shim
  emits `DeprecationWarning`; removal no earlier than 3.x final.
- `restgdf.Settings` / `restgdf.get_settings()` — use `restgdf.Config`
  / `restgdf.get_config()` / `restgdf.reset_config_cache()`.
  `get_settings()` emits `DeprecationWarning` on first call and
  delegates to `get_config()`. `reset_settings_cache()` clears both
  caches bidirectionally.
- `TokenSessionConfig.refresh_threshold_seconds` — use
  `refresh_leeway_seconds` + `clock_skew_seconds`.
- `restgdf.get_token` (synchronous helper) — migrate to
  `ArcGISTokenSession` for async token lifecycle. `get_token` now
  accepts `pydantic.SecretStr` passwords.
- `FeatureLayer.row_dict_generator` — use `FeatureLayer.stream_rows`.
  Behavior is equivalent; `stream_rows` adds the `on_truncation` /
  `order` / `max_concurrent_pages` knobs and emits the R-61 parent
  span when telemetry is enabled.

All deprecations are shim-backed — existing code keeps working and
emits `DeprecationWarning`. Removal of any deprecated surface will not
happen before the 3.0 final release.

### Configuration

`restgdf.Config` composes eight frozen pydantic sub-configs:

- `TransportConfig` — user-agent, default headers, verify-SSL.
- `TimeoutConfig` — `total_s` (default `30.0`); replaces the flat
  `Settings.timeout_seconds`.
- `RetryConfig` — stamina knobs surfaced via the resilience extra.
- `LimiterConfig` — aiolimiter token-bucket knobs.
- `ConcurrencyConfig` — `max_concurrent_requests` (default **8**,
  matches aiohttp `TCPConnector` default). Enforced at the three
  internal `asyncio.gather` sites (orchestrator call paths), not at
  leaf helpers.
- `AuthConfig` — token URL, transport (default `"header"`),
  `refresh_leeway_seconds` (default **120**), `clock_skew_seconds`
  (default `30`), `referer`, credentials.
- `TelemetryConfig` — `enabled` (default `False`), log level, span
  attributes.
- `ResilienceConfig` — opt-in wrapper for the stamina-based retry
  policy and per-service-root token-bucket rate limiter. Disabled by
  default (`enabled=False`); toggle via `RESTGDF_RESILIENCE_ENABLED=1`
  or an explicit `ResilienceConfig(enabled=True, ...)`.

Use `restgdf.get_config()` to resolve the process-wide cached instance
and `restgdf.reset_config_cache()` to clear it (tests, long-running
processes).

#### Environment-variable aliases

Old flat `RESTGDF_*` variables are still honoured with
`DeprecationWarning` on read. When both old and new are set, the new
name wins and the warning notes the override.

| Deprecated (still honoured)        | Replacement                                      |
| ---------------------------------- | ------------------------------------------------ |
| `RESTGDF_TIMEOUT_SECONDS`          | `RESTGDF_TIMEOUT_TOTAL_S`                        |
| `RESTGDF_TOKEN_URL`                | `RESTGDF_AUTH_TOKEN_URL`                         |
| `RESTGDF_REFRESH_THRESHOLD`        | `RESTGDF_AUTH_REFRESH_THRESHOLD_S`               |
| `RESTGDF_USER_AGENT`               | `RESTGDF_TRANSPORT_USER_AGENT`                   |
| `RESTGDF_LOG_LEVEL`                | `RESTGDF_TELEMETRY_LOG_LEVEL`                    |
| `RESTGDF_MAX_CONCURRENT_REQUESTS`  | `RESTGDF_CONCURRENCY_MAX_CONCURRENT_REQUESTS`    |

`RESTGDF_CHUNK_SIZE` and `RESTGDF_DEFAULT_HEADERS_JSON` remain on
`Settings` only for now; they do not yet have a `Config` home.

Resilience / telemetry toggles:

- `RESTGDF_RESILIENCE_ENABLED=1` turns on retry + rate-limiting.
- `RESTGDF_TELEMETRY_ENABLED=1` turns on OpenTelemetry spans.

### Observability

- **Named loggers** — one per responsibility:
  `restgdf.transport` / `retry` / `limiter` / `concurrency` / `auth` /
  `pagination` / `normalization` / `schema_drift`. All attached with a
  `NullHandler`; opt in by adding a handler.
- **Auth log events** — `update_token` emits `auth.refresh.start`,
  `auth.refresh.success`, and `auth.refresh.failure` at DEBUG level via
  `restgdf.auth`.
- **Streaming spans** — `iter_pages` emits exactly one INTERNAL
  `feature_layer.stream` parent span per call when the telemetry extra
  is installed and `TelemetryConfig.enabled=True`. The span is
  constructed inside `restgdf.utils.getgdf._iter_pages_raw`. No
  per-page child spans are emitted.
- **Tracing recipe** — `docs/recipes/tracing.md` documents structured
  observability, error-attribute inspection, and the OpenTelemetry
  integration.

### Transport and auth hardening

- **Bounded internal concurrency.** Every top-level orchestration call
  (`service_metadata`, `fetch_all_data`, `safe_crawl`) caps in-flight
  HTTP fan-out through a single `asyncio.BoundedSemaphore` sized to
  `ConcurrencyConfig.max_concurrent_requests`. Saturation semantics =
  wait (no new exception). No public signature changed.
- **Single-flight token refresh.** `ArcGISTokenSession.update_token`
  is guarded by a lazily-initialized per-instance `asyncio.Lock` with
  double-checked `token_needs_update()`. Happy-path behavior (no
  contention, no expiry) is unchanged; under N concurrent requesters
  exactly one `/generateToken` POST is issued.
- **Reactive 498/499.** `_call_with_auth_retry` intercepts HTTP 498
  (token expired) with a single-flight refresh + one automatic retry.
  HTTP 499 (token not attached) raises `AuthNotAttachedError`
  immediately — no retry.
- **Bounded token retry.** `update_token` retries transient network
  errors up to 3 times with exponential backoff (0.5 s → 1.0 s).
  Deterministic errors (invalid credentials, content-type mismatches)
  propagate immediately. After exhaustion,
  `TokenRefreshFailedError` is raised with the last exception chained
  as `__cause__`.
- **Feature-count timeout retry.** `_feature_count_with_timeout` in
  `restgdf.utils.getinfo` wraps `get_feature_count` with exponential-
  backoff retry on **timeout failures only**
  (`asyncio.TimeoutError`, `TimeoutError`,
  `aiohttp.ServerTimeoutError`). Connection-level failures
  (`aiohttp.ClientConnectionError`) and deterministic failures
  (`RestgdfResponseError`, validation errors, 4xx) fail fast.
  Exhausted timeouts raise `RestgdfTimeoutError` with the original
  exception chained as `__cause__`. Inline-only; no soft-dep on the
  resilience extra.
- **`verify_ssl` plumbed through.** `ArcGISTokenSession.update_token`
  now forwards `ssl=self.verify_ssl` to aiohttp, matching the existing
  behavior of other library-maintained request sites.
- **Safe-crawl concurrency bound.** `Directory.safe_crawl` routes the
  per-layer `feature_count` probe through a `BoundedSemaphore` sized
  from `ConcurrencyConfig.max_concurrent_requests`.
- **Request-verb seam.** `restgdf.utils._http._choose_verb(url,
  body=None)` returns `"POST"` for `/query` / `/queryRelatedRecords`,
  `"GET"` for bare service/layer metadata URLs, and `"POST"` for
  unknown URLs. Internal seam only; call sites are unchanged in 3.0.
- **Referer binding.** When `TokenSessionConfig.referer` /
  `AuthConfig.referer` is set, `token_request_payload` includes
  `"referer": <url>` and switches the ArcGIS `client` field from
  `"requestip"` to `"referer"`.
- **UTC wall-clock expiry.** `ArcGISTokenSession.expires_at` returns
  a tz-aware UTC `datetime.datetime` (or `None`). `_utc_now()` shim
  is monkeypatchable for deterministic time tests.

### Upgrading checklist

1. **Pin the geo extra** if you materialize GeoDataFrames or call any
   of the pandas/geopandas helpers: change `restgdf` to
   `"restgdf[geo]"` in `requirements.txt` / `pyproject.toml` /
   lockfiles / deployment manifests.
2. **Widen `except` clauses** on the small number of legacy shapes:
   `except RuntimeError:` around `get_gdf` / feature-count paths
   → `except PaginationError:` (or the broader
   `ArcGISServiceError` / `RestgdfError`). Replace
   `FIELDDOESNOTEXIST` sentinel checks with
   `except FieldDoesNotExistError:`.
3. **Swap `get_settings()` for `get_config()`** if you touched the
   flat `Settings` model directly; same for
   `reset_settings_cache()` → `reset_config_cache()`. Environment
   variables can stay on their old names during the transition.
4. **Migrate `row_dict_generator` to `stream_rows`.** Pick an
   `on_truncation` policy explicitly (default is now
   `"raise"` — previously pagination silently continued).
5. **Audit auth config.** If you relied on the implicit body/query
   token transport, set `transport="body"`. Bump monitoring windows
   for the 60 → 120 second proactive-refresh shift if you alert on
   `auth.refresh.start` cadence.
6. **Split `refresh_threshold_seconds`** into
   `refresh_leeway_seconds` + `clock_skew_seconds` in
   `TokenSessionConfig` to silence the deprecation warning.
7. **Attach a handler to the named loggers you care about**
   (`restgdf.auth`, `restgdf.pagination`, `restgdf.schema_drift`,
   `restgdf.retry`, `restgdf.limiter`, `restgdf.transport`,
   `restgdf.concurrency`, `restgdf.normalization`). They are
   `NullHandler`-muted by default.
8. **(Optional) Install the extras you want:**
   `pip install "restgdf[resilience]"` for retry + rate limiting,
   `pip install "restgdf[telemetry]"` for OpenTelemetry spans.

# Migrating from restgdf 1.x to 2.0

restgdf 2.0 replaces the dict / `TypedDict` public surface with
[pydantic 2.13](https://docs.pydantic.dev/) `BaseModel` classes. This means
every response and config object you consumed in 1.x is now a typed model:
attribute access instead of dict indexing, runtime validation instead of
silent `KeyError`, and structured drift logging instead of opaque failures.

This guide lists every breaking change, the migration aids shipped with 2.0,
and the new capabilities you can opt into.

## Contents

- [Why 2.0](#why-20)
- [Breaking changes](#breaking-changes)
- [Migration aids](#migration-aids)
- [New capabilities](#new-capabilities)
- [Environment variables](#environment-variables)
- [Drift logger](#drift-logger)
- [`Settings` usage](#settings-usage)
- [`SecretStr` credentials](#secretstr-credentials)
- [Troubleshooting](#troubleshooting)

## Why 2.0

Real-world ArcGIS REST responses vary between vendor versions, deployments,
and service types. In 1.x these variances surfaced as `KeyError` /
`IndexError` deep in call stacks, or silently passed through as partially
valid dicts. 2.0 fixes that:

- **Pydantic-validated envelopes** catch malformed responses at the
  boundary and raise a typed `RestgdfResponseError` that carries the raw
  payload and request context.
- **Permissive models** (`LayerMetadata`, `ServiceInfo`, `FieldSpec`, crawl
  models) accept unknown extra keys and tolerate missing optional fields;
  drift is reported through a dedicated `restgdf.schema_drift` logger
  instead of crashing.
- **Strict models** (`CountResponse`, `ObjectIdsResponse`, `TokenResponse`,
  `ErrorResponse`) keep their fail-fast contract on operation-critical
  payloads.
- **Typed credentials** — passwords are `pydantic.SecretStr`, redacted
  from `repr()` / logs.

## Breaking changes

Every change below is a public-API shape change from 1.x.

| What changed | 1.x (dict) | 2.0 (model) |
|---|---|---|
| `FeatureLayer.metadata` | `dict` | `LayerMetadata` |
| `Directory.metadata` | `dict` | `LayerMetadata` |
| `Directory.services` | `list[dict]` | `list[CrawlServiceEntry]` |
| `Directory.services_with_feature_count` | `list[dict]` | `list[CrawlServiceEntry]` |
| `Directory.crawl(...)` return value | `list[dict]` | `list[CrawlServiceEntry]` |
| `Directory.report` | *(did not exist)* | `Optional[CrawlReport]` |
| `get_metadata(...)` | returns `dict` | returns `LayerMetadata` |
| `get_feature_count(...)` | returns `int` (unvalidated) | returns `int` (validated via `CountResponse`) |
| `get_object_ids(...)` | returns `tuple[str, list[int]]` (unvalidated) | returns `tuple[str, list[int]]` (validated via `ObjectIdsResponse`) |
| `safe_crawl(...)` | returns `dict` | returns `CrawlReport` |
| `fetch_all_data(...)` | returns raw `dict` (short-circuits on error) | unchanged signature, but internally validates; see `safe_crawl` for the typed report |
| `AGOLUserPass.password` | plain `str` | `pydantic.SecretStr` (call `.get_secret_value()` at the HTTP boundary) |
| `ArcGISTokenSession` config | ad-hoc dataclass | backed by `TokenSessionConfig` (pydantic) |
| `restgdf._types.*` | `TypedDict` aliases | re-exported pydantic models, emit `DeprecationWarning` on import |

### Code rewrites

Dict indexing → attribute access. The examples below are representative,
not exhaustive.

**`FeatureLayer.metadata`**
```python
# 1.x
layer_name = fl.metadata["name"]
fields = fl.metadata["fields"]
max_record_count = fl.metadata["maxRecordCount"]

# 2.0
layer_name = fl.metadata.name
fields = fl.metadata.fields                 # list[FieldSpec] | None
max_record_count = fl.metadata.max_record_count
```

**`Directory.services`**
```python
# 1.x
for svc in directory.services:
    print(svc["name"], svc["url"])

# 2.0
for svc in directory.services:              # list[CrawlServiceEntry]
    print(svc.name, svc.url)
    if svc.metadata is not None:            # LayerMetadata | None
        print(svc.metadata.max_record_count)
```

**`AGOLUserPass`**
```python
# 1.x
creds = AGOLUserPass(username="alice", password="hunter2")
token_form["password"] = creds.password

# 2.0
creds = AGOLUserPass(username="alice", password="hunter2")
token_form["password"] = creds.password.get_secret_value()
```

**`get_metadata`**
```python
# 1.x
md = await get_metadata(url, session)
service_type = md.get("type")

# 2.0
md = await get_metadata(url, session)       # LayerMetadata
service_type = md.type                      # str | None
```

### ArcGIS camelCase round-trip

Models accept either camelCase (native ArcGIS) or snake_case input via
`pydantic.AliasChoices`. To emit camelCase for an ArcGIS round-trip, use
`model.model_dump(by_alias=True)`. To get Python-native snake_case keys,
use `model.model_dump()` or the `restgdf.compat.as_dict` helper.

## Migration aids

### `restgdf.compat.as_dict(obj)`

Wrap any returned model to get a plain Python dict. Non-model values
(plain dicts, `None`, primitives) pass through unchanged, so you can
sprinkle it through transitional code without type checks:

```python
from restgdf.compat import as_dict

for entry in directory.services:
    row = as_dict(entry)                    # dict whether model or legacy
    save(row["name"], row.get("url"))
```

`as_dict` uses `model_dump(mode="python", by_alias=False)` — snake_case
keys, nested models recursively converted.

### `restgdf.compat.as_json_dict(obj)`

Like `as_dict`, but `mode="json"` so every value is JSON-serializable
(`SecretStr` → `"**********"` placeholder, `datetime` → ISO string).
Handy for structured logging:

```python
from restgdf.compat import as_json_dict

logger.info("crawl_result", extra={"payload": as_json_dict(report)})
```

### Deprecated `restgdf._types` aliases

`from restgdf._types import LayerMetadata` still works; it now returns
the pydantic class and emits a `DeprecationWarning`:

```python
import warnings

warnings.filterwarnings("default", category=DeprecationWarning)
from restgdf._types import LayerMetadata   # DeprecationWarning
```

Switch the import to `from restgdf import LayerMetadata`. The shim will
be removed in 3.x.

## New capabilities

### Typed response errors

Strict-tier envelopes raise `RestgdfResponseError` on validation failure,
carrying the raw payload and context:

```python
from restgdf import RestgdfResponseError, get_feature_count

try:
    count = await get_feature_count(url, session)
except RestgdfResponseError as exc:
    logger.error(
        "ArcGIS returned malformed count envelope",
        extra={
            "model": exc.model_name,       # "CountResponse"
            "context": exc.context,        # the request URL
            "raw": exc.raw,                # the decoded body
        },
    )
    raise
```

Permissive payloads still log ordinary vendor drift, but they no longer treat a
top-level ArcGIS JSON error envelope (`{"error": {...}}`) as harmless metadata
variance. If a metadata/query/crawl helper decodes JSON successfully and the
payload is an ArcGIS error envelope, restgdf now raises
`RestgdfResponseError` immediately with the original `raw` body attached.

### Schema-drift observability

Permissive models never raise on *ordinary vendor variance* (unknown extras,
missing optional fields, bad optional field types); instead they log one
record per `(model_name, path, kind, value_type)` tuple through
`restgdf.schema_drift`. The logger is installed with a `NullHandler` by
default — opt in by attaching a handler (see below). Top-level ArcGIS error
envelopes remain fail-fast and are surfaced as `RestgdfResponseError` rather
than schema drift.

### Pydantic round-trip

You can validate, inspect, and re-emit any response payload:

```python
from restgdf import LayerMetadata

md = LayerMetadata.model_validate(raw_dict)
native = md.model_dump(by_alias=True)   # camelCase, ArcGIS-compatible
python = md.model_dump()                # snake_case, Python-native
```

### Centralized `Settings` / `get_settings()`

See the [`Settings` usage](#settings-usage) section below.

### `SecretStr` on credential passwords

See the [`SecretStr` credentials](#secretstr-credentials) section below.

## Environment variables

All settings are overridable via `RESTGDF_*` env vars. Unset vars use
the documented default.

| Variable | Field | Type | Default |
|---|---|---|---|
| `RESTGDF_CHUNK_SIZE` | `chunk_size` | int (>0) | `100` |
| `RESTGDF_TIMEOUT_SECONDS` | `timeout_seconds` | float (>0) | `30.0` |
| `RESTGDF_USER_AGENT` | `user_agent` | str (non-empty) | `"restgdf/<version>"` |
| `RESTGDF_LOG_LEVEL` | `log_level` | one of `CRITICAL`/`ERROR`/`WARNING`/`INFO`/`DEBUG`/`NOTSET` | `"WARNING"` |
| `RESTGDF_TOKEN_URL` | `token_url` | `http(s)://` URL | `https://www.arcgis.com/sharing/rest/generateToken` |
| `RESTGDF_REFRESH_THRESHOLD` | `refresh_threshold_seconds` | int (≥0) | `60` |
| `RESTGDF_DEFAULT_HEADERS_JSON` | `default_headers_json` | JSON dict string | `None` |

Malformed values raise `RestgdfResponseError` at first access.

## Drift logger

`restgdf.schema_drift` is the single logger name. It is silent by
default — install a handler to see what ArcGIS deployments are sending
you:

```python
import logging

drift_logger = logging.getLogger("restgdf.schema_drift")
drift_logger.setLevel(logging.DEBUG)
drift_logger.addHandler(logging.StreamHandler())

# Now any permissive model drift is visible:
# WARNING restgdf.schema_drift: LayerMetadata.max_record_count missing at <url>
# DEBUG   restgdf.schema_drift: LayerMetadata unknown extra 'foo' at <url>
```

Log levels:

- **WARNING** — a field `restgdf` actually consumes is missing or has the
  wrong shape. Library behavior is preserved (defaults to `None`), but
  operators likely want to see this.
- **DEBUG** — an unknown-extra key is present. Purely informational.

Drift events are deduped per process via `(model_name, path, kind,
value_type)` so repeated calls against the same drifty server don't
spam the log.

## `Settings` usage

`Settings` is a frozen pydantic `BaseModel`. `get_settings()` returns a
process-cached instance; tests can reset the cache to pick up environment
changes:

```python
import os
from restgdf import Settings, get_settings
from restgdf._models._settings import reset_settings_cache

# Default: read from os.environ.
settings = get_settings()
print(settings.chunk_size, settings.user_agent)

# Programmatic override.
settings = Settings(chunk_size=250, user_agent="my-app/1.0")

# In tests, mutate env then reset the cache.
os.environ["RESTGDF_CHUNK_SIZE"] = "500"
reset_settings_cache()
assert get_settings().chunk_size == 500

# Bypass the real environment entirely:
settings = Settings.from_env({"RESTGDF_TOKEN_URL": "http://internal/arcgis"})
```

## `SecretStr` credentials

`AGOLUserPass.password` is a `pydantic.SecretStr`: its literal value is
never in `repr()` or `str()`, so it is safe for log records, tracebacks,
and error reports.

```python
from restgdf import AGOLUserPass

creds = AGOLUserPass(username="alice", password="hunter2")
print(creds)
# username='alice' password=SecretStr('**********') ...

# Unwrap only at the HTTP-POST boundary.
password_str = creds.password.get_secret_value()
```

Do not store or log the unwrapped value.

## Troubleshooting

### `AttributeError: 'LayerMetadata' object has no attribute 'get'`

You're calling `.get(...)` on what used to be a dict. Switch to attribute
access:

```python
# old
name = md.get("name", "unknown")

# new
name = md.name or "unknown"
```

Or wrap it: `as_dict(md).get("name", "unknown")`.

### `TypeError: 'LayerMetadata' object is not subscriptable`

Indexing (`md["name"]`) is gone. Use `md.name`, or `as_dict(md)["name"]`
during a transitional window.

### `RestgdfResponseError: Settings validation failed`

A `RESTGDF_*` env var is malformed (for example, `RESTGDF_CHUNK_SIZE=0`
fails `gt=0`). Check `exc.raw` for the offending values and `exc.context`
for the origin (`"Settings.from_env"`).

### `RestgdfResponseError` from `get_feature_count` / `get_object_ids` / `update_token`

The ArcGIS server returned a payload that did not match the strict
envelope (often an HTML error page or an `{"error": {...}}` body).
`exc.model_name` identifies the expected envelope, `exc.context` holds
the request URL, and `exc.raw` holds the decoded body for triage.

### Silencing the deprecation warnings

During migration you may want to suppress the `restgdf._types.*`
`DeprecationWarning` without papering over others:

```python
import warnings

warnings.filterwarnings(
    "ignore",
    message=r"restgdf\._types\..* is deprecated",
    category=DeprecationWarning,
)
```

Remove the filter once all imports are updated.

### `SecretStr` string coercion

`str(creds.password)` returns `"**********"`, not the password. If some
library expects a plain `str`, unwrap explicitly with
`creds.password.get_secret_value()`.
