# 04 — Pagination & streaming data path

> Workstream of the restgdf remediation plan · audit pinned `4673b08` · 2026-06-13

## Goal

Close the silent-data-loss gaps on the flagship `get_gdf()` / streaming surface so that a truncated server response is never returned as if complete. Landing this workstream makes the GeoDataFrame path detect `exceededTransferLimit` and raise (matching the raw-feature engine), makes multi-page offset/count pagination deterministic by defaulting `orderByFields` to the resolved OID, hardens the `on_truncation='split'` escape hatch so it works on the large layers it exists for, and completes the `verify_ssl`/`user_agent` wiring at the getgdf-owned session seam plus the deferred R-71 type widening. These are correctness fixes on the single most common geo call, not polish.

## Collision domain

This workstream is single-writer on:

- `restgdf/utils/getgdf.py` — touched by **W4-1, W4-2, W4-3, W4-4, W4-5, W4-6** (the hot file of this workstream; all five getgdf items must serialize against each other).
- `restgdf/utils/_pagination.py` — touched by **W4-2** only.
- `restgdf/utils/utils.py` — touched by **W4-3** only.

`getgdf.py` is the workstream's internal hot file: no other workstream owns it, but every getgdf-touching item here edits overlapping regions (`get_sub_gdf`, `get_query_data_batches`, `_resolve_page`, `get_gdf`), so they cannot run in parallel with each other.

Cross-workstream coupling (no shared file, but ordering edges):

- **W4-5** is the getgdf application seam (part C) of the `verify_ssl`/`user_agent` source-of-truth split. The source of truth (`TransportConfig`) is owned by **W3-1** in `restgdf/_config.py`/`_models/_settings.py`; the token/`_http` seams (parts A·B) are **W2-10**. W4 writes none of those files.
- **W4-1** and **W4-2** feed doc-side items in W6 (README/streaming.md/configuration.rst). W4 writes none of those docs; it hands off the behavior facts.

## Sequencing & parallelization

Milestone order for this workstream: **M2** (W4-1, W4-2, W4-5, W4-6) → **M3** (W4-3, W4-4).

Because all six items write `getgdf.py`, they **serialize on that file**; treat the workstream as a single ordered lane:

