# CLAUDE.md

## What this is

`restgdf` is a **lightweight async Esri/ArcGIS REST client** for Python ≥ 3.11, published to
PyPI as a Production/Stable library (currently v3.0.0; a 3.1.0 release carrying the Python
floor bump and other `## [Unreleased]` CHANGELOG entries is pending). The light core depends only on
`aiohttp` + `pydantic` v2; GeoPandas/pandas, retry/rate-limiting, and OpenTelemetry are
**optional extras** (`geo`, `resilience`, `telemetry`). The two public entry points are
`FeatureLayer` (one ArcGIS feature layer) and `Directory` (service discovery / crawl).
Async-first: nearly every public method is a coroutine or async generator.

Naming trap: the package is `restgdf` and there is a real nested submodule `restgdf.utils.utils`
(parent and child share a name). Underscore-prefixed modules (`_config`, `_models`, `_client`,
`_compat`, `_logging`, `_types`) are **internal** — the supported surface is the flat `restgdf`
namespace plus `restgdf.{adapters,compat,utils,errors}`.

## Authoritative docs (point to these; keep them in sync — do not duplicate here)

- **`ARCHITECTURE.md`** — module layers, exception taxonomy, logger hierarchy, config
  precedence, session ownership, streaming shapes, extras matrix. The conceptual reference.
- **`CONTRIBUTING.md`** — gate suite, PR checklist, commit conventions, the red-first rule.
- **`MIGRATION.md` / `CHANGELOG.md`** — every user-visible change; behavior-change PRs add a
  bullet under `## [Unreleased]`.
- **`README.md`** — user-facing usage; **`SECURITY.md`** — vuln reporting + supply-chain.

> Companion docs predate the 3.0 release in places and carry **known drift** (e.g.
> CONTRIBUTING's `integration/3.0-rewrite` branch target and ARCHITECTURE.md's
> `ErrorPayload`/`.env`/logger-name claims). **When code and companion prose disagree, the
> code is the source of truth.** The `audit-recommendations/` directory catalogs the specific
> drift; the remediation program is closing it item by item.

## Commands

All commands assume the repo root. Prefer the repo venv by absolute path (Windows / pwsh):
`.\.venv\Scripts\python.exe` (it is Python 3.11 with the full `.[dev,resilience,telemetry,geo]`
install). `CONTRIBUTING.md` documents the activated-venv `python -m …` form — same modules.

```
.\.venv\Scripts\python.exe -m pytest -q -m "not network"          # offline test suite (default gate)
.\.venv\Scripts\python.exe -m pytest tests/test_token.py -q        # a single test module
.\.venv\Scripts\python.exe -m pytest -q -k "refresh_lock"          # a single test by name
.\.venv\Scripts\python.exe -m pytest tests/test_compat.py -q       # 2.x legacy patch-seam compat tests
.\.venv\Scripts\python.exe -m coverage run -m pytest -q -m "not network"
.\.venv\Scripts\python.exe -m coverage report --fail-under=97      # coverage floor (≥ 97%)
.\.venv\Scripts\python.exe -m pre_commit run --all-files           # ruff/mypy/black/bandit/gitleaks/typos/…
.\.venv\Scripts\python.exe -m sphinx -n -W --keep-going -b html docs docs/_build/html  # docs (warnings = errors)
.\.venv\Scripts\python.exe -m build && .\.venv\Scripts\python.exe -m twine check --strict dist/*
```

- **Live-network and stress tests are opt-in:** `-m network --run-network` /
  `-m stress --run-stress`. Plain `-m "not network"` skips network; stress is skipped unless
  `--run-stress` is passed. Markers are strict (`--strict-markers`): `network`, `stress`,
  `characterization`, `compat` are the only declared ones.
- **Never trip a `restgdf.*` DeprecationWarning in library code or tests** — pytest escalates
  `DeprecationWarning`/`PendingDeprecationWarning` *from the `restgdf` namespace* to errors
  (`pyproject.toml` `filterwarnings`). Touching a deprecated alias (legacy env var, `getgdf()`,
  `restgdf._types.*`) from inside the package fails the suite.

## Quality gate (definition of done — from `CONTRIBUTING.md` §Gate suite)

`pytest -m "not network"` green · `pre-commit run --all-files` green · coverage ≥ 97% ·
`sphinx -n -W` builds · `build` + `twine check --strict` pass · `tests/test_compat.py` green.
Run pre-commit before declaring done; never `--no-verify`. Each commit must pass the full gate
on its own (so `git bisect` stays useful).

## Architecture (flow + invariants — see `ARCHITECTURE.md` for the layer diagram)

- **Layered, downward-only deps:** config/logging → errors/protocols → transport/auth →
  models → adapters → directory → featurelayer → public surface. Nothing in a lower layer
  imports a higher one.
- **Public surface is lazy (PEP 562):** `restgdf/__init__.py` resolves a 54-name `__all__`
  through `_LAZY_EXPORTS` via module `__getattr__`. Three internal duplications (`__all__`,
  `_LAZY_EXPORTS`, the `TYPE_CHECKING` import block) must stay in sync — they can drift
  undetected (all three surfaces list `FieldDoesNotExistError` as of #193/W5-7; watch for the
  next name that drifts).
- **`FeatureLayer.from_url()` issues exactly two network calls** (metadata `?f=json` GET, count
  POST), then everything else is lazy. `.where(clause)` reuses the parent's cached metadata and
  only re-issues the scoped count.
