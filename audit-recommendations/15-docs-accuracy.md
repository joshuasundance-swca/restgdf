> **15 — Documentation accuracy vs code** · restgdf audit · **read-only** · no code was modified
> Commit `4673b08` · 2026-06-13 · Index: [README](README.md) · Machine-readable: [findings.json](findings.json)

## Assessment

The published reference docs are mostly accurate and well-curated: the streaming recipe (`docs/recipes/streaming.md`), telemetry/observability recipe, `errors.rst` hierarchy diagram, and the README usage examples all match the code, and `CLAUDE.md` is notably precise (the 54-name `__all__`, the `FieldDoesNotExistError`-missing-from-`TYPE_CHECKING` note, and the "no CI gate on push to main / coverage only post-merge" claims all verify against the code/workflows). The risk concentrates in two places that are published to readthedocs AND `llms.txt` and therefore feed both human and LLM consumers: (1) `docs/configuration.rst`, which invents four `RESTGDF_*` env vars that are not wired into the resolver, states wrong defaults, and shows a `Config(...)` example that raises — a config consumer following it silently gets default behavior; and (2) the release-narrative docs (`CHANGELOG`'s empty `3.0.0` header, `MIGRATION.md` framed entirely around 2.0, `README`'s 2.0 collapsible, `SECURITY.md` listing only 2.x) which are stale for the shipped v3.0.0. `ARCHITECTURE.md` carries three concrete code-contradicting claims (`ErrorPayload`, logger names, `FeatureLayer.close()`). None corrupt data, but the config-doc drift can cause a developer's intended timeout/auth/concurrency tuning to be silently ignored.

## Findings at a glance

| ID | Finding | Severity | Effort |
|----|---------|----------|--------|
| `DOCS-01` | Published CHANGELOG has an empty `## [3.0.0]` header and MIGRATION.md is framed entirely as 2.0 — both included verbatim into readthedocs/llms.txt | medium | M |
| `DOCS-02` | configuration.rst documents four RESTGDF_* env vars that are not wired into Config.from_env (silently ignored) | medium | S |
| `DOCS-03` | ARCHITECTURE.md claims FeatureLayer/Directory own a session and expose close(); they do not | medium | S |
| `DOCS-04` | configuration.rst and authentication.rst claim `.env`-file / pydantic-settings support that does not exist | medium | S |
| `DOCS-05` | configuration.rst Config(...) example uses fields that raise (extra='forbid'/frozen) and wrong nesting | low | S |
| `DOCS-06` | ARCHITECTURE.md documents a structured detail type `ErrorPayload` that does not exist | low | S |
| `DOCS-07` | ARCHITECTURE.md logger-hierarchy names contradict the enforced LOGGER_SUFFIXES allowlist | low | S |
| `DOCS-08` | CONTRIBUTING.md targets the stale `integration/3.0-rewrite` branch and references unshipped plan.md | low | S |
| `DOCS-09` | docs/errors.rst documents FieldDoesNotExistError attribute as `field`; the real attribute is `field_name` | low | S |
| `DOCS-10` | README 2.0 collapsible and SECURITY.md supported-versions are stale for the shipped v3.0.0 | low | S |
| `DOCS-11` | _config.py module docstring says "Seven" sub-configs; there are eight | low | S |
| `DOCS-12` | docs/quickstart.md light-core example uses the deprecated row_dict_generator | low | S |

## Findings

### DOCS-01 · Published CHANGELOG has an empty `## [3.0.0]` header and MIGRATION.md is framed entirely as 2.0 — both included verbatim into readthedocs/llms.txt

**Severity:** medium · **Effort:** M · **Location:** `CHANGELOG.md:6-8; MIGRATION.md:1-5,518; docs/changelog.md:5-6; docs/migration.md:5-6`

**Evidence**

`CHANGELOG.md` line 6 is `## [3.0.0] - 2026-05-02` immediately followed by `## [2.0.0] - 2026-05-02` with no body — the 3.0 section is empty; the breaking changes (header-token default, refresh_leeway 60→120, PaginationError taxonomy) are listed under the 2.0.0 heading. `MIGRATION.md` opens `## 2.0.0 migration notes` and `restgdf 2.0.0 reshapes install surface...` with no 2.x→3.0 section. `docs/changelog.md` and `docs/migration.md` are pure MyST `{include} ../CHANGELOG.md` / `../MIGRATION.md` shims, so the empty/mislabeled content is published to RTD and `llms-full.txt` verbatim.

