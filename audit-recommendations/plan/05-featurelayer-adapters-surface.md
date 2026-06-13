# 05 — FeatureLayer, stats, adapters, public surface, telemetry/logging

> Workstream of the restgdf remediation plan · audit pinned `4673b08` · 2026-06-13

## Goal

Land the correctness, contract, and observability fixes for the consumer-facing read path: `FeatureLayer` (caching, stats query bodies, arity), the dict/pandas/geopandas output adapters, the lazy public namespace (`__all__`/`_LAZY_EXPORTS`/`TYPE_CHECKING` set-equality), the published inline types (Protocol vs aiohttp, drift union-attr, metadata annotations), and the telemetry/logging seam (log-correlation filter, per-service drift attribution). These are the surfaces a downstream user touches directly — every fix here either removes a documented-contract violation, a silent-wrong-result, or a published-type lie. The workstream also carries the FeatureLayer-construction consume seam for the config wiring rooted in W3.

## Collision domain

This workstream OWNS as single-writer:

- `restgdf/featurelayer/featurelayer.py`
- `restgdf/utils/_stats.py`
- `restgdf/utils/_metadata.py`
- `restgdf/adapters/*` (`restgdf/adapters/geopandas.py`, `restgdf/adapters/pandas.py`; `dict.py`/`stream.py` untouched)
- `restgdf/_client/request.py`
- `restgdf/_client/_protocols.py`
- `restgdf/__init__.py`
- `restgdf/_models/_drift.py`
- `restgdf/_logging.py`
- `tests/test_resolve_domains.py`
- `tests/test_public_api.py`
- `tests/test_models_primitives.py`
- `tests/test_telemetry_log_span_correlation.py`

Hot-file notes (multiple W5 items write the same file — serialize within the workstream, no cross-workstream split):

- `restgdf/featurelayer/featurelayer.py` — touched by **W5-1, W5-3, W5-9, W5-14** (plus the test for W5-2 drives it). Single-writer to W5, but four items contend; sequence them.
- `restgdf/utils/_stats.py` — touched by **W5-2, W5-3**.
- `restgdf/utils/_metadata.py` — touched by **W5-4, W5-11**.
- `restgdf/_models/_drift.py` — touched by **W5-10, W5-13**.
- `restgdf/__init__.py` — touched by **W5-7, W5-8**.
- `restgdf/_client/request.py` — touched by **W5-2** only.

No file in this workstream is split-owned with another workstream. The only cross-workstream coupling is via *dependency edges* (W5-9/W5-10/W5-11 depend on W1-2 flipping the mypy gate; W5-14 depends on W3-3/W3-4 landing the config source of truth). The verify_ssl/user_agent root (CONFIG-01/AUTH-03) does NOT touch any W5 file — that wiring is W2/W3/W4.

## Sequencing & parallelization

Order is milestone-first, then dependency.

**M1 (quick win, no deps):**
- **W5-7** (add `FieldDoesNotExistError` to TYPE_CHECKING block) — must land before W5-8.

**M2 (high-severity correctness + the mypy-gated typing fixes):**
- **W5-1** (cache copy-on-return) — independent, `featurelayer.py`.
- **W5-4** (permissive-tier field guard) — independent, `_metadata.py`.
- **W5-8** (set-equality test) — **Depends W5-7**; `__init__.py` + `test_public_api.py`.
- **W5-12** (log-correlation filter) — independent, `_logging.py` + test.
- **W5-9** (Protocol vs aiohttp), **W5-10** (drift union-attr), **W5-11** (metadata annotation) — all **Depend W1-2** (mypy gate must see aiohttp/pydantic before any of these can be *verified*). These three are the errors W1-2 surfaces; they MUST land with or before the gate flips to required (per the W1-2 note). W5-10 and W5-11 are pure annotation/soundness fixes; W5-9 is the load-bearing Protocol/docstring fix that also unblocks W4-6 (getgdf widening).

**M3 (medium correctness + config consume + drift scope):**
- **W5-2** (stats datadict clobber) — `_stats.py` + `request.py`. Serialize with W5-3 on `_stats.py`.
- **W5-3** (nested_count arity) — `_stats.py` + `featurelayer.py`. Serialize after W5-2 on `_stats.py`.
- **W5-6** (resolve_domains robustness) — independent, `pandas.py` + test.
- **W5-13** (per-service drift attribution) — `_drift.py` + `test_models_primitives.py`. Serialize with W5-10 on `_drift.py`.
- **W5-14** (FeatureLayer `from_config` consume) — **Depends W3-3, W3-4**; `featurelayer.py`.

**M4 (polish):**
- **W5-5** (geopandas docstring fix) — independent, docs-only edit in `geopandas.py`.

**Cross-workstream `Depends` edges (explicit):**
- W5-8 blocks on **W5-7** landing the missing TYPE_CHECKING entry (same workstream).
- W5-9, W5-10, W5-11 block on **W1-2** flipping the mypy gate to a deps-present run (the errors are invisible until then). They in turn unblock **W4-6** (TYPING-04 getgdf widening, owned by W4) — W4-6 must not land before W5-9 fixes the Protocol or it merely relocates the error.
- W5-14 blocks on **W3-3** (CONFIG-02 AuthConfig exposure) and **W3-4** (CONFIG-03 explicit-Config precedence). Token consume side is **W2-11**.
- Doc-side counterparts (not in this workstream): W5-12 → W6-7 (observability.md), W5-13 → W6-4 (MIGRATION.md).

**Parallel-safe batches (disjoint files):** {W5-1, W5-4, W5-12} can run in parallel. {W5-9+W5-11} (different files) parallel with W5-10. W5-6 parallel with anything. Serialize: W5-7→W5-8 (both `__init__.py`); W5-2→W5-3 (both `_stats.py`); W5-10↔W5-13 (both `_drift.py`); W5-1/W5-3/W5-9/W5-14 all contend on `featurelayer.py` — apply in that order or rebase carefully.

## Work items

