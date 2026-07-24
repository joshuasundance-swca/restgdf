# 03 — Config spine (source of truth)
> Workstream of the restgdf remediation plan · audit pinned `4673b08` · 2026-06-13

## Goal
This workstream owns the two configuration-model modules that every other workstream's "consume" item reads from. Landing it makes the layered `Config`/sub-config surface tell the truth: `TransportConfig.verify_ssl`/`user_agent` become a single authoritative source the token/transport/getgdf seams can wire to (CONFIG-01/AUTH-03), the dead `AuthConfig` refresh knobs and env vars are either resolved or honestly marked inert (CONFIG-02/AUTH-04, DOCS-02), the documented-but-unimplemented precedence layers (explicit `Config` instance, `.env` file) get a code-side decision (CONFIG-03/04), and the self-contradicting module docstring is corrected (DOCS-11). Because W2 (token/_http), W4 (getgdf), W5 (FeatureLayer), and W6 (docs) all `Depends` on the source-of-truth decisions made here, this workstream is the unblocking spine for the high-severity verify_ssl wiring and the medium config-construction wiring.

## Collision domain
Single-writer files OWNED by W3:

- `restgdf/_config.py` — the layered `Config` aggregate + eight sub-configs + `_NEW_ENV_SPEC`/`_DEPRECATED_ALIASES` env resolver. **Hot file: all seven W3 items touch it.** They MUST serialize (one writer at a time) — see Sequencing.
- `restgdf/_models/_settings.py` — the deprecated `Settings` shim. Touched only by W3-1 (the `_settings.py:112` user_agent doc-string-vs-reality note) within this workstream.

No file in this workstream is split-owned with another workstream at the *file* level (W3 is the sole writer of `_config.py` and `_settings.py`). However, several W3 items are the **config PART of a split-ownership finding** whose consume/application parts live in other workstreams:

- CONFIG-01 + AUTH-03 (verify_ssl/user_agent): root = **W3-1** here; application seams = W2-10 (`token.py`/`_http.py`), W4-5 (`getgdf.py`); docs = W6-4.
- AUTH-04 (refresh knobs): config part = **W3-2** here; consume part = W2-11 (`token.py`); docs = W6-4.
- CONFIG-02 (AuthConfig exposure): config part = **W3-3** here; consume = W2-11 (`token.py`); FeatureLayer wiring = W5-14; docs = W6-4/W6-6.
- CONFIG-03 (explicit `Config` instance): config part = **W3-4** here; FeatureLayer `from_config` part = W5-14; docs = W6-3.

## Sequencing & parallelization
All seven items write the same hot file (`restgdf/_config.py`), so **they cannot run in parallel** — serialize every W3 item behind a single writer to avoid merge collisions on `_config.py`. Order within the hot file is by milestone, then by who-unblocks-whom:

1. **M1 — W3-7** (docstring `Seven`→`Eight`). Trivial, zero-risk, no dependents. Land first to clear the hot file for the riskier edits and so M1's "obvious metadata correct" milestone is satisfied.
2. **M2 — W3-1** (TransportConfig verify_ssl/user_agent source of truth). **Highest leverage in this workstream** — it is `high` severity and three cross-workstream items block on it: **W2-10 blocks on W3-1**, **W4-5 blocks on W3-1**, and **W4-6 (typing)** is adjacent. Land this as soon as W3-7 is in.
3. **M2 — W3-5** (`.env` loading decision) and **M2 — W3-6** (four unwired `RESTGDF_*` env vars). Both are M2, both small, both touch `_config.py` resolver/docstrings. Serialize after W3-1. W3-6's docs prose fix is W6-7; W3-5's docs prose fix is W6-3.
4. **M3 — W3-2** (AuthConfig refresh knobs), **M3 — W3-3** (AuthConfig exposure), **M3 — W3-4** (explicit Config precedence). These three are M3, and their consume parts (W2-11, W5-14) `Depend` on them. **W2-11 blocks on W3-3 and W3-2; W5-14 blocks on W3-3 and W3-4.** Land W3-2/W3-3/W3-4 (serialized, same hot file) before the W2/W5 consume items can begin.

Cross-workstream `Depends` edges this workstream creates (downstream consumers wait on W3):
- **W2-10 → W3-1** (token/_http verify_ssl seam waits on the source-of-truth decision).
- **W4-5 → W3-1** (getgdf ssl-connector seam waits on the source-of-truth decision).
- **W2-11 → W3-2, W3-3** (token AuthConfig consume waits on config part).
- **W5-14 → W3-3, W3-4** (FeatureLayer from_config waits on config exposure + precedence decision).
- **W6-4 → W3-1, W3-3** and **W6-3 → W3-4, W3-5** (docs prose sequences after the code decisions).

W3 has **no inbound `Depends`** — it can start immediately. It is the bottleneck spine; prioritize W3-7 then W3-1.

## Work items

