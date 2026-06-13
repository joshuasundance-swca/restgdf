# 01 — CI/CD, release gates & tooling config

> Workstream of the restgdf remediation plan · audit pinned `4673b08` · 2026-06-13

## Goal

Make the release-protecting gates actually protect releases and make the type
gate actually type-check. Today the entire PR test rig (`pytest.yml`) is bypassed
on the tag-push / `workflow_dispatch` publish path, the mypy hook runs with no
runtime deps so it reports green over 6 real type errors, the 97% coverage floor
only trips post-merge, and the CHANGELOG gate passes on an empty section.
Landing this workstream turns those four hollow gates into enforced ones, SHA-pins
the remaining write-token workflows, and clears stale tooling config — so that
"CI green" on a PR and on a release means what CONTRIBUTING claims it means.

## Collision domain

This workstream is single-writer on the following paths (from the allocation `owns[]`):

- `.github/workflows/*` — every workflow file (`publish_on_pypi.yml`, `pytest.yml`,
  `coverage.yml`, `bumpver.yml`, `readthedocs.yml`, `verify_attestation.yml`).
- `pyproject.toml` — **shared hot-file**. W1 owns the CI-adjacent tables
  (`[tool.coverage.*]`, `[tool.mypy]`, the mypy hook deps). W3 is single-writer on
  the *config-spine code* (`restgdf/_config.py`, `restgdf/_models/_settings.py`) but
  does **not** edit `pyproject.toml`. W2-13 notes a possible *additive* touch to
  `restgdf/_config.py` (not `pyproject.toml`). No other workstream writes
  `pyproject.toml`, so within this plan W1 is the sole `pyproject.toml` writer — but
  treat it as a hot-file and serialize the three W1 items that touch it (W1-2, W1-3,
  W1-7) rather than running them as parallel branches that each rewrite it.
- `.pre-commit-config.yaml` — single-writer (only W1-2 touches it).
- `scripts/bumpver_stamp_date.py` — single-writer (only W1-8 touches it).
- `tests/conftest.py`, `tests/test_characterization.py` — single-writer (only W1-9).

Files referenced but **owned by other workstreams** (do NOT edit here):
`CONTRIBUTING.md` (W6-2), `CHANGELOG.md` (W6-5), and the compat fakes in
`tests/test_FeatureLayer.py` / `tests/test_getgdf.py` / `tests/test_base_install.py`
(W4/W5 territory — see W1-9 anti-recommendation).

## Sequencing & parallelization

**M1 (validation spine & quick wins)** — W1-1, W1-2, W1-3, W1-4, W1-5, W1-6, W1-7.
- Disjoint-file, parallel-safe right away: **W1-5** (bumpver/coverage/readthedocs
  SHA-pins), **W1-6** (verify_attestation comment) — neither touches a hot file.
- **W1-1** (publish gate + pytest.yml `workflow_call`) and **W1-4** (CHANGELOG gate
  in publish_on_pypi.yml) both edit `publish_on_pypi.yml`; W1-1 also refactors
  `pytest.yml`. Serialize W1-1 then W1-4 on `publish_on_pypi.yml` (or land W1-4's
  small step inside the W1-1 branch). W1-1 also edits `pytest.yml`, which W1-2 and
  W1-3 edit too — serialize the `pytest.yml` edits: **W1-1 → W1-2 → W1-3**.
- **W1-2**, **W1-3**, **W1-7** all touch `pyproject.toml` — serialize them in that
  order (W1-2 adds `[tool.mypy] plugins`; W1-3 may add nothing to pyproject but reads
  `command_line`/`fail_under`; W1-7 deletes the omit entry). W1-2 also touches
  `pytest.yml` (mypy CI job) and `.pre-commit-config.yaml`.
- **Hard ordering inside M1:** W1-2 flips the mypy gate to *real*. The moment it does,
  it surfaces the 6 errors catalogued in TYPING-01 — which are fixed by
  **W5-9, W5-10, W5-11, W4-6** (and the `_bounded_retry`/`_metadata` items in W2/W5).
  Those code fixes (`Depends: W1-2`) must land **with or before** the gate flips to
  *required*. W1-2 ships the gate machinery; do NOT add the new mypy job to the `ci`
  aggregator's required `needs:` until the dependent fix items are green. This is the
  one cross-workstream coupling that gates M1→M2.

**M2** — **W1-8** (CHANGELOG-aware bumpver) depends on **W1-4** (the publish-time gate
it complements must exist first).

**M3** — **W1-9** (restore verb separation in characterization tests) depends on
**W2-1** (the AUTH-01 verb-routing fix) so the restored assertions pin the *corrected*
behavior, not today's behavior.

**Cross-workstream `Depends` edges out of W1:**
- W4-6 (`get_gdf` session annotation) `Depends: W1-2` — needs the real mypy gate to
  verify the fix.
