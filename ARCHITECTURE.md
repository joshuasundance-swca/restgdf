# restgdf architecture

This document sketches the runtime structure of restgdf 3.x for
contributors. It is **not** a user guide — see the README and
[Read the Docs](https://restgdf.readthedocs.io/) for that — but it is
the reference we point at in code review when someone asks *"which
layer does this belong in?"*

Contents

- [Module layers](#module-layers)
- [Exception taxonomy](#exception-taxonomy)
- [Logger hierarchy](#logger-hierarchy)
- [Config precedence](#config-precedence)
- [Session ownership](#session-ownership)
- [Streaming shapes](#streaming-shapes)
- [Extras matrix](#extras-matrix)

## Module layers

restgdf is organised as a layered async client. Each layer depends
downward; nothing in a lower layer imports from a higher one.

```
┌──────────────────────────────────────────────────────────────┐
│ 8. Typed public surface (restgdf/__init__.py)                │
│    FeatureLayer, Directory, models, exceptions, helpers       │
├──────────────────────────────────────────────────────────────┤
│ 7. Feature layer API (restgdf/featurelayer/)                 │
│    FeatureLayer, streaming generators, pagination            │
├──────────────────────────────────────────────────────────────┤
│ 6. Directory / service discovery (restgdf/directory/)        │
│    Directory, service enumeration, crawl helpers             │
├──────────────────────────────────────────────────────────────┤
│ 5. Output adapters (restgdf/adapters/)                       │
│    dict, stream, pandas, geopandas — tabular output shapes   │
├──────────────────────────────────────────────────────────────┤
│ 4. Typed response models (restgdf/_models/)                  │
│    Pydantic v2 models for layer metadata, query responses    │
├──────────────────────────────────────────────────────────────┤
│ 3. Transport & auth (restgdf/utils/_http.py, utils/token.py) │
│    aiohttp session wiring, token sessions, verb selection    │
│    Optional: restgdf/resilience/ (stamina retry + rate limit)│
│    Optional: restgdf/telemetry/ (OTel spans + log correlation│
├──────────────────────────────────────────────────────────────┤
│ 2. Errors & protocols (restgdf/errors.py,                    │
│    restgdf/_client/_protocols.py)                            │
│    RestgdfError hierarchy; AsyncHTTPSession Protocol (BL-17) │
├──────────────────────────────────────────────────────────────┤
│ 1. Config & logging (restgdf/_config.py, restgdf/_logging.py)│
│    Config, env loading, logger names                         │
└──────────────────────────────────────────────────────────────┘
```

## Exception taxonomy

All runtime failures raise a subclass of `restgdf.RestgdfError`. The
hierarchy lets callers catch broad categories (transport vs. service
vs. schema) without giving up precise handling when they want it.

```
RestgdfError
├── ConfigurationError(RestgdfError, ValueError)
│   └── OptionalDependencyError(ConfigurationError, ModuleNotFoundError)
├── RestgdfResponseError(RestgdfError, ValueError)
│   ├── SchemaValidationError
│   │   └── FieldDoesNotExistError
│   ├── ArcGISServiceError
│   │   └── PaginationError(ArcGISServiceError, IndexError)
│   └── AuthenticationError(RestgdfResponseError, PermissionError)
│       ├── InvalidCredentialsError      # /generateToken HTTP 4xx (400/401/403)
│       ├── TokenExpiredError            # HTTP 498 after refresh
│       ├── TokenRequiredError           # reserved — not currently raised
│       ├── TokenRefreshFailedError      # /generateToken retries exhausted
│       └── AuthNotAttachedError         # HTTP 499
├── TransportError
│   ├── RestgdfTimeoutError(TransportError, TimeoutError)
│   └── RateLimitError(TransportError)   # .retry_after
└── OutputConversionError
```

All classes are re-exported from the top-level `restgdf` package.
Several classes co-inherit from stdlib exceptions (`ValueError`,
`TimeoutError`, `IndexError`, `ModuleNotFoundError`, `PermissionError`)
so existing `except ValueError:` / `except TimeoutError:` code keeps
working — see [MIGRATION.md](MIGRATION.md) for the full story.

Exceptions in `restgdf.errors` carry structured attributes for
programmatic recovery — for example `RestgdfResponseError.raw` /
`RestgdfResponseError.model_name`, `RateLimitError.retry_after`, and
`PaginationError.batch_index`.

## Logger hierarchy

restgdf uses namespaced loggers under the `restgdf.` prefix so
applications can configure verbosity per subsystem.

```
restgdf                       # root logger (NullHandler; get_logger(""))
├── restgdf.transport         # aiohttp requests, verb selection (HTTP)
├── restgdf.retry             # stamina retry attempts (restgdf[resilience])
├── restgdf.limiter           # rate limiting (restgdf[resilience])
├── restgdf.concurrency       # page-fetch concurrency gating
├── restgdf.auth              # token lifecycle, refresh attempts
├── restgdf.pagination        # streaming + split-on-truncation decisions
├── restgdf.normalization     # attribute / row normalization
├── restgdf.schema_drift      # permissive-tier schema-drift warnings
└── restgdf.crawl             # directory-crawl containment warnings (3.3)
```

These nine suffixes are the *only* names `get_logger()` accepts (see
`LOGGER_SUFFIXES` in `restgdf/_logging.py`); any other suffix raises
`ValueError`, so there are no `restgdf.featurelayer` / `restgdf.streaming`
/ `restgdf.directory` / `restgdf.telemetry` loggers. Subsystem → logger:
HTTP transport → `restgdf.transport` (retries → `restgdf.retry`),
streaming/pagination → `restgdf.pagination`, schema drift →
`restgdf.schema_drift`, normalization → `restgdf.normalization`,
per-layer crawl failures contained inside `service_metadata` →
`restgdf.crawl` (WARNING).

Loggers never emit at `DEBUG` with secrets; tokens and password-bearing
request bodies are redacted at the transport layer.

## Config precedence

`restgdf.Config` (Pydantic v2, defined in `restgdf/_config.py`) resolves
values in this order, highest precedence first:

1. **Explicit constructor / aiohttp keyword arguments**
   (`FeatureLayer.from_url(timeout=…)`), applied per call.
2. **Process environment variables** (`RESTGDF_*`), read by
   `Config.from_env` and exposed process-globally through the size-1
   LRU-cached `restgdf.get_config()` (reset with `reset_config_cache()`).
3. **Library defaults** (see `Config.model_fields`).

restgdf does **not** read a `.env` file — only the process environment,
or a mapping you pass to `Config.from_env(env=…)`; `python-dotenv` is not
a dependency. A directly built `Config(...)` instance is **not**
injectable into the `FeatureLayer` / `Directory` request path (there is
no `config=` parameter on either), so it does not sit in the precedence
chain above; it is used in tests and to construct a session-scoped
`ArcGISTokenSession(config=…)`, which is separate from the process-global
`get_config()`.

The legacy `restgdf.Settings` name is retained as a deprecation alias
over `Config`; both resolve to the same cached instance via
`restgdf.get_config()` / `restgdf.get_settings()`.

Token-session settings (`TokenSessionConfig` in
`restgdf/_models/credentials.py`) are stored on the session object, not
globally.

## Session ownership

`aiohttp.ClientSession` ownership is explicit and caller-driven:

- **Caller-owned session (the only model for `FeatureLayer` /
  `Directory`)** — both require a `session` argument
  (`FeatureLayer.from_url(..., session=...)`, `Directory(...,
  session=...)`). restgdf never closes a caller-supplied session, and
  neither class defines `close()` / `__aenter__` / `__aexit__`; the
  caller's `async with session:` block owns lifecycle.
- **The one lazy-owning helper** — `restgdf.utils.getgdf.get_gdf(url,
  session=None, ...)` builds a temporary `ClientSession` when none is
  passed and closes it in a `finally` block. A caller-supplied session is
  used as-is and left open.

Token sessions wrap an inner `ClientSession` and propagate the same
rule: the token session only closes what it created.

## Streaming shapes

`FeatureLayer` exposes four pagination shapes. The first three share
the modern `iter_pages`-backed pipeline with
`on_truncation="raise" | "ignore" | "split"` and
`max_concurrent_pages` knobs; the fourth (`stream_gdf_chunks`) is a
legacy `chunk_generator`-backed path retained for geo workflows.

| Method                   | Element shape                    | Pipeline        | Use when…                                        |
|--------------------------|----------------------------------|-----------------|--------------------------------------------------|
| `stream_features`        | one `Feature` per iteration      | `iter_pages`    | you want the raw REST feature objects            |
| `stream_feature_batches` | one `list[Feature]` per page     | `iter_pages`    | you want to bulk-process per-page                |
| `stream_rows`            | one `dict[str, Any]` per feature | `iter_pages`    | you want attributes without the envelope         |
| `stream_gdf_chunks`      | one `GeoDataFrame` per chunk     | `chunk_generator` | you want geo chunks (requires `restgdf[geo]`)  |

The three `iter_pages`-backed methods default to `order="request"`
(yield in request order, keeping memory bounded) and can optionally
yield in `order="completion"` order when downstream code doesn't care
about ordering. `stream_gdf_chunks` preserves its legacy ordering
semantics.

`on_truncation="split"` recursively subdivides the OID range when
ArcGIS returns `exceededTransferLimit=true`, up to 32 levels deep, and
emits a `SplitTruncationEvent` for each recursion so observers can
tune `page_size`.

## Extras matrix

```
restgdf                    # light core: aiohttp + pydantic
restgdf[resilience]        # + stamina      (retry on transient errors)
restgdf[telemetry]         # + opentelemetry-api/sdk (tracing spans)
restgdf[geo]               # + geopandas/pyogrio (GeoDataFrame conversion)
restgdf[dev]               # + pytest, pre-commit, sphinx, twine, build
```

Extras are additive and composable:

```bash
pip install "restgdf[resilience,telemetry]"      # retry/rate-limit + tracing building blocks
pip install "restgdf[geo]"                        # notebooks / analytics
pip install -e ".[dev,resilience,telemetry,geo]" # full contributor install
```

Installing `[resilience]` only makes `restgdf.resilience.ResilientSession`
importable — it does not itself wire retry/rate-limiting into any request.
A caller must construct `ResilientSession(inner, ResilienceConfig(enabled=
True, ...))` and pass it as `session=` to `FeatureLayer`/`Directory`; see
the `docs/recipes/bulk_crawl.md` recipe for a full worked example.

Importing a module that depends on an un-installed extra raises
`OptionalDependencyError` with a message that names the missing extra.
