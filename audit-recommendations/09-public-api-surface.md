> **09 — Public API surface, semver & compatibility seams** · restgdf audit · **read-only** · no code was modified
> Commit `4673b08` · 2026-06-13 · Index: [README](README.md) · Machine-readable: [findings.json](findings.json)

## Assessment

The public surface is unusually disciplined for an Esri client: a single flat lazy namespace via PEP 562 `__getattr__` over an explicit `_LAZY_EXPORTS` table (`restgdf/__init__.py`), a frozen `__all__`, `py.typed` shipped, and a real graceful-removal extension point (`_REMOVED_EXPORTS`) that is wired AND tested (`tests/test_pep562_removed_exports.py`), refuting the "dead code" lead. Back-compat seams are governed by documented decisions: `_types` retention to "no earlier than 3.x final" (`MIGRATION.md:345`), `compat.as_dict`'s snake_case/`by_alias=False` choice is explicitly documented (`MIGRATION.md:635-661`), and the errors taxonomy preserves multi-inheritance contracts. Residual risk is concentrated in the static-typing seam of the public namespace: the three sources of truth (`__all__`, `_LAZY_EXPORTS`, `TYPE_CHECKING`) are hand-maintained and can silently drift because no test asserts they are set-equal — which has already produced one drift (`FieldDoesNotExistError`). Net posture: low runtime risk, low-to-medium DX/typing risk.

## Findings at a glance

| ID | Finding | Severity | Effort |
|----|---------|----------|--------|
| `API-01` | FeatureLayer.get_value_counts / get_nested_count send returnGeometry=True and outFields=* because the instance datadict clobbers the stats-only flags | medium | M |
| `API-02` | FieldDoesNotExistError exported at runtime but absent from the TYPE_CHECKING block — `from restgdf import FieldDoesNotExistError` is unresolved for static type checkers on a py.typed package | low | S |
| `API-03` | No test asserts the three public-surface sources of truth stay set-equal, so the TYPE_CHECKING block can silently drift from __all__/_LAZY_EXPORTS | low | S |
| `API-04` | get_nested_count documents 'two or more fields' but nested_count hardcodes fields[0]/fields[1]: silently wrong for 3+ fields, IndexError for 1 | low | S |

## Findings

### API-01 · FeatureLayer.get_value_counts / get_nested_count send returnGeometry=True and outFields=* because the instance datadict clobbers the stats-only flags

**Severity:** medium · **Effort:** M · **Location:** `restgdf/utils/_stats.py:117-126 and 165-174; restgdf/featurelayer/featurelayer.py:141-150,626-631,662-667`

**Evidence**

In `_stats.get_value_counts` the body is built as `data = {"where": "1=1", "f": "json", "returnGeometry": False, "outFields": field, "outStatistics": statstr, "groupByFieldsForStatistics": field, **data}` — the caller-supplied `data` is spread LAST, so it overrides the operation flags. `FeatureLayer` always populates `data`: `self.datadict = default_data(kwargs.pop("data", {}))` (`featurelayer.py:141`) merges `DEFAULTDICT` `{"returnGeometry": True, "outFields": "*", ...}` and then `self.kwargs["data"] = self.datadict` (line 150). That `datadict` is forwarded via `**self.kwargs` to `get_value_counts`/`nested_count` (lines 630/666). Result: `returnGeometry` is reset to `True` and `outFields` to `*`, overriding the `False`/`field` the stats path set. Contrast `get_unique_values` (same module, line 60) which routes through the PROTECTIVE `build_conservative_query_data` that forwards only `where`+`token`.

**Why it matters**

Every `FeatureLayer.get_value_counts()`/`get_nested_count()` call — the documented common path — issues an `outStatistics` query with `returnGeometry=true` and `outFields=*`. ArcGIS servers that reject combining `outStatistics` with `outFields=*` / `returnGeometry=true` (a common server configuration) will return an error envelope, surfacing as `RestgdfResponseError` on a request that should succeed; where it does succeed it wastefully transfers geometry. The hardening applied to `get_unique_values` (`build_conservative_query_data`) was never applied to the two stats helpers.

**Recommendation**