1. **W4-6** (TYPING-04) — depends on `W1-2` (mypy gate un-defanged) and on `W5-9` (TYPING-02, the Protocol fix) landing first; it is a one-line annotation widen. Land it early in the getgdf lane so later items inherit the corrected `session: AsyncHTTPSession | None` signature. **Do NOT start W4-6 before W5-9 lands** — widening `get_gdf` while the Protocol still rejects `ClientSession` only relocates the mypy error to line 510 (`session = session or ClientSession()`).
2. **W4-5** (CONFIG-01/AUTH-03 part C) — depends on **W3-1** landing the `TransportConfig` source of truth. Edits the session-creation seam in `get_gdf` (and is adjacent to W4-6's signature edit on the same function), so sequence W4-6 then W4-5 (or fold both into one getgdf touch).
3. **W4-1** (PAGINATION-01) — no cross-WS dependency; edits `get_sub_gdf`. Highest-severity correctness fix; land as soon as the getgdf lane is free.
4. **W4-2** (PAGINATION-02) — no cross-WS dependency; edits `get_query_data_batches` (and reads `_pagination.py`). Independent region from W4-1 but same file, so serialize.
5. **W4-3** (PAGINATION-03, M3) — edits `_resolve_page` split path + `utils.py`. `utils.py` is disjoint from `getgdf.py`, but the `_resolve_page` edit shares the file.
6. **W4-4** (ASYNC-03, M3) — documentation-leaning fix in `getgdf.py`/featurelayer docstring; the audit's accepted resolution is the doc fix, not a code fix (see item).

W4-3 and W4-4 (both M3, both touch the split path / `_resolve_page` region) should be done back-to-back by the same writer to avoid conflicting edits to the bisection code.

**Cross-workstream `Depends` edges:**

- **W4-5 blocks on W3-1** landing the `TransportConfig.user_agent`/`verify_ssl` source of truth in `_config.py`. Coordinate with **W2-10** (token/`_http` seam) so all three verify_ssl seams (A=config, B=token/_http, C=getgdf) agree on one source.
- **W4-6 blocks on W1-2** (mypy gate must actually see aiohttp/pydantic) **and W5-9** (the Protocol must structurally accept `ClientSession` before `get_gdf` can be widened).
- **W6-6 blocks on W4-1** (README truncation note) and **W6-7 blocks on W4-1** (streaming.md / configuration.rst recipes). W4 supplies the behavior; W6 writes the prose.

## Work items

### W4-6 · Fix get_gdf session annotation to the AsyncHTTPSession contract

**Audit refs:** TYPING-04 · **Severity:** low · **Effort:** S · **Milestone:** M2
**Depends:** W1-2, W5-9 · **Blocks:** — (but unblocks a clean mypy run over `restgdf.utils`)
**Split-ownership:** — (TYPING-04 is wholly owned here; the Protocol root cause TYPING-02 is W5-9).
**Scope** — In: widen the `get_gdf` parameter annotation in `restgdf/utils/getgdf.py` from `ClientSession | None` to `AsyncHTTPSession | None`, completing the R-71 widening that missed this function. Out-of-scope: editing the `AsyncHTTPSession` Protocol itself (that is W5-9 / `_protocols.py`); adding any `# type: ignore`; reverting `gdf_by_concat` back to `ClientSession` (anti-recommendation — un-does R-71 and re-fragments the transport seam).

**Spec**

1. In `restgdf/utils/getgdf.py`, change the signature of `get_gdf` from `session: ClientSession | None = None` (verified: `restgdf/utils/getgdf.py:503`) to `session: AsyncHTTPSession | None = None`. `AsyncHTTPSession` is already imported at the top (verified: `restgdf/utils/getgdf.py:15`); `gdf_by_concat` already takes `session: AsyncHTTPSession` (verified: `restgdf/utils/getgdf.py:491`), so this makes line 522 (`gdf_by_concat(url, session, ...)`) and the `FeatureLayer.session` → `get_gdf` call (featurelayer.py:300 per audit) type-consistent in both directions.
2. The body keeps `session = session or ClientSession()` (verified: `restgdf/utils/getgdf.py:510`). This line is only mypy-clean once W5-9 has relaxed the Protocol so `ClientSession` is assignable to `AsyncHTTPSession`; **do NOT land this item before W5-9**, or the error merely relocates from line 522 to line 510 (audit TYPING-04 recommendation, explicit ordering).
3. Do NOT silence with `# type: ignore`; the fix must be the annotation, not a suppression (anti-recommendation).

**Acceptance criteria**

- [ ] `get_gdf`'s `session` parameter is annotated `AsyncHTTPSession | None` (no `ClientSession` annotation remains on that param).
- [ ] Deps-present mypy reports no `arg-type` error at the `get_gdf`→`gdf_by_concat` call site nor at the `FeatureLayer.get_gdf`→`get_gdf` call site (the two TYPING-04 error locations).
- [ ] No new `# type: ignore` introduced in `getgdf.py`.
- [ ] W5-9 (Protocol fix) is confirmed merged before this lands (record the commit in the PR description).

**Validation** — lint (the un-defanged mypy hook from W1-2 must now see aiohttp/pydantic); test; coverage.

**Risks & rollback** — Failure mode: landing ahead of W5-9 produces a fresh mypy error at `getgdf.py:510`. Rollback: revert the one-line annotation change (purely a type annotation; zero runtime effect). Anti-recommendations preserved: no `type: ignore`, no revert of `gdf_by_concat` to `ClientSession`.

---

### W4-5 · Build the get_gdf bare session with the configured ssl connector (verify_ssl part C)

**Audit refs:** CONFIG-01, AUTH-03 · **Severity:** high · **Effort:** S · **Milestone:** M2
**Depends:** W3-1 · **Blocks:** — (doc-side W6-4 MIGRATION verify_ssl note depends on the consolidated verify_ssl wiring landing)
**Split-ownership:** This item owns ONLY the getgdf-owned bare-session creation seam (part C). The `TransportConfig.user_agent`/`verify_ssl` **source of truth** is owned by **W3-1** (`restgdf/_config.py`, `restgdf/_models/_settings.py`). The token-refresh / `_http` seams — `default_headers()` UA injection and `token._call_with_auth_retry` ssl forwarding (parts A·B) — are owned by **W2-10** (`restgdf/utils/_http.py`, `restgdf/utils/token.py`). W4-5 writes neither.
**Scope** — In: build the bare session created inside `get_gdf` with a `TCPConnector(ssl=get_config().transport.verify_ssl)` so a configured `verify_ssl=False` is honored on the library-owned data-request path. Out-of-scope: blanket-injecting `ssl=` into every `_arcgis_request` kwargs (anti-recommendation — conflicts with caller connectors and aiohttp per-request-vs-connector TLS interplay is fragile); touching caller-supplied sessions (their connector owns TLS); the UA `default_headers()` change (that is `_http.py`, owned by W2-10); deciding the single source of truth for verify_ssl (W3-1 decision).

**Spec**

1. In `restgdf/utils/getgdf.py`, the bare-session branch currently reads `session = session or ClientSession()` (verified: `restgdf/utils/getgdf.py:510`), with no connector and no TLS policy from config. Only build a configured connector when `get_gdf` **owns** the session — `owns_session = session is None` is already computed (verified: `restgdf/utils/getgdf.py:509`). Change the construction so that when `owns_session` is true, the session is built as `ClientSession(connector=TCPConnector(ssl=get_config().transport.verify_ssl))`. `get_config` is already imported (verified: `restgdf/utils/getgdf.py:16`); add the `TCPConnector` import alongside the existing `from aiohttp import ClientSession` (verified: `restgdf/utils/getgdf.py:13`).
2. Read `verify_ssl` from the W3-1 source of truth. Per CONFIG-01 §3 / AUTH-03 §3, W3-1 reconciles the two disconnected `verify_ssl` fields (`TransportConfig.verify_ssl` at `_config.py:78` — verified: `restgdf/_config.py:78` — vs `TokenSessionConfig.verify_ssl`) into one knob. This item consumes `get_config().transport.verify_ssl`; if W3-1's decision renames or relocates the field, follow W3-1's resolved attribute path. **Do NOT hardcode a second source** — defer to whatever W3-1 lands.
3. Leave caller-supplied sessions untouched (`owns_session is False` → use the session as-is). The caller's connector owns its TLS policy (anti-recommendation: do not override a caller connector's SSL).
4. Do NOT add `ssl=` to the `gdf_by_concat(url, session, data=datadict, **kwargs)` call (verified: `restgdf/utils/getgdf.py:522`) — the connector on the owned session carries the policy; per-leaf `ssl=` injection is the rejected naive fix.