**Why it matters**

A user upgrading 2.x→3.0 finds an empty changelog entry and a migration guide that never mentions 3.0; the actual 3.0 breaking changes are mis-filed under 2.0.0. LLMs ingesting `llms-full.txt` will misattribute the header-transport flip and taxonomy changes to 2.0. `README:443` also says MIGRATION covers "upgrading from 1.x to 2.0" only.

**Recommendation**

Fix is sound and safe (pure docs editing, no code/import-boundary/API/semver-version impact). Concretely: (1) In `CHANGELOG.md`, the real 3.0 content lives under a MIS-LABELED second `## [2.0.0] - 2026-05-02` header (line 8) — there are TWO `## [2.0.0]` headers (line 8 dated 2026-05-02 vs. the genuine original at line 536 dated 2026-04-20). Rename the line-8 header to `## [3.0.0] - 2026-05-02` and delete the now-redundant empty `## [3.0.0]` stub at line 6 (do NOT just copy the body, which would duplicate ~530 lines and double-publish to `llms-full.txt`). (2) Add the missing bottom compare link `[3.0.0]: .../compare/v2.0.0...v3.0.0` and re-base `[Unreleased]: ...compare/v2.0.0...HEAD` to `...v3.0.0...HEAD`. (3) In `MIGRATION.md`, rename the `## 2.0.0 migration notes` heading (line 3) and its intro (line 4-5) to a 2.x→3.0 section — its body already describes the actual 3.0 deltas (header transport, 60→120 leeway, PaginationError taxonomy), so the content is fine; only the framing/labels are wrong. (4) Update `README.md:443` ("upgrading from 1.x to 2.0") plus the four other 1.x→2.0-only references (lines 185-186, 392-393) to mention 2.x→3.0. Anti-recommendation: do not delete or merge the genuine `## [2.0.0] - 2026-04-20` section (line 536) — that is the real prior release and must stay.

**Fix touches:** `CHANGELOG.md`, `MIGRATION.md`

---

### DOCS-02 · configuration.rst documents four RESTGDF_* env vars that are not wired into Config.from_env (silently ignored)

**Severity:** medium · **Effort:** S · **Location:** `docs/configuration.rst:44,53,56,59; restgdf/_config.py:219-257`

**Evidence**

`configuration.rst` lists `RESTGDF_TRANSPORT_TIMEOUT_TOTAL` (default 300), `RESTGDF_AUTH_TRANSPORT`, `RESTGDF_AUTH_REFRESH_LEEWAY_SECONDS`, `RESTGDF_AUTH_CLOCK_SKEW_SECONDS`. None appear in `_NEW_ENV_SPEC` — the only auth/timeout keys actually resolved are `RESTGDF_TIMEOUT_TOTAL_S`, `RESTGDF_AUTH_TOKEN_URL` and `RESTGDF_AUTH_REFRESH_THRESHOLD_S`. There is no `transport.timeout_total` field (`TransportConfig` only has `verify_ssl`/`user_agent`) and no env wiring for `auth.transport`, `auth.refresh_leeway_s`, or `auth.clock_skew_s`. Defaults are also wrong: docs say timeout default 300 (code `TimeoutConfig.total_s=30.0`) and concurrency default 10 (code `ConcurrencyConfig.max_concurrent_requests=8`).

**Why it matters**

A developer who sets `RESTGDF_AUTH_TRANSPORT=body`, `RESTGDF_AUTH_REFRESH_LEEWAY_SECONDS`, `RESTGDF_AUTH_CLOCK_SKEW_SECONDS`, or `RESTGDF_TRANSPORT_TIMEOUT_TOTAL` per the published docs gets ZERO effect — the var is never read, the library silently keeps defaults (e.g. header transport, 30s timeout). This is published to readthedocs and `llms.txt` so coding agents will emit broken config. The wrong defaults (300 vs 30, 10 vs 8) also mislead capacity planning.

**Recommendation**

