> **06 — Async / concurrency correctness** · restgdf audit · **read-only** · no code was modified
> Commit `4673b08` · 2026-06-13 · Index: [README](README.md) · Machine-readable: [findings.json](findings.json)

## Assessment

The proactive concurrency machinery is genuinely well-built: `bounded_gather` and the per-call `BoundedSemaphore` threading (R-18/R-44) are correct and tested; the crawl fan-out cannot deadlock because the non-reentrant semaphore is always acquired/released without holding a slot across another acquire; the proactive token single-flight (`update_token_if_needed`, double-checked under a lazy per-instance lock) is correct and tested; and the streaming span lifecycle uses a non-current span + `aclosing` to avoid the OTel context-detach trap. The residual risk is concentrated in two areas: (1) the *reactive* 498 refresh path violates the documented "exactly one /generateToken POST under N concurrent requesters" single-flight contract because it calls `update_token()` unconditionally under the lock with no double-check, and (2) the per-instance `FeatureLayer` caches (`uniquevalues`/`valuecounts`/`nestedcount`/`gdf`) are plain dicts with no in-flight coordination, so concurrent awaiters double-fetch and the cached DataFrame/GeoDataFrame is handed out by reference to multiple tasks. Overall posture is solid for the single-task happy path but has concrete, documented-contract-breaking gaps when a session/layer is shared across tasks.

## Findings at a glance

| ID | Finding | Severity | Effort |
|----|---------|----------|--------|
| `ASYNC-01` | Reactive 498 refresh fires a redundant /generateToken per concurrent requester, breaking the documented single-flight contract | medium | S |
| `ASYNC-02` | Cached DataFrame/GeoDataFrame returned by reference to every (possibly concurrent) caller — shared mutable state | medium | S |
| `ASYNC-03` | on_truncation='split' sub-fetches bypass the max_concurrent_pages accounting, so peak in-flight exceeds the advertised bound | low | M |

## Findings

### ASYNC-01 · Reactive 498 refresh fires a redundant /generateToken per concurrent requester, breaking the documented single-flight contract

**Severity:** medium · **Effort:** S · **Location:** `restgdf/utils/token.py:389-394`

**Evidence**

In `_call_with_auth_retry` the 498 branch acquires the lock then refreshes UNCONDITIONALLY: `if self._refresh_lock is None: self._refresh_lock = asyncio.Lock()` / `async with self._refresh_lock:` / `await self.update_token()`. Unlike `update_token_if_needed` (token.py:341-343) which double-checks `if self.token_needs_update():` inside the lock, the 498 path has NO guard. MIGRATION.md:440-444 documents the opposite as the contract: "Single-flight token refresh ... under N concurrent requesters exactly one /generateToken POST is issued."

**Why it matters**

When a server-side token rotation/invalidation causes N concurrent in-flight requests to all return HTTP 498, each task acquires the lock serially and calls `update_token()` again even though the first refresh already installed a fresh token — N redundant /generateToken POSTs instead of 1. This can trip ArcGIS Online rate limits / lockout on the credential exactly when the service is already under stress, and contradicts a contract the README/MIGRATION explicitly advertise. The proactive path is single-flight; the reactive path is not.

**Recommendation**

Adopt the proposed double-check, snapshotting the token used for the failed request before refreshing. Concretely in `_call_with_auth_retry` (token.py:389-394): capture `tok_before = self.token` BEFORE issuing the request, then in the 498 branch do `async with self._refresh_lock: if self.token == tok_before: await self.update_token()`. The first task to win the lock refreshes; later tasks (whose `tok_before` is the same now-superseded token) observe `self.token != tok_before`, skip the redundant /generateToken, and proceed to retry with the current token. This mirrors `update_token_if_needed` (token.py:341-343) and restores the "single-flight refresh" wording in MIGRATION.md:445-446 and the docstring at token.py:356. Do NOT instead gate on `token_needs_update()` here — after a server-side invalidation the local token still looks valid (returns False), so that predicate would suppress the needed refresh entirely; the equality-of-snapshot check is the correct guard. Add a concurrent-498 regression test asserting exactly one `update_token` call under N simultaneous 498 responses (the existing tests in test_token_498_499.py only cover the single-requester case and the `AsyncMock` keeps `self.token` unchanged, so the fix keeps them green).