### W5-7 · Add FieldDoesNotExistError to the TYPE_CHECKING block
**Audit refs:** API-02 · **Severity:** low · **Effort:** S · **Milestone:** M1
**Depends:** — · **Blocks:** W5-8
**Split-ownership:** —
**Scope** — In: add the single missing static import binding to `restgdf/__init__.py`. Out-of-scope: do NOT remove the `def __getattr__(name) -> Any` PEP-562 lazy-import pattern (that is the deliberate light-core boundary enforced by `test_lazy_imports.py`); do NOT touch `__all__` or `_LAZY_EXPORTS` (they already list the name correctly).
**Spec**
1. In `restgdf/__init__.py`, the `if TYPE_CHECKING:` errors import block at `from .errors import (...)` (verified: `restgdf/__init__.py:45-63`) imports every error EXCEPT `FieldDoesNotExistError` — it currently steps from `ConfigurationError` (verified: `restgdf/__init__.py:49`) directly to `InvalidCredentialsError` (verified: `restgdf/__init__.py:50`).
2. Insert `FieldDoesNotExistError,` alphabetically between `ConfigurationError` and `InvalidCredentialsError` in that tuple. `__all__` already lists it (verified: `restgdf/__init__.py:87`) and `_LAZY_EXPORTS` already maps it to `restgdf.errors` (verified: `restgdf/__init__.py:174`), so runtime is already correct — this fix is static-checker-only.
3. The `TYPE_CHECKING` block runs only for static analysis, never at runtime, so it cannot perturb the lazy-import boundary; `.errors` is already imported there for its 16 sibling exceptions.
**Acceptance criteria**
- [ ] `FieldDoesNotExistError` appears in the `if TYPE_CHECKING:` `from .errors import (...)` tuple, alphabetically placed.
- [ ] `from restgdf import FieldDoesNotExistError` resolves cleanly under the deps-present mypy run (no unknown-export / `Any`-fallback).
- [ ] Set-equality test W5-8 (which lands next) passes against this change.
**Validation** — lint; test (runtime unaffected, but confirm green).
**Risks & rollback** — Near-zero risk (static-only). Rollback = remove the one inserted line. Anti-rec: do not "fix" by deleting the lazy `__getattr__`.

---

### W5-1 · Return cached frames as copies (or document the shared-reference contract)
**Audit refs:** ASYNC-02 · **Severity:** medium · **Effort:** S · **Milestone:** M2
**Depends:** — · **Blocks:** —
**Split-ownership:** —
**Scope** — In: copy-on-return for the four cache-hit return sites in `restgdf/featurelayer/featurelayer.py`. Out-of-scope: do NOT advertise concurrency safety on the back of this fix — the cache *population* (`if self.gdf is None: ...`) is still racy under `asyncio.gather`; that is a separate, out-of-scope concern. Do NOT change the cache-population logic or eviction.
**Spec**
1. `get_gdf` cache hit returns the stored GeoDataFrame by reference: `return self.gdf` (verified: `restgdf/featurelayer/featurelayer.py:301`). Change to `return self.gdf.copy()`.
2. `get_unique_values` cache hit: `return self.uniquevalues[cache_key]` (verified: `restgdf/featurelayer/featurelayer.py:597`). Branch the copy by stored type — `.copy()` for the multi-field DataFrame branch, `list(...)` for the single-field scalar-list branch (the cache stores `list | DataFrame`; verified annotation `restgdf/featurelayer/featurelayer.py:152-155`). A clean approach: `cached = self.uniquevalues[cache_key]; return cached.copy() if hasattr(cached, "copy") and not isinstance(cached, list) else list(cached)` — or simpler, copy at the return by checking `isinstance(cached, list)`.
3. `get_value_counts` cache hit: `return self.valuecounts[field]` (verified: `restgdf/featurelayer/featurelayer.py:632`). Change to `return self.valuecounts[field].copy()`.
4. `get_nested_count` cache hit: `return self.nestedcount[fields]` (verified: `restgdf/featurelayer/featurelayer.py:668`). Change to `return self.nestedcount[fields].copy()`.
5. ANTI-RECOMMENDATION caveat (R-65): the `get_gdf` copy MUST preserve `gdf.attrs["spatial_reference"]`. pandas/geopandas `.copy()` propagates `.attrs`, so this holds — but it must be asserted by a test (see acceptance).
6. The documentation-only alternative (docstring "the returned object is a shared cached reference callers MUST NOT mutate") is acceptable but weaker; copy-on-return is preferred here for a Production/Stable library.
**Acceptance criteria**
- [ ] Red-first: a test mutating a cached frame in place (e.g. `df.rename(columns=..., inplace=True)` or column assignment) and asserting a second call returns an unmutated frame — written and confirmed failing on `main` before the fix.
- [ ] After fix: second-call frame is value-equal to the first but `first is not second` for all four cache paths.
- [ ] A test asserts `(await layer.get_gdf()).attrs["spatial_reference"]` survives the copy (R-65 regression guard).
- [ ] Existing cache tests stay green: `test_featurelayer_getgdf_caches_result` and the `*_caches_*` tests assert `.equals()` + `assert_awaited_once()`, neither of which a post-await copy violates (no existing test asserts `first is second`).
**Validation** — lint; single `.\.venv\Scripts\python.exe -m pytest -k "caches or get_gdf"`; test; coverage.
**Risks & rollback** — Per-call `.copy()` adds memory/CPU on cache hits (acceptable for correctness). Rollback = revert the four return sites. Anti-rec carried: do not claim task-safety; do not skip the `attrs` assertion.

---

### W5-4 · Tolerate permissive-tier fields missing name/type in get_fields
**Audit refs:** ADAPTERS-01 · **Severity:** medium · **Effort:** S · **Milestone:** M2
**Depends:** — · **Blocks:** —
**Split-ownership:** —
**Scope** — In: guard the field iterators in `restgdf/utils/_metadata.py` so a field entry missing `name` or `type` returns the resolvable subset instead of raising. Out-of-scope: do NOT change `get_object_id_field` (already guarded); do NOT introduce geometry normalization.
**Spec**
1. `get_fields(types=False)` returns `[f["name"] for f in fields]` and `get_fields(types=True)` returns `{f["name"]: f["type"].replace("esriFieldType", "") ...}` (verified: `restgdf/utils/_metadata.py:149-150`). `_field_rows` does `[(f["name"], f["type"].replace(...)) for f in fields]` (verified: `restgdf/utils/_metadata.py:157`). These fields come from `_as_dict(...)["fields"]` whose `FieldSpec` has `name`/`type` as `str | None = None` (permissive tier).
2. The sibling `get_object_id_field` already guards with `isinstance(field.get("name"), str)` (verified: `restgdf/utils/_metadata.py:92`) — mirror that filter.
3. Route BOTH `get_fields` and `get_fields_frame` through the same guarded `_field_rows`-style logic so the dict/list/DataFrame views agree on the surviving field set. Concretely:
   - `get_fields(types=False)`: `[f["name"] for f in fields if isinstance(f.get("name"), str)]`.
   - `get_fields(types=True)` / `_field_rows`: only emit a row when `isinstance(f.get("name"), str)`, and default a missing/`None` `type`: `(f["name"], (f.get("type") or "").replace("esriFieldType", ""))`.