Bring `docs/configuration.rst` into exact agreement with `_config.py`'s `_NEW_ENV_SPEC` (the source of truth, corroborated by `MIGRATION.md` lines 398-405). Specifically: (1) Replace `RESTGDF_TRANSPORT_TIMEOUT_TOTAL` (default 300) with `RESTGDF_TIMEOUT_TOTAL_S` (default 30.0) — there is no `transport.timeout_total` field; `TransportConfig` only has `verify_ssl`/`user_agent`. (2) Fix `RESTGDF_CONCURRENCY_MAX_CONCURRENT_REQUESTS` default from 10 to 8. (3) For `RESTGDF_AUTH_TRANSPORT` / `RESTGDF_AUTH_REFRESH_LEEWAY_SECONDS` / `RESTGDF_AUTH_CLOCK_SKEW_SECONDS`, choose ONE of two paths and apply consistently: (a) drop them from the env table (they remain settable via `Config(auth=AuthConfig(transport=..., refresh_leeway_s=..., clock_skew_s=...))` which is the safe, no-code-change option), or (b) if env control is intended, add three entries to `_NEW_ENV_SPEC` mapping `RESTGDF_AUTH_TRANSPORT`->`auth.transport` (str), `RESTGDF_AUTH_REFRESH_LEEWAY_S`->`auth.refresh_leeway_s` (float), `RESTGDF_AUTH_CLOCK_SKEW_S`->`auth.clock_skew_s` (float) — note the canonical suffix is `_S` not `_SECONDS` to match the field names and existing convention, and the leeway/skew validators cap at 600/120 respectively so docs should state those bounds. Path (b) is the more useful fix but is a behavior change (code, not just docs); path (a) is the minimal docs-only correction. (4) Separately, the rst opening (lines 4-12) is also wrong and worth fixing in the same pass: it claims the system is "based on Pydantic Settings" with a 5-step precedence including a `.env` file and `Config`-level constructor `timeout=`, but no `pydantic_settings`/`BaseSettings` exists in the package and `Config.from_env` reads only `os.environ` (or an explicit mapping). Replace with the real `RESTGDF_<CATEGORY>_<FIELD>` env-only resolution plus the deprecated-alias layer. Do not actually delete the `AuthConfig` fields — they are live and used by `token.py`/`credentials.py`.

**Fix touches:** `docs/configuration.rst`, `restgdf/_config.py`

---

### DOCS-03 · ARCHITECTURE.md claims FeatureLayer/Directory own a session and expose close(); they do not

**Severity:** medium · **Effort:** S · **Location:** `ARCHITECTURE.md:129-143; CLAUDE.md:87-91`

**Evidence**

`ARCHITECTURE.md` §Session ownership: "Library-owned session — if no session is provided, restgdf lazily constructs one and closes it when the owning object is `close()`d or used as an async context manager." `CLAUDE.md` (the verified self-check) states the opposite and is correct: "`FeatureLayer`/`Directory` have **no** `close()`/`closed` and require a caller-owned `session` (only the module-level `get_gdf` helper owns a session)." README/quickstart/auth examples always pass `session=...` inside an `async with ClientSession()` and never call `.close()`.

**Why it matters**

A reader relying on the documented "construct without a session, it'll close it" contract will hit a missing/required-session error (`FeatureLayer.from_url` requires `session`) and there is no `close()`/async-context-manager to call. The single authoritative architecture doc directly contradicts the shipped API.

**Recommendation**

Rewrite `ARCHITECTURE.md` §"Session ownership" (lines 137-139). The "Library-owned session" bullet is false as written: it attributes lazy session construction + `close()`/async-context-manager lifecycle to `FeatureLayer`/`Directory`, which have neither. Correct text: the caller must always provide and own the session (it is a REQUIRED positional parameter on both `FeatureLayer.__init__` and `Directory.__init__`); restgdf never closes a caller-supplied session. The ONLY place lazy ownership exists is the module-level helper `restgdf.utils.getgdf.get_gdf(url, session=None, ...)`, which constructs a temporary `aiohttp.ClientSession` when `session is None` and closes it in a `finally` block (`owns_session = session is None; ... if owns_session: await session.close()`). Do NOT "fix" this by adding a `close()`/`__aenter__`/`__aexit__` to `FeatureLayer`/`Directory` to match the doc — that would change the public lifecycle contract the README and all quickstart/auth examples already depend on (every example wraps `from_url(session=session)` in `async with ClientSession() as session:` and never closes the object), and would also be inconsistent with the token-session rule. Fix the doc to match the code, not the reverse. The token-session bullet (lines 141-142) is accurate and can stay.