### W3-7 · Fix the _config.py module docstring (Seven->eight sub-configs)
**Audit refs:** DOCS-11 · **Severity:** low · **Effort:** S · **Milestone:** M1
**Depends:** — · **Blocks:** — (but land first to clear the hot file for the M2/M3 `_config.py` edits)
**Split-ownership:** — (the `CHANGELOG.md:176` "seven" fix is doc-side and belongs to W6-5; this item touches only `_config.py`).
**Scope** — In: the `_config.py` module docstring enumeration of sub-configs. Out-of-scope: any code/field change; the `CHANGELOG.md` "seven" wording (W6-5).
**Spec**
1. In `restgdf/_config.py` module docstring (verified: `restgdf/_config.py:3` reads `Seven frozen pydantic 2.x sub-configs mirror the plan-obs §3 taxonomy:`), change `Seven` to `Eight`.
2. Append `:class:`ResilienceConfig`` to the enumerated list at the end of the existing enumeration (verified: list runs `_config.py:4-6` ending `:class:`TelemetryConfig``; `ResilienceConfig` is defined at `_config.py:190` and aggregated at `_config.py:311` as the 8th field). Mirror field order so it follows `TelemetryConfig`.
3. The `Config` class docstring already correctly says "eight" (verified: `_config.py:296` "Aggregate of the eight sub-configs. Frozen."). Do NOT touch it; only the module docstring is wrong.
**Acceptance criteria**
- [ ] `restgdf/_config.py:3` says "Eight frozen pydantic 2.x sub-configs".
- [ ] `ResilienceConfig` appears in the module-docstring enumeration.
- [ ] No code/field/`__all__` change (pure prose edit).
- [ ] lint lane passes (docstring-only edit does not perturb mypy/ruff).
**Validation** — lint; test (regression sanity — no behavior change expected).
**Risks & rollback** — Negligible (prose only). Rollback = revert the one-word/one-line docstring edit. No anti-recommendation (the audit confirms the naive fix is safe).

---