- W5-9 / W5-10 / W5-11 (Protocol reconcile, `_drift` union-attr, `_metadata`
  annotation) `Depends: W1-2` — same reason.
- W1-9 `Depends: W2-1` (verb-routing fix lands first).
- W6-2 reconciles CONTRIBUTING prose for the coverage/dev-extra claims **after** W1-3
  fixes the gate; the pyproject `twine`/`build` dev-extra decision (PACKAGING-03)
  surfaced in W6-2's note also sits with W1 — see the Decision in W1-3's section.

## Work items

### W1-1 · Gate the release path on the test suite
**Audit refs:** CICD-01 · **Severity:** high · **Effort:** M · **Milestone:** M1
**Depends:** — · **Blocks:** W1-4 (shares `publish_on_pypi.yml`)
**Split-ownership:** —
**Scope** — In: refactor `.github/workflows/pytest.yml` to expose its gate jobs via
`workflow_call`; add a `call-tests` job to `.github/workflows/publish_on_pypi.yml`
that runs on the `push:tags` / `workflow_dispatch` paths and that `build-distributions`
(and therefore `publish-pypi`) `needs:`. Out-of-scope: do NOT add the live `network`
or `stress` markers to the release gate (they require `--run-network`/`--run-stress`
and hit external ArcGIS endpoints — a flaky upstream would block legitimate releases);
do NOT re-run the full 6-version 3.9–3.14 matrix on the release path (a single-version
`-m "not network"` run is sufficient and avoids latency); the actual CHANGELOG empty-section
gate is W1-4; the CHANGELOG content fix is W6-5.

**Spec** —
1. In `.github/workflows/pytest.yml`, add `workflow_call:` to the `on:` block
   (currently `on: pull_request:` only, verified: `.github/workflows/pytest.yml:3-18`).
   Keep the existing `pull_request:` trigger.
2. Choose the **preferred minimal-duplication** shape from CICD-01: make `pytest.yml`
   reusable so the same `test` / `base_install` / `install_combinations` jobs that
   guard PRs also guard releases. The `test` job already installs
   `-e ".[dev,geo,resilience,telemetry]"` and runs `python -m pytest -q -m "not network"`
   (verified: `.github/workflows/pytest.yml:55-62`). The `network` (`:123-138`) and
   `stress` (`:140-155`) jobs and the `docs` strict build (`:157-179`) should NOT be
   pulled onto the release-cut path — exclude them from any `workflow_call` surface the
   publish workflow consumes, or expose a `call`-only subset job list.
3. In `.github/workflows/publish_on_pypi.yml`, add a `call-tests` job before
   `build-distributions` that `uses: ./.github/workflows/pytest.yml` (the reusable
   subset) on the release paths, checking out `ref: ${{ inputs.release_tag || github.ref }}`
   so it tests the exact commit being built. Add `call-tests` to `build-distributions`'s
   `needs:` (today `build-distributions` has no `needs:`, verified:
   `.github/workflows/publish_on_pypi.yml:27-34`). `publish-pypi` already `needs:
   build-distributions` (verified: `:124-127`) so it inherits the gate transitively.
4. If the reusable-workflow refactor proves heavy, fall back to CICD-01's **lighter**
   shape: an inline job in `publish_on_pypi.yml` that installs
   `-e ".[dev,geo,resilience,telemetry]"` and runs `python -m pytest -q -m "not network"`
   (mirroring the bumpver BL-42 step at `.github/workflows/bumpver.yml:48-51`, verified),
   made a `needs:` of `build-distributions`, run against `ref: ${{ inputs.release_tag || github.ref }}`.
5. Do NOT remove or weaken the existing tag/version-match gate (`:67-78`) or the
   attestation/Sigstore chain — they are sound; this item only adds a test precondition.

**Decision required** — see the Decision-required line below re: the `release` GH
environment reviewer.

**Acceptance criteria** —
- [ ] `publish_on_pypi.yml`'s `build-distributions` job `needs:` a test job, and that
      test job runs `python -m pytest -q -m "not network"` against the release ref.
- [ ] A simulated tag-push / `workflow_dispatch` cannot reach `publish-pypi` if the
      test job fails (verify via the job graph; the gate is structural, not behavioral —
      no red-state runtime test required, but confirm `actionlint` / `check-github-workflows`
      accept the `workflow_call` wiring).
- [ ] `network` and `stress` markers are NOT present on the release path.
- [ ] PR runs are unaffected (the `pull_request` trigger and `ci` aggregator still fire).

**Validation** — lint (`pre-commit` runs `actionlint` + `check-github-workflows` over
`.github/workflows/*`, verified: `.pre-commit-config.yaml:70-83`). No `test`/`coverage`
lane applies (CI-only change).