4. ANTI-RECOMMENDATION: do NOT just swap `f["type"]` for `f.get("type")` without the `None`-guard — that converts the `KeyError` into `AttributeError: 'NoneType' has no attribute 'replace'`. The fix must handle BOTH missing-key AND explicit-`None`.
5. Document the skip behavior (a field with no usable `name` is dropped) in the `get_fields`/`get_fields_frame`/`_field_rows` docstrings so the drop is an intentional, contract-aligned decision.
**Acceptance criteria**
- [ ] Red-first: a test feeding a field dict missing `type` (and one missing `name`) through `_parse_response(LayerMetadata, ...)` then `get_fields(types=True)` / `get_fields_frame` — confirmed raising `KeyError`/`AttributeError` on `main` before the fix.
- [ ] After fix: the resolvable subset is returned without raising; the nameless field is dropped consistently across `get_fields`, `get_fields_frame`, and `get_fieldtypes`.
- [ ] Docstrings state the skip behavior.
**Validation** — lint; single `.\.venv\Scripts\python.exe -m pytest -k "fields or metadata"`; test; coverage.
**Risks & rollback** — Skip-vs-default changes the returned key/row set for malformed layers (intended, documented). Rollback = revert the guards. Anti-rec carried: never leave `.replace()` reachable on `None`.

---

### W5-8 · Add a set-equality test for __all__/_LAZY_EXPORTS/TYPE_CHECKING
**Audit refs:** API-03 · **Severity:** low · **Effort:** S · **Milestone:** M2
**Depends:** W5-7 · **Blocks:** —
**Split-ownership:** —
**Scope** — In: add an AST-based test to `tests/test_public_api.py` that the names bound under the `if TYPE_CHECKING:` block stay set-equal to the runtime sources of truth. Out-of-scope: do NOT rip out the `def __getattr__(name) -> Any` pattern to force hard errors (that is the deliberate PEP-562 boundary `test_lazy_imports.py` enforces); do NOT justify the test by claiming the gap "fails type-checking for downstream users" (it guards type-*precision*, not type-*safety*).
**Spec**
1. `test_public_all_is_complete` (verified: `tests/test_public_api.py:80-83`) only checks `__all__` == expected sets; `test_all_names_in_all_are_attributes` (verified: `tests/test_public_api.py:105-107`) only checks runtime `hasattr`. Nothing compares the `TYPE_CHECKING` block names.
2. Add a test that `ast.parse`s `restgdf/__init__.py`, walks the `if TYPE_CHECKING:` body, collects all names bound by its `ImportFrom`/`Import` nodes, and asserts that set equals `set(restgdf.__all__) - _EXPECTED_MODULES` (module names `adapters`/`compat`/`utils` are imported as `from . import ...` and may be treated separately) — or equivalently `set(_LAZY_EXPORTS) - {module-valued keys}`.
3. Note: `set(restgdf.__all__) == set(restgdf._LAZY_EXPORTS)` is ALREADY true at runtime (verified by inspection of `restgdf/__init__.py:67-122` vs `126-196`), so the only unguarded axis is the static `TYPE_CHECKING` block — the test only needs to cover that one axis.
4. This test, once W5-7 has landed, must pass; on a tree without W5-7 it must fail reporting `FieldDoesNotExistError` as the sole drifted name (use that as the red-state demonstration if landing W5-8 before W5-7 in a branch).
**Acceptance criteria**
- [ ] AST test added to `tests/test_public_api.py`; passes with W5-7 applied.
- [ ] Red-first demonstration: the test fails (reporting `FieldDoesNotExistError`) when run against the pre-W5-7 `__init__.py`.
- [ ] The module-name handling (`adapters`/`compat`/`utils`, which are `from . import ...` not `from .X import Y`) is correct and documented in a comment.
**Validation** — lint; single `.\.venv\Scripts\python.exe -m pytest tests/test_public_api.py`; test.
**Risks & rollback** — AST walking can be brittle to import-style changes; keep it tolerant of both `ImportFrom` and aliased imports. Rollback = remove the test. Anti-rec carried: do not remove `__getattr__`.

---

### W5-12 · Make the log-correlation filter not error outside an active span
**Audit refs:** TELEMETRY-01 · **Severity:** medium · **Effort:** S · **Milestone:** M2
**Depends:** — · **Blocks:** —
**Split-ownership:** Code part (the `_SpanContextFilter` fix in `restgdf/_logging.py`) owned here; the `docs/recipes/observability.md` log-correlation recipe prose half of TELEMETRY-01 is owned by **W6-7**.
**Scope** — In: make `_SpanContextFilter.filter` always stamp `record.trace_id`/`record.span_id` (defaulting outside a valid span) in `restgdf/_logging.py`, and flip the one contradicting test pin. Out-of-scope: do NOT change `span_context_fields()` (independent helper, returns `{}` outside a span — its test must stay green); do NOT recommend `logging.Formatter(defaults=...)` (Python 3.10+, package declares `requires-python >= 3.9`). The `docs/recipes/observability.md` prose is W6-7, not this item.
**Spec**
1. `_SpanContextFilter.filter` sets the attributes ONLY inside `if ctx is not None and ctx.is_valid:` with no else (verified: `restgdf/_logging.py:179-181`), so a record emitted outside a `feature_layer.stream` span (the common case — `auth.refresh.start` DEBUG, the pagination `exceededTransferLimit` warning, the `maxRecordCountFactor clamp` warning) has no `trace_id`/`span_id`, and the documented `%(trace_id)s` recipe raises `ValueError: Formatting field not found` swallowed into a stderr `--- Logging error ---` dump.
2. Adopt option (a): ALWAYS stamp, defaulting when no valid span. Replace the conditional assignment with:
   ```
   if ctx is not None and ctx.is_valid:
       record.trace_id = format(ctx.trace_id, "032x")
       record.span_id = format(ctx.span_id, "016x")
   else:
       record.trace_id = ""
       record.span_id = ""
   ```
   The filter is already attached across the whole `restgdf.*` tree via `_install_span_context_filter` (verified: `restgdf/_logging.py:191-198`), so transport/auth/pagination records are covered.
3. Flip the one contradicting pin: `test_restgdf_log_record_outside_span_has_no_trace_id` currently asserts `assert not hasattr(record, "trace_id")` / `span_id` (verified: `tests/test_telemetry_log_span_correlation.py:60-67`). Update it to assert the sentinel: `record.trace_id == ""` and `record.span_id == ""` (rename the test accordingly).
4. Do NOT touch `test_span_context_fields_empty_outside_span` (verified: `tests/test_telemetry_log_span_correlation.py:70-73`) — `span_context_fields()` is independent of the filter and its `{}`-outside-span contract is preserved.
5. Minor accepted caveat: an empty-string default is indistinguishable from a degenerate all-zero context — cosmetic, acknowledged.
**Acceptance criteria**
- [ ] Red-first: a test configuring a stdlib formatter with `%(trace_id)s` and emitting a `restgdf.transport` record OUTSIDE a span — confirmed producing a logging `ValueError`/stderr dump on `main` before the fix.
- [ ] After fix: the same record renders with empty trace/span fields and no logging error.
- [ ] `test_restgdf_log_record_auto_carries_trace_id` (inside-span path) stays green.
- [ ] `test_span_context_fields_empty_outside_span` unchanged and green.
- [ ] Doc-sync flagged for W6-7 (observability.md recipe) — not edited here.
**Validation** — lint; single `.\.venv\Scripts\python.exe -m pytest tests/test_telemetry_log_span_correlation.py`; test; coverage.
**Risks & rollback** — Empty-string default could surprise a consumer expecting absence; documented as intentional. Rollback = revert the else-branch and the test pin together. Anti-rec carried: no `Formatter(defaults=...)`.

