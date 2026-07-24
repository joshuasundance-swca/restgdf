# 02 — Auth, token, transport & error taxonomy (code)
> Workstream of the restgdf remediation plan · audit pinned `4673b08` · 2026-06-13

## Goal
Close the credential-confidentiality, error-contract, and transport-config gaps in the token/auth/resilience code so the library's *advertised* behavior matches its *actual* behavior. Landing this workstream stops the on-the-wire token leak on the documented `FeatureLayer(token=...)` path (the single highest-leverage security fix), makes the public exception taxonomy (`InvalidCredentialsError`, `AuthenticationError`, the `498/499` classes) fire where the docs say it does, makes `verify_ssl`/`user_agent`/retry knobs load-bearing on data requests, and hardens the token single-flight + retry-filter against deterministic-error mislabeling. These are correctness/contract defects on a Production/Stable release, not polish.

## Collision domain
This workstream is single-writer on the following files (from the allocation `owns[]`):

- `restgdf/utils/token.py` — **hot file**: written by W2-2, W2-3, W2-4, W2-5, W2-6, W2-10, W2-11. All seven items touch this one module, so they MUST serialize (see Sequencing).
- `restgdf/utils/_http.py` — written by W2-1, W2-10.
- `restgdf/utils/_query.py` — written by W2-1.
- `restgdf/errors.py` — written by W2-2, W2-9.
- `restgdf/_models/_errors.py` — owned but not touched by any current W2 item (no finding maps to it).
- `restgdf/_models/credentials.py` — written by W2-11.
- `restgdf/resilience/*` — `restgdf/resilience/_errors.py` (W2-7), `restgdf/resilience/_retry.py` (W2-13).
- `restgdf/utils/_optional.py` — written by W2-8.
- `tests/test_gate3_fixes.py` (W2-1), `tests/test_token_498_499.py` (W2-4), `tests/test_resilience_retry.py` (W2-7), `tests/test_base_install.py` (W2-8).

**Cross-workstream shared/seam files (NOT owned here):**
- `restgdf/_config.py` is owned by **W3** (single-writer). W2-13 may need an *additive* field there; if so, the `_config.py` edit must be delegated to W3 to avoid a collision (see W2-13).
- `restgdf/featurelayer/featurelayer.py` is owned by **W5**; W2-11 only touches `token.py`/`credentials.py`, the FeatureLayer construction seam is W5-14.
- `restgdf/utils/getgdf.py` is owned by **W4**; the bare-session `verify_ssl` seam is W4-5, not here.
- Doc files (`README.md`, `MIGRATION.md`, `ARCHITECTURE.md`, `CHANGELOG.md`, `docs/*`) are owned by **W6** — every doc-sync below is delegated to a W6 item.

## Sequencing & parallelization

**Milestone order:** M1 → M2 → M3 → M4.

- **M1 (security quick win):** `W2-1` (force POST on body-carried token). Independent — touches `_http.py` + `_query.py` + `tests/test_gate3_fixes.py`, none of which collide with the `token.py` cluster. Land first; it is the highest-leverage security fix and unblocks W1-9 (FakeSession verb separation) and W6-6 (README note).
- **M2 (can run in parallel — disjoint files):**
  - `W2-4` (498 single-flight double-check) → `token.py` + `tests/test_token_498_499.py`.
  - `W2-6` (route `restgdf.auth` through `get_logger`) → `token.py` (one-line).
  - `W2-10` (apply UA + `verify_ssl` at token/_http seams) → `token.py` + `_http.py`. **Depends on W3-1** landing the `TransportConfig` source of truth first.
  - `W2-7` (reject NaN/Inf in `_parse_retry_after`) → `resilience/_errors.py` + `tests/test_resilience_retry.py`. Fully disjoint — parallel-safe.
  - `W2-8` (broaden `require_*` to `ImportError`) → `utils/_optional.py` + `tests/test_base_install.py`. Fully disjoint — parallel-safe.
  - **Serialization hazard:** W2-4, W2-6, and W2-10 all write `token.py`. They must serialize against each other (recommended order W2-6 → W2-4 → W2-10, smallest-blast-radius first). W2-7 and W2-8 run in parallel with the `token.py` cluster.
- **M3 (token.py cluster + errors.py + credentials.py):**
  - `W2-2` (raise `InvalidCredentialsError` on `/generateToken` 4xx) → `token.py` + `errors.py`. Land first in M3 because W2-3 depends on it.
  - `W2-3` (stop retry filter swallowing deterministic auth errors) → `token.py`. **Depends on W2-2** (coordinate so the `except RestgdfError: raise` ordering and the new `InvalidCredentialsError` raise site land coherently).
  - `W2-5` (in-body 498/499 envelope detection) → `token.py`. Independent of W2-2/W2-3 in principle but shares `token.py`; serialize after W2-3.
  - `W2-11` (token sessions read AuthConfig refresh knobs) → `token.py` + `credentials.py`. **Depends on W3-3 + W3-2** landing the config exposure first.
  - **Serialization:** all four write `token.py`; order them W2-2 → W2-3 → W2-5 → W2-11.
- **M4 (decision/polish):** `W2-9` (ValueError co-inheritance docstring) → `errors.py` (docstring text only). Independent; land any time after M1 gates are green.

**Cross-workstream `Depends` edges (explicit):**
- `W2-10` blocks on **W3-1** landing the `TransportConfig.user_agent`/`verify_ssl` source-of-truth + the verify_ssl reconciliation decision.
- `W2-11` blocks on **W3-3** (expose `AuthConfig` for token-session construction) and **W3-2** (wire-or-retire the refresh-threshold knobs).
- `W2-1` **blocks** W1-9 (characterization FakeSession verb separation) and W6-6 (README token-in-body note).
- `W2-2` **blocks** W6-3 (ARCHITECTURE AUTH-02 prose) and W6-4 (MIGRATION AUTH-02 prose).
- `W2-10` **blocks** W6-4 (MIGRATION verify_ssl prose) jointly with W3-1.

---

## Work items

