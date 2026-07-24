> **12 — Optional-dependency gating & light-core hygiene** · restgdf audit · **read-only** · no code was modified
> Commit `4673b08` · 2026-06-13 · Index: [README](README.md) · Machine-readable: [findings.json](findings.json)

## Assessment

The light-core promise is well-engineered and genuinely holds. Base-install import safety is complete across every module reachable from `import restgdf`, `restgdf.adapters`, `restgdf.utils`, and `restgdf.telemetry`: heavy deps (pandas/geopandas/pyogrio/stamina/aiolimiter/opentelemetry) are imported only inside function bodies or behind PEP-562 lazy `__getattr__`, the only column-0 heavy imports live in `restgdf/resilience/*` (intentionally eager-raise-gated and consumed via `try/except ImportError` in getinfo.py), and this is backed by dedicated guarded-import tests (test_base_install, test_minimal_install, test_lazy_imports, test_telemetry_base_install_importable, test_resilience_optional_dependency). The `eval_type_backport; python_version<'3.10'` dependency is correct and necessary (responses.py uses `X | None` unions under `from __future__ import annotations` with a runtime `LayerMetadata.model_rebuild()`). The residual risk is not in import safety but in the pandas/geo packaging boundary: docs advertise pandas-only capabilities as distinct from the geo stack, yet no `restgdf[pandas]` extra exists and the gate's error message + a MIGRATION.md claim both diverge from that documented split. Overall a clean axis with packaging/doc-contract polish needed, not structural defects.

## Findings at a glance

| ID | Finding | Severity | Effort |
|----|---------|----------|--------|
| `OPTDEPS-01` | `require_*` catches only `ModuleNotFoundError`, so a broken (present-but-unimportable) geo dependency escapes the documented OptionalDependencyError contract | low | S |
| `OPTDEPS-02` | MIGRATION.md documents a non-existent `extra="pandas"` on OptionalDependencyError and the wrong extra for get_df | low | S |

## Findings

### OPTDEPS-01 · `require_*` catches only `ModuleNotFoundError`, so a broken (present-but-unimportable) geo dependency escapes the documented OptionalDependencyError contract

**Severity:** low · **Effort:** S · **Location:** `restgdf/utils/_optional.py:29-35`

**Evidence**

`_import_optional_module` wraps only the narrow subclass: `try:\n    return import_module(module_name)\nexcept ModuleNotFoundError as exc:\n    ...raise _optional_dependency_error(...)`. geopandas and pyogrio depend on compiled C-extensions (GDAL, shapely, pyproj). When the package is installed but its native layer fails to load, CPython raises a plain `ImportError` (e.g. `ImportError: DLL load failed while importing ...` on Windows) — a *parent* of `ModuleNotFoundError`, not an instance of it — so the `except ModuleNotFoundError` does not catch it and the raw error propagates. ARCHITECTURE.md:188-189 states the contract: "Importing a module that depends on an un-installed extra raises `OptionalDependencyError` with a message that names the missing extra."

**Why it matters**

On the common Windows broken-GDAL scenario, callers of `get_gdf()`/`get_df()`/value-count helpers get an opaque `ImportError`/`OSError` with no `restgdf[geo]` install hint, and `except OptionalDependencyError` / `except restgdf.errors` blocks built per the documented taxonomy silently miss it. The failure is misattributed to a non-restgdf bug.

**Recommendation**

Broaden the catch in `_import_optional_module` (restgdf/utils/_optional.py:31-35) from `except ModuleNotFoundError` to `except ImportError as exc:`. This is safe and strictly more compliant: (1) `ModuleNotFoundError` is a subclass of `ImportError`, so the existing missing-package path is unchanged; (2) the existing `exc.name or module_name` line already handles a plain `ImportError` whose `.name` defaults to `None` (verified) — it falls back to the literal `module_name` like "geopandas", so the message still names the extra; (3) the `raise _optional_dependency_error(...) from exc` executes inside the except and propagates out, so there is no risk of self-swallowing; (4) no back-compat seam breaks, since `OptionalDependencyError` itself multi-inherits `ModuleNotFoundError`→`ImportError`, so every downstream `except ImportError`/`except ModuleNotFoundError`/`except OptionalDependencyError` block keeps matching. This change also aligns the geo gate with the codebase's own established pattern: the telemetry gates (restgdf/telemetry/_spans.py:91, _instrumentor.py:34) and the resilience gate (restgdf/resilience/__init__.py:19) already use `except ImportError` to satisfy the same OptionalDependencyError contract — the geo gate is the lone outlier using the narrow catch. Add a test that patches `restgdf.utils._optional.import_module` to raise a bare `ImportError("DLL load failed ...")` (with `.name=None`) and asserts `OptionalDependencyError` is raised with the `restgdf[geo]` hint. Do NOT widen to `except Exception` — keep it `ImportError` so genuinely unrelated runtime errors during import still surface.