---

### W5-9 · Reconcile AsyncHTTPSession Protocol with aiohttp.ClientSession
**Audit refs:** TYPING-02 · **Severity:** medium · **Effort:** M · **Milestone:** M2
**Depends:** W1-2 · **Blocks:** W4-6 (TYPING-04 getgdf widening, owned by W4)
**Split-ownership:** —
**Scope** — In: fix the `AsyncHTTPSession` Protocol in `restgdf/_client/_protocols.py` and the internal bidirectional session-type inconsistency at `restgdf/featurelayer/featurelayer.py`. Out-of-scope: do NOT pair with a blanket global `--strict`/`ignore_missing_imports` removal (that surfaces the intended-`Any` boundaries noisily — W1-2 anti-rec); do NOT widen `get_gdf` here (that is W4-6 and must follow this fix).
**Spec**
1. GATE FIRST (load-bearing): W1-2 must have added `aiohttp` (and `pydantic`) to the mypy run so `ClientSession` resolves to a real type. Until then NO Protocol fix is verifiable — today the hook env has only `types-requests`, `ClientSession` collapses to `Any`, and no `arg-type` error surfaces. This item is sequenced behind W1-2 for exactly that reason.
2. The Protocol docstring asserts "Matches :class:`aiohttp.ClientSession`" (drift: audit cited `_protocols.py:24-25`, now at `restgdf/_client/_protocols.py:26`) but `get`/`post` are declared with explicit keyword-only params `params/headers/ssl/timeout/**kwargs` (verified: `restgdf/_client/_protocols.py:50-74`), which do not structurally match aiohttp's `def get(self, url: str | URL, **kwargs: **_RequestOptions) -> _BaseRequestContextManager[...]`.
3. ANTI-RECOMMENDATION (verify before claiming a fix): simply rewriting to `(self, url: str, **kwargs: Any) -> Any` is NOT guaranteed to make `ClientSession` structurally assignable — a minimal `**kwargs: Any` protocol still fails against aiohttp's typed `**_RequestOptions` unpack and `_BaseRequestContextManager` return. VERIFY any signature change against the real aiohttp stubs (post-W1-2) before declaring it resolves the conflict. Likely you need `url: str | URL` plus a matching return type, OR accept that a `runtime_checkable` Protocol cannot be a static supertype of `ClientSession` and instead scope the docstring "Matches aiohttp.ClientSession"/"signature details are advisory" (drift: audit cited lines 26/30-31; "Matches" now `_protocols.py:26`, "advisory per typing.Protocol" now `restgdf/_client/_protocols.py:30-31`) to runtime `isinstance` only.
4. Fix the internal inconsistency exposed once aiohttp is visible: `FeatureLayer.session` is typed `AsyncHTTPSession` (verified: `restgdf/featurelayer/featurelayer.py:94`) and passed straight into `get_gdf` at `self.gdf = await get_gdf(self.url, self.session, **self.kwargs)` (verified: `restgdf/featurelayer/featurelayer.py:300`), while `get_gdf` is still typed `session: ClientSession | None` (verified: `restgdf/utils/getgdf.py:503`). Pick one direction; the W5 side is `featurelayer.py` + the Protocol — the `get_gdf` widening itself is W4-6 and must land AFTER this Protocol fix (else line 510 `session = session or ClientSession()` fails assigning `ClientSession` to an `AsyncHTTPSession`-typed name).
5. Correct user-facing scope in the docstring/notes: the README canonical path is `FeatureLayer.from_url(url, session=session)` and `from_url(cls, url, **kwargs)` is untyped (verified: `restgdf/featurelayer/featurelayer.py:212`), so that documented path does NOT error for users — the spurious `arg-type` fires only via the direct `FeatureLayer(url, session)` constructor (verified non-preferred per the `__init__` docstring "Prefer :meth:`from_url`", `restgdf/featurelayer/featurelayer.py:101`).
**Acceptance criteria**
- [ ] Under the deps-present mypy run (W1-2), `FeatureLayer("…/0", aiohttp.ClientSession())` no longer produces the `arg-type`/"Following member(s) ... have conflicts" error — OR, if a Protocol cannot be a static supertype, the docstring is corrected to scope the "matches" claim to runtime `isinstance` and a mypy comment documents the boundary.
- [ ] `restgdf/featurelayer/featurelayer.py:300` no longer reports a `ClientSession | None` vs `AsyncHTTPSession` mismatch under deps-present mypy.
- [ ] `isinstance(aiohttp.ClientSession(), AsyncHTTPSession)` still returns `True` at runtime (runtime_checkable presence-only contract preserved).
- [ ] W4-6 (getgdf widening) is unblocked and noted as the follow-on.
**Validation** — lint (includes the W1-2 mypy hook once flipped); test; coverage.
**Risks & rollback** — A Protocol signature change risks breaking the runtime `isinstance` (Python checks `iscoroutinefunction` for Protocol members — see the existing docstring note at `restgdf/_client/_protocols.py:33-40`); keep `get`/`post` as non-async `def`. Rollback = revert `_protocols.py` and the `featurelayer.py` annotation together. Anti-rec carried: no global strict flip; verify against real stubs before claiming resolution.

---

### W5-10 · Fix the union-attr bug in _models/_drift.py
**Audit refs:** TYPING-03 · **Severity:** low · **Effort:** S · **Milestone:** M2
**Depends:** W1-2 · **Blocks:** —
**Split-ownership:** — (shares file `_drift.py` with W5-13 — serialize)
**Scope** — In: narrow `info.validation_alias` with `isinstance(choices, AliasChoices)` in `_known_keys`, replacing the broad try/except. Out-of-scope: do NOT land this as a drive-by before W1-2 — it is invisible in CI until the gate sees pydantic; do NOT touch the drift dedup logic (that is W5-13).
**Spec**
1. `_known_keys` does `choices = info.validation_alias` (verified: `restgdf/_models/_drift.py:82`), then `for choice in choices.choices:` (verified: `restgdf/_models/_drift.py:85`) wrapped in `try/except AttributeError: pass` (verified: `restgdf/_models/_drift.py:84,88-89`). `validation_alias` has pydantic type `str | AliasPath | AliasChoices | None`; only `AliasChoices` has `.choices`, so mypy (deps present) reports `union-attr` for the `str`/`AliasPath` arms.
2. `from pydantic import AliasChoices` (pydantic is already a hard dep — light-core safe; `BaseModel`/`ConfigDict`/`ValidationError` already imported at `restgdf/_models/_drift.py:27`).
3. Replace the try/except with an explicit narrow:
   ```
   choices = info.validation_alias
   if isinstance(choices, AliasChoices):
       for choice in choices.choices:
           if isinstance(choice, str):
               names.add(choice)
   ```