**Fix touches:** `ARCHITECTURE.md`

---

### DOCS-04 · configuration.rst and authentication.rst claim `.env`-file / pydantic-settings support that does not exist

**Severity:** medium · **Effort:** S · **Location:** `docs/configuration.rst:4-12; docs/authentication.rst:101-107; restgdf/_config.py:295-302; CLAUDE.md:87`

**Evidence**

`configuration.rst`: "uses a layered configuration system based on `Pydantic Settings`" and precedence step 4 "`.env` file in the working directory". `authentication.rst:101`: "Or use a `.env` file (supported by pydantic-settings)". But `Config(BaseModel)` (not `BaseSettings`) resolves only via `from_env` reading `os.environ`; a repo-wide grep finds zero `pydantic-settings`/`pydantic_settings`/`BaseSettings` references and it is not a dependency. `CLAUDE.md` confirms: "no `.env`-file loading (env vars only, despite ARCHITECTURE.md)". `ARCHITECTURE.md:118` repeats the false "`.env` file in the working directory, if present" step.

**Why it matters**

A developer who drops a `.env` with `RESTGDF_*`/`ARCGIS_*` vars per the docs gets none of them loaded (no dotenv reader runs). For the authentication page this is a credential-config footgun: `ARCGIS_USER`/`ARCGIS_PASSWORD` in `.env` are silently not picked up.

**Recommendation**