**Acceptance criteria**

- [ ] When `get_gdf` is called with `session=None` and `RESTGDF_TRANSPORT_VERIFY_SSL=false` (or `TransportConfig(verify_ssl=False)` via the W3-1 source), the constructed session's connector carries `ssl=False`.
- [ ] Red-state test (behavior change): a test that asserts `get_gdf(url)` with a configured `verify_ssl=False` builds a `TCPConnector(ssl=False)` — mirroring the existing token-only `tests/test_verify_ssl_plumbing.py` pattern (verified: `tests/test_verify_ssl_plumbing.py:53-82`). The test must fail against the current tree (no connector built) before the fix.
- [ ] A caller-supplied session is passed through unchanged (no connector override) — assert the owned-vs-supplied branch.
- [ ] W3-1 confirmed merged; the consumed attribute path matches W3-1's resolved source of truth.
- [ ] Doc-sync handoff recorded: MIGRATION verify_ssl claim (W6-4) and CHANGELOG line 530-531 (W2-10/W6 scope) note the data-path now honors config verify_ssl.

**Validation** — test; single (`-k verify_ssl` over the new getgdf test); lint; coverage.

**Risks & rollback** — Failure modes: (a) overriding a caller-supplied connector's TLS — guarded by the `owns_session` check; (b) consuming a stale/duplicate verify_ssl field if W3-1's reconciliation lands differently — mitigated by deferring to W3-1's resolved path and confirming merge order. Rollback: revert to `session = session or ClientSession()`. Anti-recommendations preserved: no blanket `ssl=` at every leaf call; no override of caller connectors; do not strip `ssl=` off the token POST to make docs literally true (that is W2-10's surface, but the principle holds — reconcile docs UP to behavior, not down).

---

### W4-1 · Detect exceededTransferLimit in the GeoDataFrame path and raise

**Audit refs:** PAGINATION-01 · **Severity:** high · **Effort:** M · **Milestone:** M2
**Depends:** — · **Blocks:** W6-6 (README truncation note), W6-7 (streaming.md / docs truncation recipes)
**Split-ownership:** — (PAGINATION-01 code is wholly owned here; the doc corrections to `docs/recipes/streaming.md` and `README.md` are W6-7/W6-6).
**Scope** — In: make `get_sub_gdf` parse the response envelope for `exceededTransferLimit` BEFORE/separately from `read_file` and raise by default, matching the raw-feature engine `_get_sub_features`. Out-of-scope: threading the full `on_truncation` (`raise`/`ignore`/`split`) knob set through `chunk_generator`/`get_gdf_list`/`get_gdf` (anti-recommendation — `ARCHITECTURE.md:146-150` and `MIGRATION.md:184-190` deliberately document `stream_gdf_chunks` as the legacy path that does NOT accept those knobs; widening that contract is a separate design change); editing `docs/recipes/streaming.md` / `README.md` prose (handed to W6-7 / W6-6).