4. This module is inside the `restgdf._models.*` strict override (verified: `pyproject.toml:200` lists `"restgdf._models.*"` in a per-module override) so the soundness fix matters for the strict tier once W1-2 makes the gate real.
5. This fix is INVISIBLE in CI until W1-2 lands — sequence accordingly; do not claim a green-diff signal before then.
**Acceptance criteria**
- [ ] Under deps-present mypy, `restgdf/_models/_drift.py:85` no longer reports `union-attr`.
- [ ] Runtime behavior unchanged: `_known_keys` still collects alias-choice names; existing `test_models_primitives.py` drift/alias tests stay green.
- [ ] The broad `try/except AttributeError` is removed (replaced by the `isinstance` narrow).
**Validation** — lint (mypy via W1-2 hook); single `.\.venv\Scripts\python.exe -m pytest tests/test_models_primitives.py`; test; coverage.
**Risks & rollback** — If a future pydantic changes `AliasChoices.choices`, the `isinstance` narrow degrades gracefully (skips). Rollback = restore the try/except. Anti-rec: do not silence with `# type: ignore`.

---

### W5-11 · Fix the misleading list[FieldSpec] annotation in _metadata
**Audit refs:** TYPING-05 · **Severity:** low · **Effort:** S · **Milestone:** M2
**Depends:** W1-2 · **Blocks:** —
**Split-ownership:** — (shares file `_metadata.py` with W5-4 — serialize)
**Scope** — In: correct the `list[FieldSpec]` annotation in `_field_rows` to `list[dict[str, Any]]` in `restgdf/utils/_metadata.py`. Out-of-scope: do NOT switch to attribute access (`f.name`/`f.type`) on `LayerMetadata.fields` — `_as_dict()` calls `model_dump(by_alias=True, exclude_none=True)` so `fields` is already a list of plain dicts and `f.name` would `AttributeError` at runtime.
**Spec**
1. `_field_rows` annotates `fields: list[FieldSpec] = layer_metadata.get("fields") or []` (verified: `restgdf/utils/_metadata.py:156`) then indexes `f["name"]`/`f["type"]` (verified: `restgdf/utils/_metadata.py:157`). But `layer_metadata` was just passed through `_as_dict()` (verified call at `restgdf/utils/_metadata.py:155`; `_as_dict -> dict` signature verified at `restgdf/utils/_metadata.py:55,62-64`), so `fields` is really `list[dict]`. mypy reports `Value of type "FieldSpec" is not indexable [index]`.
2. Change the annotation to `fields: list[dict[str, Any]]` (`Any` is already imported via `from typing import TYPE_CHECKING, Any, Union` — verified `restgdf/utils/_metadata.py:11`). This silences the `[index]` error while keeping the dict-indexing code unchanged. The `or []` fallback is covered cleanly by `list[dict[str, Any]]`.
3. ANTI-RECOMMENDATION: do NOT switch to `f.name`/`f.type` — bypassing `_as_dict` would break the documented case-insensitive extras-preservation that `get_name`/`get_max_record_count` rely on (they regex-scan dict keys, verified `restgdf/utils/_metadata.py:124-141`).
4. Optionally add the same annotation to `get_fields` (verified currently unannotated at `restgdf/utils/_metadata.py:147`) for consistency — clarification only, not a correction.
5. COORDINATION: W5-4 also edits `_field_rows`/`get_fields` (the permissive-tier guard). If W5-4 lands first and routes both through a guarded helper, apply this annotation to whatever the final shared iterator is. Serialize after W5-4 to avoid churn.
**Acceptance criteria**
- [ ] Under deps-present mypy, `restgdf/utils/_metadata.py:157` no longer reports `[index]`.
- [ ] Annotation reads `list[dict[str, Any]]` (no `# type: ignore`).
- [ ] Runtime behavior unchanged; metadata/fields tests stay green.
**Validation** — lint (mypy via W1-2); single `.\.venv\Scripts\python.exe -m pytest -k metadata`; test.
**Risks & rollback** — None material (annotation-only). Rollback = restore `list[FieldSpec]`. Anti-rec carried: no attribute-access rewrite.

---