### W3-1 · Establish the TransportConfig user_agent/verify_ssl source of truth (verify_ssl part A)
**Audit refs:** CONFIG-01, AUTH-03 · **Severity:** high · **Effort:** M · **Milestone:** M2
**Depends:** — · **Blocks:** W2-10, W4-5, W6-4 (and informs W4-6)
**Split-ownership:** This item owns the **CONFIG source-of-truth PART** of the consolidated verify_ssl/user_agent finding: it decides the single authoritative source for `verify_ssl` (reconcile `TransportConfig.verify_ssl` vs `TokenSessionConfig.verify_ssl`) and confirms `TransportConfig.user_agent` is the UA source. The **application seams own the wiring**: W2-10 owns the `default_headers()` UA injection + `token._call_with_auth_retry` ssl forwarding; W4-5 owns the `getgdf` bare-session `TCPConnector(ssl=...)`. Docs reconciliation = W6-4 (MIGRATION) / W6-7 (configuration.rst, via W3-6). Do NOT implement the application seams in this item.
**Scope** — In: the `_config.py` model-level decision/exposure that makes `TransportConfig` the single source of truth for `verify_ssl` and `user_agent`; the doc-string-vs-reality correction at `_settings.py:112`. Out-of-scope: per-request `ssl=` injection at leaf call sites (explicit anti-recommendation — see step 5); `default_headers()` edit (W2-10); `getgdf.py` connector (W4-5); `token.py` forwarding (W2-10); MIGRATION/README prose (W6-4/W6-6).
**Spec**
1. **Confirm the dead-config evidence holds in the current tree.** Verified: `get_config().transport` is read ONLY by the deprecated Settings shim (`restgdf/_models/_settings.py:269` `"user_agent": cfg.transport.user_agent`); no live request/auth path reads `transport.verify_ssl` or `transport.user_agent` (grep over `restgdf/` excluding `_config.py` returns only `_settings.py` shim reads + the `token.py`/`credentials.py` `TokenSessionConfig.verify_ssl` field, which is a *separate* knob). `DEFAULT_METADATA_HEADERS = {... "User-Agent": "Mozilla/5.0"}` (verified: `restgdf/utils/_http.py:18-21`) hardcodes the UA; `default_headers()` merges only that constant (verified: `_http.py:32-34`).
2. **Decide the single source of truth for `verify_ssl` (Decision required — see below).** The audit (CONFIG-01 step 3, AUTH-03) identifies two disconnected fields: `TransportConfig.verify_ssl` (verified: `_config.py:78`, default `True`) and `TokenSessionConfig.verify_ssl` (verified: `restgdf/_models/credentials.py:80`, default `True`), which `ArcGISTokenSession` consumes via `self.config.verify_ssl` (verified: `restgdf/utils/token.py:137`, applied at `token.py:159` and forwarded only on the token POST at `token.py:278`). RECOMMENDED default: keep `TransportConfig.verify_ssl` as the **library-owned data-path** source of truth (consumed by W4-5's getgdf connector and W2-10's `_http` seam) and leave `TokenSessionConfig.verify_ssl` as the **explicit session-scoped override** the caller passes — do NOT make `TokenSessionConfig` silently default-from `get_config().transport.verify_ssl` (that mirrors the CONFIG-02 anti-recommendation against implicit process-wide singleton sourcing). Document the relationship in the `TransportConfig` docstring (`_config.py:73-79`): "`verify_ssl` governs library-owned data-request sessions; `TokenSessionConfig.verify_ssl` is an explicit per-session override for the `/generateToken` POST and token-attached data requests."
3. **Confirm `user_agent` exposure is adequate.** `TransportConfig.user_agent` already exists with the correct default (verified: `_config.py:79` `Field(default_factory=_default_user_agent, min_length=1)`, i.e. `restgdf/<version>`). No new field needed; W2-10 will inject `get_config().transport.user_agent` into `default_headers()`. Add a one-line docstring note on `TransportConfig` that `user_agent` is the source the data-path request headers default from (so a future reader does not re-add a hardcoded UA).
4. **Fix the doc-vs-reality drift inside `_settings.py:112`** (the only `_settings.py` edit W3 owns). Verified: `_settings.py:109-113` field doc says `"User-Agent header sent on ArcGIS REST requests."` — true only AFTER W2-10 lands. Until W2-10/W4-5 land, the statement overstates behavior. Soften to reflect that this legacy shim field mirrors `TransportConfig.user_agent` and that the *applied* UA is governed by the transport layer (avoid re-asserting unconditional "sent on every request" until the seams land). Keep the change minimal and forward-compatible so W2-10's landing makes it literally true.
5. **Preserve the anti-recommendations as explicit do-NOTs:**
   - Do NOT blanket-inject `ssl=get_config().transport.verify_ssl` into every `_arcgis_request` kwargs / leaf call site (CONFIG-01 step 2: per-request `ssl=` conflicts with caller-supplied connectors and aiohttp's per-request-vs-connector TLS interplay is fragile). That belongs to the session-creation seams (W4-5/W2-10), not this model item.
   - Do NOT swap the `"Mozilla/5.0"` default in `DEFAULT_METADATA_HEADERS` here — that is W2-10's edit and is a CHANGELOG-noteworthy behavior change (some Esri WAFs sniff UA); W3-1 only ratifies `TransportConfig.user_agent` as the source.
   - Do NOT make `ArcGISTokenSession`/`TokenSessionConfig` implicitly read `get_config().transport` (process-wide singleton footgun).
**Acceptance criteria**
- [ ] `TransportConfig` docstring (`_config.py:73-79`) states `verify_ssl` is the library-owned data-path TLS source of truth and names its relationship to `TokenSessionConfig.verify_ssl`.
- [ ] `TransportConfig.user_agent` docstring note identifies it as the data-path UA source.
- [ ] `_settings.py:112` field description no longer overstates that the UA is unconditionally applied (forward-compatible with W2-10).
- [ ] No new per-request `ssl=` injection added in `_config.py` (anti-recommendation honored).
- [ ] Decision recorded (single source-of-truth choice) so W2-10/W4-5 wire to the same field.
- [ ] coverage lane stays ≥97 (model-only edits should not drop coverage).
**Validation** — lint; test; coverage. (No behavior change in this item itself; the red-state test for verify_ssl *application* lands with W2-10/W4-5.)
**Risks & rollback** — Failure mode: choosing a source-of-truth that the seam items (W2-10/W4-5) then wire inconsistently — mitigated by recording the Decision and having the consume items reference it. Rollback = revert the `_config.py`/`_settings.py` docstring edits (no code-path change to undo). Anti-recommendation guardrails (do-NOTs in step 5) must survive into the seam items' specs.
**Decision required** — surfaced below.

---

### W3-5 · Implement .env loading or remove the documented layer
**Audit refs:** CONFIG-04 · **Severity:** low · **Effort:** S · **Milestone:** M2
**Depends:** — · **Blocks:** W6-3 (ARCHITECTURE.md `.env` precedence prose sequences after this decision)
**Split-ownership:** — (the ARCHITECTURE.md / docs/configuration.rst / docs/authentication.rst `.env` prose deletions are W6-3 and W6-7; this item is the `_config.py` code-side decision only).
**Scope** — In: the `_config.py` resolver's treatment of a `.env` file (i.e. confirm it reads `os.environ` only and decide whether to add opt-in dotenv support). Out-of-scope: editing ARCHITECTURE.md:118 / docs/configuration.rst:11 / docs/authentication.rst:101-107 (all W6 prose); adding `python-dotenv` as a hard runtime dep (anti-recommendation).
**Spec**
1. Confirm the evidence: `Config.from_env` reads only the process environment (verified: `restgdf/_config.py:344` `source: Mapping[str, str] = os.environ if env is None else env`); identical pattern in `Settings.from_env` (verified: `restgdf/_models/_settings.py:197`). No `dotenv`/`load_dotenv` anywhere and `python-dotenv` is not a declared dependency.
2. RECOMMENDED default (docs-only resolution): do NOT add implicit cwd `.env` loading. Per the CONFIG-04 anti-recommendation, `Config` is a plain `pydantic.BaseModel` (verified: `_config.py:295` `class Config(BaseModel)`), the documented architecture invariant is env-only resolution via `get_config()`, and implicit `.env` reading would (a) introduce CWD-dependent behavior into an embedded library, (b) risk loading a consumer's app-level `.env` into restgdf's namespace, and (c) require `python-dotenv` as a hard runtime dep (currently only transitive via `pydantic-settings`, which itself is not declared in `pyproject.toml` — only `pydantic>=2.13.3,<3`). The code part is therefore a no-op confirmation that `from_env` is env-only; the `.env` precedence claims are deleted on the docs side (W6-3 for ARCHITECTURE.md; W6-7 for the two `docs/*.rst`).
3. If the OPT-IN alternative is chosen instead: do NOT add implicit magic. The audit's sanctioned shape is an explicit, documented helper — callers do `Config.from_env(env={**dotenv_values(path), **os.environ})` — which requires NO code change to `_config.py` because `from_env` already accepts an explicit `env` mapping (verified: `_config.py:316` `env: Mapping[str, str] | None = None`). So even the opt-in path is satisfiable today without new code; at most add a docstring example on `from_env`.
4. Preserve the anti-recommendation as an explicit do-NOT step: do NOT convert `Config`/`Settings` to `pydantic_settings.BaseSettings` or add implicit `.env` discovery.
**Acceptance criteria**
- [ ] `_config.py` confirmed env-only (no dotenv reader added).
- [ ] If opt-in chosen: a `from_env` docstring example shows the explicit `{**dotenv_values(path), **os.environ}` merge; no new dependency, no implicit discovery.
- [ ] Decision recorded so W6-3/W6-7 delete-vs-document the `.env` precedence consistently.
- [ ] No `python-dotenv` added to `pyproject.toml` runtime deps.
**Validation** — lint; test. (No runtime behavior change under the recommended path.)
**Risks & rollback** — Failure mode: adding implicit `.env` loading that picks up an embedding app's `.env` (the audit's named footgun). Mitigated by the recommended docs-only resolution. Rollback = none needed under recommended path; if opt-in docstring added, revert the docstring.
**Decision required** — surfaced below.

