# 00 — Master remediation plan

> Turns the [restgdf audit](../README.md) (61 verified findings at commit `4673b08`) into an
> executable program. 2026-06-13. Companion files: per-workstream specs
> [`01`](01-ci-cd-and-tooling.md)–[`06`](06-docs-release-narrative.md), and the
> [`99-traceability`](99-traceability.md) ledger (every finding → work item). Execute it through
> the current-state prerequisites, integration order, parallel lanes, and recovery rules in
> [`07-execution-runbook.md`](07-execution-runbook.md).

## Vocabulary

- **Work item** — one coherent, independently-landable change (a PR or commit). 55 items total.
  IDs are `W<workstream>-<n>` (e.g. `W2-1`). Each traces to ≥1 audit finding via its **Audit refs**.
- **Workstream** — a **collision domain**, i.e. a set of files edited by a *single writer* at a
  time. Workstreams with disjoint file sets run in parallel; items inside one workstream that
  touch the same hot file serialize. Organized by *files*, not topic.
- **Milestone** — a delivery wave with an **exit gate** (a condition that must hold before the
  next wave starts). M1→M4 below.
- **Split-ownership** — a finding whose fix spans two collision domains is split into named
  parts, each a concrete item, with explicit cross-references (21 such findings — see
  [`99-traceability`](99-traceability.md#split-ownership-ledger)).
- **Governance** — restgdf has PR review + CODEOWNERS but **no formal change-approval process**,
  so this plan defines **no governance packets**; "approval" means a maintainer merges the PR.
  Release/supply-chain items (`W1-1`, `W1-4`) are the closest to governance-sensitive and are
  called out as such, not gated by an invented process.

## Plan principles (load-bearing — keep them)

1. **Safety nets before surgery.** The validation spine (`W1-1` release gate, `W1-2` real mypy,
   `W1-3` PR coverage) lands in **M1**, before the correctness changes those gates must protect.
   Every subsequent change pays the validation tax, so the highest-leverage move is making the
   gates real first.
2. **Red-state demonstration is mandatory for behavior changes.** Per CONTRIBUTING's red-first
   rule, every behavior-changing item lands its failing test in its own commit first — *a net
   that has never failed proves nothing.* Acceptance criteria encode this.
3. **Fail loud, not silent.** The audit's dominant theme is silent contract-falseness (truncation,
   dead config, never-raised exceptions). Fixes must surface the condition (raise/warn/typed
   error), never paper over it.
4. **Disjoint-file parallelism with enumerated single-writer hot files** (collision map below).
   Never let two in-flight items edit the same hot file.
5. **Re-verify before you cut.** The audit's claims were adversarially verified, but its line
   numbers are pinned to `4673b08` and are *perishable*. Each item's spec re-verifies its load-
   bearing references against the working tree (drift protocol); flagged drift rides in the item.
6. **Doc-sync in the same change set.** Code that changes a documented contract updates the doc.
   Because all prose is single-writer in **W6**, code items name the W6 item that carries their
   doc-side (see split-ownership), and that W6 item depends on the code item.
7. **Effort calibration is inherited from the audit** (S < ~1h · M a few files+tests · L cross-
   cutting). Restated, not recalibrated.

## Milestones & exit gates

| MS | Theme | Exit gate |
|----|-------|-----------|
| **M1** | **Validation spine + zero-risk quick wins.** Make the gates real; fix obvious metadata/docstrings; land the trivial-but-high `AUTH-01` token-leak fix. | Release path runs the test suite (`W1-1`); mypy gate is real and green (`W1-2`); PR coverage enforced (`W1-3`); `AUTH-01` shipped; full local quality gate green. |
| **M2** | **High-severity correctness + config source-of-truth & its application seams.** | All 5 high findings closed with regression tests (`W2-1`✓M1, `W4-1`, `W4-2`, verify_ssl trio `W3-1`/`W2-10`/`W4-5`, `W1-1`✓M1); `verify_ssl=False` demonstrably reaches data requests. |
| **M3** | **Medium correctness, error-contract truth, larger config-into-construction wiring.** | Documented exceptions actually raise (`W2-2/3/5`); stats/adapters correctness (`W5-2/4/6`); AuthConfig/Config-instance wiring landed or consciously deferred to doc-only (`W3-3/4`, `W5-14`). |
| **M4** | **Low-severity polish + full documentation/release-narrative refresh.** | All docs match code; CHANGELOG `[3.0.0]` populated; MIGRATION/README/ARCHITECTURE/SECURITY current for v3.0.0; docs build `-W` clean. |

Item→milestone assignments are in [`99-traceability`](99-traceability.md#reverse-map--work-item--findings--milestone).

## Critical path

```
M1: W1-2 (real mypy) ─┬─> unblocks TYPING-* fixes (W4-6, W5-9/10/11) landing green
    W1-1 (release gate)│   [W1-1 must precede the NEXT release cut, regardless of milestone]
    W1-3 (PR coverage) │
    AUTH-01 (W2-1) ────┘   [independent; ship first — security, S]
M2: W3-1 (config source of truth: verify_ssl/UA) ──> W2-10 (token/_http seam) ──┐
                                                  └─> W4-5 (getgdf seam)        ├─> verify_ssl works end-to-end
    W4-1 (geo truncation) ───────── independent, parallel ─────────────────────┘
    W4-2 (orderByFields) ────────── independent, parallel
M3: W3-3 (AuthConfig expose) ──> W2-11 (token consume) ; W3-3/W3-4 ──> W5-14 (FeatureLayer from_config)
    W2-2 (raise InvalidCredentialsError) ──> W2-3 (retry filter)
M4: code items ──> their W6 doc-sync items (W6-3/4/5/6/7 depend on the code landing)
```

The single highest-leverage sequencing decision (per the audit's CI/CD theme): **`W1-1` before any
new release is cut.** Until the release path is test-gated, a tag push can ship an untested wheel
— so no release should be tagged between now and `W1-1` landing.

## Prioritization

Rank = **severity × blast-radius × 1/effort**, with boosts for: *security* (`AUTH-01`),
*validation-velocity* (`W1-1/2/3` — they multiply every later item's safety), and *silent data
loss* (`W4-1`, `W4-2`). The resulting top tier (do first):

1. `AUTH-01` (high, S) — credential-in-URL leak; trivial body-aware POST fix. **Ship immediately.**
2. `W1-1` (high, M) — gate the release path. Protects every future release.
3. `W4-1` (high, M) — stop silent geo truncation on the flagship `get_gdf()`.
4. `W3-1`→`W2-10`/`W4-5` (high) — make `verify_ssl`/`user_agent` actually take effect.
5. `W4-2` (high, M) — stable cross-page ordering.
6. `W1-2` (med, M) — real mypy; unblocks the typing fixes and stops shipping broken inline types.

## Collision map (single-writer hot files)

| File | Owning workstream | Notes |
|------|-------------------|-------|
| `restgdf/utils/token.py` | **W2** | hottest code file (9 findings); split parts `W2-10`, `W2-11` are same-WS |
| `restgdf/_config.py` | **W3** | config source of truth; `W2-13` may need a coordinated additive touch — route via W3 |
| `restgdf/utils/getgdf.py` | **W4** | pagination core; verify_ssl seam `W4-5` is same-WS |
| `restgdf/featurelayer/featurelayer.py` | **W5** | construction seam `W5-14` is same-WS |
| `restgdf/utils/_http.py`, `_query.py`, `errors.py`, `resilience/*`, `_optional.py` | **W2** | |
| `restgdf/_models/_settings.py` | **W3** | |
| `restgdf/utils/_pagination.py`, `utils.py` | **W4** | |
| `restgdf/utils/_stats.py`, `_metadata.py`, `adapters/*`, `_client/*`, `__init__.py`, `_models/_drift.py`, `_logging.py` | **W5** | |
| `.github/workflows/*`, `pyproject.toml`, `.pre-commit-config.yaml`, `tests/conftest.py` | **W1** | |
| **all** `*.md`, `*.rst`, `CITATION.cff` | **W6** | prose is single-writer to avoid doc collisions; code items hand their doc-side to W6 |

Parallelizable now (disjoint files): W1, W4, and the W5 items with no config dependency can run
concurrently. W2/W3 serialize on the verify_ssl and AuthConfig split-ownership chains.

## Decision record (maintainer interview, 2026-06-13)

Four program-shaping decisions were taken with the maintainer; the rest default to each item's
recommended option (stated in the item spec) and can be revisited.

| Item(s) | Decision | DECIDED (maintainer interview 2026-06-13) |
|---------|----------|-------------------------------------------|
| `CONFIG-02/03/04` (W3-3, W5-14, W3-4, W3-5) | Config-wiring direction | **Hybrid.** Wire `AuthConfig` *only* via an opt-in `ArcGISTokenSession.from_config` classmethod (never an implicit process-global in `__post_init__`); **document-down** the `.env` (W3-5) and explicit-`Config`-instance precedence (W3-4) claims — delete them rather than implement. ⇒ W3-4/W3-5 become **doc-only**; W3-3/W5-14 shrink to the minimal classmethod + doc fix; no `python-dotenv` dep added. |
| `TRANSPORT-01` (W2-13), `AUTH-04` (W3-2, W2-11) | Inert config knobs | **Warn-now, wire-later.** Emit a one-time warning when an inert `RESTGDF_RETRY_*`/`RESTGDF_LIMITER_*`/`RESTGDF_AUTH_REFRESH_*` var is set + add a docstring caveat; **keep** the knobs and the back-compat env aliases (tests pin them); defer real wiring to a separate design that first resolves the LimiterConfig vs ResilienceConfig rate-limit overlap. |
| `PACKAGING-02` / `DOCS-10` (W6-1) | Security-support policy | **Current major only.** 3.x supported; 2.x and below unsupported. Reword the policy to "the current major release line (currently 3.x) receives security updates" so the table can't rot on the next bump. |
| `CICD-01` (W1-1) | `release` env reviewer? | **Verified NONE** — `gh api repos/joshuasundance-swca/restgdf/environments/release` on 2026-06-13 returns `protection_rules: []`. The publish path is fully automated on a tag push, so **W1-1's test gate is the sole guard — top release-safety priority**, and adding a required reviewer to the `release` environment is a recommended complementary repo-settings fix (call it out in W1-1). |

**Defaulted** to each item's recommended option (revisit any time): `W1-2` keep the mypy strict
scope narrow and fix the 6 known errors first; `W2-2` demote `TokenRequiredError` (499 stays
`AuthNotAttachedError`); `W2-9` keep the `ValueError` co-inheritance and fix only the "dropped in
3.1+" docstring → "removed only in a future major (≥4.0), preceded by a `DeprecationWarning`";
`W5-3` restrict `nested_count` to exactly two fields; `W1-8` bumpver fail-fast on an empty CHANGELOG
section (not full consolidation); `W6-2`/`PACKAGING-03` make `[dev]` compose `restgdf[doc]` and add
`build`+`twine` so the docs' "`.[dev]` covers docs+packaging" claim becomes true.

## Risk register

| Risk | L×I | Mitigation | Trigger signal |
|------|-----|------------|----------------|
| A behavior change (`W4-1` raise, `W4-2` orderByFields, `W5-1` copy) breaks a downstream consumer relying on today's silent behavior | M×H | Land behind the next **minor** version with a CHANGELOG `### Changed/Breaking` note; red-first tests; the audit anti-recommendations are baked into each item's "out-of-scope". | A consumer issue after release |
| `W1-2` real mypy surfaces *more* than the 5 known type errors | H×M | Treat the first real run as discovery; fix the known set (`TYPING-02/03/04/05`) in the same wave; allow a short allowlist for anything out-of-scope. | mypy reports unexpected errors |
| `verify_ssl` split (`W3-1`/`W2-10`/`W4-5`) lands partially → split-brain TLS | M×H | Single-source the value in `W3-1` first; the two application seams `Depends:` on it; an integration test sets `verify_ssl=False` and asserts both token + data requests honor it. | TLS behavior differs by request type |
| `W4-2` orderByFields injection breaks on layers with ambiguous/missing OID | M×M | Degrade gracefully (skip injection, optional warn) — never hard-fail the happy path; pinned by a test. | `FieldDoesNotExistError` on a previously-working query |
| Doc-sync items (`W6-*`) drift from the code that landed in M2/M3 | M×L | W6 items `Depends:` on their code items and land in M4 after the code is final. | docs describe pre-fix behavior |
| Releasing before `W1-1` ships an untested wheel | L×H | **Freeze releases** until `W1-1` merges. | a tag pushed pre-gate |

## What "done" looks like (outcomes, not tasks)

- A caller's `token=` never appears in a request URL; `verify_ssl=False` and a custom
  `user_agent` actually take effect on every library-owned request.
- `get_gdf()` either returns every matching row or raises — never silently truncates; multi-page
  reads are order-stable.
- Every exported, documented exception has a real raise site; `except RestgdfError` catches all
  restgdf failures (no raw `aiohttp` escapes).
- Every validated config knob either does what it says or is gone; the docs describe only what
  the code does.
- The release path cannot publish an untested or undocumented (`[3.0.0]`-empty) wheel; the mypy
  gate reflects the inline types shipped to consumers.
- readthedocs + `llms.txt` describe restgdf 3.0.0 accurately (no `ErrorPayload`, no phantom
  `.env`, correct logger names, current SECURITY/CHANGELOG/MIGRATION).

## Verification deltas (post-critic, coordinator-resolved)

Two adversarial critics (traceability + sequencing/collisions) verified this plan. Both rated it
**fundamentally sound**: all 61 findings traced (0 missing, 0 invented), per-axis counts exact, the
21 split-ownership findings split across **disjoint** files, no dependency cycles, no milestone-
order violations, validation front-loaded to M1. An automated repair pass fixed three file-scoped
issues (W4-6's missing `W5-9` dependency, W6-3's M2→M3 milestone trap, the W6-3→W6-7 `DOCS-04`
cross-reference). The remaining cross-file items were routed to the coordinator and resolved here:

- **Split-ownership cross-references tightened** (the documented #1 failure mode): W5-12↔W6-7
  (`TELEMETRY-01`), W5-13↔W6-4 (`TELEMETRY-02`), and the mutual W6-2↔W6-3 reference for
  `PACKAGING-03` now carry explicit part-statements. No traceability was lost (each co-owner was
  already named in the item's Scope), but the convention is now satisfied. W6-4 gained its
  `W4-5` dependency edge.
- **`W2-5` → `_drift.py` collision** (`ERRTAX-03`, M3, maintainer go/no-go-gated): if implemented,
  its in-body-envelope mapping must edit `restgdf/_models/_drift.py`, which is **W5**-owned. W2-5's
  spec already delegates that edit to W5 (single-writer) and gates the whole item behind a
  go/no-go. **Resolution:** if GO, the `_drift.py` change is a W5 sub-task serialized after W5-13;
  W2-5 never writes `_drift.py` directly. As the item may be deferred, no standing W5 item is
  pre-created — the delegation note in W2-5 is the contract.
- **`W4-4` `ASYNC-03` doc handoffs** (M3, doc-only): the `iter_pages` public-docstring correction
  lives in `featurelayer.py` (**W5**) and the `docs/recipes/streaming.md` note in **W6-7**.
  **Resolution:** the W5 implementer touching `featurelayer.py` (bundle with W5-1) makes the
  docstring edit; W6-7 adds the streaming.md concurrency-bound note; W4-4 itself reduces to a
  `getgdf.py` inline-comment check.
- **Test-file ownership:** a new/edited test file an item drives is single-writer to that item's
  workstream (`test_pagination_characterization.py`/`test_getgdf*.py`/`test_pagination_planner.py`
  → W4; `test_FeatureLayer.py` → W5; `test_verify_ssl_plumbing.py` assertions split so W2-10 and
  W4-5 each add under their own milestone, serialized). Correction: `test_base_install.py` is
  **W2**-owned (used by W2-8), not "W4/W5 territory" as W1-9's note implied.

## Execution model (proposed — renegotiable with the maintainer)

Not presumed; offered as a starting default: per-item branches off `main` with red-first commits;
risk-class merge gates (security/release items reviewed; pure-doc + S-effort items batched);
the local quality gate (`lint`+`test`+`coverage`+`docs`+`build`+`compat`) is "green" since there
is no PR-push CI on `main` until `W1-1`/`W1-3` land. Run an operating-model retro at each
milestone boundary. The full Draft→implement fan-out is proposed but execution-unverified — treat
M1 as the calibration wave.