### W5-2 · Stop the instance datadict clobbering stats-only query flags
**Audit refs:** API-01 · **Severity:** medium · **Effort:** M · **Milestone:** M3
**Depends:** — · **Blocks:** —
**Split-ownership:** — (shares file `_stats.py` with W5-3 — serialize; W5-2 first)
**Scope** — In: route `get_value_counts` and `nested_count` through a conservative merge that forwards only `where`+`token` from caller `data`, mirroring the already-correct `get_unique_values` path; the merge helper lives in `restgdf/_client/request.py`. Out-of-scope: do NOT take the naive `{**data, <stats flags>}` approach — see anti-rec.
**Spec**
1. `get_value_counts` builds `data = {"where": "1=1", ..., "returnGeometry": False, "outFields": field, "outStatistics": statstr, "groupByFieldsForStatistics": field, **data}` with caller `data` spread LAST (verified: `restgdf/utils/_stats.py:118-126`). Same pattern in `nested_count` (verified: `restgdf/utils/_stats.py:166-174`). Because `FeatureLayer` always populates `data` via `self.datadict = default_data(...)` (verified: `restgdf/featurelayer/featurelayer.py:141`) → `self.kwargs["data"] = self.datadict` (verified: `restgdf/featurelayer/featurelayer.py:150`) → forwarded via `**self.kwargs` (verified: `restgdf/featurelayer/featurelayer.py:630,666`), the caller `data` resets `returnGeometry` to `True` and `outFields` to `*`, overriding the stats flags.
2. The correct path is the PROTECTIVE merge already used by `get_unique_values` via `build_conservative_query_data` (verified: `restgdf/utils/_stats.py:60`; helper at `restgdf/_client/request.py:16-49` forwards ONLY `where`+`token`).
3. Implement a stats-specific conservative merge. Either reuse `build_conservative_query_data(base=<stats flags incl. outStatistics/groupBy/returnGeometry=False/outFields=field>, caller_data=kwargs.get("data"))` — which forwards only `where`+`token` and lets the base stats flags win — or add a sibling helper in `restgdf/_client/request.py` if the stats body needs `outStatistics`/`groupByFieldsForStatistics` preserved exactly. Note the `build_conservative_query_data` quirk (verified docstring `restgdf/_client/request.py:36-41`): a truthy `caller_data` without `where` resets `where` to `"1=1"`. Since `FeatureLayer` always sets `datadict["where"] = self.wherestr` (verified: `restgdf/featurelayer/featurelayer.py:142`), the instance `where` IS present in caller_data and is preserved — confirm this in the integration test.
4. ANTI-RECOMMENDATION: do NOT use `{**data, <stats flags>}` — that lets the hardcoded `"where": "1=1"` in the stats base clobber the instance WHERE clause (`datadict["where"] = self.wherestr`), silently dropping the user's filter from `get_value_counts`/`get_nested_count` on a refined layer. The conservative-merge route is the ONLY fix that preserves `where` while neutralizing `returnGeometry`/`outFields`/`returnCountOnly`.
5. Mirror the `get_feature_count` contract asserted in `tests/test_characterization.py:64,74-86` (that path is owned by W1; do not edit it here, just match the body shape).
**Acceptance criteria**
- [ ] Red-first: an integration test driving `FeatureLayer.get_value_counts()` AND `FeatureLayer.get_nested_count()` (NOT the bare module helper) through a fake session, asserting the outgoing body has `returnGeometry` false, `outFields=<field>`, no `returnCountOnly`, AND the instance `where` preserved — confirmed FAILING on `main` (current bodies send `returnGeometry=True`/`outFields=*`). The current `test_FeatureLayer.py:536-566` mocks the helper entirely and never exercises this seam, so a new test is required.
- [ ] After fix: both stats helpers emit conservative bodies; `where` survives on a refined layer.
- [ ] `nested_count` change coordinated with W5-3 (arity guard) on the same file.
**Validation** — lint; single `.\.venv\Scripts\python.exe -m pytest -k "value_counts or nested_count or stats"`; test; coverage.
**Risks & rollback** — Servers that previously tolerated `outFields=*` with `outStatistics` see a narrower body (intended, fixes the failure case). Rollback = revert `_stats.py` (+ any new `request.py` helper). Anti-rec carried: never the `{**data, flags}` route.

---

### W5-3 · Enforce nested_count arity (>= 2 fields)
**Audit refs:** API-04 · **Severity:** low · **Effort:** S · **Milestone:** M3
**Depends:** — · **Blocks:** —
**Split-ownership:** — (shares `_stats.py` with W5-2 and `featurelayer.py` with several — serialize after W5-2)
**Scope** — In: validate arity in BOTH `FeatureLayer.get_nested_count` and the `nested_count` helper, and align the docstring. Out-of-scope: do NOT silently keep the two-field-only logic while leaving the "two or more" docstring (that is the actual finding). The `== f"{f}_count"` exact-match suggestion is cosmetic — skip it.
**Spec**
1. `nested_count` post-processing hardcodes `fields[0]`/`fields[1]`: `dropcol = [c for c in cc.columns if c.startswith(f"{fields[0]}_count")][0]` and `rencol = [... f"{fields[1]}_count" ...][0]` then sorts by `[fields[0], "Count"]` (verified: `restgdf/utils/_stats.py:192-197`). `FeatureLayer.get_nested_count` docstring says "Two or more field names to cross-tabulate" (verified: `restgdf/featurelayer/featurelayer.py:643`) and only validates membership via `any(field not in self.fields ...)` (verified: `restgdf/featurelayer/featurelayer.py:657`) — never `len(fields)>=2`. With a single-element tuple, `fields[1]` raises `IndexError` deep in the helper; with 3+ fields a redundant `*_count` column lingers and the sort is incomplete.
2. Simplest sound fix — restrict to EXACTLY two fields:
   - In `FeatureLayer.get_nested_count` (verified entry `restgdf/featurelayer/featurelayer.py:634`): add `if len(fields) != 2: raise ValueError(...)` (or a clear `FieldDoesNotExistError`-style error) before the membership check.
   - In the `nested_count` helper (verified `restgdf/utils/_stats.py:147`): add the same guard — REQUIRED because the helper is a public re-exported name (verified re-export `restgdf/utils/getinfo.py:51` and `__all__` entry `restgdf/utils/getinfo.py:84`), so a direct caller can still hit `fields[1]` `IndexError`.
   - Amend the docstring `restgdf/featurelayer/featurelayer.py:643` from "Two or more field names" to "Exactly two field names" — otherwise the fix merely relocates the doc/impl divergence.
3. (Alternative if 3+ cross-tabs are wanted) generalize the post-processing: `count_cols = [c for c in cc.columns if c.endswith("_count")]`, keep one as `Count`, drop the rest, sort by `[*fields, "Count"]`. **Decision** — see below; default is the exact-two restriction (simpler, matches the only-ever-exercised path).
4. Note the audit caveat: the "silently wrong cross-tab" claim for 3+ fields is overstated (every `*_count` equals the group row count, so values/rows are correct) — the real defects are the leftover redundant `*_count` column and incomplete sort. This does not change the fix; just frames severity.
**Acceptance criteria**
- [ ] Red-first: a test calling `get_nested_count(("A",))` (single-element) — confirmed raising `IndexError` (unclear) on `main`; after fix raises a clear `ValueError`/`FieldDoesNotExistError`.
- [ ] A test calling the bare `nested_count(url, ("A",), session)` helper also raises the clear validation error (not `IndexError`).
- [ ] Docstring reads "Exactly two field names" (assuming the default decision).
- [ ] Existing two-field nested-count tests stay green.
**Validation** — lint; single `.\.venv\Scripts\python.exe -m pytest -k nested_count`; test; coverage.
**Risks & rollback** — Restricting to exactly two is a (documented) tightening; a caller relying on undefined 3+ behavior would now get a clear error (acceptable). Rollback = revert the guards and docstring. Anti-rec carried: never keep two-field logic under a "two or more" docstring.
**Decision required** — see Decisions section (exact-two vs generalize to N).

---