**Spec**

1. The flaw: `get_sub_gdf` reads the page straight into geopandas with no envelope inspection — `response = await _arcgis_request(...)` then `sub_gdf = read_file(await response.text(), engine="pyogrio")` then `return sub_gdf` (verified: `restgdf/utils/getgdf.py:323-335`). Contrast the raw-feature engine `_get_sub_features` which raises on truncation: `if envelope.exceeded_transfer_limit: raise PaginationError(...)` (verified: `restgdf/utils/getgdf.py:95-101`). `get_sub_gdf` is consumed only by `get_gdf_list` (verified: `restgdf/utils/getgdf.py:348`) and `chunk_generator` (verified: `restgdf/utils/getgdf.py:415`); neither checks truncation.
2. Implementation hazard (audit-flagged): `get_sub_gdf` requests `f=GeoJSON` or `ESRIJSON` (verified: `restgdf/utils/getgdf.py:317-319`) and consumes `response.text()`. `read_file`/pyogrio **discards** the top-level `exceededTransferLimit` member, so inspect the parsed JSON dict directly — do NOT rely on `read_file` to surface it. Read the body once into text, parse it to a dict (e.g. `json.loads`), inspect the truncation flag, THEN hand the same text to `read_file`. The flag is a top-level member in both ESRIJSON and the Esri-emitted GeoJSON `FeatureCollection` (confirmed by fixture `tests/fixtures/pagination/query_exceeded_transfer_limit_short_page.json` which carries top-level `"exceededTransferLimit": true`).
3. Prefer reusing the existing typed parse: `_parse_response(FeaturesResponse, raw, context=f"{url}/query")` already exposes `envelope.exceeded_transfer_limit` (verified: used at `restgdf/utils/getgdf.py:94-95` and in `_resolve_page` at `restgdf/utils/getgdf.py:638-643`). For ESRIJSON the body IS a FeaturesResponse-shaped dict; for GeoJSON the truncation flag is still top-level so a direct `raw.get("exceededTransferLimit") is True` check is the robust common path across both drivers. Use the direct top-level check to stay format-agnostic, and only parse what is needed.
4. On truncation detected, raise by default. Mirror `_get_sub_features`'s `PaginationError` (verified: `restgdf/utils/getgdf.py:96-101`; signature `PaginationError(message, *, batch_index=None, page_size=None)` verified: `restgdf/errors.py:188-198`) OR `RestgdfResponseError(..., context="exceededTransferLimit")` to mirror `_resolve_page`'s raise default (verified: `restgdf/utils/getgdf.py:671-677`). **Decision** below — recommend `PaginationError` to mirror the sibling geo-adjacent raw engine and keep the IndexError-back-compat lineage consistent.
5. Optionally accept an opt-out kwarg (defaulting to raise) so callers who knowingly accept partial geo pages can continue — but the default MUST be raise. Do NOT name/route this as the legacy `on_truncation` knob (Out-of-scope above).
6. `get_sub_gdf` takes `**kwargs`; the page body to inspect is the `data` dict actually sent (after the `f=GeoJSON` mutation, verified: `restgdf/utils/getgdf.py:316-319`), and `query_data.get("resultRecordCount")` supplies `page_size` for the error context (mirroring `_get_sub_features` at `restgdf/utils/getgdf.py:100`).

**Acceptance criteria**

- [ ] Red-state test (behavior change, CONTRIBUTING red-first): a test driving `get_sub_gdf` (or `get_gdf`/`chunk_generator` end-to-end with a mocked session) against a response carrying top-level `exceededTransferLimit=true` asserts a raise; it must fail (currently returns a truncated GeoDataFrame silently) before the fix. Cover BOTH ESRIJSON and GeoJSON driver shapes.
- [ ] The raised exception type/`context` matches the chosen contract (Decision) and is consistent with the raw-feature engine's `PaginationError` (or `RestgdfResponseError(context="exceededTransferLimit")`).
- [ ] A non-truncated geo page still returns a GeoDataFrame unchanged (no regression in `get_gdf` happy path; existing `tests/test_getgdf.py` stays green).
- [ ] The fix inspects the parsed JSON dict, NOT `read_file` output, for the flag (assert via test that a flag pyogrio would strip is still detected).
- [ ] Doc-sync handoff recorded for W6-7 (streaming.md line 11 "safe to use ... unless explicitly noted" — verified: `docs/recipes/streaming.md:11`; and the `stream_gdf_chunks` note) and W6-6 (README geo-truncation note).