**Fix touches:** `restgdf/utils/_optional.py`, `tests/test_base_install.py`

---

### OPTDEPS-02 · MIGRATION.md documents a non-existent `extra="pandas"` on OptionalDependencyError and the wrong extra for get_df

**Severity:** low · **Effort:** S · **Location:** `MIGRATION.md:211-215, restgdf/errors.py:68-74, restgdf/utils/_optional.py:18-26`

**Evidence**

MIGRATION.md:214-215 states get_df "raises `OptionalDependencyError` (`extra="pandas"`) if pandas is missing." But `OptionalDependencyError(ConfigurationError, ModuleNotFoundError)` in errors.py defines no `extra` attribute or constructor kwarg, and `_optional_dependency_error` builds the message with `GEO_EXTRA = "restgdf[geo]"` — so the actual raised error has no `.extra` and its text says `restgdf[geo]`, never `pandas`. The README/MIGRATION pandas-only framing is thus contradicted by the only install hint the user actually sees.

**Why it matters**

A consumer who reads MIGRATION.md and writes `except OptionalDependencyError as e: if e.extra == "pandas": ...` hits an `AttributeError`, and the documented pandas/geo split is not reflected in the runtime message. Doc-vs-implementation divergence on the public error contract.

**Recommendation**

Prefer option (b): correct MIGRATION.md:214-215 to drop the false `(extra="pandas")` parenthetical. The accurate contract is: `OptionalDependencyError` carries NO `.extra` attribute, the raised message names `restgdf[geo]` (built from `GEO_EXTRA` in _optional.py), and pandas ships only via the `geo` extra (there is no `restgdf[pandas]` extra in pyproject.toml). Aligning MIGRATION.md with the already-correct get_df docstring (featurelayer.py:484-487, which just says "Raises `OptionalDependencyError` when pandas is not installed") is the proportionate fix. REJECT option (a) as scope creep for a low-severity doc bug: it modifies a public exception class and presumes a not-yet-existing `restgdf[pandas]` extra. Adding a structured `extra`/install-hint field could be a reasonable future DX improvement, but it should be applied uniformly across the error taxonomy with its own design decision and tests — not bolted on to fix one stray parenthetical, and not by inventing a `pandas` extra that contradicts the deliberate "pandas only via geo" packaging.

**Fix touches:** `MIGRATION.md`, `restgdf/errors.py`, `restgdf/utils/_optional.py`

---

## Minor notes (not adversarially verified)

These were flagged by the axis auditor but did NOT go through per-finding verification — treat as leads, not confirmed findings.

- **resilience eager-raise is intentional and tested (seed refuted)** — The audit seed implies `import restgdf.resilience` should work without stamina. It does NOT, by design: restgdf/resilience/__init__.py:16-24 raises `OptionalDependencyError` at import if stamina/aiolimiter are missing, and test_resilience_optional_dependency.py:18-35 explicitly asserts this. Consumer-facing safety is via the `try/except ImportError` in getinfo.py:57-59, and `import restgdf` itself stays clean (test line 13-16). This asymmetry with telemetry (which IS base-import-safe) is deliberate but undocumented in ARCHITECTURE.md's extras matrix — a one-line note that resilience is import-eager while telemetry is import-lazy would help maintainers.
- **rows_to_geodataframe over-gates on pyogrio** — restgdf/adapters/geopandas.py:85-90: `rows_to_geodataframe` calls `require_geo_stack` (pandas+geopandas+pyogrio) but only constructs `geopandas.GeoDataFrame`, which needs pandas+geopandas, not pyogrio (pyogrio is geopandas' IO engine, used only by `get_sub_gdf`'s `read_file`). Harmless because the docstring and the `restgdf[geo]` extra bundle all three, and geopandas pulls pyogrio anyway — but technically the gate is stricter than the function's actual dependency.
- **eval_type_backport dependency confirmed correct (seed confirmed)** — pyproject.toml:21 `eval_type_backport; python_version < '3.10'` is necessary: restgdf/_models/responses.py uses PEP 604 `X | None` unions under `from __future__ import annotations` and forces resolution via `LayerMetadata.model_rebuild()` at import (responses.py:197). On 3.9 pydantic auto-uses eval_type_backport to evaluate the new-syntax annotation strings. Marker and placement are correct.
- **partial geo install (pandas-yes, geopandas-no) does produce a clear per-module error** — Seed sub-claim checked: `require_geo_stack` runs `require_pandas` then `require_geopandas` then `require_pyogrio` in order (restgdf/utils/_optional.py:53-57). With pandas present but geopandas absent, the error names 'geopandas' specifically (`exc.name`) plus the `restgdf[geo]` hint — clear enough. The only gap is the `ImportError`-vs-`ModuleNotFoundError` one already filed as a finding.