### W5-6 · Make resolve_domains robust to malformed domain metadata
**Audit refs:** ADAPTERS-03 · **Severity:** low · **Effort:** S · **Milestone:** M3
**Depends:** — · **Blocks:** —
**Split-ownership:** —
**Scope** — In: add an `isinstance(domain, dict)` guard and a stricter coded-value comprehension in `restgdf/adapters/pandas.py`, plus regression tests. Out-of-scope: do NOT use `cv.get("name")` — see CRITICAL anti-rec.
**Spec**
1. `resolve_domains` checks only `if not name or not domain or name not in df.columns` (verified: `restgdf/adapters/pandas.py:98`) then calls `domain.get("type")` (verified: `restgdf/adapters/pandas.py:100`) — a non-dict (e.g. `str`) `domain` raises `AttributeError`. The map build `mapping = {cv["code"]: cv["name"] for cv in coded_values if "code" in cv}` (verified: `restgdf/adapters/pandas.py:105`) guards only `"code" in cv`, so a `codedValue` entry with `code` but no `name` raises `KeyError`.
2. Add `if not isinstance(domain, dict): continue` BEFORE `domain.get("type")`.
3. Build the map only from well-formed entries: `mapping = {cv["code"]: cv["name"] for cv in coded_values if isinstance(cv, dict) and "code" in cv and "name" in cv}`.
4. CRITICAL ANTI-RECOMMENDATION: do NOT use `cv.get("name")` — it returns `None` for a name-less coded value, mapping that code to `None` and SILENTLY replacing the real code with `None`/NaN via `Series.replace` (verified replace usage `restgdf/adapters/pandas.py:113-116`) — a silent data-corruption far worse than the current loud `KeyError`. The `"name" in cv` membership guard is REQUIRED so unresolvable codes are left untouched (consistent with the documented pass-through contract).
5. The `isinstance(domain)` guard aligns with `FieldSpec.domain` being typed `dict | None`; touches no light-core boundary or back-compat seam.
**Acceptance criteria**
- [ ] Red-first: a test feeding `resolve_domains(df, fields)` where one field's `domain` is a `str` (confirmed `AttributeError` on `main`) and another field's `codedValues` entry has `code` but no `name` (confirmed `KeyError` on `main`).
- [ ] After fix: malformed entries are skipped; the resolvable subset is applied; name-less codes pass through unchanged (NOT mapped to NaN).
- [ ] New tests added to `tests/test_resolve_domains.py` alongside the existing standalone-helper tests (`test_resolve_domains_helper_with_dict_fields` etc.).
**Validation** — lint; single `.\.venv\Scripts\python.exe -m pytest tests/test_resolve_domains.py`; test; coverage.
**Risks & rollback** — None material. Rollback = revert the two guards. Anti-rec carried: never `cv.get("name")`.

---

### W5-13 · Scope schema-drift dedup per service context
**Audit refs:** TELEMETRY-02 · **Severity:** low · **Effort:** M · **Milestone:** M3
**Depends:** — · **Blocks:** —
**Split-ownership:** Code part (drift dedup-key/message threading in `restgdf/_models/_drift.py`) owned here; the `MIGRATION.md` drift-dedup-scope prose half of TELEMETRY-02 is owned by **W6-4**. (Intra-W5: shares `_drift.py` with W5-10 — serialize.)
**Scope** — In: thread `context` into the drift LOG MESSAGE/record so the first emission is attributable, while LEAVING the dedup key context-free to preserve anti-spam; tests in `tests/test_models_primitives.py`. Out-of-scope: do NOT blindly add the full per-layer/per-service URL `context` to `_DriftKey` (regresses the documented anti-spam guarantee). MIGRATION.md prose is W6-4, not this item.
**Spec**
1. `_log_drift` dedups on `key: _DriftKey = (model_name, path, kind, sample_type)` (verified: `restgdf/_models/_drift.py:109`) where `model_name` is just the class name; `_seen_drift` is a module-level set (verified: `restgdf/_models/_drift.py:34`). `_parse_response` always calls with `model_name=model_cls.__name__` (verified: `restgdf/_models/_drift.py:205,227,259`). Directory crawl validates every service with the same `LayerMetadata` class, so service B's drift is silenced once service A logged the same tuple.
2. The MORE MATERIAL gap is that the drift log MESSAGE omits `context` entirely (verified: `_log_drift` logs model_name/path/kind/sample_type/sample at `restgdf/_models/_drift.py:113-122`, never the URL), so even the first non-deduped occurrence is not attributable.
3. Prefer option (1): thread `context` into the log record. Add a `context` parameter to `_log_drift` (passed by `_parse_response`, which already has `context` in scope — verified signature `restgdf/_models/_drift.py:156-161`), and include it in the format string or as `extra={"context": context}`. LEAVE the dedup key context-free (do NOT add it to `_DriftKey`) to preserve the anti-spam guarantee.
4. ANTI-RECOMMENDATION: adding the raw per-layer URL `context` to `_DriftKey` would make a single drifty server with 500 layers emit 500 identical records instead of 1 (every layer URL is distinct — `getinfo.py:245`/`_query.py:80`). The `FieldSetDriftObserver[{context}]` pattern works only because ITS context is a coarse layer/service label (verified: `restgdf/_models/_drift.py:317`), not a per-layer URL — do not generalize from it.
5. If per-service dedup is genuinely wanted (alternative, heavier), key on a coarse SERVICE-ROOT derived from `context` (not the raw URL) and document the new behavior — but the default is message-attribution only.
**Acceptance criteria**
- [ ] Red-first: a test asserting that two distinct service contexts producing the same `(model, field, kind, type)` tuple still emit attributable records (the `context` appears in each record) — and that repeated identical drift on the SAME context still dedups to one.
- [ ] After fix: the first drift emission includes the originating `context` in the message/record.
- [ ] `_DriftKey` remains 4-tuple (no context component) — anti-spam preserved.
- [ ] Tests added/updated in `tests/test_models_primitives.py` (coordinate with the `_reset_drift_cache` autouse fixture, verified `tests/test_models_primitives.py:43-45`).
- [ ] Doc-sync flagged for W6-4 (MIGRATION.md drift-scope prose) — not edited here.
**Validation** — lint; single `.\.venv\Scripts\python.exe -m pytest tests/test_models_primitives.py`; test; coverage.
**Risks & rollback** — Adding a positional/kw arg to `_log_drift` touches all call sites in `_drift.py` (including `FieldSetDriftObserver` — give it a sensible default). Rollback = revert `_drift.py` message threading. Anti-rec carried: never add URL context to the dedup key.

---

