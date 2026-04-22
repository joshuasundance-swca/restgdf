# Upcoming: restgdf 2.x to 3.x optional Geo extras

## Unreleased migration notes

### phase-1a

- **Bounded internal concurrency (BL-01).** Every restgdf top-level
  orchestration call (`service_metadata`, `fetch_all_data`, `safe_crawl`)
  now caps in-flight HTTP fan-out through a single
  `asyncio.BoundedSemaphore` sized to
  `Settings.max_concurrent_requests`. The new setting defaults to **8**
  (matches aiohttp's `TCPConnector` default connection-pool size) and is
  overridable via the `RESTGDF_MAX_CONCURRENT_REQUESTS` environment
  variable. Saturation semantics = wait (no new exception is raised);
  the only observable effect is that operators no longer see unbounded
  fan-out on large directories or services with many layers. No public
  signature changed — leaf helpers (`get_metadata`, `get_feature_count`)
  remain semaphore-free; the cap is enforced at the three internal
  `asyncio.gather` sites only.
- **Single-flight token refresh (BL-03).** `ArcGISTokenSession` now
  guards `update_token_if_needed` with a lazily-initialized per-instance
  `asyncio.Lock` and double-checks `token_needs_update()` inside the
  lock. Under N concurrent request paths that would previously have
  each issued their own `/generateToken` POST, restgdf now issues
  exactly one. Happy-path behavior (no contention, no expiry) is
  unchanged. The lock field is excluded from `repr`/`compare` and
  defaults to `None` so instances constructed outside a running event
  loop (e.g. at import time) do not emit a deprecation warning.
- **Request-verb seam (BL-20).** A new private helper
  `restgdf.utils._http._choose_verb(url, body=None)` returns `"POST"`
  for `/query` and `/queryRelatedRecords`, `"GET"` for bare
  service / layer metadata URLs, and `"POST"` as the conservative
  default for unknown URLs. This slice only introduces the seam —
  existing call sites are unchanged. A later slice (BL-50) will extend
  the helper to auto-switch `GET` → `POST` when a `where` clause pushes
  a GET URL past the ArcGIS ~1800-byte URL budget.

### phase-1b

#### HTTP timeouts are now plumbed via `Settings.timeout_seconds` (BL-02)

Every library-maintained `session.get` / `session.post` call-site now
forwards an explicit `aiohttp.ClientTimeout` whose `total` is resolved
from `Settings.timeout_seconds` (float, default `30.0`). The knob is
overridable via the `RESTGDF_TIMEOUT_SECONDS` environment variable; call
`restgdf._models._settings.reset_settings_cache()` in long-lived
processes or tests that mutate the environment at runtime.

| Call-site | Behaviour before | Behaviour after |
|---|---|---|
| `restgdf.utils._query.get_feature_count` | No timeout (aiohttp default) | `timeout=default_timeout()` |
| `restgdf.utils._query.get_metadata` | No timeout | `timeout=default_timeout()` |
| `restgdf.utils._query.get_object_ids` | No timeout | `timeout=default_timeout()` |
| `restgdf.utils._stats.get_unique_values` | No timeout | `timeout=default_timeout()` |
| `restgdf.utils._stats.get_value_counts` | No timeout | `timeout=default_timeout()` |
| `restgdf.utils._stats.nested_count` | No timeout | `timeout=default_timeout()` |
| `restgdf.utils.getgdf._get_sub_features` | No timeout | `timeout=default_timeout()` |
| `restgdf.utils.getgdf.get_sub_gdf` | No timeout | `timeout=default_timeout()` |
| `restgdf.utils.token.ArcGISTokenSession.update_token` | No timeout | `timeout=default_timeout()` |
| `restgdf.utils.token.ArcGISTokenSession.get` | No timeout | `kwargs.setdefault("timeout", default_timeout())` |
| `restgdf.utils.token.ArcGISTokenSession.post` | No timeout | `kwargs.setdefault("timeout", default_timeout())` |

The BL-08 pagination-probe POST in `restgdf.utils.getgdf` is intentionally
still unmigrated in phase-1b and will move in its dedicated slice.
Callers that already pass an explicit `timeout=` kwarg continue to
override the default.

#### Token refresh threshold split into leeway + clock skew (BL-04)

`TokenSessionConfig` now exposes two explicit fields:

| Field | Type | Default | Meaning |
|---|---|---|---|
| `refresh_leeway_seconds` | `int` (≥ 0) | `60` | How far in advance of the token expiry to refresh. |
| `clock_skew_seconds` | `int` (≥ 0) | `30` | Extra padding for client/server clock drift. |

`refresh_threshold_seconds` is retained as a **deprecation alias**:

- **Reads** emit `DeprecationWarning` and return
  `refresh_leeway_seconds + clock_skew_seconds`.
- **Writes** via the constructor kwarg emit `DeprecationWarning`, then
  split the supplied total: `clock_skew_seconds = min(30, total)` and
  `refresh_leeway_seconds = total - clock_skew_seconds`. Negative
  totals are rejected by the `ge=0` field constraint.

`ArcGISTokenSession.__post_init__` now respects a caller-supplied
`config=TokenSessionConfig(...)` instead of overwriting it, and
synthesises the split fields from `self.token_refresh_threshold` when
no config is supplied. Constructing a plain
`ArcGISTokenSession(credentials=...)` no longer fires a
`DeprecationWarning`; the dataclass mirror
`self.token_refresh_threshold` is resynced from the validated config
after construction so the two never drift.

Migrate existing configuration eagerly:

```python
# before
TokenSessionConfig(token_url=..., credentials=..., refresh_threshold_seconds=90)

# after
TokenSessionConfig(
    token_url=...,
    credentials=...,
    refresh_leeway_seconds=60,
    clock_skew_seconds=30,
)
```

The alias will be removed in a future release (no earlier than 3.0
final) — coordinate with the `restgdf._compat` migration planned for
phase-1c (BL-56) which will centralise the warning helper.

#### `ArcGISTokenSession.verify_ssl` now plumbs into token refresh (BL-05)

`ArcGISTokenSession.update_token` previously issued the
`/generateToken` POST without forwarding the session's `verify_ssl`
flag, so `ArcGISTokenSession(..., verify_ssl=False)` still performed
TLS verification against ArcGIS Enterprise deployments with
self-signed or internal certificates. The POST now forwards
`ssl=self.verify_ssl` to `aiohttp`, matching the existing behaviour of
other library-maintained request sites.

### phase-1c

Phase-1c introduces the canonical exception taxonomy at
`restgdf.errors`. Every new class is additive for `except` semantics:
callers that previously caught `ValueError`, `ModuleNotFoundError`,
`TimeoutError`, `PermissionError`, `IndexError`, or `ImportError` around
restgdf APIs continue to work because the new classes multi-inherit the
appropriate builtin.

**BL-06 — public error classes.** Public taxonomy rooted at
`restgdf.errors.RestgdfError`:

```
RestgdfError
├── ConfigurationError(RestgdfError, ValueError)
│   └── OptionalDependencyError(ConfigurationError, ModuleNotFoundError)
├── RestgdfResponseError(RestgdfError, ValueError)
│   ├── SchemaValidationError
│   ├── ArcGISServiceError
│   │   └── PaginationError(ArcGISServiceError, IndexError)   # .batch_index, .page_size
│   └── AuthenticationError(RestgdfResponseError, PermissionError)
├── TransportError
│   ├── RestgdfTimeoutError(TransportError, TimeoutError)
│   └── RateLimitError(TransportError)                        # .retry_after
└── OutputConversionError
```

All classes re-export from the top-level `restgdf` package. The existing
`RestgdfResponseError` definition moved from
`restgdf._models._errors` to `restgdf.errors`; the old import path is
preserved via a pure alias shim and class identity is unchanged
(`restgdf._models._errors.RestgdfResponseError is restgdf.errors.RestgdfResponseError`).

The preserved 2.x migration notes continue below.

**BL-07 — `OptionalDependencyError` in `utils/_optional.py`.**
Optional-dependency gates now raise
`restgdf.errors.OptionalDependencyError` instead of bare
`ModuleNotFoundError`. Because `OptionalDependencyError` multi-inherits
`ModuleNotFoundError` (and therefore `ImportError`), existing
`except ModuleNotFoundError:` and `except ImportError:` call sites
continue to catch the new exception with no source changes.

**BL-56 — private `restgdf._compat` helper (internal).** New private
module `restgdf._compat` centralizes `DeprecationWarning` emission for
the 3.x migration period; it exposes `_warn_deprecated` and
`async_deprecated_wrapper`. Not part of the public API; no caller
changes.

**BL-57 — `restgdf.__getattr__` extension point.** The lazy-import hook
in `restgdf/__init__.py` now consults a `_REMOVED_EXPORTS: dict[str,
str]` mapping *after* the lazy-import path. The mapping is empty in
phase-1c; later phases register removed/renamed top-level names here
so that importing them emits a `DeprecationWarning` (via
`restgdf._compat._warn_deprecated`) and raises `AttributeError` with a
migration message. Existing lazy imports (`FeatureLayer`, `Directory`,
`utils`, `compat`, the pydantic re-exports, and the new `restgdf.errors`
re-exports) are unchanged. `dir(restgdf)` now advertises every
lazy-export key.

### phase-1b-bl08

`getgdf` / `_get_sub_features` no longer raise `RuntimeError` when an ArcGIS
service returns `exceededTransferLimit=true` on a query batch; they now raise
`restgdf.errors.PaginationError` (which multi-inherits `IndexError` per BL-06).

- Callers doing `except RuntimeError:` around `get_gdf` / iter_gdf paths must
  migrate to `except restgdf.errors.PaginationError:` or the broader
  `except restgdf.errors.ArcGISServiceError:`.
- `except Exception:` continues to catch it (no action).
- `except IndexError:` also continues to catch it due to the multi-inherit
  preserved for 2.x callers that treated cursor-exhaustion as an index error.
- The exception now carries `batch_index` and `page_size` attributes useful
  for resumable-pagination callers.

Rationale: ties into the BL-06 exception taxonomy landed in phase-1c.

## Upcoming: restgdf 2.x to 3.x optional Geo extras

restgdf 2.0 just landed, so the 1.x → 2.0 notes stay below unchanged. This
new top section documents the next planned breaking change: GeoPandas-backed
and pandas-backed workflows move behind the `restgdf[geo]` extra instead of
coming along for the ride in a default install.

A plain `pip install restgdf` will continue to cover the async REST client,
typed pydantic models, raw-row iteration, directory crawling, and token/session
helpers. Install `restgdf[geo]` when you want `geopandas`, `pandas`,
`pyogrio`, or the GeoDataFrame/tabular helpers that depend on them.

## Why 3.x is making this split

- **Keep the default install light.** Many users only need typed metadata,
  count/object-id helpers, raw feature rows, crawl utilities, or token auth.
- **Avoid heavy compiled dependencies when they are not needed.** CI jobs,
  serverless deployments, and minimal containers should not need the geo stack
  unless they actually materialize GeoDataFrames.
- **Make dependency intent explicit.** Geo workflows stay fully supported, but
  they become an opt-in install choice rather than an implicit one.

## Install changes

| Workflow | Install command |
|---|---|
| Typed metadata/models, count/object-id helpers, raw row dictionaries, directory crawl, and token/session helpers | `pip install restgdf` |
| `FeatureLayer.get_gdf()`, `sample_gdf()`, `head_gdf()`, `fieldtypes`, `get_fields_frame()`, multi-field `get_unique_values()`, `get_value_counts()`, `get_nested_count()`, and `restgdf.utils.getgdf` helpers | `pip install "restgdf[geo]"` |

If you manage dependencies in `requirements.txt`, `pyproject.toml`, lockfiles,
or deployment manifests, update geo-enabled environments to request
`restgdf[geo]` explicitly instead of assuming `geopandas`, `pandas`, or
`pyogrio` arrive transitively.

## Breaking changes

- `pip install restgdf` no longer guarantees that `geopandas`, `pandas`, or
  `pyogrio` are importable.
- GeoDataFrame and pandas-backed helpers now require `restgdf[geo]` and raise
  `ModuleNotFoundError` with an install hint when the optional stack is
  missing.
- Light-core workflows keep working without the geo stack: typed response
  models, `FeatureLayer.from_url`, `.metadata`, `.count`, `.get_oids()`,
  `row_dict_generator()`, single-field `get_unique_values()`, directory
  crawling, and token helpers remain part of the base install.

The preserved 1.x → 2.0 migration guide starts here.

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