Route `get_value_counts` and `nested_count` through a conservative merge (like `build_conservative_query_data`) that forwards only `where` + `token` from the caller-supplied `data` and lets the operation-specific stats flags (`returnGeometry=False`, `outFields=<field>`, `outStatistics`, `groupByFieldsForStatistics`) win — mirroring the already-correct `get_unique_values` path (`_stats.py:60-69`) and the `get_feature_count` contract asserted in `test_characterization.py:64,74-86`. IMPORTANT anti-recommendation: do NOT take the naive `{**data, <stats flags>}` approach the finding offers as its second option. That would let the hardcoded `"where": "1=1"` in the stats flags clobber the instance WHERE clause that `FeatureLayer` stores in `datadict["where"] = self.wherestr` (`featurelayer.py:142`), silently dropping the user's filter from `get_value_counts`/`get_nested_count` on a refined layer — trading one bug for a worse one. The conservative-merge route is the only fix that preserves `where` while neutralizing `returnGeometry`/`outFields`/`returnCountOnly`. Add an integration test that drives `FeatureLayer.get_value_counts()`/`get_nested_count()` (NOT the bare module helper) through a fake session and asserts the outgoing body has `returnGeometry` coerced false, `outFields=<field>`, no `returnCountOnly`, and the instance `where` preserved — the current `FeatureLayer` tests (`test_FeatureLayer.py:536-566`) mock the helper entirely and never exercise this seam.

**Fix touches:** `restgdf/utils/_stats.py`, `restgdf/_client/request.py`

---

### API-02 · FieldDoesNotExistError exported at runtime but absent from the TYPE_CHECKING block — `from restgdf import FieldDoesNotExistError` is unresolved for static type checkers on a py.typed package

**Severity:** low · **Effort:** S · **Location:** `restgdf/__init__.py:45-63, restgdf/__init__.py:87, restgdf/__init__.py:174`

**Evidence**

`__all__` lists `"FieldDoesNotExistError"` (line 87) and `_LAZY_EXPORTS` maps it to `restgdf.errors` (line 174), so `import restgdf; restgdf.FieldDoesNotExistError` works at runtime via `__getattr__`. But the `if TYPE_CHECKING:` errors import block (lines 45-63) imports every error EXCEPT this one: it lists `... SchemaValidationError, TokenExpiredError ...` but never `FieldDoesNotExistError`. It is the only name in `errors.__all__` (`restgdf/errors.py:424`) missing from the static block. The package ships `restgdf/py.typed`, so downstream code does `from restgdf import FieldDoesNotExistError`. A module-level `__getattr__` returning `Any` does NOT rescue a `from`-import of a name that appears in `__all__` but has no static binding: pyright reports it as an unknown export symbol, and the symbol resolves to an untyped/`Any` fallback under mypy, so `except FieldDoesNotExistError` and `isinstance(e, FieldDoesNotExistError)` lose their declared type.

**Why it matters**

A documented, top-level public exception (callers are explicitly told in `FeatureLayer` docstrings to `except FieldDoesNotExistError`) is not statically importable from the advertised top-level path on a typed package. Downstream users running pyright/mypy in strict mode get a spurious error or silent `Any` on the canonical import form, while every sibling exception resolves cleanly — an inconsistent, surprising typing contract.

**Recommendation**

Add `FieldDoesNotExistError` to the `from .errors import (...)` tuple inside the `if TYPE_CHECKING:` block in `restgdf/__init__.py` (alphabetically between `ConfigurationError` and `InvalidCredentialsError`). This is the correct and safe fix: the `TYPE_CHECKING` block executes only for static checkers, never at runtime, so it cannot perturb the light-core lazy-import boundary, and `.errors` is a dependency-free pure-Python module already imported there for its 16 sibling exceptions. No `.pyi` stub exists, so this inline block is the sole static surface. Note for whoever writes the fix: the underlying root cause is that the `TYPE_CHECKING` block and `_LAZY_EXPORTS`/`__all__` are maintained by hand and can drift; consider a unit test that asserts every name in `restgdf.__all__` is statically importable (the existing `test_public_api.py` only checks runtime `getattr`, which is why this gap slipped through) so future drift is caught by the gate.

