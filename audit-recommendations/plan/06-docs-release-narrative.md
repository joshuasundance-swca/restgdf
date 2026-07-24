# 06 — Docs, release narrative & packaging metadata

> Workstream of the restgdf remediation plan · audit pinned `4673b08` · 2026-06-13

## Goal

Bring every human- and LLM-facing prose surface back into agreement with the shipped v3.0.0 code: fix the botched CHANGELOG 3.0.0 promotion, re-frame MIGRATION/README/SECURITY for the current major, and purge the concrete code-contradicting claims in ARCHITECTURE.md and the Sphinx `.rst`/`.md` docs (invented env vars, `.env`/pydantic-settings support, a non-existent `ErrorPayload`, dead logger names, a raising `Config(...)` example). These docs are published verbatim to readthedocs and `llms-full.txt`, so the drift actively mis-trains both developers and coding agents; landing this workstream makes the published narrative trustworthy and lets the BL-41 release gate (hardened in W1-4) protect a real, non-empty changelog. This is single-writer prose with zero runtime/import-boundary impact — its risk is sequencing against the code decisions it must mirror, not the edits themselves.

## Collision domain

W6 owns as **single-writer** (from the allocation `owns[]`):

- `ARCHITECTURE.md`
- `MIGRATION.md`
- `CHANGELOG.md`
- `README.md`
- `CONTRIBUTING.md`
- `SECURITY.md`
- `docs/*.rst` (configuration, authentication, errors; adapters/models/resilience/telemetry/restgdf/index untouched here)
- `docs/*.md` (quickstart, changelog/migration shims)
- `CITATION.cff`

No file in this domain is a split-writer with another workstream. Every W6 item is **prose-only**; the *code* halves of the shared findings live in other workstreams (W1 owns the `pyproject.toml`/workflow gate edits; W2/W3/W4/W5 own the `restgdf/` source). The split-ownership relationship is therefore "doc-side here, code-side elsewhere" — W6 never writes code and the code workstreams never write these prose files. The only shared hot-files *inside* W6 are the docs that several W6 items co-touch, all serialized by single-writer ordering below:

- `CHANGELOG.md` — W6-5 (primary) plus a one-word "seven→eight" sub-config fix that DOCS-11 lists for it (line 175).
- `MIGRATION.md` — W6-4 only.
- `README.md` — W6-6 only.
- `SECURITY.md` — W6-1 only.
- `ARCHITECTURE.md` — W6-3 only.
- the three `docs/*.rst`/`docs/*.md` config/auth/errors/quickstart/recipe files — W6-7 only.

## Sequencing & parallelization

**Milestone order:** M1 (W6-1, W6-2) → M3 (W6-3) → M4 (W6-4, W6-5, W6-6, W6-7).

- **M1 — fully parallel, no deps.** W6-1 (`SECURITY.md`) and W6-2 (`CONTRIBUTING.md`) touch disjoint files and have no `Depends`. Land both immediately; they are pure quick wins that do not wait on any code decision. W6-2 carries a `Decision` (PACKAGING-03 dev-extra) but its doc fix is decoupled from the pyproject decision (see item).

- **M3 — W6-3 (`ARCHITECTURE.md`), formally gated on the code DECISIONS it mirrors.** W6-3's allocation note is explicit: the CONFIG-03/CONFIG-04 and AUTH-02 prose "must match whatever the code items (W3-4 / W3-5 / W2-2) decide — sequence after those decisions." Its CONFIG-03 (`Config(...)` precedence), CONFIG-04 (`.env`), and AUTH-02 (`InvalidCredentialsError` raise-site) paragraphs are correct only once those items have chosen *implement vs delete-the-claim*. To make the milestone gate actually protect those paragraphs (rather than relying on a prose-only "do not finalize" note against an M2 schedule), W6-3 now carries **formal `Depends: W2-2, W3-4`** and is scheduled at **M3**; the CONFIG-04 `.env` step additionally mirrors W3-5, an **M2** code item that lands before this M3-gated item, so the M3 gate covers it without a separate edge. **Decision-free split:** the ErrorPayload/logger-name/session-ownership/dev-extra paragraphs (Spec steps 1, 2, 3, 7) are pure code-is-truth deletions with no pending decision and MAY be drafted as an early M2 sub-commit; the two decision-dependent paragraphs (CONFIG-03 precedence step 5, AUTH-02 `# HTTP 401` step 6) finalize only after W3-4/W2-2 land. As a unit the item gates at M3.

- **M4 — W6-4, W6-5, W6-6, W6-7: each gated on its code lane, but mutually disjoint files so parallel across the four once unblocked.**
  - W6-4 (`MIGRATION.md`) `Depends`: **W2-2, W2-10, W3-1, W3-3, W5-13** — it documents the final verify_ssl source/seam (W3-1/W2-10), AuthConfig wiring decision (W3-3), the InvalidCredentialsError/RestgdfResponseError contract (W2-2), and the drift-scope behavior (W5-13). Sequence after those land.
  - W6-5 (`CHANGELOG.md`) `Depends`: **W1-4** (the hardened empty-section gate). W6-5 must produce a non-empty `## [3.0.0]` body so the W1-4 gate (and the W1-1 release-cut test gate) goes green; conversely W1-4's gate is what proves W6-5 succeeded. Land W6-5 before or in lockstep with the next release cut.
  - W6-6 (`README.md`) `Depends`: **W2-1, W4-1** — it documents that `token=`/`data["token"]` now routes via POST (W2-1 / AUTH-01) and that the geo path now raises on truncation (W4-1 / PAGINATION-01). Sequence after those code items land.
  - W6-7 (Sphinx docs) `Depends`: **W3-6, W5-12, W4-1** — env-var table truth (W3-6 reconciliation decision), observability filter behavior (W5-12), streaming truncation (W4-1).
  - These four write four disjoint file sets, so once each one's code lane is green they can be drafted and merged in parallel. The only cross-W6 coupling is that W6-4 and W6-5 both reference the same v3.0.0 breaking-change set — keep them consistent (same canonical wording for the token-transport flip, PaginationError taxonomy, ValueError-shim policy) but they remain separate files.