---

### W3-6 · Reconcile the 4 documented-but-unwired RESTGDF_* env vars (code part)
**Audit refs:** DOCS-02 · **Severity:** medium · **Effort:** S · **Milestone:** M2
**Depends:** — · **Blocks:** W6-7 (docs/configuration.rst prose fix sequences after this decision)
**Split-ownership:** This item owns the **code/resolver PART**: either wire the env vars into `_NEW_ENV_SPEC` or confirm their removal. The **prose part** (rewriting `docs/configuration.rst:44,53,56,59`, fixing the wrong defaults 300→30 and 10→8, and the "based on Pydantic Settings"/`.env` framing at rst:4-12) is **W6-7**. Do NOT edit `docs/configuration.rst` here.
**Scope** — In: `_config.py` `_NEW_ENV_SPEC` (verified: `restgdf/_config.py:219-257`) — decide whether to add entries for the three auth env vars; confirm the timeout/concurrency vars are already correctly wired. Out-of-scope: all `docs/configuration.rst` edits (W6-7); the `AuthConfig` field definitions themselves (they are live and must NOT be deleted — see step 4).
**Spec**
1. Enumerate the four documented-but-unwired vars (verified against `docs/configuration.rst`): `RESTGDF_TRANSPORT_TIMEOUT_TOTAL` (default shown 300, rst:44-46), `RESTGDF_AUTH_TRANSPORT` (rst:53-55), `RESTGDF_AUTH_REFRESH_LEEWAY_SECONDS` (rst:56-58), `RESTGDF_AUTH_CLOCK_SKEW_SECONDS` (rst:59-61). Also note rst lists `RESTGDF_CONCURRENCY_MAX_CONCURRENT_REQUESTS` default `10` (rst:50-52) which is wrong (code default 8).
2. Confirm none are in `_NEW_ENV_SPEC` (verified: `_config.py:219-257` resolves `RESTGDF_TIMEOUT_TOTAL_S`, `RESTGDF_AUTH_TOKEN_URL`, `RESTGDF_AUTH_REFRESH_THRESHOLD_S` — but NOT `RESTGDF_TRANSPORT_TIMEOUT_TOTAL`, `RESTGDF_AUTH_TRANSPORT`, `RESTGDF_AUTH_REFRESH_LEEWAY_S`, or `RESTGDF_AUTH_CLOCK_SKEW_S`). There is no `transport.timeout_total` field — `TransportConfig` has only `verify_ssl`/`user_agent` (verified: `_config.py:78-79`); timeout lives in `TimeoutConfig.total_s` (verified: `_config.py:89`).
3. `RESTGDF_TRANSPORT_TIMEOUT_TOTAL` is a **docs error, not a code gap** — the real var is `RESTGDF_TIMEOUT_TOTAL_S` and it is already wired (verified: `_config.py:224`). The code part is a no-op for this one; W6-7 fixes the rst name+default. Same for the concurrency default-10 error (real wiring at `_config.py:230-234`).
4. For the three `RESTGDF_AUTH_*` vars — **Decision required** (path a vs path b from DOCS-02):
   - **Path (a) — docs-only, RECOMMENDED default:** leave `_NEW_ENV_SPEC` unchanged; the three `AuthConfig` fields (`transport`, `refresh_leeway_s`, `clock_skew_s`, verified: `_config.py:131,136,137`) remain settable via `Config(auth=AuthConfig(...))`. W6-7 drops the three vars from the rst env table. Zero code change, zero behavior change. This is consistent with W3-2's finding that `AuthConfig` is not auto-applied to sessions anyway (so an env var for it would still be inert without W2-11/W5-14 wiring).
   - **Path (b) — wire them:** add three entries to `_NEW_ENV_SPEC` mapping `RESTGDF_AUTH_TRANSPORT`→`auth.transport` (str), `RESTGDF_AUTH_REFRESH_LEEWAY_S`→`auth.refresh_leeway_s` (float), `RESTGDF_AUTH_CLOCK_SKEW_S`→`auth.clock_skew_s` (float). NOTE the canonical suffix is `_S` not `_SECONDS` (to match field names + the existing `_S` convention at `_config.py:224,236`); the leeway/skew validators cap at 600/120 (verified: `_config.py:136-137`) so W6-7 must state those bounds. Path (b) is a behavior change and only useful once `AuthConfig` is actually consumed (W2-11/W5-14) — otherwise the env var validates into an inert sub-config.