### W5-14 · FeatureLayer/Directory from_config construction (consume part)
**Audit refs:** CONFIG-02, CONFIG-03 · **Severity:** medium · **Effort:** M · **Milestone:** M3
**Depends:** W3-3, W3-4 · **Blocks:** —
**Split-ownership:** SPLIT — this is the FeatureLayer-construction consume seam. The CONFIG-02 (AuthConfig) config-exposure part is **W3-3**; the CONFIG-03 (explicit-`Config`-instance precedence) config part is **W3-4**; the token consume side of AuthConfig is **W2-11**. This item owns ONLY `restgdf/featurelayer/featurelayer.py`.
**Scope** — In: implement the FeatureLayer-side construction seam for whatever W3-3/W3-4 decide (the consume half). Out-of-scope: do NOT naively add `config=` to `FeatureLayer.from_url` as a quick fix that threads a global `Config` through transport/streaming/telemetry — that is a net-new feature, not a bug fix (CONFIG-03 anti-rec). Do NOT make `ArcGISTokenSession.__post_init__` read `get_config().auth` implicitly (CONFIG-02 anti-rec) — that is W2-11's concern and is opt-in only. The actual config decisions live in W3.
**Spec**
1. This item is GATED on the W3 decisions (W3-3: full AuthConfig wiring vs minimal; W3-4: implement explicit-`Config` precedence vs delete the doc claim). Do NOT begin the FeatureLayer seam until those decisions land — the shape of this item depends entirely on them.
2. CONFIG-02 context: `FeatureLayer.__init__`/`from_url` accept no `config`/`auth`/`AuthConfig` parameter (verified: `restgdf/featurelayer/featurelayer.py:91-98,212`); `AuthConfig` is never read by any token session. If W3-3 chooses the opt-in classmethod route (audit-preferred: `ArcGISTokenSession.from_config(...)`), the FeatureLayer-side seam is at most a thin `FeatureLayer.from_config(...)` / a documented way to pass a pre-built session — NOT an implicit default.
3. CONFIG-03 context: there is no mechanism to pass a `Config(...)` instance explicitly; the request layer always calls the global `get_config()` (verified consumers per audit: `restgdf/utils/_http.py`, `utils/getgdf.py`, `utils/getinfo.py`, `utils/crawl.py`, `telemetry/_spans.py`). If W3-4 chooses the DOC-FIX route (audit-preferred), this item shrinks to NOTHING on the FeatureLayer side (no constructor param) and the ARCHITECTURE.md prose fix is W6-3 — verify and close W5-14 as a no-op with a note. If W3-4 chooses to IMPLEMENT precedence, this item threads the injected `Config`/`TokenSessionConfig` into the FeatureLayer constructor without disturbing the light-core import boundary.
4. The `TokenSessionConfig` injection (`ArcGISTokenSession(config=...)`) already works and is intentionally session-scoped — do NOT conflate it with global Config level-2.
**Acceptance criteria**
- [ ] Construction seam matches the W3-3/W3-4 decision exactly (no divergence between code and the W6 doc prose).
- [ ] If W3-4 chose doc-fix: W5-14 closes as a verified no-op with a recorded note; no `config=` param added to `FeatureLayer`.
- [ ] If implemented: red-first test demonstrating an explicit `Config`/auth instance is honored at construction (was silently ignored on `main`).
- [ ] No implicit `get_config().auth` default added to `ArcGISTokenSession.__post_init__` (W2-11 owns the token consume, opt-in only).
**Validation** — lint; single `.\.venv\Scripts\python.exe -m pytest -k "featurelayer or config"`; test; coverage; compat (`.\.venv\Scripts\python.exe -m pytest -q tests/test_compat.py`).
**Risks & rollback** — Threading a `Config` instance risks the light-core boundary and is the highest-risk W5 item if the implement-route is chosen — keep it scoped, prefer the audit-preferred doc-fix routes in W3. Rollback = revert the FeatureLayer constructor change. Anti-recs carried: no implicit global-config defaulting; no naive `config=` threading.
**Decision required** — surfaced; inherits the W3-3/W3-4 decisions (this item cannot self-decide).

---

### W5-5 · Fix the self-contradicting geopandas adapter docstrings
**Audit refs:** ADAPTERS-02 · **Severity:** low · **Effort:** S · **Milestone:** M4
**Depends:** — · **Blocks:** —
**Split-ownership:** —
**Scope** — In: docstring-only edits in `restgdf/adapters/geopandas.py`. Out-of-scope: do NOT implement the optional "raise `OutputConversionError` instead of the bare geopandas `TypeError`" try/except (the TypeError text is geopandas-version-specific, it adds catch logic to a deliberately thin adapter, and risks masking legitimate caller errors); do NOT implement ArcGIS-dict-to-shapely conversion here (deferred to BL-27/BL-28/BL-35).
**Spec**
1. `rows_to_geodataframe` Parameters names `iter_rows`/`features_to_rows` as the typical feed while requiring shapely-compatible geometry (verified: `restgdf/adapters/geopandas.py:47-52`). `arows_to_geodataframe` Parameters names `stream_rows`/`iter_rows` (verified: `restgdf/adapters/geopandas.py:106-109`). But `stream_rows`/`iter_rows` yield the RAW ArcGIS geometry dict via `_feature_to_row_dict` (verified usage in `FeatureLayer.stream_rows` at `restgdf/featurelayer/featurelayer.py:461`; helper at `restgdf/utils/getgdf.py:170-171` per audit), which raises `TypeError` here.
2. Edit (1) — both `rows_to_geodataframe` (lines 47-52) and `arows_to_geodataframe` (lines 106-109) Parameters: keep the "must be shapely-compatible" requirement but stop naming `stream_rows`/`iter_rows` as "typical" without a caveat; add a one-line note that ArcGIS geometry dicts must be converted to shapely first, pointing to `FeatureLayer.get_gdf` / `stream_gdf_chunks` (or `restgdf.adapters.stream.iter_gdf_chunks`) for the batteries-included path.
3. Edit (2) — the `arows_to_geodataframe` See Also at `restgdf/adapters/geopandas.py:126-128` currently reads "Equivalent to `await arows_to_geodataframe(layer.stream_rows())` with geometry normalization ... handled for you" (verified). This is doubly wrong: that idiom CRASHES, and `get_gdf` is actually implemented via `get_sub_gdf -> read_file(..., engine="pyogrio")` over the server's ESRIJSON/GeoJSON response (not over `stream_rows`). Reword to "High-level accessor that returns the full layer as a single GeoDataFrame" — matching the already-correct `rows_to_geodataframe` See Also (verified: `restgdf/adapters/geopandas.py:78-83`).
**Acceptance criteria**
- [ ] Both Parameters sections no longer present `stream_rows`/`iter_rows` as a drop-in feed without the shapely-conversion caveat.
- [ ] The `arows_to_geodataframe` See Also no longer claims `get_gdf` is equivalent to the (crashing) `arows_to_geodataframe(layer.stream_rows())` idiom.
- [ ] docs build clean (Sphinx napoleon parses the edited docstrings).
**Validation** — lint; docs (`.\.venv\Scripts\python.exe -m sphinx -n -W --keep-going -b html docs docs/_build/html`); test (docstrings don't change behavior, confirm no doctest breakage).
**Risks & rollback** — Docs-only; near-zero risk. Rollback = revert the docstring edits. Anti-rec carried: no `try/except` TypeError remap, no geometry normalization.

## Decisions required

(Surfaced for the maintainer; recommended defaults inline. The two W3-inherited decisions on W5-14 are listed because W5-14 cannot resolve them itself.)