**Risks & rollback** — Risk: a malformed `workflow_call` interface breaks both PR and
release runs. Mitigate by validating with `actionlint` locally and on a draft PR before
merge; per the governed-CI rule, hold the merge for adversarial review since this edits
shared CI infra. Rollback: revert the two workflow files (no runtime/package surface
touched). Anti-recommendation honored: never add live `network`/`stress` to the gate.

---

### W1-4 · Reject an empty CHANGELOG section in the publish gate
**Audit refs:** CICD-02 · **Severity:** medium · **Effort:** S · **Milestone:** M1
**Depends:** — (serialize on `publish_on_pypi.yml` after W1-1) · **Blocks:** W1-8
**Split-ownership:** This item owns the **gate logic only**. The CHANGELOG.md
structural fix (rename misplaced `## [2.0.0]` → `## [3.0.0]`, delete empty header,
add compare-link footer) is owned by **W6-5 (PACKAGING-01)**.
**Scope** — In: strengthen the "Require CHANGELOG entry for release" step in
`publish_on_pypi.yml` to fail when the `## [X.Y.Z]` section body is empty/whitespace.
Out-of-scope: do NOT edit `CHANGELOG.md` (W6-5); do NOT make the gate auto-rename
`## [Unreleased]` (keep it a fail-fast assertion so human consolidation stays explicit);
the gate cannot retroactively repair the already-published 3.0.0 PyPI/GitHub release.

**Spec** —
1. Target the existing step (verified: `.github/workflows/publish_on_pypi.yml:85-102`,
   `if: steps.release_meta.outputs.raw != ''` at `:86`, `header="## [${RELEASE_VERSION}]"`
   at `:97`, `grep -F -- "$header"` at `:98`). It currently only checks header presence.
2. Replace the presence-only check with a body-non-empty assertion. Per CICD-02, extract
   the lines strictly between `## [${RELEASE_VERSION}]` and the next `## [` header and
   fail if they contain no non-blank line, e.g.:
   `awk -v h="## [${RELEASE_VERSION}]" '$0 ~ "^"h {f=1;next} f && /^## \[/ {exit} f {print}'`
   captured into a var, then fail unless it contains a non-blank line.
3. Optionally also fail when more than one identically-named `## [X.Y.Z]` header exists
   (`grep -cF "## [${RELEASE_VERSION}]"` > 1) to catch the duplicate-header class directly.
4. The step still runs only when `raw != ''` (`:86`) — i.e. tag-push / `workflow_dispatch`
   — so it never fires on PR runs or against the `## [Unreleased]` convention
   (CONTRIBUTING.md:13-15,47-49). Preserve that guard.
5. Do NOT auto-rename `## [Unreleased]`; keep the step a fail-fast assertion.

**Acceptance criteria** —
- [ ] Against the current tree (empty `## [3.0.0]` section at `CHANGELOG.md:6`
      immediately followed by `## [2.0.0]` at `:8`, verified), the strengthened gate
      logic FAILS for `RELEASE_VERSION=3.0.0` (red-state demonstration — verify by running
      the awk/grep snippet locally against `CHANGELOG.md` and confirming non-zero exit).
- [ ] The same logic PASSES once W6-5 populates the `## [3.0.0]` body.
- [ ] PR runs and `## [Unreleased]`-only states are unaffected (guard at `:86` intact).

**Validation** — lint (`actionlint` + `check-github-workflows` via pre-commit). Local
red-state check: run the awk extraction against `CHANGELOG.md` and assert it captures
only blank lines for the current empty 3.0.0 section.

**Risks & rollback** — Risk: an awk pattern that mis-parses a legitimately-populated
section blocks a real release. Mitigate by testing against both the current (empty) and
a hand-populated section before merge. Rollback: revert the step to the prior header-grep.
Anti-recommendation honored: gate stays a hard assertion; no auto-mutation of the changelog.

---

### W1-2 · Un-defang the mypy gate (install runtime deps + pydantic plugin)
**Audit refs:** TYPING-01 · **Severity:** medium · **Effort:** M · **Milestone:** M1
**Depends:** — (serialize `pyproject.toml` after/with W1-3, W1-7; serialize `pytest.yml`
after W1-1) · **Blocks:** W4-6, W5-9, W5-10, W5-11 (all `Depends: W1-2`)
**Split-ownership:** —
**Scope** — In: add `[tool.mypy] plugins = ["pydantic.mypy"]` to `pyproject.toml`; make
mypy type-check against real dependency types (preferred: a dedicated CI mypy job that
`pip install -e ".[geo,resilience,telemetry,dev]"`); keep the pre-commit hook lean or
extend its `additional_dependencies`. Out-of-scope: do NOT pair this with a blanket
global `--strict` or removal of `ignore_missing_imports` across the board (the audit's
explicit anti-recommendation — aiohttp's `ClientSession` deliberately does not conform to
`AsyncHTTPSession` per BL-17/TYPING-02, and optional-extra modules intentionally treat
un-installed deps as untyped; a global strict flip surfaces large numbers of
intended-`Any` boundaries and breaks the gate noisily). Fixing the 6 surfaced errors is
out-of-scope here — those are W5-9/W5-10/W5-11/W4-6 + the `_bounded_retry`/`_metadata`
items; this item ships only the gate machinery.