5. Do NOT delete the `AuthConfig` fields (`transport`/`refresh_leeway_s`/`clock_skew_s`) — they are live model fields consumed by the `Config(auth=...)` path and by `TokenSessionConfig` mapping; DOCS-02 explicitly warns against deleting them.
**Acceptance criteria**
- [ ] `RESTGDF_TRANSPORT_TIMEOUT_TOTAL` confirmed as a docs-only error (no code change for it); real var `RESTGDF_TIMEOUT_TOTAL_S` confirmed wired.
- [ ] Decision (path a vs b) recorded so W6-7 writes the env table to match the resolver exactly.
- [ ] If path (b): three `_NEW_ENV_SPEC` entries added with `_S` suffixes; a red-state test asserts e.g. `RESTGDF_AUTH_REFRESH_LEEWAY_S=300` resolves to `Config.from_env(env=...).auth.refresh_leeway_s == 300.0` (and rejects >600 per the cap).
- [ ] `AuthConfig` fields unchanged (not deleted).
- [ ] coverage lane ≥97.
**Validation** — lint; test; single (`-k auth` or the new `test_config` case if path b); coverage.
**Risks & rollback** — Path (a): no risk (no code change). Path (b): risk that an env var validates into an inert `AuthConfig` until W2-11/W5-14 wire consumption — surface this as a known limitation, not a bug, and sequence the wiring items accordingly. Rollback = remove the three `_NEW_ENV_SPEC` entries. Do NOT delete `AuthConfig` fields under any path.
**Decision required** — surfaced below.

---