**Fix touches:** `restgdf/utils/token.py`, `tests/test_token_498_499.py`

---

### ASYNC-02 · Cached DataFrame/GeoDataFrame returned by reference to every (possibly concurrent) caller — shared mutable state

**Severity:** medium · **Effort:** S · **Location:** `restgdf/featurelayer/featurelayer.py:301,597,632,668`

**Evidence**

On a cache hit the methods return the stored mutable object directly: `return self.gdf`, `return self.uniquevalues[cache_key]`, `return self.valuecounts[field]`, `return self.nestedcount[fields]`. `_stats.get_value_counts`/`nested_count` and the multi-field `get_unique_values` build a pandas/GeoDataFrame that is then cached and aliased. `test_featurelayer_getgdf_caches_result` confirms identity reuse (same object on second call). Docstrings say results are "cached ... for the lifetime of this instance" but never state the returned object is shared and must not be mutated.

**Why it matters**

Two tasks (or sequential callers) that both receive the same cached GeoDataFrame/DataFrame and one performs an in-place mutation (`df.sort_values(..., inplace=True)`, `df.rename(..., inplace=True)`, column assignment, `gdf.to_crs(..., inplace=...)`) silently corrupts the cache for every other holder — a data-correctness footgun that is especially likely to bite when the layer is shared across concurrent tasks operating on the same frame. The bug surfaces non-deterministically depending on task interleaving.

**Recommendation**

Return a defensive copy on cache hit: `.copy()` for the GeoDataFrame (`get_gdf`) and DataFrame paths (`get_value_counts`, `get_nested_count`, and the tuple/DataFrame branch of `get_unique_values`), and `list(...)` for the single-field scalar-list branch of `get_unique_values`. This is the safer default for a Production/Stable public library where the returned frames are query results callers naturally transform. Two anti-recommendation caveats: (1) the `get_gdf` copy MUST preserve `gdf.attrs["spatial_reference"]` (R-65) — pandas/geopandas `.copy()` propagates `.attrs` so this holds, but it should be asserted in a test. (2) Copy-on-return does NOT make a shared instance task-safe — the cache population (`if self.gdf is None: self.gdf = await get_gdf(...)`) is itself racy under `asyncio.gather`, so do not advertise concurrency safety on the back of this fix; that is a separate concern. The fix breaks no existing test: the cache tests (`test_featurelayer_getgdf_caches_result` and the `*_caches_*` tests) assert value-equality (`.equals()`) plus `assert_awaited_once()`, neither of which a post-await copy violates; no test asserts `first is second`. A documentation-only alternative (state in each docstring that the returned object is a shared cached reference callers MUST NOT mutate in place) is acceptable but weaker — copy-on-return is preferred here.

**Fix touches:** `restgdf/featurelayer/featurelayer.py`

---

### ASYNC-03 · on_truncation='split' sub-fetches bypass the max_concurrent_pages accounting, so peak in-flight exceeds the advertised bound

**Severity:** low · **Effort:** M · **Location:** `restgdf/utils/getgdf.py:879-902,694,715-720`

**Evidence**

In the bounded `_iter_pages_raw` loops, after `task = pending_in_order.pop(0); await task`, `_submit_next()` immediately refills to `max_concurrent_pages` in-flight `_fetch_bounded` tasks, THEN the consumer enters `async for resolved in _resolve_page(...)`. For `on_truncation='split'`, `_resolve_page` issues its OWN HTTP calls — `oid_field, oids = await get_object_ids(url, session, **split_kwargs)` (line 694) and `sub_page = await _fetch_page_dict(url, session, sub_qd, ...)` (line 715) — none of which are counted against `max_concurrent_pages` or submitted as tracked tasks. The completion-order bounded branch (845-877) has the same structure.

**Why it matters**

A caller who sets `max_concurrent_pages=K` to cap server load on a layer that returns `exceededTransferLimit=true` will see peak concurrent HTTP requests of K (background page fetches still in flight) plus the split path's serial fetches — exceeding the bound the public `iter_pages` docstring advertises ("Upper bound on concurrent in-flight page fetches"). Bounded (split is serial, ~K+1), but a real contract overshoot on the split path.