**Critical cross-workstream edges to call out:**
- W6-3 carries formal `Depends: W2-2, W3-4` (config/auth-401 decisions) and is M3-scheduled; it additionally mirrors W3-5's `.env` decision; W3-5 is an **M2** code item and lands earlier, so the M3 gate covers it. Block on those decisions/landings before finalizing the precedence/`.env`/auth-401 prose.
- W6-4 blocks on W3-1 landing the verify_ssl source-of-truth and W2-10 landing the seam, plus W3-3 (AuthConfig wiring) and W2-2 (auth-401 contract) and W5-13 (drift scope).
- W6-5 blocks on W1-4 landing the CHANGELOG-aware empty-section gate.
- W6-6 blocks on W2-1 (token-in-body POST) and W4-1 (geo truncation raise).
- W6-7 blocks on W3-6 (env-var reconciliation), W5-12 (log filter), W4-1 (streaming truncation).

## Work items

### W6-1 · SECURITY.md: add the 3.x supported row

**Audit refs:** PACKAGING-02, DOCS-10 · **Severity:** medium · **Effort:** S · **Milestone:** M1
**Depends:** — · **Blocks:** —
**Split-ownership:** Owns the SECURITY half of DOCS-10; the README half of DOCS-10 (2.0 collapsible re-framing, MIGRATION pointer) is owned by **W6-6**. Covers PACKAGING-02 in full.
**Scope** — In: the Supported-Versions table and its governing sentence in `SECURITY.md`. Out-of-scope: README/MIGRATION (W6-6/W6-4); wiring the table into bumpver `file_patterns` — the audit (PACKAGING-02) explicitly warns this is awkward because bumpver does MAJOR.MINOR.PATCH literal substitution, not an "X.x" major token, so do NOT attempt to auto-stamp the table.
**Spec**
1. In `SECURITY.md`, the table lists only `2.x ✅`, `1.x ✗`, `< 1.0 ✗` (verified: SECURITY.md:9-11) under the sentence "Only the latest minor release line of `restgdf` receives security updates." (verified: SECURITY.md:5). Package is at `version = "3.0.0"` (verified: pyproject.toml:14, audit-cited). The table is internally inconsistent: per its own rule the *latest* line (3.x) is unlisted.
2. Add a `| 3.x | :white_check_mark: |` row and demote 2.x to `| 2.x | :x: |` (per PACKAGING-02 / DOCS-10 recommendation), UNLESS the maintainer confirms 2.x is still patched — see Decision below.
3. Reconcile line 5 (verified: SECURITY.md:5) with the table: it says only the *latest minor* line is supported. The consistent edit is the single-major form. PACKAGING-02's preferred refinement is to make the policy self-maintaining: replace the hard-coded rows with prose like "the current major release line (currently 3.x) receives security updates" so it can't silently rot on the next bump. Apply that wording so line 5 and the table agree.
4. Do NOT add a SECURITY.md review step to the release gate here — PACKAGING-02 floats it as a CONTRIBUTING checklist idea, but the CONTRIBUTING gate-table edits are W6-2's surface; if added, do it there, not as a code/workflow change (W1 owns workflows).
**Acceptance criteria**
- [ ] `SECURITY.md` table contains a `3.x ✅` row and 2.x is reconciled (✗ or an explicit, documented N-1 grace window).
- [ ] Line 5 prose and the table no longer contradict each other (single-major-line rule, or a stated grace window).
- [ ] No bumpver `file_patterns` change introduced (anti-recommendation honored).
- [ ] Doc-sync: SECURITY.md self-consistency confirmed by reading; no code change so no red-state test (pure prose, PACKAGING-02 is doc-only).
**Validation** — lint (pre-commit will run prettier/markdown hooks over `SECURITY.md`).
**Risks & rollback** — Failure mode: claiming 2.x is unsupported when the maintainer still patches it. Mitigated by the Decision below. Rollback: revert the single-file edit. Anti-recommendation honored: no bumpver auto-stamp of the X.x table.

**Decision required** — see Decisions section (2.x support window).

---

### W6-2 · CONTRIBUTING.md: fix stale branch, coverage claim, dev-extra claim