Confirmed and the fix is sound. In `docs/configuration.rst`: remove the ".env file in the working directory" precedence step (line 11) and the "based on Pydantic Settings" framing (lines 4-5); reframe as "layered, environment-variable + explicit-argument configuration." In `docs/authentication.rst`: delete the ".env file (supported by pydantic-settings)" block (lines 101-107) — keep the `os.environ` example (lines 88-99), which is the real, working pattern — or, if a `.env` example is desired, show explicit user-side loading (e.g. python-dotenv's `load_dotenv()` before reading `os.environ`), making clear restgdf itself does not read `.env`. Also fix `ARCHITECTURE.md:118` (drop the same `.env` precedence step). ANTI-RECOMMENDATION: do NOT "fix" this by adding `pydantic-settings`/`BaseSettings` to make the docs true — `pydantic-settings` is only a transitive docs-build dep (via `autodoc-pydantic`), not a runtime dependency; adding it to the light core would bloat the base install and risk the import-boundary contract guarded by `tests/test_minimal_install.py`. The minimal-fix is docs-only. Optional adjacent cleanup (separate finding, not this one): `tests/test_minimal_install.py:5` docstring also wrongly lists `pydantic_settings` as a "core" dependency though the test never imports it.

**Fix touches:** `docs/configuration.rst`, `docs/authentication.rst`, `ARCHITECTURE.md`

---

### DOCS-05 · configuration.rst Config(...) example uses fields that raise (extra='forbid'/frozen) and wrong nesting

**Severity:** low · **Effort:** S · **Location:** `docs/configuration.rst:24-28; restgdf/_config.py:58,73-79,304-311`

**Evidence**

The quick-start shows `Config(transport={"timeout_total": 120}, concurrency={"max_concurrent_requests": 8})`. `_FROZEN = ConfigDict(extra="forbid", frozen=True, ...)` and `TransportConfig` declares only `verify_ssl` and `user_agent`; `timeout` is a separate sub-config (`TimeoutConfig.total_s`). Passing `transport={"timeout_total":120}` raises pydantic `ValidationError` (unknown field on a `forbid`-extra model).

**Why it matters**

Copy-pasting the documented snippet raises at runtime. The intended knob (`timeout.total_s`) is not discoverable from the example, undermining the configuration page's primary code sample.

**Recommendation**

Fix the quick-start sample in `docs/configuration.rst:25-28` to a valid form, e.g. `Config(timeout={"total_s": 120}, concurrency={"max_concurrent_requests": 8})`. Verified working empirically (yields `timeout.total_s=120.0`, `concurrency.max_concurrent_requests=8`). Note the dict-keyed-by-category form is the canonical pattern already used correctly elsewhere in docs (`observability.md`, `tracing.md`). The recommendation's secondary note is also accurate: `Config` is frozen (`model_config = _FROZEN` at line 302) and the docstring (lines 296-302) directs production code to `get_config()`/`Config.from_env()` rather than direct instantiation, so the example could optionally lead with `get_config()`/`from_env` and present explicit `Config(...)` as a test/override convenience. Anti-rec: do NOT "fix" by relaxing `extra='forbid'` on the sub-configs or adding a `timeout_total` alias to `TransportConfig` — `extra='forbid'` is the intentional design (catches typos), the env table at `rst:44` documents `RESTGDF_TRANSPORT_TIMEOUT_TOTAL` only as an env-var name, and the canonical timeout knob is `timeout.total_s` (line 89). This is a pure doc fix; no code change.

**Fix touches:** `docs/configuration.rst`

---

### DOCS-06 · ARCHITECTURE.md documents a structured detail type `ErrorPayload` that does not exist

**Severity:** low · **Effort:** S · **Location:** `ARCHITECTURE.md:88-90; restgdf/errors.py:419-439`

**Evidence**

`ARCHITECTURE.md`: "Detail types in `restgdf.errors` (e.g. `ErrorPayload`, `RateLimitError.retry_after`, `PaginationError.batch_index`) expose structured metadata". A grep for `ErrorPayload` across the repo matches only `ARCHITECTURE.md` and `CLAUDE.md`'s drift note; `restgdf/errors.py` `__all__` has no such name and no `ErrorPayload` class/type is defined anywhere. (The other two examples, `RateLimitError.retry_after` and `PaginationError.batch_index`, are real.)

**Why it matters**

A reader (or LLM) trying `from restgdf.errors import ErrorPayload` gets `ImportError`. `CLAUDE.md` flags this as known drift but the authoritative architecture doc still asserts the type exists.

**Recommendation**

In `ARCHITECTURE.md:88-90`, remove `ErrorPayload` from the example list, since no such class/type/alias exists in `restgdf.errors` (it is absent from `__all__` at `errors.py:419-439` and from every `class` definition). Replace it with a real structured-detail attribute to keep the sentence illustrative — `RestgdfResponseError.raw` and `RestgdfResponseError.model_name` are both confirmed (`errors.py:77`, `89-90`, `107-109`) and parallel the other two valid examples (`RateLimitError.retry_after`, `PaginationError.batch_index`). This is a pure prose edit to a doc file: it touches no code, no `__all__`, and no import/back-compat boundary, so it carries no risk. Do NOT add an actual `ErrorPayload` class to satisfy the doc — that would invent public API to match stale prose; the code is the source of truth (per `CLAUDE.md`). Note the same paragraph also references `.env`/logger-name claims flagged as drift, which may be worth addressing in the same pass.

**Fix touches:** `ARCHITECTURE.md`

---

### DOCS-07 · ARCHITECTURE.md logger-hierarchy names contradict the enforced LOGGER_SUFFIXES allowlist

**Severity:** low · **Effort:** S · **Location:** `ARCHITECTURE.md:97-104; restgdf/_logging.py:24-33,69-73`

**Evidence**

`ARCHITECTURE.md` documents loggers `restgdf.featurelayer`, `restgdf.streaming`, `restgdf.directory` (and `restgdf.telemetry`). The actual allowlist is `LOGGER_SUFFIXES = ("transport","retry","limiter","concurrency","auth","pagination","normalization","schema_drift")`, and `get_logger` raises `ValueError` for any suffix not in it: `if suffix != "" and suffix not in LOGGER_SUFFIXES: raise ValueError(...)`. So `get_logger("featurelayer")` / `"streaming"` / `"directory"` / `"telemetry"` all raise; none of those logger names are emitted by the library.

**Why it matters**

Operators following the doc to `logging.getLogger("restgdf.featurelayer")` / `"restgdf.streaming"` attach handlers to dead names and see no output (pagination/normalization events actually go to `restgdf.pagination` / `restgdf.normalization`). `MIGRATION.md:41-44` and the upgrading checklist (lines 509-513) list the correct names, so the two docs disagree.

**Recommendation**

Replace the `ARCHITECTURE.md` "Logger hierarchy" tree (lines 97-104) with the eight enforced suffixes from `LOGGER_SUFFIXES` — `transport`, `retry`, `limiter`, `concurrency`, `auth`, `pagination`, `normalization`, `schema_drift` — matching `MIGRATION.md:41-44` and the upgrading checklist (509-513). Keep short inline comments, but make them map the code subsystem to its real logger name rather than reintroducing module-named loggers: e.g. note that feature-layer streaming/pagination events emit under `restgdf.pagination`, drift under `restgdf.schema_drift`, geometry/SR normalization under `restgdf.normalization`, and HTTP under `restgdf.transport`/`restgdf.retry`. Do NOT instead "fix" the code by adding `featurelayer`/`streaming`/`directory`/`telemetry` to `LOGGER_SUFFIXES` — those four are never used as `get_logger()` suffixes, `restgdf.schema_drift`/`restgdf.auth`/`restgdf.transport` etc. are the 2.x public logging contract that tests assert on (docstring lines 3-8), and broadening the allowlist would create dead, never-emitting logger names and weaken the BL-25 "every logger needs an explicit ledger entry" invariant.

**Fix touches:** `ARCHITECTURE.md`

---

### DOCS-08 · CONTRIBUTING.md targets the stale `integration/3.0-rewrite` branch and references unshipped plan.md

**Severity:** low · **Effort:** S · **Location:** `CONTRIBUTING.md:1-6,86,16-17`

**Evidence**

`CONTRIBUTING.md`: "the gate suite contributors are expected to run before opening a pull request against `integration/3.0-rewrite` (or `main` once 3.0 is released)". 3.0.0 is released (`CHANGELOG`/`CLAUDE.md` confirm). It also says "Gates mirror `plan.md` §2 exactly" and "Reference plan item IDs (e.g. `BL-46`) and backlog rows" — `plan.md` is not shipped in the repo (internal plan).

**Why it matters**

A new contributor branches PRs against a non-default/likely-deleted branch and is pointed at a `plan.md` that isn't in the tree. Minor friction; doesn't affect library consumers.

**Recommendation**

Sound, with one caveat. Two distinct sub-issues, both verified:

1. Stale branch target (`CONTRIBUTING.md:5-6`): "before opening a pull request against `integration/3.0-rewrite` (or `main` once 3.0 is released)". 3.0.0 is released (`CHANGELOG.md:6` "[3.0.0] - 2026-05-02") AND `integration/3.0-rewrite` no longer exists on the remote (`git ls-remote --heads origin` shows only main, fix/spatial-filter-curve-support, and dependabot branches; `origin/HEAD -> main`). A new contributor reading this would target a deleted branch. FIX: replace lines 5-6 with just `main`. Safe edit, no contract/import-boundary impact.

2. `plan.md` references (`CONTRIBUTING.md:86` "Gates mirror `plan.md` §2 exactly"; `:67` "Reference plan item IDs (e.g. `BL-46`)"). `plan.md` is confirmed NOT shipped (Glob `**/plan.md` = no files; it is referenced only as a citation token in docstrings). CAVEAT on the recommendation: the BL-/R-/plan IDs are NOT merely "fine as commit references" to be loosely kept — they are load-bearing internal citation anchors pervasive across the SHIPPED source (`restgdf/errors.py:128` R-02, `utils/_concurrency.py` R-18/R-19/R-44, `utils/token.py`, `_models/_settings.py`, plus tests). So do NOT strip the IDs from the codebase. For `CONTRIBUTING.md` specifically: drop the phrase "mirror `plan.md` §2 exactly" (replace with "the gate suite below") and soften `:67` to not promise an in-tree `plan.md`, but leave the `BL-46` example as an illustrative ID. The original recommendation's "BL-/R- IDs are fine as commit references" line is correct; its "`mirror plan.md §2` should be dropped" is correct.

Both edits are docs-only, touch no public API, light-core boundary, or back-compat seam.

**Fix touches:** `CONTRIBUTING.md`

---

### DOCS-09 · docs/errors.rst documents FieldDoesNotExistError attribute as `field`; the real attribute is `field_name`

**Severity:** low · **Effort:** S · **Location:** `docs/errors.rst:118; restgdf/errors.py:143-167`

**Evidence**

`errors.rst` structured-attributes table row: `FieldDoesNotExistError` → attributes `field`, `context`. The class sets `self.field_name = field_name` (`errors.py:150`); there is no `field` attribute (grep confirms only `self.field_name`). The docstring (`errors.py:134`) also names it `field_name`.

**Why it matters**

A caller doing `exc.field` for programmatic recovery hits `AttributeError`; the correct access is `exc.field_name`. Low frequency but a real wrong-API claim in the published error-handling reference.

**Recommendation**

In `docs/errors.rst:119`, change the structured-attribute name from `field` to `field_name` so the table matches the actual attribute (`errors.py:150`), the class docstring (`errors.py:134`), and the tests (`test_fielddoesnotexist_raises.py:57,64`). Docs-only edit; safe and breaks nothing. Do NOT take the inverse fix of adding a `field` attribute/alias to the class — that would create a duplicate name for the same data and contradict the documented `field_name` contract in the docstring.

**Fix touches:** `docs/errors.rst`

---

### DOCS-10 · README 2.0 collapsible and SECURITY.md supported-versions are stale for the shipped v3.0.0

**Severity:** low · **Effort:** S · **Location:** `README.md:51-138,443; SECURITY.md:7-11; CLAUDE.md:26-30`

**Evidence**

README collapsible is titled "2.0 release highlights and migration summary" and the body reads "restgdf 2.0.0 includes..." / "restgdf 2.0 is a **major release**" though the package is v3.0.0; `README:443` says MIGRATION covers "upgrading from 1.x to 2.0". `SECURITY.md` supported-versions table lists only `2.x ✅` (no 3.x row) for a 3.0.0 release. `CLAUDE.md` explicitly catalogs both as known drift, so the `CLAUDE.md` self-check note is accurate but the underlying docs remain drifted.

**Why it matters**

Users on the PyPI/RTD landing page see 2.0-era framing for a 3.0 library and a security policy that doesn't list the current major as supported. Cosmetic-to-trust drift; no functional breakage.

**Recommendation**

Docs-only fix, breaks no code/import boundary. (1) `README.md:51-97` — reframe the collapsible to 3.0 (retitle the summary, change "restgdf 2.0.0 includes" / "restgdf 2.0 is a major release" to 3.0) OR relabel it explicitly as "Historical: 2.0 release notes" so the 2.0 framing reads as intentional history rather than the current major. (2) `SECURITY.md:7-11` — add a `3.x ✅` row. Caveat: do not naively "mark 2.x per policy" without reconciling line 5, which states only the *latest minor line* gets updates; the consistent edit is `3.x ✅` and `2.x ✗` (or soften line 5 to a deliberate N-1 grace window if 2.x is in fact still patched). Pick one and make the table and the prose agree. (3) `README.md:443` — align the MIGRATION pointer with `MIGRATION.md`'s actual scope: the file currently documents "2.0.0 migration notes" plus the preserved "1.x → 2.0" guide and has NO 3.0 section, so either add a 3.0 migration section to `MIGRATION.md` and update the pointer, or restate it as "upgrading to 2.0 (and 1.x → 2.0)". Avoid claiming a 3.0 migration guide exists until one is written.

**Fix touches:** `README.md`, `SECURITY.md`

---

### DOCS-11 · _config.py module docstring says "Seven" sub-configs; there are eight

**Severity:** low · **Effort:** S · **Location:** `restgdf/_config.py:3-6,295-311`

**Evidence**

Module docstring: "Seven frozen pydantic 2.x sub-configs ... `:class:`TransportConfig``, `:class:`TimeoutConfig``, `:class:`RetryConfig``, `:class:`LimiterConfig``, `:class:`ConcurrencyConfig``, `:class:`AuthConfig``, `:class:`TelemetryConfig``." But the `Config` class aggregates eight (it adds `resilience: ResilienceConfig`, lines 311), and the `Config` class docstring itself (line 296) correctly says "Aggregate of the eight sub-configs." `MIGRATION.md:367` and `README:74` also say eight. `CHANGELOG.md:176` likewise still says "seven".

**Why it matters**

Minor internal-doc inconsistency; `ResilienceConfig` is omitted from the docstring enumeration. Low user impact (the docstring isn't the primary config reference) but it's a self-contradiction within the same file.

**Recommendation**

In `restgdf/_config.py` module docstring (lines 3-6), change "Seven frozen pydantic 2.x sub-configs" to "Eight" and add `:class:`ResilienceConfig`` to the enumerated list (it can be appended after `:class:`TelemetryConfig``, mirroring the field order at line 311). This is a prose-only edit with no runtime, import-boundary, or back-compat impact. Optionally fix the "seven" wording in `CHANGELOG.md:176` for consistency. No anti-recommendation needed — the naive fix is safe.

**Fix touches:** `restgdf/_config.py`, `CHANGELOG.md`

---

### DOCS-12 · docs/quickstart.md light-core example uses the deprecated row_dict_generator

**Severity:** low · **Effort:** S · **Location:** `docs/quickstart.md:35; CLAUDE.md:54-57`

**Evidence**

`quickstart.md` light-core sample: `async for row in beaches.row_dict_generator(data={"outFields": "CITY,STATE"}):`. `CHANGELOG`/`MIGRATION` mark `row_dict_generator` deprecated in favour of `stream_rows`, and `CLAUDE.md` notes that touching the deprecated alias from inside the package escalates to an error in the suite. The README light-core example (`README.md:207`) correctly uses `stream_rows`, so the two user-facing docs diverge.

**Why it matters**

New users copying the quickstart adopt a deprecated API (and will see a `DeprecationWarning`). Not broken, but steers users to the soon-to-be-removed surface; inconsistent with the README's own modern example.

**Recommendation**

Change `docs/quickstart.md:35` from `async for row in beaches.row_dict_generator(data={"outFields": "CITY,STATE"}):` to `async for row in beaches.stream_rows(data={"outFields": "CITY,STATE"}):`. This is a safe, docs-only edit: `stream_rows` accepts the identical `data=` kwarg (the README's parallel example at `README.md:207` uses exactly this call shape), there is no import-boundary or back-compat risk, and it aligns the quickstart with the project's own recommended API. No anti-recommendation needed — the naive fix is the correct fix.

**Fix touches:** `docs/quickstart.md`

---

## Minor notes (not adversarially verified)

These were flagged by the axis auditor but did NOT go through per-finding verification — treat as leads, not confirmed findings.

- **errors.rst OptionalDependencyError example message is illustrative, not literal** — `docs/errors.rst:74` comment shows `# "geopandas required — pip install 'restgdf[geo]'"`. The actual message from `restgdf/utils/_optional.py:23-26` is `"<feature> requires optional dependency 'geopandas'. Install \`restgdf[geo]\` to enable ..."`. It's a code comment (illustrative), so low impact, but a reader matching on the string would be surprised.
- **ARCHITECTURE.md extras matrix omits aiolimiter from the resilience extra description** — `ARCHITECTURE.md:174` lists `restgdf[resilience] # + stamina (retry on transient errors)` but `CHANGELOG.md:317-318` and `MIGRATION.md:17` state the resilience extra is `stamina>=24.2` AND `aiolimiter>=1.1` (the limiter is half the feature). Minor incompleteness in the extras table; the README resilience section (line 133) correctly mentions both.
- **ARCHITECTURE.md config-precedence lists constructor `timeout=` precedence that has no general mechanism** — `ARCHITECTURE.md:115-119` and `configuration.rst:8` present a 5-level precedence with `FeatureLayer.from_url(timeout=…)` as level 1. Could not fully verify a general Config-override-from-constructor pathway exists beyond per-call aiohttp timeout kwargs; flagging as possibly-overstated precedence prose. Left unverified pending an ASYNC/CONFIG-axis read of `from_url` timeout plumbing.
- **CHANGELOG self-inconsistency: 3.0 breaking changes filed under the 2.0.0 heading** — Beyond the empty `## [3.0.0]` header, the CHANGELOG's 2.0.0 'Changed/Breaking' section (lines 9-533) describes 3.0-era work (Gate-3 hardening, `_choose_verb` POST forcing, v3-followup tranches, fail_under 96→97). The dated `## [2.0.0] - 2026-04-20` section lower down (line 536) is the real 2.0 entry, so there are two 2.0.0 headers with different dates (2026-05-02 vs 2026-04-20). Worth a maintainer pass to disambiguate which content belongs to 3.0.
- **README 'Plain Markdown (per page)' URL example may not match sphinx-llm output path** — `README.md:424` documents "append `.md` to any page — e.g. `.../quickstart.html.md`". Could not verify the sphinx-llm.txt extension actually emits `<page>.html.md` files (vs `<page>.md`); flagging as an unverified docs claim about the publishing pipeline output naming.