### W3-2 · Wire or retire the AuthConfig refresh-threshold knobs (config part)
**Audit refs:** AUTH-04 · **Severity:** low · **Effort:** M · **Milestone:** M3
**Depends:** — · **Blocks:** W2-11 (token consume part), W6-4 (MIGRATION prose)
**Split-ownership:** This item owns the **CONFIG PART** of AUTH-04: the `_config.py`-side decision/docstring for `AuthConfig.refresh_threshold_s`/`refresh_leeway_s`/`clock_skew_s`. The **consume PART** (making `token.py` sessions read these knobs, e.g. a `TokenSessionConfig.from_auth_config` factory) is **W2-11**; the MIGRATION.md prose is **W6-4**. Do NOT edit `token.py`/`credentials.py` here.
**Scope** — In: `_config.py` `AuthConfig` docstring + the decision on whether the knobs are wired or marked-inert. Out-of-scope: removing the fields or the `RESTGDF_AUTH_REFRESH_THRESHOLD_S`/`RESTGDF_REFRESH_THRESHOLD` env vars (anti-recommendation — back-compat seam); the `from_auth_config` factory body (that is consume-side, W2-11); MIGRATION prose (W6-4).
**Spec**
1. Confirm the evidence: `AuthConfig` declares `refresh_threshold_s=60.0`, `refresh_leeway_s=120.0`, `clock_skew_s=30.0` (verified: `_config.py:135-137`). None are read by any session — only `auth.token_url`/`auth.refresh_threshold_s` are consumed, and only via the deprecated Settings shim (verified: `_settings.py:272-276`). The session's actual refresh window comes from `ArcGISTokenSession.token_refresh_threshold` (dataclass default 60, verified: `token.py:119`) or, when a `TokenSessionConfig` is built, `refresh_leeway_seconds(120)+clock_skew_seconds(30)` (verified: `token.py:138-140`; `credentials.py:78-79` defaults 120/30 → 150, not 180). **(drift: AUTH-04 evidence text states the `TokenSessionConfig` path yields 180; the field defaults are `refresh_leeway_seconds=120` + `clock_skew_seconds=30` = 150 — verified at `restgdf/_models/credentials.py:78-79`. The audit's own Recommendation step 3 also says 150, so the "180" in the Evidence/Why-it-matters paragraphs is an internal inconsistency; the correct default sum is 150.)**
2. RECOMMENDED default (the audit's sound fix, config part): add a docstring note on `AuthConfig` (verified: `_config.py:119-126`) that `refresh_threshold_s`/`refresh_leeway_s`/`clock_skew_s` are **config holders not auto-applied to sessions**, mirroring the existing `RetryConfig` "phase-3a wires the executor" (verified: `_config.py:93`) and `LimiterConfig` "disabled by default" (verified: `_config.py:103`) inertness notes. State the caller-constructs-the-session model: "the library never constructs the token session itself; pass a `TokenSessionConfig` to `ArcGISTokenSession` explicitly. Use `TokenSessionConfig.from_auth_config(get_config().auth)` (W2-11) to thread these values."
3. Note the default-split reconciliation for the docstring: a bare `TokenSessionConfig` yields `120+30=150` while the `ArcGISTokenSession` dataclass default is `60` — call this out so a caller migrating from the dataclass arg to a config is not surprised (the `from_auth_config` path W2-11 builds will be internally consistent).
4. Preserve the anti-recommendations as explicit do-NOTs:
   - Do NOT remove the fields or the `RESTGDF_AUTH_REFRESH_THRESHOLD_S` / `RESTGDF_REFRESH_THRESHOLD` alias / `Settings.refresh_threshold_seconds` — they are a documented back-compat seam pinned by tests (`test_settings.py`, `test_settings_deprecation.py`, `test_config.py`).
   - Do NOT claim a factory makes the env var "automatically drive refresh timing" — there is no library chokepoint that constructs the session; a factory only helps opt-in callers (the consume mechanics are W2-11).
**Acceptance criteria**
- [ ] `AuthConfig` docstring (`_config.py:119-126`) marks the three refresh knobs as config-holders-not-auto-applied, naming the caller-constructs-the-session model and the `from_auth_config` opt-in path.
- [ ] Docstring states the 150 (config) vs 60 (dataclass) default split (the corrected number per the drift note).
- [ ] Fields and env vars/aliases left intact (no deletion).
- [ ] Decision recorded so W2-11 and W6-4 align (wire-via-factory vs mark-inert).
- [ ] coverage lane ≥97.
**Validation** — lint; test; coverage.
**Risks & rollback** — Failure mode: deleting the back-compat seam and breaking the deprecation tests (the named anti-recommendation). Mitigated by the do-NOT step. Rollback = revert the docstring note. The default-split number (150) must be the one carried into W2-11/W6-4 — flag the audit's "180" inconsistency to those owners.
**Decision required** — surfaced below.

---

### W3-3 · Expose AuthConfig for token-session construction (config part)
**Audit refs:** CONFIG-02 · **Severity:** medium · **Effort:** L · **Milestone:** M3
**Depends:** — · **Blocks:** W2-11 (token consume), W5-14 (FeatureLayer from_config), W6-4/W6-6 (docs)
**Split-ownership:** This item owns the **CONFIG-exposure PART** of CONFIG-02: the `_config.py`-side `AuthConfig` docstring/inertness note (and, only if the full-wiring decision is taken, any additive `_config.py` surface needed by the consume side). The **token consume PART** (`TokenSessionConfig.from_auth_config` factory / `__post_init__` behavior) is **W2-11**; the **FeatureLayer wiring** is **W5-14**; docs are **W6-4/W6-6**. Do NOT edit `token.py`/`featurelayer.py` here.
**Scope** — In: `_config.py` `AuthConfig` exposure + inertness docstring. Out-of-scope: making `ArcGISTokenSession.__post_init__` read `get_config().auth` (explicit anti-recommendation); the `from_config` classmethod body (W2-11); FeatureLayer `config=`/`auth=` params (W5-14); README:89/MIGRATION:109 prose (W6-4/W6-6).
**Spec**
1. Confirm the evidence: `ArcGISTokenSession.__post_init__` builds exclusively from `TokenSessionConfig` or dataclass kwargs and never references `get_config()`/`AuthConfig` (verified: `token.py:131-166` — `__post_init__` reads `self.config` (a `TokenSessionConfig`) or derives from `self.credentials`, no `get_config()` call). `AuthConfig` usage is limited to the model def, the `Config.auth` default (verified: `_config.py:309`), and the Settings shim (verified: `_settings.py:272-276`). `FeatureLayer.__init__`/`from_url` accept no `config`/`auth` parameter (consume side, W5-14). Docs present `AuthConfig` as operative: README:89 / MIGRATION:110 say `AuthConfig(transport="body")` self-applies (it does not).
2. **Decision required** (full wiring vs minimal): the audit's PREFERRED resolution is the **low-risk doc fix + inertness note** (minimal), NOT auto-wiring. RECOMMENDED default = minimal: (a) here in `_config.py`, add an `AuthConfig` docstring note exactly parallel to `RetryConfig`/`LimiterConfig`: "`AuthConfig` is a validated namespace for `RESTGDF_AUTH_*` env vars; it is NOT auto-applied to `ArcGISTokenSession`. Construct `TokenSessionConfig(transport=...)` and pass it explicitly." (b) The operative remediation (`TokenSessionConfig(transport="body")` self-applies, `AuthConfig` does not) is corrected in README:89/MIGRATION:109 by W6-4/W6-6, and the opt-in `from_config` factory (if built) is W2-11.
3. If FULL wiring is chosen instead: the only sanctioned shape is an **opt-in classmethod** `ArcGISTokenSession.from_config(session, credentials, config=get_config().auth)` (built in W2-11) that derives a `TokenSessionConfig` — and any additive `_config.py` surface it needs (e.g. a helper to project `AuthConfig`→`TokenSessionConfig` kwargs) lands here as the single-writer of `_config.py`. Coordinate the exact additive symbol with W2-11.
4. Preserve the anti-recommendation as an explicit do-NOT step: do NOT make `ArcGISTokenSession.__post_init__` read `get_config().auth` as a default — `get_config()` is a process-wide LRU-cached singleton (verified: `_config.py:415` `@functools.lru_cache(maxsize=1)`), so a single env-var flip would change transport for every session in the process and could interact badly with the `_http._session_requires_body_transport` GET→POST credential guard and explicit-config precedence.
**Acceptance criteria**
- [ ] `AuthConfig` docstring marks it a validated env namespace NOT auto-applied to sessions, naming the explicit-`TokenSessionConfig` path.
- [ ] If full wiring chosen: the additive `_config.py` projection helper exists and is referenced (by symbol name) in W2-11's spec; no implicit `get_config().auth` read in `__post_init__`.
- [ ] Decision recorded (minimal vs full) so W2-11/W5-14/W6-4/W6-6 align.
- [ ] No implicit singleton sourcing in any session path (anti-recommendation honored).
- [ ] coverage lane ≥97.
**Validation** — lint; test; coverage.
**Risks & rollback** — Failure mode: choosing full wiring and threading the singleton implicitly (the named footgun) — mitigated by the opt-in-classmethod-only constraint. Rollback = revert the docstring (minimal) or the additive helper (full). The minimal path is L-effort here only because of the decision/coordination surface, not code volume.
**Decision required** — surfaced below.

---

### W3-4 · Implement the documented explicit-Config-instance precedence (config part)
**Audit refs:** CONFIG-03 · **Severity:** low · **Effort:** M · **Milestone:** M3
**Depends:** — · **Blocks:** W5-14 (FeatureLayer from_config), W6-3 (ARCHITECTURE.md precedence prose)
**Split-ownership:** This item owns the **CONFIG PART** of CONFIG-03: the `_config.py`-side decision on the documented precedence level 2 ("`Config(...)` instance passed explicitly"). The **FeatureLayer `from_config` part** is **W5-14**; the ARCHITECTURE.md prose is **W6-3**. Do NOT edit `featurelayer.py` here.
**Scope** — In: `_config.py` docstring/decision on whether a freshly-built `Config(...)` is injectable into the request path. Out-of-scope: adding `config=` to `FeatureLayer.from_url` (explicit anti-recommendation against the naive route; any sanctioned consume seam is W5-14); the ARCHITECTURE.md:113-119 precedence list edit (W6-3).
**Spec**
1. Confirm the evidence: config is resolved only process-globally — `get_config()` (`lru_cache` size-1, verified: `_config.py:415-423`) calls `Config.from_env()` reading `os.environ`; no public API accepts a `Config` instance. Verified the runtime consumers call the no-arg global `get_config()`: `restgdf/utils/_http.py:16` imports it; grep confirms live `get_config()` reads in `utils/getgdf.py`, `utils/getinfo.py`, `utils/crawl.py`, `telemetry/_spans.py` (verified via grep: 7 files import/call `get_config()`, none thread an injected instance). **(drift: CONFIG-03 cites `restgdf/utils/_http.py:213` as a `get_config()` call site; in the current tree `_http.py` imports `get_config` at `_http.py:16` and the file is shorter than 213 lines — the specific line 213 is stale, but the audit's substantive claim (every runtime consumer calls the no-arg global) holds. Treat the line number as perished, not the claim.)** The `Config.from_env` docstring scopes direct instantiation as "useful for tests" (verified: `_config.py:298-299`).
2. **Decision required** (implement vs delete the doc claim): the audit's PREFERRED resolution is the **doc-side fix** — reword/remove ARCHITECTURE.md precedence level 2 (W6-3) so the listed layers match reality (constructor/aiohttp kwargs > env vars > defaults, resolved process-globally; a freshly built `Config(...)` is NOT injectable). RECOMMENDED default = delete-the-claim: this item's code part is a no-op confirmation that no `config=` injection exists, plus (optionally) a one-line note on the `Config` docstring (`_config.py:295-300`) clarifying that `Config(...)` direct instantiation is test-only and not injected into the request path. W6-3 owns the ARCHITECTURE.md edit; W5-14 stays scoped to whatever (if any) session-scoped `TokenSessionConfig` injection is exposed.
3. Preserve the anti-recommendation as an explicit do-NOT step: do NOT take the naive "add `config=` to `FeatureLayer.from_url`" route — it is not a one-liner. Every runtime consumer calls the no-arg global `get_config()` far below the public constructor with no `Config` in scope, so honoring an injected instance means threading it through transport/streaming/telemetry or introducing a `ContextVar`. That is a net-new feature on a Production/Stable library and risks the light-core import boundary; it is a deliberate design proposal, not an audit remediation.
4. Note the separate, already-working `TokenSessionConfig` injection (`ArcGISTokenSession(config=...)`, verified: `token.py:123` `config: TokenSessionConfig | None`) is intentionally session-scoped and does NOT satisfy global Config level-2 — do not conflate them in the docstring or in W5-14.
**Acceptance criteria**
- [ ] `_config.py` confirmed to expose no `Config`-instance injection into the request path (no new `config=` parameter added here).
- [ ] If clarifying note added: the `Config` docstring states direct instantiation is test-only / not request-path-injected.
- [ ] Decision recorded (delete-claim vs implement) so W6-3 and W5-14 align.
- [ ] No `ContextVar`/threading feature introduced (anti-recommendation honored).
- [ ] coverage lane ≥97.
**Validation** — lint; test; coverage.
**Risks & rollback** — Failure mode: taking the naive `config=` route and introducing a half-threaded injection that some leaf consumers ignore (silent precedence violation) — mitigated by the do-NOT step. Rollback = revert the docstring note (delete-claim path) or the threading (implement path, not recommended).
**Decision required** — surfaced below.

## Decisions required (summary)

| Item | Question | Recommendation |
|------|----------|----------------|
| W3-1 | Single source of truth for `verify_ssl`: reconcile `TransportConfig.verify_ssl` vs `TokenSessionConfig.verify_ssl` how? | `TransportConfig.verify_ssl` governs library-owned data-path sessions (W4-5/W2-10 wire to it); keep `TokenSessionConfig.verify_ssl` as the explicit session-scoped override; do NOT implicitly default one from the other. |
| W3-5 | Implement `.env` loading or remove the documented layer? | Docs-only removal (W6-3/W6-7 delete the `.env` precedence claims); keep `from_env` env-only; if opt-in wanted, document the explicit `{**dotenv_values(path), **os.environ}` merge — no new dependency, no implicit discovery. |
| W3-6 | Three `RESTGDF_AUTH_*` env vars: wire into `_NEW_ENV_SPEC` (path b) or drop from docs (path a)? | Path (a) docs-only: leave `_NEW_ENV_SPEC` unchanged (fields stay settable via `Config(auth=...)`), W6-7 drops them from the rst table — wiring is inert until `AuthConfig` is consumed (W2-11/W5-14). |
| W3-2 | Wire the AuthConfig refresh knobs or mark them inert? | Mark inert via docstring (parallel to RetryConfig/LimiterConfig), keep all fields/aliases; provide the opt-in `from_auth_config` thread via W2-11. Carry the corrected 150 (not 180) default-split into W2-11/W6-4. |
| W3-3 | Full AuthConfig wiring vs minimal (doc + inertness note)? | Minimal: inertness docstring + W6-4/W6-6 fix the README/MIGRATION `AuthConfig(transport="body")` claim; if wiring desired, opt-in `from_config` classmethod only (W2-11), never implicit `get_config().auth` in `__post_init__`. |
| W3-4 | Implement explicit-Config-instance precedence or delete the doc claim? | Delete the claim (W6-3 rewords ARCHITECTURE.md precedence); confirm no `config=` injection in the request path; do NOT add `config=` to `FeatureLayer.from_url` (net-new feature, not a remediation). |