**Validation** — single (`tests/test_pagination_error_on_exceeded_transfer_limit.py` plus the new geo-path test); test; coverage. The existing red-test harness `JsonSession` in `tests/test_pagination_error_on_exceeded_transfer_limit.py:19-41` is a reusable session double pattern.

**Risks & rollback** — Failure modes: (a) double-reading the response body (`await response.text()` is a one-shot stream) — read once into a local, parse and pass the same text to `read_file`; (b) GeoJSON vs ESRIJSON flag-location divergence — covered by testing both shapes and using the top-level `raw.get("exceededTransferLimit")` check; (c) breaking the documented legacy `stream_gdf_chunks` contract — guarded by NOT threading `on_truncation`. Rollback: revert `get_sub_gdf` to the pass-through read. Anti-recommendation preserved as a do-NOT step: do not widen the `stream_gdf_chunks`/`get_gdf` knob contract.

**Decision required** — Exception type for the geo truncation raise: `PaginationError` (mirrors the raw-feature sibling `_get_sub_features`, inherits `IndexError` for legacy `except IndexError`) vs `RestgdfResponseError(context="exceededTransferLimit")` (mirrors `_resolve_page`'s `iter_pages` raise default, inherits `ValueError`). Recommended default: **`PaginationError`** — `get_sub_gdf` is the geo analogue of `_get_sub_features`, both are batch-fetch primitives, and `PaginationError` carries the `batch_index`/`page_size` context fields the geo path can populate; `_resolve_page`'s `RestgdfResponseError` is the `iter_pages`-engine convention, a different code path.

---

### W4-2 · Default orderByFields to the resolved OID on multi-page plans

**Audit refs:** PAGINATION-02 · **Severity:** high · **Effort:** M · **Milestone:** M2
**Depends:** — · **Blocks:** —
**Split-ownership:** — (PAGINATION-02 is wholly owned here; reads `_pagination.py` but the planner needs no change).
**Scope** — In: for the explicit offset/count pagination branch in `get_query_data_batches`, default `orderByFields` to the layer's resolved OID field UNLESS the caller already supplied one, so multi-page offset/count traversal is deterministic. Out-of-scope: injecting `orderByFields` on the OID-chunked WHERE fallback branch (the non-explicit-pagination branch) or on the `on_truncation='split'` bisection path (anti-recommendation — those use deterministic predicate partitioning; a sort there is unnecessary churn); changing `build_pagination_plan` in `_pagination.py` (the planner is pure offset/count math and needs no edit — it is read-only context here).

**Spec**

1. Target ONLY the explicit-pagination branch of `get_query_data_batches` (verified: `restgdf/utils/getgdf.py:264-293`) — both the caller-`resultRecordCount` sub-branch (verified: `restgdf/utils/getgdf.py:265-273`) and the planner sub-branch (verified: `restgdf/utils/getgdf.py:281-293`). These are the branches that emit batches carrying `resultOffset`. The audit-cited planner emission `(offset, min(effective_page_size, total_records - offset))` is verified at `restgdf/utils/_pagination.py:119-122`.
2. `orderByFields` is never injected today — it only rides through optional `QueryOptions` passthrough into `request_data` (audit grep). `request_data = dict(kwargs.get("data") or {})` is computed at the top of `get_query_data_batches` (verified: `restgdf/utils/getgdf.py:250`) and `metadata` is already fetched in this function (verified: `restgdf/utils/getgdf.py:253`), so the OID is resolvable with NO extra request via `get_object_id_field(metadata)` (verified: `restgdf/utils/_metadata.py:87`).
3. Override guard (anti-recommendation §1 — robust, case-insensitive, never clobber): `orderByFields` can arrive through `QueryOptions.extra` and flows into `data`/`request_data`. Check the merged `request_data` keys **case-insensitively** for an existing `orderByFields` (any case) and skip injection if present. Never overwrite a caller-supplied sort.
4. Graceful degradation (anti-recommendation §2 — OID failure must NOT break the happy path): `get_object_id_field` raises `FieldDoesNotExistError` on ambiguous/missing OID (verified: `restgdf/utils/_metadata.py:102, 118`). Wrap the OID resolution in a guard that, on `FieldDoesNotExistError`, **skips injection** (optionally emit a debug/warning log via `get_logger`, consistent with the module's `_METADATA_LOG` pattern at `restgdf/utils/getgdf.py:54`) and proceeds with un-sorted batches exactly as today. Do NOT let OID-resolution failure propagate and break queries that work now.
5. When injecting, set `orderByFields` to the resolved OID field name on each explicit-pagination batch body (alongside `resultOffset`/`resultRecordCount`). Keep the existing `{**request_data, ...}` merge shape (verified: `restgdf/utils/getgdf.py:266-272, 286-292`).
6. Do NOT inject on the OID-chunked WHERE fallback branch (verified: `restgdf/utils/getgdf.py:295-306`) nor in `_resolve_page`'s split path (anti-recommendation §3).
7. Semver/byte-change note: this changes wire payloads. Hand off to W6 (ARCHITECTURE/CHANGELOG) the new guarantee that multi-page offset/count traversal now carries a deterministic `orderByFields`.

**Acceptance criteria**

- [ ] Red-state test (behavior change): a test asserting that explicit-pagination batch bodies now carry `orderByFields=<OID>` when the caller supplied none — must fail (currently absent) before the fix. Cover both the caller-`resultRecordCount` and the planner sub-branches.
- [ ] A caller-supplied `orderByFields` (including a differently-cased key, e.g. `orderbyfields`) is preserved unchanged and NOT clobbered.
- [ ] When `get_object_id_field` raises `FieldDoesNotExistError` (ambiguous/missing OID), batches are produced un-sorted exactly as today (no exception escapes the happy path) — assert via a metadata fixture with ambiguous/no OID.
- [ ] The OID-chunked WHERE fallback branch and the `split` path are unchanged (no `orderByFields` injected) — assert via the existing `test_missing_pagination_flag_does_not_drive_offset_batching` (verified: `tests/test_pagination_characterization.py:21-41`) staying green.
- [ ] Characterization tests pinning byte-exact batch bodies are updated deliberately (audit anti-recommendation §3): `tests/test_pagination_characterization.py` and any byte-exact assertions in `tests/test_getgdf*.py` / `tests/test_pagination_planner.py` are reviewed and the explicit-pagination expectations adjusted to include `orderByFields`.
- [ ] Doc-sync handoff recorded for ARCHITECTURE/CHANGELOG (semver-relevant payload change) via W6.

**Validation** — single (`tests/test_pagination_characterization.py`, the new ordering test); test; coverage; compat (`tests/test_compat.py` to confirm no public-API regression).

**Risks & rollback** — Failure modes: (a) clobbering a caller sort — guarded by case-insensitive presence check; (b) breaking the happy path when OID is unresolvable — guarded by `FieldDoesNotExistError` swallow + skip; (c) over-reaching into the WHERE-fallback/split branches — explicitly excluded. Rollback: remove the injection block; batches revert to no `orderByFields`. Anti-recommendations preserved as do-NOT steps: do not inject on the WHERE-fallback or split branches; do not let OID failure become a hard error; do not clobber a caller sort.

---

### W4-3 · Bound the on_truncation='split' OID IN-lists & reuse the parent slice

**Audit refs:** PAGINATION-03 · **Severity:** low · **Effort:** M · **Milestone:** M3
**Depends:** — · **Blocks:** —
**Split-ownership:** — (PAGINATION-03 is wholly owned here; touches `getgdf.py` split path and `utils.py` `where_var_in_list`).
**Scope** — In: two low-risk improvements to the `_resolve_page` split path — (1) pass the parent half's OID slice down instead of re-calling `get_object_ids` at every recursion node; (2) cap the IN-list element count and recurse one more level when a half exceeds the cap. Out-of-scope: replacing the explicit IN-list with a numeric-midpoint BETWEEN range (anti-recommendation — ArcGIS OIDs are frequently non-contiguous/sparse after deletes, so a midpoint-of-range split produces wildly uneven/empty halves and breaks the `len(oids) <= 1` irreducibility guard); URL-length mitigation (already handled by the R-74/T8 length router in `_http.py` which routes oversized bodies to POST — per audit, NOT a failure mode to re-fix).

**Spec**

1. The split path: on truncation, `oid_field, oids = await get_object_ids(url, session, **split_kwargs)` returns the full OID list under the current predicate (verified: `restgdf/utils/getgdf.py:694`), the irreducibility guard `if len(oids) <= 1: raise` (verified: `restgdf/utils/getgdf.py:695-702`), then `mid = len(oids) // 2; halves = (oids[:mid], oids[mid:])` (verified: `restgdf/utils/getgdf.py:703-704`), and each half becomes `combine_where_clauses(current_where, where_var_in_list(oid_field, half))` (verified: `restgdf/utils/getgdf.py:705-709`). `where_var_in_list` emits a literal `<var> In (v1, v2, ...)` with one element per OID (verified: `restgdf/utils/utils.py:15-20`). `resultOffset`/`resultRecordCount` are popped per half (verified: `restgdf/utils/getgdf.py:713-714`).
2. Improvement (1) — reuse the parent slice (eliminate redundant `returnIdsOnly` round-trips): each recursion node re-calls `get_object_ids` for OIDs the parent already materialized. Thread the parent half's OID slice into the recursive `_resolve_page` call so a child does NOT re-fetch. The recursion signature `_resolve_page(..., depth, max_depth, request_kwargs)` (verified: `restgdf/utils/getgdf.py:626-636, 721-731`) gains an optional `oid_hint: list[int] | None = None` (or similar); when present and non-empty, skip the `get_object_ids` call at `restgdf/utils/getgdf.py:694` and bisect the held list. Preserve the `len(oids) <= 1` irreducibility guard against the held list (anti-recommendation — the guard depends on the materialized OID list).
3. Improvement (2) — cap the IN-list element count: when a half's element count exceeds a cap (audit suggests a conservative cap; common ArcGIS backing-store IN-predicate limit ~1000), recurse one more level rather than emitting one oversized IN-list. The per-node list already shrinks geometrically (N/2, N/4, ...), so recursing further is the natural mechanism. Add a module-level constant for the cap.
4. Do NOT switch to min/max BETWEEN ranges (anti-recommendation). If ranges are ever adopted later they must split at the **median OID value of the actual list**, not the numeric midpoint, and re-derive halves from the held list — but that is explicitly NOT this item.
5. `where_var_in_list` in `utils.py` (verified: `restgdf/utils/utils.py:15-20`) needs no signature change for the cap (the cap is enforced in the splitter, not the formatter); the `utils.py` touch is only if a shared chunk/cap helper is extracted there — keep it minimal.

**Acceptance criteria**

- [ ] Red-state test: a test driving the split path on a layer whose first split would exceed the IN-list cap asserts the splitter recurses (produces capped IN-lists) rather than emitting one oversized IN-list — must fail (currently emits N/2 literals) before the fix.
- [ ] A test asserting that child recursion nodes do NOT call `get_object_ids` again (the parent slice is reused) — e.g. mock/count `get_object_ids` invocations across a 2-level split and assert it is called only at the root.
- [ ] The `len(oids) <= 1` irreducibility guard still fires (against the held list) — existing split-depth/irreducibility tests stay green.
- [ ] No BETWEEN-range logic introduced (anti-recommendation honored).
- [ ] Existing `on_truncation='split'` behavior tests (the `_resolve_page` split coverage in `tests/test_getgdf*.py` / streaming tests) stay green for the small-layer case.

**Validation** — single (the split-path tests); test; coverage.

**Risks & rollback** — Failure modes: (a) the held-slice threading skips the irreducibility guard — explicitly re-assert the guard against the held list; (b) cap set too low causing excessive recursion depth vs `max_split_depth` (verified default 32: `restgdf/utils/getgdf.py:741`) — choose a cap (~1000) far above the depth bound's reach for realistic layers. Rollback: revert to per-node `get_object_ids` + single IN-list. Anti-recommendation preserved as do-NOT: no numeric-midpoint BETWEEN; do not re-mitigate URL length (already POST-routed).

---

### W4-4 · Count split sub-fetches against max_concurrent_pages

**Audit refs:** ASYNC-03 · **Severity:** low · **Effort:** M · **Milestone:** M3
**Depends:** — · **Blocks:** —
**Split-ownership:** — (ASYNC-03 is wholly owned here; the audit's accepted resolution touches the `iter_pages` docstring in `restgdf/featurelayer/featurelayer.py` and `docs/recipes/streaming.md`, but per the allocation this item is scoped to `restgdf/utils/getgdf.py`; the featurelayer docstring/streaming.md prose is the W5/W6 surface — see Scope).
**Scope** — In: per the audit's PREFERRED resolution, the documentation fix — clarify that `max_concurrent_pages` bounds only the top-level page-plan fetches and that `on_truncation='split'` adds serial, uncounted sub-fetches (`get_object_ids` + bisected page fetches) on top of the cap, so worst-case in-flight is roughly K+1. Out-of-scope (anti-recommendation): threading the semaphore into `_resolve_page` (there is NO semaphore in `_iter_pages_raw` — concurrency is a manual `pending_in_order`/`_submit_next()` task window, so the literal recommendation cannot be applied; and having the split fetch acquire a top-level slot while the consumer is suspended inside `_resolve_page` creates a re-entrancy deadlock). A hard cap would require a single shared re-entrant-safe semaphore on every leaf HTTP call — a larger redesign than the low-severity issue warrants; do NOT do it here.

**Spec**

1. Confirm the structure the audit describes: the bounded `_iter_pages_raw` in-order loop pops a task, awaits it, immediately refills via `_submit_next()` to `max_concurrent_pages` in-flight `_fetch_bounded` tasks, THEN the consumer enters `async for resolved in _resolve_page(...)` (verified: `restgdf/utils/getgdf.py:879-902`; the completion-order branch has the same shape at `restgdf/utils/getgdf.py:845-877`). For `on_truncation='split'`, `_resolve_page` issues its OWN HTTP calls — `get_object_ids` (verified: `restgdf/utils/getgdf.py:694`) and `_fetch_page_dict` for each bisected sub-page (verified: `restgdf/utils/getgdf.py:715`) — none counted against `max_concurrent_pages`.
2. Apply the DOCUMENTATION fix, not the code fix. The audit's accepted resolution is to update the `iter_pages` docstring (`restgdf/featurelayer/featurelayer.py:325-326` per audit) and `docs/recipes/streaming.md` to state that `max_concurrent_pages` bounds only top-level page-plan fetches and that `split` adds serial uncounted sub-fetches (worst-case ~K+1). streaming.md already discloses the extra round-trips (audit cites lines 122-124); the fix connects that to the concurrency bound.
3. Allocation scoping note: this item's owns[] is `restgdf/utils/getgdf.py`. The featurelayer docstring lives in W5's collision domain and the streaming.md prose in W6's. The actionable change for THIS item is therefore: (a) if `_iter_pages_raw` or `_resolve_page` carries any inline docstring/comment about the concurrency bound, correct it in `getgdf.py`; (b) hand off the `iter_pages` public-docstring correction to **W5** (owner of `featurelayer.py`) and the `docs/recipes/streaming.md` correction to **W6-7**. Surface this as the Decision below.
4. Do NOT thread the semaphore into `_resolve_page` (anti-recommendation — there is no semaphore to thread; the windowing loop is manual, and a slot-acquiring split fetch under a suspended consumer deadlocks).

**Acceptance criteria**

- [ ] Any inline docstring/comment in `getgdf.py` (`_iter_pages_raw`/`_resolve_page`) about the concurrency bound accurately states `max_concurrent_pages` bounds only top-level fetches and `split` adds serial uncounted sub-fetches (~K+1 worst case). If none exists, this is a no-op in `getgdf.py` and the change is purely the handoff.
- [ ] Handoff recorded: W5 to correct the `iter_pages` public docstring (`featurelayer.py:325-326`); W6-7 to correct `docs/recipes/streaming.md` (connect the existing round-trip disclosure at lines 122-124 to the concurrency bound).
- [ ] No code change to `_resolve_page` concurrency accounting (anti-recommendation honored — no semaphore threading, no deadlock-prone slot acquisition).
- [ ] No behavior change; existing concurrency/bounded-stream tests stay green.

**Validation** — test (confirm no regression); docs (the Sphinx build for the streaming.md correction, executed under W6-7); lint.

**Risks & rollback** — Failure mode: attempting the code fix introduces a re-entrancy deadlock (split fetch blocks on a slot freed only when the suspended consumer advances). Mitigation: do NOT do the code fix — documentation only. Rollback: revert the docstring text. Anti-recommendation preserved as the central do-NOT: no semaphore threading into `_resolve_page`.

**Decision required** — This item is documentation-only (audit PREFERRED resolution) and its real surface (the `iter_pages` docstring in `featurelayer.py` and `docs/recipes/streaming.md`) is owned by W5 and W6, not W4. Recommended default: **scope W4-4's actionable work to confirming/correcting any concurrency-bound comment inside `getgdf.py` and explicitly hand the public-docstring and streaming.md corrections to W5 (featurelayer docstring) and W6-7 (streaming.md)** — do not attempt the rejected code fix in any workstream.