### W2-1 · Force POST when the request body carries a token (body-aware leak guard)
**Audit refs:** AUTH-01 · **Severity:** high · **Effort:** S · **Milestone:** M1
**Depends:** — · **Blocks:** W1-9 (characterization verb separation), W6-6 (README token-in-body note)
**Split-ownership:** AUTH-01 code fix is fully owned here. Doc-side (README:363 / README:328-329) is W6-6. The misleading test comment at `test_gate3_fixes.py:88-97` is owned here (W2 owns that test file).
**Scope** — In: make the credential-leak guard in `_arcgis_request` body-aware so a caller-supplied `token` in the outgoing body forces POST even on a plain `aiohttp.ClientSession` or a default header-mode `ArcGISTokenSession`; add a regression test; fix the misleading comment in the existing Gate-3 test. Out-of-scope: changing the auth *scheme* (do NOT strip the token from params and move it to an `X-Esri-Authorization` header — the audit's explicit anti-recommendation); do NOT remove or weaken the existing session-transport guard (`_session_requires_body_transport`); no public-API/import-boundary change.
**Spec**
1. In `restgdf/utils/_http.py`, `_arcgis_request` currently routes via `_session_requires_body_transport(session)` then falls through to `_choose_verb`/`session.get(...)` (verified: `restgdf/utils/_http.py:117-123`). Make the guard body-aware: before `_choose_verb`, force POST whenever the outgoing `body` carries a credential key. Concretely change the guard at `_http.py:117` to also POST when `body and "token" in body`, e.g. `if _session_requires_body_transport(session) or (body and "token" in body): return await session.post(url, data=body, **kwargs)`. This *complements* the session-transport guard (do NOT replace it).
2. Confirm the body actually carries the token on the documented paths: `build_conservative_query_data` copies `if "token" in caller_data: datadict["token"] = caller_data["token"]` (verified: `restgdf/_client/request.py:47-48`), and `get_metadata` does `if token is not None: data["token"] = token` (verified: `restgdf/utils/_query.py:69-71`). The `_query.py` edit (if any) is limited to confirming/forwarding the body; the actual routing fix is in `_http.py`. No structural change to `_query.py` is required beyond confirming the body shape — keep the `_query.py` touch minimal (the allocation lists it because the leak path flows through it).
3. ArcGIS REST layer-metadata roots and `/query` already accept form-encoded POST bodies (the library POSTs to them today for long bodies and for body/query-transport sessions), so forcing POST on a token-bearing short body is low risk.
4. Fix the misleading comment block in `tests/test_gate3_fixes.py` at `test_arcgis_request_still_uses_get_for_header_transport` (verified: `tests/test_gate3_fixes.py:88-97`): the docstring claims "short requests can use GET without leaking credentials" — true ONLY because that test body carries no token. Reword to make that precondition explicit.
5. Add a regression test (red-first) in `tests/test_gate3_fixes.py` asserting that a body containing `token` routes via `session.post(..., data=body)` (NOT `session.get(..., params=...)`) on (a) a plain duck-typed session with no `_transport` and (b) a header-mode `_FakeAuthSession(transport="header")`. The existing `_FakeAuthSession` harness supports this.
6. Do NOT alter the GET param-coercion path (`_coerce_params_for_get`) — it stays for non-token bodies.
**Acceptance criteria**
- [ ] New test asserting token-in-body → POST on a plain/no-transport session FAILS before the fix (red state demonstrated) and passes after.
- [ ] New test asserting token-in-body → POST on a `transport="header"` session passes.
- [ ] Existing `test_arcgis_request_still_uses_get_for_header_transport` still passes (header-mode, no token in body → GET).
- [ ] The misleading comment at `tests/test_gate3_fixes.py:88-97` is corrected to state the token-absent precondition.
- [ ] Doc-sync: README token-in-body note delegated to W6-6 (cross-reference in the W6-6 item; no doc edit here).
**Validation** — lint; single: `.\.venv\Scripts\python.exe -m pytest tests/test_gate3_fixes.py`; test; coverage.
**Risks & rollback** — Risk: a server that ONLY honors query/GET tokens would now receive a POST body — but ArcGIS `/query` and metadata roots accept POST form bodies, so this matches the library's existing long-body behavior. Anti-recommendation enforced: do NOT switch to header-based auth (`X-Esri-Authorization`) as the "fix" — riskier for plain-ClientSession callers and silently changes the auth scheme. Rollback: revert the single `_arcgis_request` guard line and the test additions; the change is isolated routing logic.

---

### W2-6 · Route the restgdf.auth logger through the get_logger factory
**Audit refs:** TELEMETRY-03 · **Severity:** low · **Effort:** S · **Milestone:** M2
**Depends:** — · **Blocks:** —
**Split-ownership:** —
**Scope** — In: replace the raw `logging.getLogger("restgdf.auth")` call with the ledgered `get_logger("auth")` factory so the auth logger receives the documented NullHandler. Out-of-scope: do NOT also try to fix the root `restgdf` NullHandler gap (the audit's explicit anti-recommendation — that is a separate, broader item and conflating them is scope creep).
**Spec**
1. In `restgdf/utils/token.py`, replace `_auth_logger = logging.getLogger("restgdf.auth")` (verified: `restgdf/utils/token.py:37`) with an import of the factory and `_auth_logger = get_logger("auth")`. Add `from restgdf._logging import get_logger` to the imports.
2. `"auth"` is a valid suffix in `LOGGER_SUFFIXES` and `get_logger`'s NullHandler-attach + span-filter-attach are both idempotent, so no duplicate handler/filter results even though `_install_span_context_filter()` already added a `_SpanContextFilter` to `restgdf.auth` at import. No light-core boundary concern (`_logging.py` is pure stdlib and already imported by `_retry.py`/`getgdf.py`/`_pagination.py`).
3. The bare `import logging` at `token.py:17` may still be needed elsewhere; only the `getLogger` call changes. Verify `logging` is otherwise unused before removing the import (it is currently used only for this call — confirm during the edit).
4. Optionally add an assertion to the telemetry/taxonomy contract test that the module-level `token._auth_logger` carries a `NullHandler` (current tests exercise the factory, not the real logger object). This test lives in W5's `tests/test_telemetry_log_span_correlation.py` territory; if added here, place it in a W2-owned test or coordinate with W5 — do NOT write into a W5-owned test file. Default: skip the extra assertion to avoid the cross-owner test edit.
**Acceptance criteria**
- [ ] `restgdf.utils.token._auth_logger` is the object returned by `get_logger("auth")` and carries a `NullHandler` (verifiable in a REPL/test).
- [ ] No duplicate `NullHandler`/`_SpanContextFilter` on `restgdf.auth` after import.
- [ ] Existing auth-refresh logging tests still pass.
**Validation** — lint; test; single: `.\.venv\Scripts\python.exe -m pytest -k token`.
**Risks & rollback** — Very low risk (one-line swap). Rollback: restore the `logging.getLogger` line. Anti-recommendation enforced: do NOT add a `get_logger("")` call to fix the root-logger NullHandler gap here.

---

### W2-4 · Double-check token_needs_update in the reactive 498 path (single-flight)
**Audit refs:** ASYNC-01 · **Severity:** medium · **Effort:** S · **Milestone:** M2
**Depends:** — · **Blocks:** —
**Split-ownership:** —
**Scope** — In: add a snapshot-based double-check inside the 498 refresh branch so N concurrent 498 responses trigger exactly one `/generateToken` POST; add a concurrent-498 regression test. Out-of-scope: do NOT gate the 498 refresh on `token_needs_update()` (the audit's explicit anti-recommendation — after a server-side invalidation the local token still looks valid so that predicate would suppress the needed refresh).
**Spec**
1. In `restgdf/utils/token.py`, `_call_with_auth_retry` currently refreshes UNCONDITIONALLY in the 498 branch under the lock (verified: `restgdf/utils/token.py:389-394` — `if self._refresh_lock is None: ... async with self._refresh_lock: await self.update_token()`).
2. Capture `tok_before = self.token` BEFORE issuing the request (i.e. before the `session_method(...)` call at `token.py:373-379`). In the 498 branch, change the body to `async with self._refresh_lock: if self.token == tok_before: await self.update_token()`. The first task to win the lock refreshes; later tasks observe `self.token != tok_before` and skip the redundant `/generateToken`, then proceed to retry with the current token. This mirrors the proactive `update_token_if_needed` double-check (verified: `restgdf/utils/token.py:341-343`).
3. Do NOT use `token_needs_update()` as the guard — use the snapshot-equality check (`self.token == tok_before`).
4. Add a concurrent-498 regression test in `tests/test_token_498_499.py` asserting exactly one `update_token` call under N simultaneous 498 responses (e.g. fire K tasks against a session whose first response per task is 498). The existing single-requester tests use `AsyncMock` that keeps `self.token` unchanged, so the snapshot check keeps them green (the mock's `update_token` does not mutate `self.token`, so verify the regression test mutates `self.token` in its `update_token` side-effect to exercise the skip path).
**Acceptance criteria**
- [ ] Red-first: a concurrent-498 test asserting `update_token.await_count == 1` under N concurrent 498 responses FAILS before the fix and passes after.
- [ ] Existing `test_498_triggers_refresh_and_retry` and `test_498_retries_exactly_once` still pass.
- [ ] `test_499_raises_auth_not_attached` still passes (499 path untouched).
**Validation** — lint; single: `.\.venv\Scripts\python.exe -m pytest tests/test_token_498_499.py`; test.
**Risks & rollback** — Risk: if the regression test's mock does not mutate `self.token`, every concurrent task would still refresh (test would not exercise the skip). Ensure the test's `update_token` side-effect rotates `self.token`. Rollback: revert the snapshot capture + guard to the unconditional refresh. Anti-recommendation enforced: no `token_needs_update()` gate.

---

### W2-10 · Apply user_agent + verify_ssl at the token/_http request seams (verify_ssl part B)
**Audit refs:** CONFIG-01, AUTH-03 · **Severity:** high · **Effort:** M · **Milestone:** M2
**Depends:** W3-1 (TransportConfig source of truth) · **Blocks:** W6-4 (MIGRATION verify_ssl prose, jointly with W3-1)
**Split-ownership:** This is PART B of the consolidated verify_ssl/user_agent wiring (root: CONFIG-01 + AUTH-03). **Part A** (the `TransportConfig.user_agent`/`verify_ssl` source of truth + the verify_ssl reconciliation decision) is **W3-1**. **Part C** (the bare `get_gdf` session built with the configured ssl connector) is **W4-5**. This item owns ONLY: (1) `default_headers()` injecting the configured UA, and (2) `token._call_with_auth_retry` forwarding `ssl` to data requests.
**Scope** — In: (a) make `default_headers()` use `get_config().transport.user_agent` as the `User-Agent` default instead of the hardcoded `"Mozilla/5.0"`; (b) make `ArcGISTokenSession._call_with_auth_retry` forward `ssl=self.verify_ssl` to data requests via `setdefault` (won't clobber a caller-supplied `ssl=`). Out-of-scope: do NOT blanket-inject `ssl=` into every `_arcgis_request` kwarg (the audit's anti-recommendation — per-request `ssl=` conflicts with callers who built their own connector); do NOT touch the bare-`ClientSession` `get_gdf` seam (that is W4-5); do NOT change the `verify_ssl` source-of-truth reconciliation (that decision is W3-1); do NOT strip `ssl=` off the token POST to make docs literally true (anti-recommendation — re-breaks the self-signed-Enterprise token scenario).
**Spec**
1. **user_agent.** In `restgdf/utils/_http.py`, `DEFAULT_METADATA_HEADERS` hardcodes `"User-Agent": "Mozilla/5.0"` and `default_headers()` merges only that constant (verified: `restgdf/utils/_http.py:18-21, 32-34`). Change `default_headers()` to inject `get_config().transport.user_agent` as the `User-Agent` default. Preserve the existing merge order `{**DEFAULT, **(headers or {})}` so an explicit caller header still wins (back-compat-safe). NOTE the `"Mozilla/5.0"` string is a deliberate ArcGIS-compat UA — swapping the default to `restgdf/<version>` is a behavior change; the CHANGELOG note for that is W6 (some Esri WAFs sniff UA). Use whatever default `TransportConfig.user_agent` resolves to from W3-1 (verified: `TransportConfig.user_agent` exists with a `_default_user_agent` factory at `restgdf/_config.py:79`).
2. **verify_ssl.** In `restgdf/utils/token.py`, `_call_with_auth_retry` builds `session_method(url, **{payload_key: request_payload}, headers=request_headers, **kwargs)` and never injects `ssl` (verified: `restgdf/utils/token.py:373-379, 403-408`). Add `kwargs.setdefault("ssl", self.verify_ssl)` before the `session_method` call (and it carries into the retry call which reuses `**kwargs`). `setdefault` ensures a caller-supplied `ssl=` is not clobbered. This matches the `/generateToken` POST which already forwards `ssl=self.verify_ssl` (verified: `restgdf/utils/token.py:278`).
3. The `self.verify_ssl` source: `ArcGISTokenSession.verify_ssl` (dataclass field, verified: `restgdf/utils/token.py:122`), synced from `TokenSessionConfig.verify_ssl` in `__post_init__` (verified: `restgdf/utils/token.py:137, 159`). Whether this should default-from `TransportConfig.verify_ssl` is the W3-1 reconciliation decision — consume whatever W3-1 lands; do NOT re-decide it here.
4. Do NOT add `ssl=` to `ArcGISTokenSession.get`/`post` signatures (they already forward `**kwargs` into `_call_with_auth_retry`, so the `setdefault` covers them).
5. Add/extend a test mirroring the existing token-only BL-05 test (`tests/test_verify_ssl_plumbing.py`, W2-adjacent) asserting a `verify_ssl=False` data request forwards `ssl=False`. If `tests/test_verify_ssl_plumbing.py` is not in the W2 `owns[]` list, place the new assertion in a W2-owned test file (e.g. extend `tests/test_token_498_499.py` or a new `tests/`-level test) rather than editing a non-owned file — confirm ownership before writing.
**Acceptance criteria**
- [ ] Red-first: a test asserting a `verify_ssl=False` data request forwards `ssl=False` to the inner session FAILS before the fix and passes after.
- [ ] A test asserting `default_headers()` emits the configured `user_agent` (set via env/`reset_config_cache`) instead of `"Mozilla/5.0"`.
- [ ] A caller-supplied `ssl=` kwarg is NOT clobbered (setdefault verified by test).
- [ ] Existing token-POST `ssl` plumbing test (BL-05) still passes.
- [ ] Doc-sync: MIGRATION verify_ssl prose delegated to W6-4 (depends on this + W3-1).
**Validation** — lint; single: `.\.venv\Scripts\python.exe -m pytest -k "verify_ssl or token or http"`; test; coverage.
**Risks & rollback** — Risk: swapping the default UA could trip a UA-sniffing Esri WAF — mitigated because callers can override and the change is gated on whatever W3-1 sets as the default. Anti-recommendations enforced: no blanket per-request `ssl=` injection into `_arcgis_request`; no stripping of the token-POST `ssl=`. Rollback: revert `default_headers()` to the constant and remove the `setdefault("ssl", ...)` line.

---

### W2-7 · Reject NaN/Inf in _parse_retry_after
**Audit refs:** TRANSPORT-02 · **Severity:** low · **Effort:** S · **Milestone:** M2
**Depends:** — · **Blocks:** —
**Split-ownership:** —
**Scope** — In: reject NaN/Inf/-Inf at the single `_parse_retry_after` source so non-finite values cannot poison `RateLimitError.retry_after` or the 429 cooldown deadline. Out-of-scope: do NOT clamp NaN in `_retry.py`'s `min(ra, ...)` expression (the audit's anti-recommendation — that leaves the public `retry_after` attribute poisoned and patches only one of two sinks).
**Spec**
1. In `restgdf/resilience/_errors.py`, `_parse_retry_after` does `seconds = float(value); if seconds < 0: return None; return seconds` (verified: `restgdf/resilience/_errors.py:23-27`). NaN/Inf both pass the `< 0` check.
2. Add `import math` and replace `if seconds < 0: return None` with `if not math.isfinite(seconds) or seconds < 0: return None`. This rejects NaN/Inf/-Inf at the single source, fixing both the 429 cooldown deadline (`restgdf/resilience/_retry.py:194-200`) and the public `RateLimitError.retry_after` attribute (`restgdf/resilience/_retry.py:220-227`). Stdlib-only (no import-boundary concern), aligns with the docstring contract ("Returns None for empty, unparsable, or negative values").
3. The HTTP-date branch already returns `max(0.0, delta)` (finite); leave it unchanged.
**Acceptance criteria**
- [ ] Red-first: parametric test asserting `_parse_retry_after("nan") is None`, `_parse_retry_after("inf") is None`, `_parse_retry_after("-inf") is None` FAILS before the fix and passes after.
- [ ] Existing parametric cases still pass: `"120"` → `120.0`, `"-5"` → `None`, garbage → `None`.
- [ ] Test added to `tests/test_resilience_retry.py`.
**Validation** — lint; single: `.\.venv\Scripts\python.exe -m pytest tests/test_resilience_retry.py`; test.
**Risks & rollback** — Negligible risk; stdlib-only single-line guard. Anti-recommendation enforced: fix at the parse source, not at the `min()` sink. Rollback: revert the guard + `import math`.

---

### W2-8 · Broaden require_* to catch broken-but-present optional deps (ImportError)
**Audit refs:** OPTDEPS-01 · **Severity:** low · **Effort:** S · **Milestone:** M2
**Depends:** — · **Blocks:** —
**Split-ownership:** —
**Scope** — In: broaden the catch in `_import_optional_module` from `ModuleNotFoundError` to `ImportError` so a present-but-unimportable geo dependency (broken GDAL/shapely native layer) surfaces as `OptionalDependencyError` with the `restgdf[geo]` hint. Out-of-scope: do NOT widen to `except Exception` (the audit's anti-recommendation — keep genuinely unrelated runtime errors surfacing).
**Spec**
1. In `restgdf/utils/_optional.py`, `_import_optional_module` wraps only the narrow subclass: `except ModuleNotFoundError as exc:` (verified: `restgdf/utils/_optional.py:31-35`).
2. Change `except ModuleNotFoundError as exc:` to `except ImportError as exc:`. Safe and strictly more compliant: `ModuleNotFoundError` is a subclass of `ImportError` (existing path unchanged); the `missing_module = exc.name or module_name` line already handles a plain `ImportError` whose `.name` is `None` (falls back to the literal module name like `"geopandas"`); the `raise _optional_dependency_error(...) from exc` executes inside the except; and `OptionalDependencyError` itself multi-inherits `ModuleNotFoundError`→`ImportError` (verified: `restgdf/errors.py:68`) so every downstream `except ImportError`/`except ModuleNotFoundError`/`except OptionalDependencyError` block keeps matching.
3. This aligns the geo gate with the codebase's own pattern — telemetry gates and the resilience gate already use `except ImportError`.
4. Add a test in `tests/test_base_install.py` that patches `restgdf.utils._optional.import_module` to raise a bare `ImportError("DLL load failed ...")` (with `.name=None`) and asserts `OptionalDependencyError` is raised with the `restgdf[geo]` hint.
**Acceptance criteria**
- [ ] Red-first: a test patching `import_module` to raise a bare `ImportError` (`.name=None`) and asserting `OptionalDependencyError` with the `restgdf[geo]` hint FAILS before the fix and passes after.
- [ ] Existing missing-package path (a `ModuleNotFoundError`) still raises `OptionalDependencyError` with the correct module name.
- [ ] Genuinely unrelated non-ImportError exceptions during import still propagate raw (not swallowed).
**Validation** — lint; single: `.\.venv\Scripts\python.exe -m pytest tests/test_base_install.py`; test; coverage.
**Risks & rollback** — Low risk; `ImportError` is the correct breadth. Anti-recommendation enforced: do NOT widen to `except Exception`. Rollback: revert to `except ModuleNotFoundError`.

---

### W2-2 · Raise InvalidCredentialsError on /generateToken 4xx (stop raw-aiohttp escape)
**Audit refs:** AUTH-02, ERRTAX-01 · **Severity:** medium · **Effort:** M · **Milestone:** M3
**Depends:** — · **Blocks:** W2-3 (retry-filter ordering), W6-3 (ARCHITECTURE AUTH-02 prose), W6-4 (MIGRATION AUTH-02 prose)
**Split-ownership:** Consolidates AUTH-02 (dead taxonomy) and ERRTAX-01 (umbrella escape) — same root cause (a 4xx `/generateToken` reply escapes as raw `aiohttp.ClientResponseError`). Code fix owned here. Doc reconciliation: ARCHITECTURE = W6-3, MIGRATION = W6-4. The `TokenRequiredError`-vs-`AuthNotAttachedError` 499 reconciliation is a decision surfaced below.
**Scope** — In: wrap ONLY the `resp.raise_for_status()` boundary in `update_token` so a true-HTTP 4xx maps to `InvalidCredentialsError` (4xx auth) / `RestgdfResponseError` (other non-2xx) under the `RestgdfError` umbrella, chained `from exc`, raised in the deterministic (non-retried) branch; align the `InvalidCredentialsError`/`TokenRequiredError` docstrings with reality. Out-of-scope: do NOT alter the HTTP-200 + JSON-error-envelope path (already correct/tested — `raise_for_status` no-ops on 200 and `TokenResponse` strict-tier rejects the `{"error":{...}}` envelope as `RestgdfResponseError`); do NOT replace `raise_for_status` with blanket non-2xx body re-parsing (anti-recommendation — risks misclassifying the 200-envelope path); do NOT naively wrap the whole `except Exception: raise` in `InvalidCredentialsError` (anti-recommendation — would mislabel timeouts/DNS/TLS errors as credential failures).
**Spec**
1. In `restgdf/utils/token.py`, `update_token` calls `resp.raise_for_status()` (verified: `restgdf/utils/token.py:280`) which raises `aiohttp.ClientResponseError` on a 4xx; that error is not in `_RETRYABLE_ERRORS` (verified: `restgdf/utils/token.py:43`) so it hits the bare `except Exception: ... raise` (verified: `restgdf/utils/token.py:298-305`) and propagates UNWRAPPED.
2. Wrap only the `raise_for_status()` boundary: `try: resp.raise_for_status() except aiohttp.ClientResponseError as exc:` then map `exc.status in (400, 401, 403)` → `InvalidCredentialsError(..., cause=exc)` (the `_AuthSubtypeBase` constructor accepts `cause=`; verified: `restgdf/errors.py:227-247`, `InvalidCredentialsError` at `restgdf/errors.py:268-272`), other non-2xx → `RestgdfResponseError(..., context=self.token_url)`, chaining `from exc`. Raise it in the deterministic branch so it is NOT retried (it must escape the `for attempt` loop without hitting the `_RETRYABLE_ERRORS` backoff).
3. Leave the HTTP-200 + JSON-error-envelope path untouched: `raise_for_status` no-ops on 200; `_parse_response(TokenResponse, ...)` already rejects `{"error":{...}}` as `RestgdfResponseError` (verified: the parse call at `restgdf/utils/token.py:282`).
4. Align docstrings with the new reality: `InvalidCredentialsError` docstring currently asserts "Raised on 400 / bad credentials from `/generateToken`" (verified: `restgdf/errors.py:269`) — this is now TRUE for the 4xx-status path; keep it but ensure the wording matches (4xx, not only 400). `TokenRequiredError` docstring asserts "Raised when ArcGIS returns error code 499" (verified: `restgdf/errors.py:303`) which CONFLICTS with `AuthNotAttachedError` (the type actually raised at `restgdf/utils/token.py:383-387`). Resolve the 499 conflict (see Decision required).
5. Do NOT wrap the dominant 200-path or the whole `except Exception`.
**Acceptance criteria**
- [ ] Red-first: a test asserting a 400/401 `/generateToken` response raises `InvalidCredentialsError` (catchable as `AuthenticationError` and `RestgdfError` and `PermissionError`) FAILS before the fix (currently raises raw `aiohttp.ClientResponseError`) and passes after.
- [ ] A test asserting the HTTP-200 `{"error":{...}}` bad-creds envelope still surfaces as `RestgdfResponseError` (unchanged).
- [ ] A test asserting a timeout/connection error during refresh still hits the retry ladder (NOT reclassified as `InvalidCredentialsError`).
- [ ] `InvalidCredentialsError` / `TokenRequiredError` docstrings no longer advertise an unimplemented or conflicting contract.
- [ ] Doc-sync: ARCHITECTURE:71-73 (W6-3) and MIGRATION:145,147 (W6-4) reconciled in those items.
**Validation** — lint; single: `.\.venv\Scripts\python.exe -m pytest -k "token or auth or error"`; test; coverage.
**Risks & rollback** — Risk: mapping `403` to `InvalidCredentialsError` could be debatable (403 may be authz not authn) — the audit suggests `(400, 401, 403)`; if 403 semantics are uncertain, restrict to `(400, 401)` and raise `RestgdfResponseError` for 403. Anti-recommendations enforced: scoped to the `raise_for_status` edge only; no blanket re-parse; no whole-`except Exception` wrap. Rollback: revert the `try/except aiohttp.ClientResponseError` block around `raise_for_status`; raw-error escape returns.
**Decision required:** see Decision block below — `TokenRequiredError` (499) canonical vs demote to `AuthNotAttachedError`.

---

### W2-3 · Stop the token retry filter from swallowing deterministic auth errors
**Audit refs:** ERRTAX-02 · **Severity:** medium · **Effort:** S · **Milestone:** M3
**Depends:** W2-2 · **Blocks:** —
**Split-ownership:** Shares the `update_token` retry-loop region with W2-2; this item owns the handler-ordering fix (the `except RestgdfError: raise` guard), W2-2 owns the `raise_for_status` 4xx mapping. Coordinate so both land coherently in the same loop.
**Scope** — In: add an `except RestgdfError: raise` (or narrower `except AuthenticationError: raise`) handler BEFORE `except _RETRYABLE_ERRORS` so restgdf's own deterministic errors (e.g. the None-credentials `AuthenticationError` from `token_request_payload`, which co-inherits `OSError` via `PermissionError`) are never swept into the `OSError` retry bucket. Out-of-scope: do NOT widen or narrow `_RETRYABLE_ERRORS` (anti-recommendation — `OSError` is intentionally retryable for genuine socket-layer transients; the fix belongs in handler ordering).
**Spec**
1. In `restgdf/utils/token.py`, `_RETRYABLE_ERRORS = (OSError, asyncio.TimeoutError, ConnectionError)` (verified: `restgdf/utils/token.py:43`). `AuthenticationError(RestgdfResponseError, PermissionError)` → `PermissionError` → `OSError` (verified: `restgdf/errors.py:201`), so the None-credentials `AuthenticationError` raised by `token_request_payload` (verified: `restgdf/utils/token.py:172-177`, raised inside the try at `restgdf/utils/token.py:275` via `data=self.token_request_payload`) is caught by `except _RETRYABLE_ERRORS` (verified: `restgdf/utils/token.py:287`), retried 3x with backoff, then re-raised as `TokenRefreshFailedError` (verified: `restgdf/utils/token.py:307`) — the wrong class, contradicting the docstring/MIGRATION "deterministic errors propagate immediately" contract.
2. Add `except RestgdfError: raise` (import `RestgdfError` from `restgdf.errors`) as a handler BEFORE the `except _RETRYABLE_ERRORS as exc:` clause at `restgdf/utils/token.py:287`. Prefer `RestgdfError` over the narrower `AuthenticationError` because it also covers any future restgdf exception that inherits an `OSError`/`TimeoutError` builtin (and covers the `RestgdfResponseError` from `_parse_response` and the W2-2 `InvalidCredentialsError`). Order matters: the new `except RestgdfError: raise` must precede `except _RETRYABLE_ERRORS` (Python matches the first compatible handler).
3. This is safe: nothing raised inside the try that is a `RestgdfError` is ever a transient condition that should be retried.
4. Coordinate with W2-2: the W2-2 `InvalidCredentialsError` (a `RestgdfError`) will also propagate immediately through this guard — that is the intended behavior. Ensure the `except RestgdfError: raise` sits above `except _RETRYABLE_ERRORS` and below the W2-2 `raise_for_status` try/except (which is inside the loop body, before the network call returns).
5. Add a regression test asserting a None-credentials `update_token()` raises `AuthenticationError` immediately with zero `asyncio.sleep` calls (none exists today).
**Acceptance criteria**
- [ ] Red-first: a test asserting a None-credentials `update_token()` raises `AuthenticationError` (NOT `TokenRefreshFailedError`) with zero `asyncio.sleep` calls FAILS before the fix and passes after.
- [ ] Genuine `OSError`/`ConnectionError`/`asyncio.TimeoutError` during refresh still hit the retry ladder (3 attempts + backoff) and then `TokenRefreshFailedError`.
- [ ] W2-2's `InvalidCredentialsError` (if landed) also propagates immediately through the new guard (no retry).
**Validation** — lint; single: `.\.venv\Scripts\python.exe -m pytest -k "token or auth"`; test; coverage.
**Risks & rollback** — Risk: ordering bug if the new handler is placed after `except _RETRYABLE_ERRORS`. Verify handler order in review. Anti-recommendation enforced: do NOT touch the `_RETRYABLE_ERRORS` tuple. Rollback: remove the `except RestgdfError: raise` clause.

---

### W2-5 · Detect 498/499 from the in-body ArcGIS error envelope, not only HTTP status
**Audit refs:** ERRTAX-03 · **Severity:** low · **Effort:** M · **Milestone:** M3
**Depends:** — · **Blocks:** —
**Split-ownership:** —
**Scope** — In: extend 498/499 auth-condition detection to the in-body ArcGIS error envelope (`{"error":{"code":498|499,...}}` returned with HTTP 200), which is the common ArcGIS wire shape. Out-of-scope: do NOT naively call `resp.json()` inside `_call_with_auth_retry` (the audit's anti-recommendation — downstream callers consume the body themselves, so reading it in the retry helper breaks the response stream for every caller).
**Spec**
1. In `restgdf/utils/token.py`, `_call_with_auth_retry` resolves `status = getattr(resp, "status", 200)` and branches purely on HTTP `status == 499` / `status == 498` (verified: `restgdf/utils/token.py:381, 383, 389`). ArcGIS commonly returns 498/499 as HTTP 200 with a JSON error envelope, which this never catches.
2. This is a DOCUMENTED-SCOPE enhancement (HTTP-status-only is the documented contract in CHANGELOG BL-11, MIGRATION R-14, ARCHITECTURE "# HTTP 498/499"). Implementing it changes documented behavior — coordinate the doc updates (W6-3/W6-4/CHANGELOG W6-5) and gate this item behind a maintainer go/no-go (it is low severity; deferral is acceptable per the audit, which frames it as "resilience/ergonomics improvement, not a correctness emergency").
3. If implementing: do NOT consume the body in `_call_with_auth_retry`. Instead: (a) add a shared `_arcgis_auth_code(payload) -> int | None` helper; (b) have `_parse_response` map in-body code 498 → `TokenExpiredError` and 499 → `AuthNotAttachedError` (currently the generic `RestgdfResponseError` at `restgdf/_models/_drift.py:189-200` per the audit — verify exact lines in the current tree before editing); (c) for the 498 auto-refresh-and-retry to fire on the in-body shape, the refresh/retry logic must live where the body is available (lift above `_parse_response` or into the parse layer) — it cannot stay purely in `_call_with_auth_retry`. NOTE: `_parse_response` lives in `restgdf/_models/_drift.py` which is owned by **W5** (`_models/_drift.py` is in W5's `owns[]`). If step (b) requires editing `_drift.py`, that edit must be delegated to / coordinated with W5 — this item is single-writer only on `token.py`. Surface this cross-owner dependency at planning time.
4. The 499 in-body case currently degrades to `RestgdfResponseError` (callers catching `RestgdfResponseError` already catch it); only callers catching `TokenExpiredError`/`AuthNotAttachedError` specifically miss the in-body shape. No data is silently lost today.
**Acceptance criteria**
- [ ] Maintainer go/no-go recorded (documented-scope change; deferral acceptable).
- [ ] If implemented (red-first): a test asserting an HTTP-200 `{"error":{"code":498}}` envelope triggers a single-flight refresh + retry, and `{"error":{"code":499}}` raises `AuthNotAttachedError`, FAILS before the fix and passes after.
- [ ] Response stream is NOT consumed by the retry helper (no `resp.json()` in `_call_with_auth_retry`) — existing callers' `await resp.json(content_type=None)` still works.
- [ ] Any `_drift.py` edit is owned/approved by W5; doc updates delegated to W6-3/W6-4/W6-5.
**Validation** — lint; single: `.\.venv\Scripts\python.exe -m pytest -k "token or auth or drift or parse"`; test; coverage.
**Risks & rollback** — Risk: this is a cross-layer refactor touching the resp-returning contract and (potentially) W5-owned `_drift.py`; high coordination cost for a low-severity item. Strongly consider deferral. Anti-recommendation enforced: no body consumption in the retry helper. Rollback: revert the helper + parse-layer changes; HTTP-status-only detection returns.

---

### W2-11 · Make token sessions read the AuthConfig refresh-threshold knobs (consume part)
**Audit refs:** AUTH-04, CONFIG-02 · **Severity:** low · **Effort:** M · **Milestone:** M3
**Depends:** W3-3 (expose AuthConfig for token-session construction), W3-2 (wire-or-retire the refresh-threshold knobs) · **Blocks:** —
**Split-ownership:** Consume-side of the AuthConfig wiring. **Config source** is W3-2 (refresh-threshold knobs) / W3-3 (AuthConfig exposure). **FeatureLayer construction seam** is W5-14. This item owns ONLY the `token.py` consume path and the `credentials.py` factory (if a `TokenSessionConfig.from_auth_config` is added).
**Scope** — In: depending on the W3-2/W3-3 decisions, either (a) add an opt-in `TokenSessionConfig.from_auth_config(get_config().auth)` convenience factory + a docstring note on the consume side, OR (b) add the docstring-only clarification that `AuthConfig` refresh knobs are config holders not auto-applied. Out-of-scope: do NOT make `ArcGISTokenSession.__post_init__` read `get_config().auth` as an implicit default (the audit's explicit anti-recommendation — `get_config()` is a process-wide LRU-cached singleton; implicit sourcing would make one env var flip transport for every session in the process and interact badly with the GET→POST credential guard and explicit-config precedence). Do NOT delete the `RESTGDF_AUTH_REFRESH_THRESHOLD_S` env var / `RESTGDF_REFRESH_THRESHOLD` alias / `Settings.refresh_threshold_seconds` (anti-recommendation — documented back-compat seam pinned by tests).
**Spec**
1. `AuthConfig` declares `refresh_threshold_s=60.0`, `refresh_leeway_s=120.0`, `clock_skew_s=30.0` (verified: `restgdf/_config.py:135-137`); these are never read by any token session today. The session's actual refresh window comes from `ArcGISTokenSession.token_refresh_threshold` (dataclass default 60, verified: `restgdf/utils/token.py:119`) or, when a `TokenSessionConfig` is built, `refresh_leeway_seconds(120) + clock_skew_seconds(30)` (verified: `restgdf/_models/credentials.py:78-79`; combined in `__post_init__` at `restgdf/utils/token.py:138-140`).
2. Consume whatever W3-2/W3-3 land. If the decision is to wire (opt-in): add a `TokenSessionConfig.from_auth_config(auth_config)` classmethod in `restgdf/_models/credentials.py` that derives `refresh_leeway_seconds`/`clock_skew_seconds`/`token_url`/`transport` from the `AuthConfig` instance, so callers who want the env var to drive refresh timing can opt in. NOTE the default split: a bare `TokenSessionConfig` yields `refresh_leeway(120) + clock_skew(30) = 150` while the `ArcGISTokenSession` dataclass default is 60 — a `from_auth_config` path is internally consistent and reconciles this.
3. Add a docstring note on the consume side (`ArcGISTokenSession` and/or `TokenSessionConfig`) naming the caller-constructs-the-session model: the threshold fields are config holders, not auto-applied; construct `TokenSessionConfig` (or `from_auth_config`) and pass it explicitly.
4. This is a doc/DX clarification (or an opt-in factory), NOT a behavior change to existing construction paths.
**Acceptance criteria**
- [ ] W3-2/W3-3 decisions consumed (wire vs retire); this item's edits match.
- [ ] If a `from_auth_config` factory is added: a test asserting `TokenSessionConfig.from_auth_config(AuthConfig(refresh_leeway_s=300))` yields a session whose effective threshold reflects the AuthConfig values (red-first for the new factory).
- [ ] `ArcGISTokenSession.__post_init__` does NOT implicitly read `get_config()` (no behavior change to existing construction).
- [ ] Back-compat env vars/aliases and `Settings.refresh_threshold_seconds` untouched (existing deprecation tests still pass).
- [ ] Doc-sync: MIGRATION AuthConfig prose delegated to W6-4; README/docs to W6-6/W6-7.
**Validation** — lint; single: `.\.venv\Scripts\python.exe -m pytest -k "token or auth or config or settings"`; test; coverage.
**Risks & rollback** — Risk: scope drift into implicit auto-wiring — strictly avoid. Anti-recommendations enforced: no implicit `__post_init__` `get_config()` read; no deletion of the back-compat seam. Rollback: remove the `from_auth_config` factory + docstring note.

---

### W2-13 · Wire RetryConfig/LimiterConfig into the resilience executor
**Audit refs:** TRANSPORT-01 · **Severity:** medium · **Effort:** M · **Milestone:** M3
**Depends:** — · **Blocks:** —
**Split-ownership:** —
**Scope** — In: per the audit's preferred path (b) — the immediate, low-risk resolution — align the inert-config contract so callers are not silently misled (emit a one-time warning when `RESTGDF_RETRY_*`/`RESTGDF_LIMITER_*` are set but unhonored, and/or add the deferral caveat to the executor side); path (a) full wiring requires a config-ownership decision first. Out-of-scope: do NOT ship path (a) as a blind decorator edit threading `RetryConfig` into the `@stamina.retry(...)` decorator (the audit's anti-recommendation — there is a genuine semantic collision between `LimiterConfig.rate_per_host` and `ResilienceConfig.rate_per_service_root_per_second`, two competing rate-limit knobs; wiring both without deciding ownership creates ambiguous/duplicated rate limiting).
**Spec**
1. `_do_retried_request` hardcodes `@stamina.retry(on=retry_on, attempts=5, timeout=60.0, wait_initial=0.5, wait_max=10.0, wait_jitter=1.0)` (verified: `restgdf/resilience/_retry.py:167-174`). Nothing reads `RetryConfig.max_attempts`/`max_delay_s` or `LimiterConfig.rate_per_host`; the executor reads only `ResilienceConfig` (verified: `ResilientSession.__init__(self, inner, config: ResilienceConfig)` at `restgdf/resilience/_retry.py:50-60`, and the env spec wires `retry.*`/`limiter.*` at `restgdf/_config.py:225-229`).
2. **Default path (path b):** the executor receives a `ResilienceConfig`, not the aggregate `Config`, so it cannot read `RetryConfig`/`LimiterConfig` without a plumbing change. The low-risk fix is: (a) emit a one-time warning (via `warnings.warn` or the auth/retry logger) when `RESTGDF_RETRY_MAX_ATTEMPTS`/`RESTGDF_RETRY_MAX_DELAY_S`/`RESTGDF_LIMITER_*` are set but inert — this can be done by checking `get_config().retry`/`.limiter` against defaults at executor construction or first use; (b) the deferral caveat in the `RetryConfig` docstring already exists (`restgdf/_config.py:93` — "phase-3a wires the executor"); ensure `LimiterConfig` carries the same. The MIGRATION prose fixes ("configurable max-attempts" claim) are W6-4.
3. **If path (a) full wiring is chosen (requires the Decision below):** first decide config ownership between `LimiterConfig.rate_per_host` (host granularity) and `ResilienceConfig.rate_per_service_root_per_second` (service-root granularity) — consolidate or define precedence. THEN thread `max_attempts` → `attempts` and `max_delay_s` → `timeout` into the `@stamina.retry` decorator. `_do_retried_request` already receives a config object, but it is `ResilienceConfig`; threading `RetryConfig` means either passing the aggregate `Config` (or the `RetryConfig` sub-config) through `ResilientSession` → `_RetriedCtx._run` → `_do_retried_request`.
4. **`_config.py` collision note:** if path (a) requires a NEW config field (e.g. a precedence flag or a consolidated rate-limit field), `restgdf/_config.py` is owned single-writer by **W3** — the additive `_config.py` edit MUST be delegated to W3 to avoid a collision. This item is single-writer only on `restgdf/resilience/_retry.py`.
5. The `RetryConfig`/`LimiterConfig` sub-configs already exist in `_config.py` (verified: `restgdf/_config.py:92-99` RetryConfig, `102-108` LimiterConfig) — no new field is needed for path (b).
**Acceptance criteria**
- [ ] Decision recorded (path b warning-only now vs path a full wiring with config-ownership resolution).
- [ ] Path (b): a test asserting that setting `RESTGDF_RETRY_MAX_ATTEMPTS` while the executor still uses 5 attempts emits a one-time warning (red-first for the warning).
- [ ] Path (a) only: a test asserting `RetryConfig(max_attempts=10, max_delay_s=120)` actually changes the executor's `attempts`/`timeout`, AND the `rate_per_host`/`rate_per_service_root` collision is resolved with a documented precedence (red-first).
- [ ] No blind decorator edit without the config-ownership decision.
- [ ] Any new `_config.py` field delegated to W3.
- [ ] Doc-sync: MIGRATION "configurable max-attempts" claim → W6-4.
**Validation** — lint; single: `.\.venv\Scripts\python.exe -m pytest tests/test_resilience_retry.py`; test; coverage.
**Risks & rollback** — Risk: path (a) without resolving the `rate_per_host` vs `rate_per_service_root` collision produces ambiguous/duplicated rate limiting; this is why the default is path (b). Anti-recommendation enforced: no blind `@stamina.retry` decorator edit. Rollback: remove the warning (path b) or revert the threading + config field (path a).
**Decision required:** see Decision block — path (b) warning-only vs path (a) full wiring + config-ownership resolution.

---

### W2-9 · Decide & track the ValueError co-inheritance removal (semver)
**Audit refs:** ERRTAX-04 · **Severity:** low · **Effort:** S · **Milestone:** M4
**Depends:** — · **Blocks:** —
**Split-ownership:** Code/docstring fix owned here (`errors.py`). CHANGELOG/MIGRATION prose-side is W6-4/W6-5.
**Scope** — In: align the `ConfigurationError` docstring with the project's already-stated "removal only in a major release" policy (docstring text only, zero behavior change). Out-of-scope: do NOT add a 3.1-targeted `DeprecationWarning` on the `ValueError` base (anti-recommendation — that would itself be the breaking signal you are trying to avoid promising in a minor, and is more work); do NOT add a test pinning "removal in 3.1" (anti-recommendation — codifies the semver violation); do NOT add a CHANGELOG note announcing a 3.1 removal (anti-recommendation — legitimizes a SemVer-breaking minor).
**Spec**
1. In `restgdf/errors.py`, the `ConfigurationError` docstring states "The `ValueError` base will be dropped in 3.1+." (verified: `restgdf/errors.py:62-64`). The same removal is implied for `RestgdfResponseError(RestgdfError, ValueError)` (verified: `restgdf/errors.py:77`, hierarchy note at `restgdf/errors.py:13-19`).
2. Replace "The `ValueError` base will be dropped in 3.1+." with wording consistent with the documented "removal only in a major release" policy — e.g. "The `ValueError` base is a back-compat shim and will only be removed in a future major release (>=4.0), preceded by a `DeprecationWarning`." This single-source-of-truth fix resolves the contradiction with zero behavior change and no import-boundary risk (docstring text only).
3. The CHANGELOG/MIGRATION prose reconciliation (e.g. MIGRATION:361-363, MIGRATION:489-494) is W6-4/W6-5 — do NOT edit docs here.
**Acceptance criteria**
- [ ] `ConfigurationError` docstring no longer promises a 3.1 removal; matches the "major-release-only, deprecation-warned" policy.
- [ ] No behavior change: `except ValueError` still catches `ConfigurationError`/`RestgdfResponseError` (existing MRO tests still pass).
- [ ] No new `DeprecationWarning`, no removal-pinning test, no CHANGELOG 3.1-removal note added.
- [ ] Doc-sync: CHANGELOG/MIGRATION reconciliation delegated to W6-4/W6-5.
**Validation** — lint; single: `.\.venv\Scripts\python.exe -m pytest -k "error_mro or taxonomy or errors"`; test.
**Risks & rollback** — Negligible (docstring text only). Anti-recommendations enforced: no deprecation machinery, no removal-pinning test, no CHANGELOG removal note. Rollback: restore the original docstring sentence.
**Decision required:** see Decision block — keep co-inheritance with corrected docstring (recommended) vs schedule a real major-release removal path.

---

## Decision required (consolidated)

1. **W2-2 — `TokenRequiredError` (499) canonical vs demote.** The `TokenRequiredError` docstring claims it is raised on Esri 499, but the code raises `AuthNotAttachedError` for 499 (verified: `restgdf/utils/token.py:383-387`); two documented 499 types where only one fires. **Recommendation:** demote `TokenRequiredError` — update its docstring to "reserved / not currently raised; 499 surfaces as `AuthNotAttachedError`" and keep `AuthNotAttachedError` canonical for 499 (it is already the live raise site and is semantically precise). Do NOT add a second 499 raise site.

2. **W2-13 — path (b) warning-only vs path (a) full wiring.** Wiring `RetryConfig`/`LimiterConfig` into the executor (path a) requires first resolving the `LimiterConfig.rate_per_host` vs `ResilienceConfig.rate_per_service_root_per_second` ownership collision and threading the aggregate config through the executor. **Recommendation:** ship path (b) now (one-time warning on inert `RESTGDF_RETRY_*`/`RESTGDF_LIMITER_*` + deferral caveat parity), and treat path (a) as a separate design proposal with its own config-ownership decision; this matches the audit's "safe now" guidance and avoids ambiguous rate limiting on a Production/Stable release.

3. **W2-9 — keep co-inheritance (docstring fix) vs schedule a real removal.** **Recommendation:** keep the `ValueError` co-inheritance and fix only the docstring to match the project's "removal only in a major release, deprecation-warned" policy (zero behavior change, no import-boundary risk). Building 3.1-removal machinery or a removal-pinning test would itself be the SemVer hazard the audit warns against.