**Audit refs:** DOCS-08, CICD-04, PACKAGING-03 · **Severity:** low · **Effort:** S · **Milestone:** M1
**Depends:** — · **Blocks:** —
**Split-ownership:** Doc-side of CICD-04 (the actual PR coverage-gate fix is **W1-3**) and the **CONTRIBUTING.md** dev-extra prose half of PACKAGING-03 (its co-owner is **W6-3**, which owns the ARCHITECTURE.md dev-extra prose half; the `pyproject.toml` dev-extra decision itself is **W1**'s, per allocation note — keep all three consistent). Owns DOCS-08 in full.
**Scope** — In: the stale `integration/3.0-rewrite` branch target, the `plan.md` references, the `.[dev]` "covers docs tooling" prose, the "CI re-runs the same gates" coverage claim, and the "Gates mirror plan.md §2 exactly" line in `CONTRIBUTING.md`. Out-of-scope: changing the actual coverage CI gate (W1-3), changing the `pyproject.toml` dev extra (W1 / PACKAGING-03 pyproject part), stripping `BL-`/`R-` plan IDs from the shipped source (DOCS-08 anti-rec: those are load-bearing citation anchors across `restgdf/` and tests — do NOT touch code).
**Spec**
1. **Stale branch (DOCS-08 sub-issue 1):** lines 4-6 read "before opening a pull request against `integration/3.0-rewrite` (or `main` once 3.0 is released)" (verified: CONTRIBUTING.md:5-6). 3.0.0 is released and the branch no longer exists on the remote. Replace with just `main`.
2. **plan.md references (DOCS-08 sub-issue 2):** line 86 "Gates mirror plan.md §2 exactly:" (verified: CONTRIBUTING.md:86) and line 67 "Reference plan item IDs (e.g. `BL-46`)" (verified: CONTRIBUTING.md:67). `plan.md` is not shipped. Drop "mirror `plan.md` §2 exactly" → "the gate suite below". Soften line 67 so it no longer promises an in-tree `plan.md`, but KEEP the `BL-46` example as an illustrative ID (anti-rec: the IDs themselves stay).
3. **CICD-04 doc-side (coverage):** line 98 "CI will re-run the same gates" (verified: CONTRIBUTING.md:98) and gate #2 at line 91 (verified: CONTRIBUTING.md:91) assert the PR gate runs the 97% coverage floor. Today that floor runs only post-merge. Coordinate with **W1-3**: if W1-3 has already moved the coverage gate onto PRs, this claim becomes TRUE and needs no change beyond confirming wording. If W1-3 lands after, leave the prose accurate to the *target* state and note in the PR that it depends on W1-3. Do NOT weaken the claim to "post-merge only" — the agreed fix (W1-3) makes the PR gate real; the doc should describe the fixed behavior.
4. **PACKAGING-03 doc-side (dev extra):** line 30 "`.[dev]` covers testing + linting + docs tooling" (verified: CONTRIBUTING.md:30) and the Quick Start `pip install -e ".[dev,resilience,telemetry,geo]"` (verified: CONTRIBUTING.md:26), plus gate #4 (sphinx, line 93) and gate #7 (`build`/`twine`, line 96). The `dev` extra ships neither `twine`/`build` nor `sphinx` (verified: pyproject.toml:87-99 lists no twine/build/sphinx; sphinx lives in the `doc` extra at pyproject.toml:101-108). Per the Decision below, EITHER (a) if W1 adds `build`+`twine` (and composes `doc`) into `dev`, the prose is already correct — confirm only; OR (b) if W1 keeps the extras as-is, correct line 30 to stop claiming `.[dev]` covers docs/packaging and adjust the Quick Start (line 26) to add `doc` and `build`/`twine` so a contributor who follows it can actually run gates 4 and 7. Do NOT add build/twine/sphinx to any runtime/shipped extra (PACKAGING-03 anti-rec — they are dev-only and never imported by `restgdf`).
**Acceptance criteria**
- [ ] No `integration/3.0-rewrite` reference remains in `CONTRIBUTING.md`; PR target is `main`.
- [ ] No prose promises an in-tree `plan.md`; `BL-46` survives only as an illustrative ID.
- [ ] Coverage prose (line 98 / gate #2) matches the W1-3 target state (PR gate runs the floor).
- [ ] Dev-extra prose matches the W1 PACKAGING-03 decision (either `.[dev]` now ships build/twine/doc, or the docs/Quick Start no longer over-claim and name the extra(s) needed for gates 4/7).
- [ ] Doc-sync only; no code/behavior change → no red-state test required (DOCS-08/CICD-04 doc-side/PACKAGING-03 doc-side are all prose).
**Validation** — lint.
**Risks & rollback** — Failure mode: prose describes a coverage/dev-extra state that W1/W1-3 ends up not implementing → doc drifts again. Mitigated by confirming W1/W1-3 decisions before merging this. Rollback: revert the single-file edit.

**Decision required** — see Decisions section (PACKAGING-03 dev-extra direction; owned by W1's pyproject choice, W6-2 mirrors it).

---

### W6-3 · ARCHITECTURE.md: remove code-contradicting claims

**Audit refs:** DOCS-03, DOCS-04, DOCS-06, DOCS-07, CONFIG-03, CONFIG-04, PACKAGING-03, AUTH-02 · **Severity:** medium · **Effort:** M · **Milestone:** M3
**Depends:** W2-2, W3-4 · **Blocks:** —
**Milestone/Depends note:** The decision-free deletions in this item (ErrorPayload, logger names, session-ownership, dev-extra — Spec steps 1, 2, 3, 7) are M2-ready and may be drafted at M2 start, but the two decision-dependent paragraphs — CONFIG-03 precedence (step 5, gated on W3-4) and AUTH-02 `# HTTP 401` (step 6, gated on W2-2) — cannot finalize until those code decisions land. The whole item is therefore scheduled at **M3** with formal `Depends: W2-2, W3-4` so the milestone gate enforces the prose's stated ordering; the `.env` step 4 additionally mirrors W3-5 (CONFIG-04), an **M2** code item that lands before this M3 item, so the M3 gate already covers it without a separate edge. (Implementers MAY land the four decision-free deletions as an early M2 sub-commit if they prefer, but the item as a unit gates at M3.)
**Split-ownership:** ARCHITECTURE.md prose only. Code-side counterparts: CONFIG-03 → **W3-4** (implement-vs-delete explicit-`Config` precedence), CONFIG-04 → **W3-5** (implement-vs-delete `.env`), AUTH-02 → **W2-2** (InvalidCredentialsError raise-site decision), PACKAGING-03 → the **CONTRIBUTING.md** dev-extra prose half is **W6-2** and the `pyproject.toml` dev-extra decision is **W1**'s. This item's prose MUST match those decisions. DOCS-04 is split-ownership *within* the docs surface: this item owns the ARCHITECTURE.md `.env` half, and the `docs/configuration.rst` + `docs/authentication.rst` `.env`/pydantic-settings prose half of DOCS-04 is owned by **W6-7** (mirroring W6-7's reciprocal note) — keep both `.env` doc edits consistent with each other and with W3-5's decision.
**Scope** — In: the ErrorPayload example, the `.env`/`Config(...)` precedence layers, the logger-hierarchy tree, the session-ownership "Library-owned session" bullet, the dev-extra matrix line, and the AUTH-02 `# HTTP 401`/"all failures raise RestgdfError" framing in `ARCHITECTURE.md`. Out-of-scope: adding an `ErrorPayload` class, a `close()`/`__aenter__` to FeatureLayer/Directory, broadening `LOGGER_SUFFIXES`, or adding pydantic-settings — every one of these is an explicit audit anti-recommendation (fix the doc, not the code).
**Spec**
1. **DOCS-06 (ErrorPayload):** lines 88-90 list `ErrorPayload` as a detail type (verified: ARCHITECTURE.md:88-90). No such class exists. Remove `ErrorPayload` and replace it with a real structured-detail attribute to keep the sentence illustrative — DOCS-06 confirms `RestgdfResponseError.raw` and `RestgdfResponseError.model_name` exist. Keep the two already-valid examples (`RateLimitError.retry_after`, `PaginationError.batch_index`). Do NOT add an `ErrorPayload` class.
2. **DOCS-07 (logger names):** the "Logger hierarchy" tree at lines 98-105 (verified: ARCHITECTURE.md:98-105; audit cited 97-104 — drift: was 97-104, now the tree body is 98-105) lists `restgdf.featurelayer`, `restgdf.streaming`, `restgdf.directory`, `restgdf.telemetry` — all of which `get_logger()` rejects with `ValueError` (suffix not in `LOGGER_SUFFIXES`). Replace the tree with the eight enforced suffixes `transport, retry, limiter, concurrency, auth, pagination, normalization, schema_drift`, matching MIGRATION.md:41-44 (verified: MIGRATION.md:41-43) and MIGRATION.md:419 (verified: MIGRATION.md:419). Map subsystem→real logger in inline comments (streaming/pagination → `restgdf.pagination`, drift → `restgdf.schema_drift`, normalization → `restgdf.normalization`, HTTP → `restgdf.transport`/`restgdf.retry`). Do NOT add the four dead names to `LOGGER_SUFFIXES` (DOCS-07 anti-rec).
3. **DOCS-03 (session ownership):** the "Library-owned session" bullet at lines 137-139 (verified: ARCHITECTURE.md:137-139) falsely says FeatureLayer/Directory lazily construct + `close()` a session. Rewrite: the caller must always provide and own the session (required positional on both `FeatureLayer.__init__` and `Directory.__init__`); restgdf never closes a caller-supplied session; the ONLY lazy-ownership site is `restgdf.utils.getgdf.get_gdf(url, session=None, ...)`, which closes a temp session in `finally`. The token-session bullet (lines 141-142, verified: ARCHITECTURE.md:141-142) is accurate — keep it. Do NOT add `close()`/`__aenter__`/`__aexit__` to FeatureLayer/Directory (DOCS-03 anti-rec).
4. **DOCS-04 / CONFIG-04 (`.env`):** precedence step 4 "`.env` file in the working directory, if present." at line 118 (verified: ARCHITECTURE.md:118). Delete step 4 and renumber 5→4. **Sequence after W3-5 decides** implement-vs-delete `.env`; if W3-5 chooses to *not* implement dotenv (the recommended path), delete the layer; if W3-5 implements an opt-in helper, document that exact mechanism instead. **DOCS-04 co-ownership:** this ARCHITECTURE.md `.env` edit is one half of DOCS-04; the `docs/configuration.rst` + `docs/authentication.rst` `.env`/pydantic-settings prose half is owned by **W6-7** (step 2 of that item) — keep this deletion consistent with W6-7's `.env` reframing so both doc edits make the same claim about restgdf not reading `.env`. Do NOT add pydantic-settings to make the claim true (DOCS-04 anti-rec).
5. **CONFIG-03 (`Config(...)` precedence):** precedence step 2 "`Config(...)` instance passed explicitly" at line 116 (verified: ARCHITECTURE.md:116). **Sequence after W3-4 decides** implement-vs-delete. If W3-4 deletes the claim (recommended), reword the precedence to: constructor/aiohttp kwargs (e.g. `timeout=`) > env vars > defaults, resolved process-globally via the size-1-cached `get_config()`; a freshly built `Config(...)` is not injectable into the request path; note `ArcGISTokenSession(config=...)` injection is session-scoped and separate. If W3-4 implements injection, document the real seam. Do NOT add `config=` to FeatureLayer as a doc-driven quick fix (CONFIG-03 anti-rec).
6. **AUTH-02 / ERRTAX-01 (error umbrella):** line 57 "All runtime failures raise a subclass of `restgdf.RestgdfError`" (verified: ARCHITECTURE.md:57) and `InvalidCredentialsError # HTTP 401` at line 71 (verified: ARCHITECTURE.md:71). **Sequence after W2-2 decides.** If W2-2 wires `InvalidCredentialsError` into the 4xx token path (the audit's "wire it" option), the `# HTTP 401` annotation becomes true — keep it. If W2-2 takes the doc-fix-only path, change line 71's annotation and the line-57 umbrella claim to state that AGOL bad-creds surface as `RestgdfResponseError(model_name="TokenResponse")` and reserve InvalidCredentialsError/TokenRequiredError as not-currently-raised. Mirror MIGRATION.md:145 (W6-4) so the two docs stay consistent.
7. **PACKAGING-03 (dev extra, ARCHITECTURE side):** line 177 `restgdf[dev]  # + pytest, pre-commit, sphinx, twine, build` (verified: ARCHITECTURE.md:177). Per the W1 PACKAGING-03 decision (mirrored in W6-2): if `dev` does not ship sphinx/twine/build, drop `sphinx, twine, build` from line 177 (or note they install separately). Keep consistent with whatever W6-2/W1 chose. Do NOT add these to a shipped extra.
**Acceptance criteria**
- [ ] No `ErrorPayload` token remains in `ARCHITECTURE.md`; the example sentence cites only real detail attributes.
- [ ] Logger-hierarchy tree lists exactly the eight `LOGGER_SUFFIXES` and no module-named loggers.
- [ ] Session-ownership section states caller-owned-only for FeatureLayer/Directory and names `get_gdf` as the sole lazy-owning helper.
- [ ] `.env` precedence layer and `Config(...)` precedence layer match the W3-5 / W3-4 landed decisions.
- [ ] Error-umbrella/`# HTTP 401` prose matches the W2-2 landed decision and MIGRATION.md:145 (W6-4).
- [ ] dev-extra matrix line matches the W1/W6-2 PACKAGING-03 decision.
- [ ] Doc-sync: all eight findings' prose verified against current code by reading; no code change → no red-state test (all anti-recs forbid code edits here).
**Validation** — lint; docs (ARCHITECTURE.md is not Sphinx-built but run `docs` to confirm no cross-reference regressions to the included pages).
**Risks & rollback** — Failure mode: finalizing the CONFIG-03/04 or AUTH-02 prose before W3-4/W3-5/W2-2 lands → doc re-drifts to the wrong decision. Mitigated by the formal `Depends: W2-2, W3-4` edges and the M3 schedule (with W3-5 covered by the same M3 gate), which enforce the prose's stated ordering. Rollback: revert the single-file edit. All four anti-recommendations (no ErrorPayload class, no FeatureLayer close(), no LOGGER_SUFFIXES widening, no pydantic-settings) are preserved as explicit do-NOT steps.

---

### W6-4 · MIGRATION.md: refresh for 3.0 and correct claims

**Audit refs:** DOCS-01, AUTH-02, AUTH-03, AUTH-04, CONFIG-02, ERRTAX-04, OPTDEPS-02, TELEMETRY-02 · **Severity:** medium · **Effort:** M · **Milestone:** M4
**Depends:** W2-2, W2-10, W3-1, W3-3, W4-5, W5-13 · **Blocks:** —
**Split-ownership:** MIGRATION.md prose. Code-side counterparts: AUTH-02 → W2-2; AUTH-03/CONFIG-01 verify_ssl → W3-1 (source) + W2-10 (seam) + W4-5 (getgdf seam); AUTH-04/CONFIG-02 AuthConfig → W3-2/W3-3 + W2-11 + W5-14; ERRTAX-04 ValueError shim → W2-9 (decision); OPTDEPS-02 → already-correct docstring in `featurelayer.py`; TELEMETRY-02 drift scope → W5-13. CHANGELOG counterpart of DOCS-01 → W6-5.
**Scope** — In: re-framing the 2.0.0 heading to 2.x→3.0, the missing-1.x→2.0-only references, and correcting the verify_ssl/AuthConfig/InvalidCredentialsError/ValueError/extra=pandas/drift-dedup claims in `MIGRATION.md`. Out-of-scope: deleting the preserved genuine "1.x → 2.0" guide; deleting AuthConfig fields; CHANGELOG (W6-5); inventing a `restgdf[pandas]` extra (OPTDEPS-02 anti-rec); building 3.1-targeted deprecation machinery (ERRTAX-04 anti-rec).
**Spec**
1. **DOCS-01 (re-frame 2.0→3.0):** the file opens `## 2.0.0 migration notes` at line 3 with body "restgdf 2.0.0 reshapes install surface..." at line 5 (verified: MIGRATION.md:3-5). Its body already describes the actual 3.0 deltas (header transport, 60→120 leeway, PaginationError taxonomy). Rename the heading + intro to a "2.x → 3.0" section; the content is fine, only framing/labels are wrong. Do NOT delete the preserved 1.x→2.0 guide that follows.
2. **AUTH-03 (verify_ssl):** lines 465-466 "`verify_ssl` plumbed through ... `ssl=self.verify_ssl` ... matching the existing behavior of other library-maintained request sites" (verified: MIGRATION.md:465-466). **Sequence after W3-1/W2-10/W4-5 land** the real verify_ssl source-of-truth and seams. Rewrite to match the *landed* behavior: if data requests now forward `ssl` (W2-10/W4-5), say so; if only the token POST does, state "the token POST forwards `ssl=self.verify_ssl`; data requests rely on the caller-supplied session's `TCPConnector` for TLS policy." Do NOT leave the false "matching existing behavior" claim.
3. **AUTH-04 / CONFIG-02 (AuthConfig):** the AuthConfig(transport="body") / TokenSessionConfig(transport="body") guidance at lines 109-110 (verified: MIGRATION.md:109-110). **Sequence after W3-3** (AuthConfig wiring decision) and W2-11. If W3-3 keeps AuthConfig as a holder (recommended), ensure the operative remediation shown is `TokenSessionConfig(transport="body")` (the path that works) and add the inertness note; if W3-3 wires a `from_auth_config` factory, document it. Reconcile with README:89 (W6-6).
4. **AUTH-02 / ERRTAX-01 (InvalidCredentialsError):** `InvalidCredentialsError # HTTP 401` at line 145 (verified: MIGRATION.md:145). **Sequence after W2-2.** Match its decision: wired (keep the contract) or reserved (state bad-creds surface as `RestgdfResponseError(model_name="TokenResponse")`). Keep consistent with ARCHITECTURE.md:71 (W6-3).
5. **ERRTAX-04 (ValueError shim):** the "future major release" wording at line 363 (verified: MIGRATION.md:363). **Sequence after W2-9 decision.** Per ERRTAX-04 the recommended single-source-of-truth is "removed only in a future major release (>=4.0), preceded by a `DeprecationWarning`" — ensure MIGRATION.md states exactly that and does NOT announce a 3.1 removal (anti-rec). The matching `errors.py` docstring fix is W2-9's; CHANGELOG side is W6-5.
6. **OPTDEPS-02 (extra=pandas):** line 215 'get_df ... (`extra="pandas"`) if pandas is missing' (verified: MIGRATION.md:215). Drop the false `(extra="pandas")` parenthetical: `OptionalDependencyError` carries no `.extra`, the message names `restgdf[geo]`, and there is no `restgdf[pandas]` extra. Align with the already-correct `featurelayer.py` get_df docstring. Do NOT invent a `pandas` extra (OPTDEPS-02 anti-rec — rejects option a).
7. **TELEMETRY-02 (drift dedup):** the "deduped per process via `(model_name, path, kind, value_type)`" claim at lines 790-792 (verified: MIGRATION.md:790-792). **Sequence after W5-13.** If W5-13 threads `context` into the drift log message (the recommended path, dedup key unchanged), document that the first emission is now attributable while dedup stays context-free; if W5-13 keys on a coarse service-root, document the new dedup behavior here. Note: the code uses `sample_type` while docs/code labels say `value_type` — keep the doc label consistent with W5-13's final wording.
**Acceptance criteria**
- [ ] MIGRATION.md has a "2.x → 3.0" framed section; no top-level heading still labels the 3.0 content as 2.0.0.
- [ ] The preserved genuine 1.x→2.0 guide remains intact.
- [ ] verify_ssl, AuthConfig, InvalidCredentialsError, ValueError-shim, extra=pandas, and drift-dedup claims each match the landed W3-1/W2-10/W4-5, W3-3/W2-11, W2-2, W2-9, and W5-13 behavior respectively.
- [ ] No `(extra="pandas")` parenthetical and no `restgdf[pandas]` extra invented.
- [ ] No 3.1-removal announcement for the ValueError shim.
- [ ] Doc-sync: `docs/migration.md` is a `{include}` shim, so the rebuilt Sphinx docs render the corrected text — confirm via `docs` lane.
- [ ] No code change in this item → no red-state test (DOCS-01 et al. are prose-side of code items that carry their own red tests).
**Validation** — lint; docs (rebuilds `docs/migration.md` include).
**Risks & rollback** — Failure mode: drafting before the five code deps land → documents an un-shipped behavior. Mitigated by the `Depends` gate. Rollback: revert the single-file edit. Anti-recs preserved: no `restgdf[pandas]`, no 3.1 deprecation machinery, no deletion of the 1.x→2.0 guide.

---

### W6-5 · CHANGELOG.md: fix the botched 3.0.0 promotion and populate it

**Audit refs:** PACKAGING-01, DOCS-01, DOCS-11, CICD-02, CICD-03, ERRTAX-04 · **Severity:** medium · **Effort:** M · **Milestone:** M4
**Depends:** W1-4 · **Blocks:** —
**Split-ownership:** CHANGELOG.md prose. The gate-logic side of PACKAGING-01/CICD-02 (the awk non-empty-section assertion) is **W1-4**; the bumpver-hook side of CICD-03 is **W1-8**; the ERRTAX-04 errors.py docstring is **W2-9**; the MIGRATION side of DOCS-01 is **W6-4**.
**Scope** — In: consolidating the v3 content under a non-empty `## [3.0.0]`, removing the duplicate/empty headers, adding the `[3.0.0]` link ref, re-basing `[Unreleased]`, and the DOCS-11 "seven→eight" sub-config wording at CHANGELOG.md:175. Out-of-scope: editing the gate logic (W1-4); the bumpver hook (W1-8); the genuine `## [2.0.0] - 2026-04-20` section — do NOT delete or merge it (DOCS-01/PACKAGING-01 anti-rec, it is the real prior release).
**Spec**
1. **PACKAGING-01 / DOCS-01 / CICD-02 (consolidate):** there are TWO `## [2.0.0]` headers — an empty `## [3.0.0] - 2026-05-02` at line 6 immediately followed by a mis-labeled `## [2.0.0] - 2026-05-02` at line 8 carrying the real v3 content, and the genuine `## [2.0.0] - 2026-04-20` at line 536 (verified: CHANGELOG.md:6, :8, :536). Rename the line-8 header to `## [3.0.0] - 2026-05-02` and delete the empty stub at line 6. Do NOT copy the body (would double-publish ~530 lines to `llms-full.txt`). Leave line 536 untouched.
2. **Link refs:** the footer defines only `[Unreleased]: ...compare/v2.0.0...HEAD` at line 592 and `[2.0.0]: ...releases/tag/v2.0.0` at line 593 (verified: CHANGELOG.md:592-593). Add `[3.0.0]: https://github.com/joshuasundance-swca/restgdf/compare/v2.0.0...v3.0.0` and re-base `[Unreleased]` to `...v3.0.0...HEAD`.
3. **Fresh Unreleased (PACKAGING-01 note):** the file currently has no `## [Unreleased]` section, only the link ref — re-add a fresh empty `## [Unreleased]` section at the top so the CONTRIBUTING workflow ("add a bullet under `## [Unreleased]`") has a target.
4. **DOCS-11 (seven→eight):** "aggregate of seven frozen" at line 175 (verified: CHANGELOG.md:175; audit cited CHANGELOG.md:176 — drift: was 176, now 175). Change "seven" → "eight" to match the actual eight sub-configs (the `_config.py` docstring fix is W3-7). Add `:class:`ResilienceConfig`` to the enumeration if the CHANGELOG lists them.
5. **ERRTAX-04 (ValueError shim):** ensure any CHANGELOG mention of the ValueError co-inheritance does NOT announce a 3.1 removal (anti-rec); align with the "future major release (>=4.0)" policy (W2-9 / W6-4).
6. **Maintainer content (PACKAGING-01 / CICD-03):** the v3 body content already exists under the (now-renamed) header — this item corrects *presentation*, not the change set. If the maintainer identifies missing v3 entries, they add them here; MIGRATION.md (W6-4) remains the authoritative breaking-changes reference. Note: prettier may need two passes on commit (allocation note).
7. **Gate coupling (CICD-02 / W1-4):** the W1-4 hardened gate asserts the `## [3.0.0]` section has a non-blank body before the next `## [`. This item's consolidation is what makes that gate pass — confirm green after W1-4 lands.
**Acceptance criteria**
- [ ] Exactly one `## [3.0.0]` header, non-empty body, dated 2026-05-02; the empty stub is gone.
- [ ] No duplicate `## [2.0.0] - 2026-05-02` header; the genuine `## [2.0.0] - 2026-04-20` (line 536) is intact.
- [ ] `[3.0.0]` link ref present; `[Unreleased]` re-based to `v3.0.0...HEAD`; a fresh empty `## [Unreleased]` section exists.
- [ ] "seven" → "eight" at line 175 (DOCS-11).
- [ ] No 3.1-removal announcement for the ValueError shim.
- [ ] Red-state demonstration: run the W1-4 hardened publish-gate awk check (or its local equivalent) against the BEFORE file and confirm it would FAIL on the empty `## [3.0.0]`, then PASS after consolidation (couples to W1-4's gate test).
- [ ] Doc-sync: `docs/changelog.md` is a `{include}` shim → rebuilt docs render the corrected changelog; confirm via `docs`.
**Validation** — lint (prettier — expect two passes); docs (rebuilds `docs/changelog.md` include); build (`twine check --strict` validates metadata, and confirms the published changelog is non-empty once W1-4's gate is wired).
**Risks & rollback** — Failure mode: accidentally deleting/merging the genuine 2026-04-20 2.0.0 section, or copying instead of renaming (530-line duplication). Mitigated by the explicit "rename, don't copy; leave line 536" steps. Rollback: revert the single-file edit. Note (PACKAGING-01 anti-rec): this edit cannot retroactively repair the already-published 3.0.0 PyPI/GitHub release notes — that needs a manual GitHub-release edit outside this workstream.

---

### W6-6 · README.md: 2.0→3.0 refresh + token-in-body + truncation notes

**Audit refs:** DOCS-10, AUTH-01, CONFIG-02, PAGINATION-01 · **Severity:** low · **Effort:** M · **Milestone:** M4
**Depends:** W2-1, W4-1 · **Blocks:** —
**Split-ownership:** README.md prose. The SECURITY half of DOCS-10 is **W6-1**. Code-side: AUTH-01 token-in-body POST → W2-1; PAGINATION-01 geo-truncation raise → W4-1; CONFIG-02 AuthConfig remediation → W3-3/W2-11 (and the MIGRATION mirror is W6-4).
**Scope** — In: re-framing the 2.0 collapsible/headings to 3.0, the "1.x → 2.0"-only MIGRATION pointers, the `token=`/`data["token"]` POST note, the AuthConfig-vs-TokenSessionConfig transport remediation, and a get_gdf truncation note in `README.md`. Out-of-scope: SECURITY.md (W6-1); claiming a 3.0 migration guide exists in MIGRATION.md before W6-4 writes one.
**Spec**
1. **DOCS-10 (2.0→3.0 framing):** the collapsible summary "2.0 release highlights and migration summary" at line 52, "restgdf 2.0.0 includes" at line 56, "## 2.0 migration changes" at line 95, "restgdf 2.0 is a **major release**" at line 97 (verified: README.md:52,56,95,97). Either reframe to 3.0 OR relabel explicitly as "Historical: 2.0 release notes" so the 2.0 framing reads as intentional history. Pick one and apply consistently.
2. **DOCS-10 (MIGRATION pointers):** "1.x → 2.0 rewrite table" at lines 185-186 and 392-393, and "upgrading from 1.x to 2.0" at line 443 (verified: README.md:185-186, 392-393, 443). Align with MIGRATION.md's actual scope once W6-4 reframes it to 2.x→3.0: update the pointers to mention 2.x→3.0. Do NOT claim a 3.0 migration guide exists until W6-4 has written one — sequence the pointer wording to match W6-4's landed headings.
3. **AUTH-01 (token-in-body POST):** line 363 "If you already have a token, you can pass it with `token="..."` or `data={"token": "..."}`." (verified: README.md:363). **Sequence after W2-1** lands the body-aware POST guard. Add a note that passing `token=`/`data["token"]` is sent in the request *body* (forced POST) rather than the URL query string, so the token does not leak into server/proxy logs. Do NOT describe the pre-fix GET behavior as safe.
4. **PAGINATION-01 (geo truncation):** the flagship `get_gdf()` examples at lines 300-303 (verified: README.md:300-303; get_gdf is documented around README lines 300-357 per audit). **Sequence after W4-1** makes the geo path raise on `exceededTransferLimit`. Add a note that `get_gdf()` now raises (e.g. `RestgdfResponseError(context='exceededTransferLimit')`) on truncation rather than silently returning partial data, and how to handle/opt-out per W4-1's landed contract.
5. **CONFIG-02 (AuthConfig remediation):** line 89 "`AuthConfig.transport="body"` to restore the old behavior." (verified: README.md:89). Per CONFIG-02 the operative path is `TokenSessionConfig(transport="body")` (what actually works), not bare `AuthConfig(transport="body")` which self-applies to nothing. Update to show `TokenSessionConfig(transport="body")` as the working remediation, matching MIGRATION.md:109-110 (W6-4) once W3-3's AuthConfig decision lands.
**Acceptance criteria**
- [ ] No README heading/body frames the current package as "2.0" without a "historical" qualifier; or all such framing is relabeled to 3.0.
- [ ] MIGRATION pointers reference 2.x→3.0 consistent with the W6-4 landed MIGRATION headings; no claim of a 3.0 guide that does not exist.
- [ ] `token=`/`data["token"]` documented as body/POST (no-URL-leak) matching the W2-1 landed guard.
- [ ] `get_gdf()` documented as raising on truncation matching the W4-1 landed contract.
- [ ] AuthConfig-vs-TokenSessionConfig transport remediation shows the working path consistent with W3-3/CONFIG-02 and MIGRATION.md (W6-4).
- [ ] Red-state demonstration: the behavior is already covered by W2-1's and W4-1's red-first tests; this item adds no code, so confirm the README claims match those tests' asserted behavior rather than adding a new test.
- [ ] Doc-sync: README is the PyPI/RTD landing page; confirm it renders (Sphinx does not build README, but verify the markdown lints clean).
**Validation** — lint.
**Risks & rollback** — Failure mode: documenting token-POST or get_gdf-raises before W2-1/W4-1 land → README describes un-shipped behavior. Mitigated by the `Depends` gate. Rollback: revert the single-file edit.

---

### W6-7 · Sphinx .rst/.md docs: config env vars, .env, Config example, errors attr, quickstart, observability/streaming recipes

**Audit refs:** DOCS-02, DOCS-04, DOCS-05, DOCS-09, DOCS-12, TELEMETRY-01, PAGINATION-01 · **Severity:** medium · **Effort:** M · **Milestone:** M4
**Depends:** W3-6, W5-12, W4-1 · **Blocks:** —
**Split-ownership:** the Sphinx `docs/*.rst`/`docs/*.md` prose. Code-side: DOCS-02 env-var reconciliation → W3-6; TELEMETRY-01 log filter → W5-12; PAGINATION-01 geo-truncation raise → W4-1. The `.env` ARCHITECTURE.md half of DOCS-04 is W6-3; the `_config.py` docstring half of DOCS-04 is not this item.
**Scope** — In: `docs/configuration.rst` (env table + precedence + Config example), `docs/authentication.rst` (`.env` block), `docs/errors.rst` (FieldDoesNotExistError attr), `docs/quickstart.md` (deprecated streaming API), `docs/recipes/observability.md` (log-correlation recipe), `docs/recipes/streaming.md` (truncation note). Out-of-scope: deleting the live AuthConfig fields (DOCS-02 says they remain settable); adding pydantic-settings (DOCS-04 anti-rec); relaxing `extra='forbid'` or adding a `timeout_total` alias (DOCS-05 anti-rec); adding a `field` attribute/alias to FieldDoesNotExistError (DOCS-09 anti-rec).
**Spec**
1. **DOCS-02 (env vars + defaults, configuration.rst):** the env table lists `RESTGDF_TRANSPORT_TIMEOUT_TOTAL` default `300` at lines 44-46, `RESTGDF_CONCURRENCY_MAX_CONCURRENT_REQUESTS` default `10` at lines 50-52, and `RESTGDF_AUTH_TRANSPORT`/`RESTGDF_AUTH_REFRESH_LEEWAY_SECONDS`/`RESTGDF_AUTH_CLOCK_SKEW_SECONDS` at lines 53-61 (verified: configuration.rst:44-61). Bring into exact agreement with `_config.py`'s `_NEW_ENV_SPEC`: (a) replace `RESTGDF_TRANSPORT_TIMEOUT_TOTAL`(300) with `RESTGDF_TIMEOUT_TOTAL_S`(30.0) — there is no `transport.timeout_total` field; (b) fix concurrency default `10`→`8`; (c) for the three AUTH env names, **sequence after W3-6's decision**: if W3-6 wires them into `Config.from_env` (canonical suffix `_S` not `_SECONDS`, with the 600/120 validator bounds documented), update the table to the wired names; if W3-6 confirms removal, drop them from the table (they remain settable via `Config(auth=AuthConfig(...))`). Do NOT delete the AuthConfig fields.
2. **DOCS-04 (`.env`/pydantic-settings, configuration.rst + authentication.rst):** configuration.rst opening "based on Pydantic Settings" at lines 4-5 and `.env` precedence step 4 at line 11 (verified: configuration.rst:4-5,11); authentication.rst "Or use a `.env` file (supported by pydantic-settings):" at line 101 with the code block following (verified: authentication.rst:101+). Remove the "based on Pydantic Settings" framing and the `.env` precedence step in configuration.rst; reframe as "layered, environment-variable + explicit-argument configuration." In authentication.rst delete the `.env`/pydantic-settings block (keep the `os.environ` example above it, verified: authentication.rst:96-99) OR show explicit user-side `load_dotenv()` before reading `os.environ`, making clear restgdf itself does not read `.env`. Do NOT add pydantic-settings (DOCS-04 anti-rec). Keep consistent with W6-3's ARCHITECTURE.md:118 `.env` deletion and W3-5's decision.
3. **DOCS-05 (Config example, configuration.rst):** the Quick start at lines 24-28 shows `Config(transport={"timeout_total": 120}, concurrency={"max_concurrent_requests": 8})` (verified: configuration.rst:24-28), which raises (`extra='forbid'`, no `timeout_total` on TransportConfig). Fix to a valid form, e.g. `Config(timeout={"total_s": 120}, concurrency={"max_concurrent_requests": 8})` (DOCS-05 verified this yields `timeout.total_s=120.0`). Optionally lead with `get_config()`/`from_env`. Do NOT relax `extra='forbid'` or add a `timeout_total` alias (DOCS-05 anti-rec).
4. **DOCS-09 (errors.rst attr):** the FieldDoesNotExistError row shows attributes `field`, `context` at line 119 (verified: errors.rst:119; audit cited errors.rst:118 — drift: was 118, now 119). Change `field` → `field_name` to match `errors.py:150` `self.field_name`. Do NOT add a `field` attribute/alias to the class (DOCS-09 anti-rec).
5. **DOCS-12 (quickstart.md):** the light-core example uses `beaches.row_dict_generator(data=...)` at line 35 (verified: quickstart.md:35). Change to `beaches.stream_rows(data=...)` — identical `data=` kwarg, matches the README example at README.md:207. Safe docs-only edit.
6. **TELEMETRY-01 (observability.md):** the recipe at lines 68-72 shows `fmt = "%(levelname)s [trace=%(trace_id)s span=%(span_id)s] %(message)s"` then `logging.basicConfig(format=fmt)` (verified: observability.md:68-72), which raises a logging error on every record emitted outside a span. **Sequence after W5-12.** If W5-12 makes `_SpanContextFilter` always stamp `trace_id`/`span_id` (defaulting to empty/sentinel — the recommended option a), the recipe works as-is for all records; confirm the recipe and note the default. If W5-12 instead keeps current behavior, switch the recipe to a custom `Formatter` using `getattr(record, "trace_id", "-")` and note the raw `%()s` form only renders inside an active span. Do NOT switch the recipe to `logging.Formatter(defaults=...)` (admissible on the >=3.11 floor, but keep the recipe aligned with the landed W5-12 always-stamp behavior).
7. **PAGINATION-01 (streaming.md):** the blanket "safe to use on a base install unless explicitly noted" at line 11 (verified: streaming.md:11) and the `stream_gdf_chunks` note section (verified: streaming.md:62-89; exceededTransferLimit discussion at :98+). **Sequence after W4-1.** Update so the geo path's new behavior is documented: once W4-1 makes `get_sub_gdf` raise on `exceededTransferLimit`, state that the geo chunk path now detects truncation and raises (matching the raw-feature engine), and remove/soften the "safe ... unless explicitly noted" claim's gap. If W4-1 ships an opt-out kwarg, document it. Do NOT widen the `stream_gdf_chunks` legacy contract to accept the `on_truncation` knob set (PAGINATION-01 / ARCHITECTURE.md:146-150 anti-rec — that is a separate design change).
**Acceptance criteria**
- [ ] configuration.rst env table matches `_NEW_ENV_SPEC`: `RESTGDF_TIMEOUT_TOTAL_S`(30.0), concurrency default 8, and the three AUTH names consistent with the W3-6 landed decision.
- [ ] No "Pydantic Settings"/`.env` framing in configuration.rst; no pydantic-settings `.env` block in authentication.rst (or it shows explicit user-side load_dotenv with the "restgdf does not read .env" caveat).
- [ ] The configuration.rst `Config(...)` example runs without raising (valid `timeout={"total_s":...}` form).
- [ ] errors.rst FieldDoesNotExistError attribute reads `field_name`.
- [ ] quickstart.md uses `stream_rows`, not `row_dict_generator`.
- [ ] observability.md log-correlation recipe matches the W5-12 landed filter behavior.
- [ ] streaming.md documents geo-path truncation raising per the W4-1 landed contract; no `stream_gdf_chunks` knob-widening claim.
- [ ] Red-state demonstration: DOCS-05's example and the W5-12/W4-1 behaviors are validated by `docs` building clean and by those items' own red-first tests; this item adds no code. Confirm the doc snippets are copy-paste-valid against the landed code.
- [ ] Doc-sync: all six files rebuild clean under warnings-as-errors Sphinx.
**Validation** — lint; docs (warnings-as-errors — this is the primary gate for this item; all six files are Sphinx-published).
**Risks & rollback** — Failure mode: documenting wired AUTH env vars / always-stamped filter / geo-raises before W3-6/W5-12/W4-1 land → docs describe un-shipped behavior; or a `.rst` directive typo breaks the `-W` Sphinx build. Mitigated by the `Depends` gate and the `docs` lane. Rollback: revert the single-file edits. Anti-recs preserved: no pydantic-settings, no `extra='forbid'` relaxation, no `field` alias, no `stream_gdf_chunks` knob-widening, no recipe drift from the landed W5-12 logging behavior.
