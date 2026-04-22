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
│ 7. Typed public surface (restgdf/__init__.py)                │
│    FeatureLayer, Directory, models, exceptions, helpers       │
├──────────────────────────────────────────────────────────────┤
│ 6. Feature layer API (restgdf/featurelayer/)                 │
│    FeatureLayer, streaming generators, pagination            │
├──────────────────────────────────────────────────────────────┤
│ 5. Directory / service discovery (restgdf/directory.py)      │
│    Directory, service enumeration, crawl helpers             │
├──────────────────────────────────────────────────────────────┤
│ 4. Typed response models (restgdf/models/)                   │
│    Pydantic v2 models for layer metadata, query responses    │
├──────────────────────────────────────────────────────────────┤
│ 3. Transport & auth (restgdf/transport/, restgdf/auth/)      │
│    aiohttp session wiring, token sessions, retry policies    │
├──────────────────────────────────────────────────────────────┤
│ 2. Errors & protocols (restgdf/errors.py)                    │
│    RestgdfError hierarchy, structured error detail types     │
├──────────────────────────────────────────────────────────────┤
│ 1. Config & logging (restgdf/config.py, restgdf/_logging.py) │
│    Settings, env loading, logger names                       │
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
│       ├── InvalidCredentialsError      # HTTP 401
│       ├── TokenExpiredError            # HTTP 498 after refresh
│       ├── TokenRequiredError
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

Detail types in `restgdf.errors` (e.g. `ErrorPayload`,
`RateLimitError.retry_after`, `PaginationError.batch_index`) expose
structured metadata for programmatic recovery.

## Logger hierarchy

restgdf uses namespaced loggers under the `restgdf.` prefix so
applications can configure verbosity per subsystem.

```
restgdf
├── restgdf.auth              # token lifecycle, refresh attempts
├── restgdf.transport         # aiohttp requests, retries
├── restgdf.featurelayer      # prep / query / streaming
├── restgdf.streaming         # pagination, split-on-truncation decisions
├── restgdf.directory         # service enumeration
└── restgdf.telemetry         # OpenTelemetry hooks (only when `telemetry` extra installed)
```

Loggers never emit at `DEBUG` with secrets; tokens and password-bearing
request bodies are redacted at the transport layer.

## Config precedence

`restgdf.config.Settings` (Pydantic v2) resolves values in this order,
highest precedence first:

1. **Explicit constructor arguments** (`FeatureLayer.from_url(timeout=…)`).
2. **`Settings(...)` instance passed explicitly**.
3. **Process environment variables** (`RESTGDF_*`).
4. **`.env` file** in the working directory, if present.
5. **Library defaults** (see `Settings.model_fields`).

Token-session settings (`TokenSessionConfig`) follow the same order but
are stored on the session object, not globally.

## Session ownership

`aiohttp.ClientSession` ownership is explicit and documented on every
public API:

- **Caller-provided session** — passed to `FeatureLayer.from_url(...,
  session=...)` or `Directory(..., session=...)`. restgdf does **not**
  close it; the caller's `async with session:` block owns lifecycle.
- **Library-owned session** — if no session is provided, restgdf
  lazily constructs one and closes it when the owning object is
  `close()`d or used as an async context manager.

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
pip install "restgdf[resilience,telemetry]"      # production resiliency
pip install "restgdf[geo]"                        # notebooks / analytics
pip install -e ".[dev,resilience,telemetry,geo]" # full contributor install
```

Importing a module that depends on an un-installed extra raises
`OptionalDependencyError` with a message that names the missing extra.