**Fix touches:** `restgdf/__init__.py`

---

### API-03 · No test asserts the three public-surface sources of truth stay set-equal, so the TYPE_CHECKING block can silently drift from __all__/_LAZY_EXPORTS

**Severity:** low · **Effort:** S · **Location:** `tests/test_public_api.py:80-107, restgdf/__init__.py:8-63, restgdf/__init__.py:126-196`

**Evidence**

`test_public_all_is_complete` (`test_public_api.py:81`) only checks `set(restgdf.__all__) == _EXPECTED_CLASSES | _EXPECTED_CALLABLES | _EXPECTED_MODULES`, and `test_all_names_in_all_are_attributes` (line 106) only exercises runtime `hasattr`. Nothing compares the names in the `if TYPE_CHECKING:` import block (`restgdf/__init__.py:8-65`) against `_LAZY_EXPORTS` keys (lines 126-196) or `__all__`. Because `__getattr__` makes every lazy name resolve at runtime regardless, the runtime tests pass even when the static block is incomplete — which is exactly how the `FieldDoesNotExistError` gap (see separate finding) survives CI.

**Why it matters**

The static-typing half of a `py.typed` library's public contract is unguarded. Any future export added to `__all__`/`_LAZY_EXPORTS` but forgotten in the `TYPE_CHECKING` block ships an import that works at runtime but fails type-checking for downstream users, with no CI signal. This is the root cause that lets the `FieldDoesNotExistError` class of bug recur.

**Recommendation**

Keep the recommendation but reframe its purpose and downgrade urgency. The proposed test IS sound and will work: add to `tests/test_public_api.py` a test that ASTs `restgdf/__init__.py`, collects names bound under the `if TYPE_CHECKING:` block, and asserts they equal `set(_LAZY_EXPORTS) - {non-module... }` (or simply `== set(__all__) - {module names}`). I verified this catches the real drift: an AST pass reports `FieldDoesNotExistError` as the sole name in `__all__`/`_LAZY_EXPORTS` but missing from the `TYPE_CHECKING` block. Note that `set(restgdf.__all__) == set(restgdf._LAZY_EXPORTS)` is ALREADY True at runtime, so the only unguarded source-of-truth is the static block — the test only needs to cover that one axis. ANTI-RECOMMENDATION: do NOT justify this test by claiming the gap "fails type-checking for downstream users" — that is false (see notes). The test guards type-*precision*, not type-*safety*. Also do not rip out the `def __getattr__(name) -> Any` pattern to force hard errors; that is the deliberate PEP-562 lazy-import boundary that keeps the light core import-cheap, and removing it would break the documented lazy-import contract that `test_lazy_imports.py` enforces.

**Fix touches:** `tests/test_public_api.py`, `restgdf/__init__.py`

---

### API-04 · get_nested_count documents 'two or more fields' but nested_count hardcodes fields[0]/fields[1]: silently wrong for 3+ fields, IndexError for 1

**Severity:** low · **Effort:** S · **Location:** `restgdf/utils/_stats.py:192-199; restgdf/featurelayer/featurelayer.py:634-667`

**Evidence**

`nested_count` builds an `outStatistics` entry per field (lines 155-164) but the post-processing hardcodes the first two: `dropcol = [c for c in cc.columns if c.startswith(f"{fields[0]}_count")][0]` and `rencol = [c for c in cc.columns if c.startswith(f"{fields[1]}_count")][0]`, then `cc.drop(columns=dropcol).rename(columns={rencol: "Count"}).sort_values([fields[0], "Count"], ...)`. `FeatureLayer.get_nested_count` docstring says 'Two or more field names to cross-tabulate' (`featurelayer.py:642-643`) and only validates membership (`any(field not in self.fields ...)`, line 657) — it never checks `len(fields)>=2`.

**Why it matters**

With three or more fields, only the SECOND field's count column is renamed to `'Count'` and the first's is dropped; the third+ `*_count` columns linger unrenamed and the result is silently the wrong cross-tab (does not match the documented contract). With a single-element tuple, `fields[1]` raises `IndexError` deep in the helper rather than a clear validation error. The `[0]` index on the column-match list is also fragile if a field name is a prefix of another (e.g. fields `'A'` and `'A2'`).