**Recommendation**

Prefer the DOCUMENTATION fix, not the code fix. Update the `iter_pages` docstring (restgdf/featurelayer/featurelayer.py:325-326) and docs/recipes/streaming.md to state that `max_concurrent_pages` bounds only the top-level page-plan fetches, and that `on_truncation='split'` adds serial, uncounted sub-fetches (`get_object_ids` + bisected page fetches) on top of the cap — so worst-case in-flight is roughly K+1. streaming.md already discloses the extra round-trips (lines 122-124); just connect that to the concurrency bound. AVOID the naive "thread the semaphore into `_resolve_page`" fix: (a) there is no semaphore in `_iter_pages_raw` — concurrency is bounded by a manual `pending_in_order`/`_submit_next()` task window (lines 836-902), not an `asyncio.Semaphore`, so the recommendation as literally written cannot be applied; (b) more dangerously, having the split sub-fetch acquire a top-level slot while the consumer is suspended inside `_resolve_page` (still occupying the K background-fetch budget) creates a re-entrancy deadlock: the split fetch blocks waiting for a slot that only frees when the consumer advances, but the consumer is blocked awaiting the split fetch. If a hard cap is truly required, the correct (heavier) design is a single shared semaphore acquired by every leaf HTTP call (`_fetch_page_dict`/`get_object_ids`) that is re-entrant-safe w.r.t. the windowing loop — which is a larger redesign than the issue warrants.

**Fix touches:** `restgdf/utils/getgdf.py`

---

## Minor notes (not adversarially verified)

These were flagged by the axis auditor but did NOT go through per-finding verification — treat as leads, not confirmed findings.

- **Token single-flight is per-ArcGISTokenSession-instance only** — `_refresh_lock` is a per-instance field (token.py:124-129) and `test_refresh_lock_is_per_instance` asserts distinct sessions get distinct locks. If a deployment constructs multiple `ArcGISTokenSession` objects sharing the same credentials/token-url (e.g. one per `FeatureLayer` instead of one shared session), the single-flight guarantee does NOT span them — each session independently fires /generateToken. This is consistent with the documented per-instance design and ARCHITECTURE's session-ownership model, so not a defect; worth a one-line README caveat that callers should share ONE token session across layers to get single-flight. Could not find a doc statement either way, so labeling as unverified guidance rather than a contract divergence.
- **crawl shared-semaphore fan-out is deadlock-free (seed confirmed safe)** — Verified the crawl.py:43-46/150-157 design: the outer `asyncio.gather` is intentionally NOT wrapped in `_sem`, and each nested `service_metadata` acquires `_sem` for the single service-level `get_metadata` (getinfo.py:208) then releases before `bounded_gather` re-acquires per layer (getinfo.py:243). No code path holds a semaphore slot across acquisition of a second slot, so the non-reentrant `BoundedSemaphore` cannot self-deadlock or double-acquire. The seed's deadlock hypothesis is refuted; the comments and tests (test_concurrency_nesting.py) are accurate.
- **service_metadata holds a sem slot across feature-count retries** — In `_comprehensive_metadata` (getinfo.py:214-234) the `bounded_gather` slot is held while `_feature_count_with_timeout` runs, which on timeouts sleeps with exponential backoff (getinfo.py:150-151) — so a slow/retrying feature-count keeps a concurrency slot occupied during its `asyncio.sleep`. This is consistent with the documented "saturation semantics = wait" (R-19) and is not a bug, but under widespread layer timeouts effective crawl throughput can drop to near-serial. Note only.
- **iter_pages default max_concurrent_pages=None creates all page tasks up front** — getgdf.py:799-802 `tasks = [asyncio.create_task(_fetch_bounded(qd)) for qd in query_data_batches]` materializes one task per page immediately when unbounded. This is correctly documented in `iter_pages` ("None (default) leaves concurrency unbounded") so it is an intentional default, not a finding — but for a very large layer it means thousands of simultaneous HTTP tasks against the aiohttp connector. A doc nudge toward setting `max_concurrent_pages` for big layers would help DX.
