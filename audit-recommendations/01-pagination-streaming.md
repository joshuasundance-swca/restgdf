> **01 — Pagination & streaming correctness** · restgdf audit · **read-only** · no code was modified
> Commit `4673b08` · 2026-06-13 · Index: [README](README.md) · Machine-readable: [findings.json](findings.json)

## Assessment

The pure planner (`build_pagination_plan`) is genuinely solid: well-tested byte-exact offset/count math, frozen dataclass, correct tail clamping, robust `maxRecordCountFactor` clamp with NaN/inf/bool rejection (`_advertised_max_record_count_factor`), and a clean R-72 opt-in wire-up. The `iter_pages` engine has a thoughtful truncation contract (`raise`/`ignore`/`split`), a real R-73 zero-feature-cursor-stall warning, and bounded-concurrency semantics that are pinned by edge-case tests. The serious risk is the asymmetry between engines: the FLAGSHIP GeoDataFrame path (`get_gdf` / `stream_gdf_chunks` via `get_sub_gdf`) performs NO `exceededTransferLimit` check and silently returns truncated data, while the public docs present it as a co-equal, "safe" entry point. Secondary risks are paging without a deterministic `orderByFields` (silent cross-page row drift) and an `on_truncation='split'` mode whose nested OID IN-lists make it unusable on exactly the large layers that trigger truncation.

## Findings at a glance

| ID | Finding | Severity | Effort |
|----|---------|----------|--------|
| `PAGINATION-01` | GeoDataFrame path (get_gdf / stream_gdf_chunks) silently drops rows on exceededTransferLimit | high | M |
| `PAGINATION-02` | Offset/count pagination issued without orderByFields — unstable ordering can silently duplicate or drop rows across pages | high | M |
| `PAGINATION-03` | on_truncation='split' builds unbounded nested OID IN-lists, making it unusable on large layers (the exact truncation case) | low | M |

## Findings

### PAGINATION-01 · GeoDataFrame path (get_gdf / stream_gdf_chunks) silently drops rows on exceededTransferLimit

**Severity:** high · **Effort:** M · **Location:** `restgdf/utils/getgdf.py:309-335, 374-449, 489-525`

**Evidence**

`get_sub_gdf` reads the page straight into geopandas with no envelope inspection: `response = await _arcgis_request(...)` then `sub_gdf = read_file(await response.text(), engine="pyogrio")` and `return sub_gdf` — `exceededTransferLimit` is never parsed. Contrast `_get_sub_features` (`getgdf.py:95-101`): `if envelope.exceeded_transfer_limit: raise PaginationError(...)` and `_resolve_page` (`getgdf.py:643-677`) which raises `RestgdfResponseError` by default. `get_gdf` -> `gdf_by_concat` -> `get_gdf_list` -> `get_sub_gdf` and `stream_gdf_chunks` -> `chunk_generator` -> `get_sub_gdf` are the ONLY consumers of `get_sub_gdf`; neither checks truncation.

**Why it matters**

`get_gdf()` is the flagship public method (README lines 300-357). When a planner page hits ArcGIS's byte/geometry-size cap (not just record count) the server returns a short page with `exceededTransferLimit=true`; restgdf reads the partial page, concatenates it, and returns a GeoDataFrame that is silently missing rows with NO error or warning. This is silent data loss returned to the caller on the single most common geo call. `docs/recipes/streaming.md:11` even states all four streaming shapes are 'safe to use on a base install unless explicitly noted' and never notes this; the public docs imply the geo path is as safe as the raising paths.

**Recommendation**

Make the geo path detect truncation and raise by default, matching the raw-feature engine — but do NOT naively thread the full `on_truncation` (`raise`/`ignore`/`split`) knob set through `chunk_generator`/`get_gdf_list`/`get_gdf`. `ARCHITECTURE.md:146-150` and `MIGRATION.md:184-190` deliberately document `stream_gdf_chunks` as the legacy path that does not accept those knobs; widening that contract is a separate design change. Minimal safe fix: in `get_sub_gdf`, parse the envelope for `exceededTransferLimit` BEFORE/separately from `read_file` and raise `RestgdfResponseError(context='exceededTransferLimit')` (or `PaginationError`, to mirror `_get_sub_features`). Implementation hazard: `get_sub_gdf` requests `f=GeoJSON/ESRIJSON` and consumes `response.text()`; the `exceededTransferLimit` flag is a top-level member that pyogrio/`read_file` discards, so inspect the parsed JSON dict directly (do not rely on `read_file` to surface it). Optionally allow an opt-out kwarg defaulting to raise so callers who knowingly accept partial geo pages can continue. In the interim, correct `streaming.md:11` ('safe to use ... unless explicitly noted') and the `stream_gdf_chunks` note (lines 80-89) to explicitly state the geo path currently does NOT detect `exceededTransferLimit` and can return silently-truncated GeoDataFrames.