**Recommendation**

Honor the documented contract by validating arity. Simplest sound fix: restrict to exactly two fields — add `if len(fields) != 2: raise ValueError(...)` (or a clear `FieldDoesNotExist`-style error) in `FeatureLayer.get_nested_count` AND in the `nested_count` helper (the helper is a public re-exported name via `restgdf.utils.getinfo`, so a direct caller can still hit `fields[1]` `IndexError`), AND amend the docstring at `featurelayer.py:642-643` from "Two or more field names" to "Exactly two field names" — otherwise the fix merely relocates the doc/impl divergence. If 3+ field cross-tabs are actually desired, generalize the post-processing instead: keep one `*_count` as `Count` and drop the rest, e.g. `count_cols = [c for c in cc.columns if c.endswith("_count")]`, then drop all but one and rename, and sort by `[*fields, "Count"]`. ANTI-RECOMMENDATION: do not silently keep the current two-field-only logic while leaving the "two or more" docstring — that is the actual finding. Note the finding's "silently wrong cross-tab" claim for 3+ fields is overstated: in an ArcGIS group-by over all fields every `*_count` equals the group row count, so the rows and `Count` values are correct; the only defects are a leftover redundant `fields[2]_count` column and an incomplete sort. The `== f"{f}_count"` exact-match suggestion is cosmetic — the `_count` suffix delimiter already makes `startswith` prefix collisions effectively impossible.

**Fix touches:** `restgdf/utils/_stats.py`, `restgdf/featurelayer/featurelayer.py`

---

## Minor notes (not adversarially verified)

These were flagged by the axis auditor but did NOT go through per-finding verification — treat as leads, not confirmed findings.

- **_types.py docstring vs MIGRATION.md disagree on removal timing (doc drift, DOCS-axis-adjacent)** — `restgdf/_types.py:30` and `MIGRATION.md:686` both say the shim 'will be removed in 3.x', while `MIGRATION.md:345` says removal is 'no earlier than 3.x final'. The shim is correctly retained and warning at 3.0.0, so the implementation is fine; the seed's 'stale contract' concern is refuted as a behavior bug. The wording inconsistency is a doc nit (owned by DOCS), not an API contract divergence.
- **RestgdfResponseError imported twice in the TYPE_CHECKING block** — `restgdf/__init__.py` imports `RestgdfResponseError` from both `._models` (line 36) and `.errors` (line 56), while `_LAZY_EXPORTS` maps it only to `restgdf._models` (line 158). Class identity is preserved (`restgdf/_models/_errors.py:13` re-exports `restgdf.errors.RestgdfResponseError as RestgdfResponseError`), so this is harmless redundancy for type checkers, not a bug. Worth removing the duplicate `.errors` line to keep the static block aligned with the runtime resolution path.
- **_REMOVED_EXPORTS graceful-removal path is wired and tested — seed refuted** — The lead that the removal branch is dead code is wrong: `restgdf/__init__.py:205-210` is exercised by `tests/test_pep562_removed_exports.py:48-65` (which monkeypatches an entry, asserts the `DeprecationWarning` + `AttributeError`, and checks the warning filename is the caller), and the empty default is locked by `test_removed_exports_default_mapping_is_empty`. The mechanism is ready for the next deprecation cycle.
- **compat.as_dict by_alias=False is documented and intentional — seed refuted** — The lead that `as_dict` silently breaks camelCase-indexing migration code does not hold against the docs: `MIGRATION.md:635-661` and the `as_dict` docstring (`restgdf/compat.py:38-43`) both explicitly state `as_dict` returns snake_case and that camelCase round-trip requires `model_dump(by_alias=True)`. This is a documented decision, not a divergence.
- **dir(restgdf) does not advertise _REMOVED_EXPORTS names** — `restgdf/__init__.py:219-220` `__dir__` unions globals, `__all__`, and `_LAZY_EXPORTS` but not `_REMOVED_EXPORTS`. When the removal table is eventually populated, removed names won't appear in REPL/IDE completion, so a user typing the old name gets no discoverability hint before the `AttributeError`. Currently empty so no impact; consider including removed keys (or their messages) once the table is used.