**Spec** —
1. Add to `pyproject.toml` under `[tool.mypy]` (currently empty, verified:
   `pyproject.toml:197`): `plugins = ["pydantic.mypy"]`.
2. Make mypy see real types. **Preferred (per TYPING-01 option b):** add a dedicated CI
   mypy job to `.github/workflows/pytest.yml` that does
   `pip install -e ".[geo,resilience,telemetry,dev]"` then runs mypy over `restgdf/`
   — this keeps the isolated pre-commit env lean. Pin it to a single Python (3.14, matching
   the other gate jobs) and add it to the `ci` aggregator `needs:` (verified aggregator:
   `.github/workflows/pytest.yml:181-193`, `needs: [lint, test, install_combinations,
   base_install, network, stress, docs]` at `:184`) **only after** the dependent fix
   items (W5-9/W5-10/W5-11/W4-6 + `_bounded_retry`/`_metadata`) are green — see Sequencing.
3. Alternatively (TYPING-01 option a) extend the pre-commit mypy hook's
   `additional_dependencies` (verified: `.pre-commit-config.yaml:26-31`, currently only
   `- types-requests` at `:31`) with `pydantic`, `aiohttp`, plus pandas-stubs/types for
   geo and `stamina`/`aiolimiter` for resilience. The dedicated CI job is preferred for a
   layered light-core/extras package; pick one to avoid double-maintenance.
4. Keep `ignore_missing_imports` scoped per-module for genuinely-untyped third-party deps;
   do NOT flip it off globally. Preserve the existing strict override block
   (`[[tool.mypy.overrides]]` for `restgdf._client.*`, `restgdf._models.*`,
   `restgdf.compat`, verified: `pyproject.toml:199-207`).

**Decision required** — see the Decision-required line re: strict-scope widening.

**Acceptance criteria** —
- [ ] `[tool.mypy] plugins = ["pydantic.mypy"]` present in `pyproject.toml`.
- [ ] A deps-present mypy invocation (CI job or hook) surfaces the 6 TYPING-01 errors
      on the *unfixed* tree (red-state demonstration: running mypy with deps installed
      reports `Found 6 errors in 5 files` — confirm before the fix items land).
- [ ] After W5-9/W5-10/W5-11/W4-6 + the `_bounded_retry`/`_metadata` fixes, the
      deps-present mypy run is green and only then is the mypy job added to the required
      `ci` aggregator.
- [ ] No blanket global `--strict` / `ignore_missing_imports` removal was introduced.

**Validation** — lint (`pre-commit run --all-files`, which includes the mypy hook).
Local deps-present check: `.\.venv\Scripts\python.exe -m mypy restgdf/` with the venv
that has all extras installed. test lane to confirm no runtime regression.

**Risks & rollback** — Risk: flipping the gate to required before the 6 fixes land breaks
every PR. Mitigate by gating the `ci`-aggregator wiring on the dependent items (Sequencing
edge). Risk: a global strict flip surfaces intended-`Any` noise — explicitly avoided.
Rollback: revert the `plugins` line and the CI job / hook deps; the gate returns to its
prior (defanged) state with no package-surface impact.

---