**Fix touches:** `restgdf/utils/getgdf.py`, `restgdf/featurelayer/featurelayer.py`, `docs/recipes/streaming.md`, `README.md`

---

### PAGINATION-02 · Offset/count pagination issued without orderByFields — unstable ordering can silently duplicate or drop rows across pages

**Severity:** high · **Effort:** M · **Location:** `restgdf/utils/getgdf.py:264-293, restgdf/utils/_pagination.py:118-122`

**Evidence**

The pagination branch builds batches as `{**request_data, "resultOffset": offset, "resultRecordCount": count}` for each `(offset, count)` in `plan.batches`, and `build_pagination_plan` emits `(offset, min(effective_page_size, total_records - offset))` for `offset in range(0, total_records, effective_page_size)`. No `orderByFields` is ever injected into the batch payloads (grep of `restgdf/*.py` shows `orderByFields` only in optional `QueryOptions` passthrough, never defaulted). Pages are also fetched concurrently (`get_gdf_list`, `_iter_pages_raw`, `chunk_generator`).

**Why it matters**

ArcGIS does NOT guarantee a stable row order across separate `resultOffset`/`resultRecordCount` requests unless `orderByFields` is supplied (an Esri-documented gotcha). Without a deterministic sort, a feature can be returned on two adjacent pages (duplicate) or fall between page boundaries (dropped) when the server's implicit ordering shifts between calls. This is silent wrong/duplicated data on the common multi-page path for `get_gdf`, `get_df`, and all `stream_*` methods. Risk is server-dependent but the library offers no protection and no warning.

**Recommendation**

For any multi-page plan that carries `resultOffset` (the explicit-pagination branch in `get_query_data_batches` at `restgdf/utils/getgdf.py:264-293`), default `orderByFields` to the layer's resolved OID field UNLESS the caller already supplied an `orderByFields` in `request_data`. The OID is resolvable via `restgdf.utils._metadata.get_object_id_field(metadata)` and metadata is already fetched in this function, so no extra request is needed. This matches Esri's own documented remedy for reliable `resultOffset`/`resultRecordCount` paging and converts a server-dependent silent-correctness gamble into a stable contract. Document the new guarantee in `ARCHITECTURE.md`/`CHANGELOG` and note it is semver-relevant (changes wire payloads). ATTACK/anti-recommendation: (1) The override check must be robust — `orderByFields` can arrive through `QueryOptions.extra` and flows into `data`, so check the merged `request_data` case-insensitively and never clobber a caller-supplied sort. (2) `get_object_id_field` raises `FieldDoesNotExistError` on ambiguous/missing OID fields; the injection MUST degrade gracefully (skip injection, optionally warn) rather than propagate and break queries that work today — do NOT let OID resolution failure become a hard error on the happy path. (3) Characterization tests pin byte-exact batch bodies (`tests/test_pagination_characterization.py`); they will need updating, which is acceptable for a correctness fix but should be deliberate. Do NOT inject `orderByFields` on the OID-chunked WHERE fallback (the non-explicit-pagination branch) or on the `on_truncation='split'` bisection path — those use deterministic predicate partitioning and adding a sort there is unnecessary churn.

**Fix touches:** `restgdf/utils/getgdf.py`, `restgdf/utils/_pagination.py`

---

### PAGINATION-03 · on_truncation='split' builds unbounded nested OID IN-lists, making it unusable on large layers (the exact truncation case)

**Severity:** low · **Effort:** M · **Location:** `restgdf/utils/getgdf.py:694-714, restgdf/utils/utils.py:15-20`

**Evidence**

On split, `oid_field, oids = await get_object_ids(...)` returns the full OID list under the current predicate; then `mid = len(oids)//2; halves = (oids[:mid], oids[mid:])` and `half_where = combine_where_clauses(current_where, where_var_in_list(oid_field, half))`. `where_var_in_list` emits a literal `OBJECTID In (v1, v2, ...)` with one element per OID. Each recursion narrows `current_where` but the first split of an N-feature layer produces an IN-list of N/2 literal OIDs, and child predicates nest further IN-lists (`(((1=1) AND oid In (...N/2...)) AND oid In (...N/4...))`). `resultOffset`/`resultRecordCount` are popped (lines 713-714) so each half is one unbounded query.