- **Two-tier response validation:** `StrictModel` (`extra="ignore"`, raises on drift —
  `CountResponse`/`ObjectIdsResponse`/`TokenResponse`) vs `PermissiveModel` (`extra="allow"`,
  logs drift via the `restgdf.schema_drift` logger — `LayerMetadata`/`FeaturesResponse`/crawl).
- **Exception taxonomy** rooted at `RestgdfError` with deliberate stdlib co-inheritance
  (`ValueError`/`TimeoutError`/`IndexError`/`PermissionError`/`ModuleNotFoundError`) for 2.x
  back-compat. The MRO matches `ARCHITECTURE.md`.
- **Config:** 8 frozen pydantic sub-configs aggregated by `Config`, resolved **only** from
  `RESTGDF_<CATEGORY>_<FIELD>` env vars via `get_config()` (LRU size-1; reset with
  `reset_config_cache()`). `Settings`/`get_settings()` are deprecation shims over it.
- **Not implemented — do not assume:** no `.env`-file loading (env vars only, despite
  ARCHITECTURE.md); the `QueryOptions` typed builder exists but is **not wired** into call
  sites (the dict-merge path runs in production); `FeatureLayer`/`Directory` have **no**
  `close()`/`closed` and require a caller-owned `session` (only the module-level `get_gdf`
  helper owns a session).

## Non-negotiables

- **Red-first for behavior changes:** land the failing test in its own commit *before* the fix
  (`CONTRIBUTING.md`). Additive features may ship tests alongside code.
- **CHANGELOG bullet under `## [Unreleased]`** for any runtime-visible change; **Conventional
  Commits** (`feat:`/`fix:`/`refactor:`/`test:`/`docs:`/`ci:`/`build:`/`chore:`), ≤72-char
  imperative subject.
- **Keep the light core thin:** optional features go behind an extra and are gated lazily
  (import inside the function, raise `OptionalDependencyError` naming the extra). `import restgdf`
  and `import restgdf.adapters` must stay base-install-safe (`tests/test_base_install.py`,
  `test_minimal_install.py`).
- **Never log/echo secrets.** Credentials are `pydantic.SecretStr`; unwrap with
  `get_secret_value()` only at the HTTP-POST boundary.
- **Preserve back-compat seams.** Deprecated method names, the `restgdf._types` shim, and
  module-level patch targets are kept reachable and emit `DeprecationWarning` — they are
  guarded by `tests/test_compat.py`. Do not delete them.
- **mypy is strict only for `restgdf._client.*`, `restgdf._models.*`, `restgdf.compat`** — new
  code in those modules needs full annotations; the rest runs at default mypy.

## Pitfalls (machine-verified 2026-06-13)

- **Streaming memory:** `iter_pages`/`stream_*` default `max_concurrent_pages=None`, which
  creates *all* page-fetch tasks up front and buffers every page — concurrency and memory are
  unbounded. Pass `max_concurrent_pages=N` to actually bound them; `order="request"` alone does
  not (`restgdf/utils/getgdf.py`).
- **Truncation handling differs by output family** (`restgdf/utils/getgdf.py`) — three
  behaviors, easy to conflate:
  - *`iter_pages` engine* — `iter_pages`/`iter_features`/`stream_features`/
    `stream_feature_batches`/`stream_rows`, and `get_df` (built on `stream_rows`) — honors
    `on_truncation` (`raise`/`ignore`/`split`); default `raise` throws
    `RestgdfResponseError(context='exceededTransferLimit')`. `get_df` always raises (it does not
    expose the knob).
  - *GeoDataFrame path* — `get_gdf` and `stream_gdf_chunks` (via `chunk_generator`→`get_sub_gdf`)
    perform **no** `exceededTransferLimit` check and can **silently return truncated data**.
  - *Legacy feature path* — `row_dict_generator` and `adapters.stream.iter_rows`/
    `iter_feature_batches` (via `_get_sub_features`) **raise `PaginationError`**, with no
    `ignore`/`split` option.
- **WHERE building does not escape quotes:** `where_var_in_list` (`restgdf/utils/utils.py`)
  wraps string values in single quotes with no escaping; it backs OID-chunk pagination,
  `sample_gdf`/`head_gdf`, and `on_truncation="split"`. Quote-bearing values make malformed SQL.
- **Per-instance caches are not concurrency-safe:** `FeatureLayer.uniquevalues/valuecounts/`
  `nestedcount/gdf` are plain dicts with no lock; concurrent awaiters double-fetch, and
  multi-field results are returned by reference (mutating the result mutates the cache).
- **Token transport (fixed in 3.1, AUTH-01):** a token in the `data` dict on a *plain*
  `aiohttp` session used to be GET-serializable into the URL when the encoded request was
  < 8192 bytes (the credential-leak guard previously only triggered for body/query transport
  on an `ArcGISTokenSession`). `restgdf/utils/_http.py` now forces `POST` whenever the
  outgoing body carries a token, regardless of session type or encoded length. Prefer header
  transport regardless — it never touches this length-based routing at all.
- **CI surprises:** the PR-gating `pytest.yml` does **not** run coverage (the 97% floor is only
  checked post-merge in `coverage.yml` — this gap closes once W1-3 lands). `ci-offline` (a
  `pytest.yml` job) IS now a required GitHub branch-protection status check on `main`, so a PR
  cannot merge until it is green; `pytest.yml` itself still only triggers on `pull_request`
  (no separate workflow re-runs it on a direct push). Run the local gate before merging.