### W1-3 · Run the coverage floor on PRs, not only post-merge
**Audit refs:** TESTS-01, CICD-04 · **Severity:** low · **Effort:** M · **Milestone:** M1
**Depends:** — (serialize `pytest.yml` after W1-1, W1-2; `pyproject.toml` after W1-2)
· **Blocks:** — (W6-2 reconciles the CONTRIBUTING prose after this lands)
**Split-ownership:** This item owns the **CI gate**. The CONTRIBUTING.md prose
reconciliation ("CI will re-run the same gates", gate #2 coverage claim) is **W6-2**.
**Scope** — In: add a coverage-enforcing PR job to `.github/workflows/pytest.yml` (or a
dedicated job) mirroring CONTRIBUTING gate #2 exactly, and wire it into the `ci`
aggregator `needs:`/result check. Out-of-scope: do NOT add a coverage step inside the
existing `test` matrix (running `--fail-under=97` across all six 3.9–3.14 legs is wasteful
and risks spurious floor failures from interpreter-dependent branch counts); do NOT edit
`CONTRIBUTING.md` (W6-2); do NOT change `fail_under` (`pyproject.toml:147`).

**Spec** —
1. Add a single dedicated PR coverage job to `pytest.yml`, mirroring `coverage.yml`'s
   environment (Python 3.14 + `.[dev,geo,resilience,telemetry]`, verified:
   `.github/workflows/coverage.yml:26-33`).
2. Run **`python -m coverage run -m pytest -q -m "not network" && python -m coverage
   report --fail-under=97`** — note the explicit `-m pytest -q -m "not network"`: the
   `[tool.coverage.run] command_line = "-m pytest"` default (verified: `pyproject.toml:139`)
   runs the FULL suite including `network`/`stress`, so the bare `coverage run` that
   `coverage.yml` uses (verified: `.github/workflows/coverage.yml:36`) must NOT be copied —
   pass the markers explicitly to match CONTRIBUTING gate #2 (verified: `CONTRIBUTING.md:91`).
3. Pin the job to a single Python version (3.14, matching `coverage.yml`) to avoid
   measuring coverage 6× and version-skew noise on `TYPE_CHECKING`/py-gated branches.
4. Add the new job to the `ci` aggregator's `needs:` list AND its result-check shell
   (verified: `.github/workflows/pytest.yml:184` `needs:` and `:188-192` the
   `if [ "${{ needs.<job>.result }}" != "success" ]` chain) so a sub-97% PR cannot go green.
5. Leave `coverage.yml` on push-to-main as badge/`COVERAGE.md` regeneration + main-branch
   backstop (verified: `.github/workflows/coverage.yml:3-5` `on: push: branches: ["main"]`).

**Acceptance criteria** —
- [ ] A dedicated PR coverage job exists in `pytest.yml`, runs
      `coverage run -m pytest -q -m "not network"` then `coverage report --fail-under=97`
      on Python 3.14 with all extras.
- [ ] The job is in the `ci` aggregator `needs:` and its result-check chain.
- [ ] Red-state demonstration: confirm the job's command fails (non-zero exit) when run
      against a tree with coverage < 97% (e.g. by temporarily deleting a covered test
      locally) and passes at ≥97%.
- [ ] The post-merge `coverage.yml` job is unchanged (still regenerates the badge/COVERAGE.md).
- [ ] Doc-sync: note in the W6-2 hand-off that CONTRIBUTING.md:98 ("CI will re-run the
      same gates") is now TRUE for gate #2 (W6-2 owns the edit).

**Validation** — lint (`actionlint`/`check-github-workflows`). coverage lane locally:
`.\.venv\Scripts\python.exe -m coverage run -m pytest -q -m "not network"; .\.venv\Scripts\python.exe -m coverage report --fail-under=97` — confirm green at HEAD and red when coverage is dropped.

**Risks & rollback** — Risk: the `command_line` default silently pulling in network/stress
makes the PR job flaky/slow — explicitly avoided by passing markers. Risk: branch-count
skew across interpreters — avoided by single-version pinning. Note the audit's correction:
the "silently rewrites COVERAGE.md to the lower number" claim is NOT accurate (line 39
`coverage report` runs before the COVERAGE.md write under `set -e`, so a sub-97% main run
fails loudly) — do NOT design the PR gate around a non-existent ratchet-down. Rollback:
remove the job and its aggregator entry.

---

### W1-7 · Remove the stale restgdf/app.py coverage omit
**Audit refs:** TESTS-03 · **Severity:** low · **Effort:** S · **Milestone:** M1
**Depends:** — (serialize `pyproject.toml` after W1-2, W1-3) · **Blocks:** —
**Split-ownership:** —
**Scope** — In: delete the `"restgdf/app.py"` entry from the coverage omit list.
Out-of-scope: do NOT remove the `"*tests/*.py"` glob (load-bearing — excludes test files
from coverage); do NOT touch `fail_under`, `source`, or any branch config.

**Spec** —
1. Edit `pyproject.toml:138` — `omit = ["*tests/*.py", "restgdf/app.py"]` (verified) →
   `omit = ["*tests/*.py"]`. `restgdf/app.py` does not exist anywhere in the package
   (re-verified: no `restgdf/app.py` in the tree).
2. Safe to bundle with any other trivial `[tool.coverage.*]` cleanup, but since W1-2/W1-3
   also touch `pyproject.toml`, serialize the edits.

**Acceptance criteria** —
- [ ] `omit = ["*tests/*.py"]` in `pyproject.toml`; no `restgdf/app.py` entry remains.
- [ ] Coverage still excludes test files (the glob is intact).
- [ ] `check-toml` / `validate-pyproject` pre-commit hooks pass.

**Validation** — lint (`pre-commit run --all-files`, includes `check-toml` and
`validate-pyproject`, verified: `.pre-commit-config.yaml:44-45,62-68`). coverage lane to
confirm the floor still computes.

**Risks & rollback** — Negligible; config-only, zero behavioral/import-boundary risk.
Rollback: restore the entry.

---

### W1-5 · SHA-pin the release-adjacent write-token workflow actions
**Audit refs:** CICD-05 · **Severity:** low · **Effort:** S · **Milestone:** M1
**Depends:** — · **Blocks:** —
**Split-ownership:** —
**Scope** — In: pin the actions in `bumpver.yml`, `coverage.yml`, `readthedocs.yml` to
full 40-char commit SHAs with a trailing version comment, matching the convention already
used in `pytest.yml` / `publish_on_pypi.yml` / `verify_attestation.yml`. Out-of-scope: do
NOT pin to a major branch or short SHA (use the full 40-char SHA); no behavior change.

**Spec** —
1. `bumpver.yml`: `actions/checkout@v6` (verified: `.github/workflows/bumpver.yml:23`) and
   `actions/setup-python@v6` (verified: `:28`) → full SHAs, e.g.
   `actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd # v6.0.2` and
   `actions/setup-python@a309ff8b426b58ec0e2a45f0f869d46889d02405 # v6.2.0` (the SHAs
   already in use in `pytest.yml:32-33`, verified).
2. `coverage.yml`: `actions/checkout@v6` (drift: audit cited `:22`, confirmed now at
   `.github/workflows/coverage.yml:22`), `actions/setup-python@v6` (`:27`),
   `stefanzweifel/git-auto-commit-action@v7` (`:48`) → full SHAs + version comments.
3. `readthedocs.yml`: `actions/checkout@v6` (**drift: audit cited `:23`, now at
   `.github/workflows/readthedocs.yml:22`**), `actions/setup-python@v6` (**drift: audit
   cited `:28`, now at `:27`**), `stefanzweifel/git-auto-commit-action@v7` (verified: `:43`)
   → full SHAs + version comments.
4. Prioritize the token-holding `actions/checkout` steps (these run with
   `secrets.WORKFLOW_GIT_ACCESS_TOKEN`, verified: `bumpver.yml:25`, `coverage.yml:24`,
   `readthedocs.yml:25`) and `git-auto-commit-action`. Dependabot's weekly github-actions
   updater (verified: `.github/dependabot.yml`, `package-ecosystem: "github-actions"`,
   `interval: "weekly"`, `groups: actions`) keeps SHAs + comments current — maintenance is
   unchanged.

**Acceptance criteria** —
- [ ] Every `uses:` in `bumpver.yml`, `coverage.yml`, `readthedocs.yml` is a full 40-char
      commit SHA with a `# vX.Y.Z` comment.
- [ ] No mutable `@vN` tags remain in those three files; behavior is unchanged
      (SHAs resolve to the same versions already used in the PR/publish workflows).

**Validation** — lint (`actionlint` + `check-github-workflows`).

**Risks & rollback** — Risk: a typo'd SHA breaks the action resolution — verify each SHA
against the version comment (and against the SHAs already in `pytest.yml`). Anti-rec
honored: full SHA only, never a branch or short SHA. Rollback: revert the three files.
Note for scoping: the consumer-facing supply chain (PyPI build, OIDC, Sigstore, PEP 740)
is already fully SHA-pinned — this is hardening of the repo-contents/token surface.

---

### W1-6 · Fix the verify_attestation setup-python pin comment
**Audit refs:** CICD-06 · **Severity:** low · **Effort:** S · **Milestone:** M1
**Depends:** — · **Blocks:** —
**Split-ownership:** —
**Scope** — In: correct the stale version comment on the `setup-python` pin in
`verify_attestation.yml`. Out-of-scope: the secondary `2.0.0` docstring tweak (line 17) is
optional/low-value — that `2.0.0` is a generic release-version placeholder in a
`workflow_dispatch` input description, NOT a setup-python version; updating it is harmless
but not required and the audit explicitly flags the "reinforces the lag" framing as an over-reach.

**Spec** —
1. `.github/workflows/verify_attestation.yml:46` reads
   `uses: actions/setup-python@a309ff8b426b58ec0e2a45f0f869d46889d02405 # v6.0.0`
   (verified). The same SHA is commented `# v6.2.0` in `pytest.yml:33` and
   `publish_on_pypi.yml:44` (verified). Change the comment on `:46` from `# v6.0.0` to
   `# v6.2.0`. Verifiably correct direction: that SHA *is* setup-python v6.2.0; the real
   v6.0.0 SHA is the unrelated `e797f83bcb11b83ae66e0230d6156d7c80228e7c`. Comment-only,
   cannot affect Actions resolution.
2. Treat the `2.0.0` docstring at `:17` as optional — leave it or bump to an illustrative
   `3.0.0`; do not over-invest.

**Acceptance criteria** —
- [ ] `verify_attestation.yml:46` comment reads `# v6.2.0`, matching the SHA and the other
      8 occurrences across the workflows.
- [ ] No SHA was changed (resolution unaffected).

**Validation** — lint (`actionlint` + `check-github-workflows`).

**Risks & rollback** — None of note (comment-only). Rollback: revert the one line.

---

### W1-8 · Harden the bumpver release path (CHANGELOG-aware)
**Audit refs:** CICD-03 · **Severity:** low · **Effort:** M · **Milestone:** M2
**Depends:** W1-4 (the complementary publish-time gate must exist first) · **Blocks:** —
**Split-ownership:** The CHANGELOG.md content/structural fix is W6-5; this item owns the
*automation* that consolidates `## [Unreleased]` at bump time.
**Scope** — In: make the bump path consolidate the changelog (or at minimum fail when the
`## [Unreleased]` section has no body), via the single existing bumpver `pre_commit_hook`
slot. Out-of-scope: do NOT add a literal second/"sibling" bumpver hook (bumpver supports
only ONE `pre_commit_hook` path and it is already occupied — see Spec); do NOT make the
publish-time gate auto-rename (that is W1-4's hard assertion); do NOT hand-edit CHANGELOG
content here (W6-5).

**Spec** —
1. bumpver supports a SINGLE `pre_commit_hook`, already set to
   `scripts/bumpver_stamp_date.py` (verified: `pyproject.toml:125`). You CANNOT add a
   literal sibling hook. Choose: (a) extend the existing stamp script to also consolidate
   the changelog, or (b) factor a small dispatcher that runs the date-stamp + changelog
   step. Recommended: **(a)** — extend `scripts/bumpver_stamp_date.py`.
2. The existing script already runs between bumpver's file-pattern substitution and the
   commit, reads/rewrites `CITATION.cff`, and `git add`s it (verified:
   `scripts/bumpver_stamp_date.py:45-88`; the `_DATE_RELEASED_RE` rewrite at `:50-65`,
   the `git add` at `:76-82`). Add an analogous CHANGELOG step: read the just-bumped
   version (from `pyproject.toml` `version = "X.Y.Z"`, already rewritten by the
   `file_patterns` step at hook time — verified `pyproject.toml:128` substitutes
   `version = "{version}"`), rename `## [Unreleased]` → `## [{version}] - {YYYY-MM-DD}`,
   insert a fresh `## [Unreleased]` stub, refresh the compare-link footer, and `git add`
   `CHANGELOG.md`. The hook touches only `CITATION.cff` + `CHANGELOG.md` and crosses no
   light-core import boundary / public-API seam.
3. **Lower-risk fallback (sufficient on its own to have blocked the 3.0.0 empty-section
   ship):** instead of full consolidation, fail bumpver when the `## [Unreleased]` section
   has no body. This is the safer minimum; prefer it if the full rewrite is risky.
4. Keep the script's existing fail-fast discipline (it exits non-zero on unexpected
   `CITATION.cff` shape; mirror that for CHANGELOG). bumpver.yml itself stays
   `workflow_dispatch`-only (verified: `.github/workflows/bumpver.yml:3-4`); no trigger
   change required — the hook fires inside the existing
   `bumpver update --commit --tag-commit --no-push` step (verified: `:39-40`).

**Decision required** — see Decision-required line (full consolidation vs fail-fast-only).

**Acceptance criteria** —
- [ ] The bumpver `pre_commit_hook` either renames `## [Unreleased]` → `## [X.Y.Z] - <date>`
      (and stubs a fresh Unreleased + refreshes the compare link) OR fails fast when the
      Unreleased section is empty.
- [ ] No second bumpver hook was added (single-slot constraint honored).
- [ ] Red-state demonstration: add/adjust a unit test for `scripts/bumpver_stamp_date.py`
      (or a focused test) that feeds an empty `## [Unreleased]` and asserts the hook fails
      (fallback) or produces the consolidated section (full), confirming it fails for the
      right reason first.
- [ ] The existing CITATION.cff date-stamp behavior is unchanged (its test still passes).

**Validation** — lint (`pre-commit run --all-files`). single:
`.\.venv\Scripts\python.exe -m pytest -k bumpver` (or the specific new test path). test
lane to confirm no suite regression.

**Risks & rollback** — Risk: a changelog-rewrite regex that mis-parses the file corrupts
the changelog at bump time — mitigate with fail-fast on unexpected shape (mirror the
existing `n != 1` guard at `:54-60`) and prefer the fallback if uncertain. Anti-rec
honored: do NOT add a second hook; do NOT make the publish gate auto-mutate. Rollback:
revert the script changes; the date-stamp behavior is independent and unaffected.

---

### W1-9 · Restore verb separation in FakeSession / characterization tests
**Audit refs:** TESTS-02 · **Severity:** low · **Effort:** M · **Milestone:** M3
**Depends:** W2-1 (the AUTH-01 verb-routing fix) · **Blocks:** —
**Split-ownership:** —
**Scope** — In: make the affected `characterization` tests assert on the verb-correct key
again so they can detect a GET↔POST flip or a `data`↔`params` interface change; coordinate
with W2-1 so the restored assertions pin the *corrected* behavior. Out-of-scope: do NOT
remove the params↔data mirror from the **legacy compat fakes** in
`tests/test_FeatureLayer.py` / `tests/test_getgdf.py` / `tests/test_base_install.py`
(those are outside W1's `owns[]` and a desync there would break `tests/test_compat.py` —
the audit's explicit anti-recommendation; per commit `3b94983` the same `.get` delegator +
body-mirror pattern was added there).

**Spec** —
1. The unified `FakeSession` aliases `post_responses`/`get_responses` and
   `post_calls`/`get_calls` onto single shared lists (verified:
   `tests/conftest.py:142-147`) and `_snapshot_kwargs` mirrors the body under both `data`
   and `params` (verified: `:149-163`, mirror at `:160-162`). This lets named-for-POST
   characterization tests pass even though the real call is a GET recording `params`.
2. **Preferred (cheaper) fix per TESTS-02:** rename the affected tests so the name no
   longer implies POST and assert on the verb-correct key. Specifically in
   `tests/test_characterization.py`:
   - `test_get_feature_count_sends_minimal_count_payload` (verified: `:34-59`) — this is a
     GET helper (`get_feature_count` short body routes through `_arcgis_request` →
     `session.get(url, params=...)`, verified: `restgdf/utils/_query.py:44` and
     `restgdf/utils/_http.py:117-123`). Rename to drop the "payload/POST" implication
     (e.g. `*_count_query_payload`) and read `kwargs["params"]` instead of `kwargs["data"]`
     (currently reads `kwargs["data"]` at `:52`).
   - Apply the same to the other GET helpers among the characterization tests
     (count / object_ids / uniquevalues / valuecounts — e.g.
     `test_get_object_ids_preserves_where_and_returns_tuple`, verified: `:107-128`,
     reads `kwargs["data"]` at `:123`); keep `kwargs["data"]` only for genuinely-POST cases.
   - These tests already carry honest `# T8 (R-74): short count queries ride on GET`
     comments (verified: `:49-51`), so the rename removes the misnomer rather than fixing
     a lie.
3. **Coordinate with W2-1:** after the AUTH-01 body-aware leak guard lands (forces POST
   when the body carries a token), the verb for token-carrying bodies changes. Ensure the
   restored assertions pin the post-W2-1 verb (token-in-body → POST; short tokenless count
   → GET), not the pre-fix behavior. This is why W1-9 `Depends: W2-1`.
4. **Optional (heavier) alternative:** split `FakeSession` back into separate `post_*`/`get_*`
   lists and drop the `_snapshot_kwargs` mirror (TESTS-02 option 1). If chosen, scope it to
   `conftest.py` ONLY — do NOT touch the compat fakes (see Out-of-scope). Prefer the rename
   approach to avoid that blast radius.
5. Note the verb dimension is ALSO independently pinned in `tests/test_choose_verb_live.py`
   (verified present) — so this item improves test-clarity, it is not the only safety net.

**Acceptance criteria** —
- [ ] The renamed characterization tests assert on the verb-correct key (`params` for the
      GET helpers, `data` only for POST cases) and would FAIL on a GET↔POST flip.
- [ ] Red-state demonstration (CONTRIBUTING red-first rule): before fixing, confirm the
      current tests pass *regardless* of verb (the mirror masks a flip); after the fix,
      flipping the verb in a scratch edit makes them fail for the right reason.
- [ ] `FakeSession` change (if any) is confined to `tests/conftest.py`; the compat fakes in
      `test_FeatureLayer.py` / `test_getgdf.py` / `test_base_install.py` are untouched.
- [ ] `tests/test_compat.py` still passes (compat fakes / mirror intact).
- [ ] The assertions pin the post-W2-1 behavior (coordinate the merge order).

**Validation** — single: `.\.venv\Scripts\python.exe -m pytest tests/test_characterization.py`.
compat: `.\.venv\Scripts\python.exe -m pytest -q tests/test_compat.py`. test lane for the
full non-network suite. lint.

**Risks & rollback** — Risk: touching the compat-fake mirror desyncs `test_compat.py` —
explicitly out-of-scope. Risk: pinning pre-W2-1 behavior — mitigated by the `Depends: W2-1`
ordering. Rollback: revert the test renames (test-only, no public-API/runtime impact).