**Why it matters**

Truncation typically fires on large layers (tens of thousands of features). The root split then issues a query whose WHERE clause embeds ~N/2 OID literals — ArcGIS commonly caps IN-list size (~1000) and request body/URL length, so the split query itself is rejected before it can complete, or generates pathologically large request bodies. The documented 'completeness' escape hatch (`docs/recipes/streaming.md:116-124`, `ARCHITECTURE.md:165-168`) therefore fails on precisely the layers that need it, while smaller layers rarely truncate. Each node also re-fetches OIDs it could derive from the parent half (extra `returnIdsOnly` round-trips).

**Recommendation**

Two genuinely useful, low-risk improvements; the headline "use BETWEEN ranges" fix is partly an anti-recommendation. (1) Pass the parent half's OID slice down instead of re-calling `get_object_ids` at every recursion node (`getgdf.py:694`) — at each level the parent already knows the exact OIDs for the child predicate, so the extra `returnIdsOnly` round-trip per node is pure waste and trivially eliminable. (2) Cap the IN-list element count and, when a half exceeds the cap, recurse one more level (the per-node list already shrinks geometrically N/2, N/4, ...) rather than emitting one oversized IN-list — this hardens against backing stores that enforce a SQL IN-predicate element limit. ANTI-RECOMMENDATION: do not naively replace the explicit IN-list with a min/max BETWEEN range. ArcGIS OIDs are frequently non-contiguous/sparse after deletes, so a midpoint-of-range split can produce wildly uneven or empty halves and would also break the existing irreducibility guard at `getgdf.py:695` (`"len(oids) <= 1 → raise"`), which depends on holding the materialized OID list. If ranges are ever adopted they must split at the median OID value of the actual list, not the numeric midpoint, and re-derive halves from the held list. Note: the finding's primary stated failure mode (414 URI-Too-Long / URL-length rejection of the split query) is ALREADY mitigated — `_arcgis_request` routes any query whose URL+encoded body exceeds ~8k bytes to POST via the R-74/T8 length router (`restgdf/utils/_http.py:46-77,117-121`), so an oversized OID IN-list is sent as a POST body, not a giant URL. Tens of thousands of small integer OIDs serialize to only a few hundred KB, well within typical POST limits.

**Fix touches:** `restgdf/utils/getgdf.py`, `restgdf/utils/utils.py`

---

## Minor notes (not adversarially verified)

These were flagged by the axis auditor but did NOT go through per-finding verification — treat as leads, not confirmed findings.

- **Explicit resultRecordCount branch bypasses the planner clamp but is benign** — `getgdf.py:265-273` builds batches directly from a caller-supplied `resultRecordCount`, skipping `build_pagination_plan` and its `advertised_factor` clamp (R-72). This is harmless: `page_size` is already clamped to `max_record_count` at line 257 (`page_size = min(requested_page_size, max_record_count)`), so it can never exceed the advertised ceiling that the factor clamp protects. Tail batches are correctly clamped via `min(page_size, feature_count - offset)`. Pinned by `tests/test_pagination_planner.py:178-249`. Not a bug; noting only because the seed flagged it.
- **R-73 zero-feature truncation warning only fires inside the iter_pages engine** — `_resolve_page` (`getgdf.py:652-660`) emits `PaginationInconsistencyWarning` when a page has `exceededTransferLimit=true` with zero features (cursor-stall bug). This guard exists only in the `iter_pages` engine; the gdf path (`get_sub_gdf`) and the OID-chunk path never reach it, so the same ArcGIS cursor-stall on a geo query is invisible. Subsumed by finding 1 but worth noting the warning's limited reach.
- **get_query_data_batches and chunk_generator each refetch metadata/feature_count** — `chunk_generator` calls `get_query_data_batches` (which calls `get_feature_count` + `get_metadata`) and then calls `get_metadata` again for `spatial_reference` (`getgdf.py:387-401`). `_iter_pages_raw` similarly recomputes `feature_count` + `metadata` on every stream even when the caller already prepped a `FeatureLayer` with cached `self.metadata`/`self.count`. Not a correctness bug, but it adds 2-3 redundant round-trips per stream and means the pagination plan can be built from a `feature_count` that drifts from the prepped `FeatureLayer`'s count under concurrent edits.
