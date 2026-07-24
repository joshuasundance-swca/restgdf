> **04 — CI/CD pipelines, release flow & supply chain** · restgdf audit · **read-only** · no code was modified
> Commit `4673b08` · 2026-06-13 · Index: [README](README.md) · Machine-readable: [findings.json](findings.json)

## Assessment

The release/supply-chain core is genuinely strong: PyPI publish uses OIDC trusted publishing with PEP 740 attestations, the publish job has `permissions: {}` at workflow level with least-privilege per-job grants, distributions are Sigstore-signed with SHA256SUMS, twine `--strict` validates metadata, a tag/version-match gate prevents mis-tagged builds, and a post-publish attestation-verification workflow (BL-43) closes the loop. The PR-gating `pytest.yml` is thorough (6-version matrix, install-combination matrix, base-install contract, docs-strict, network/stress tiers, and an aggregator gate). The dominant risk is that none of that test rigor actually guards the release path: there is NO CI test gate on push/merge to `main` and NO test gate between a tag push and PyPI publish — `pytest.yml` fires only on `pull_request`, so a direct push, admin merge, or manually pushed tag ships to PyPI entirely untested. Secondary risks are a coverage floor that is only enforced post-merge (contradicting CONTRIBUTING's "CI re-runs the same gates" claim) and a CHANGELOG-consolidation gate that passes on an empty section (v3.0.0 shipped with zero documented changes under its header).

## Findings at a glance

| ID | Finding | Severity | Effort |
|----|---------|----------|--------|
| `CICD-01` | No CI test gate between tag push / workflow_dispatch and PyPI publish | high | M |
| `CICD-02` | CHANGELOG release gate passes on an empty section — 3.0.0 shipped with zero documented changes | medium | S |
| `CICD-03` | bumpver release path is workflow_dispatch-only and CHANGELOG-blind, so the BL-41 publish gate is the last line | low | M |
| `CICD-04` | 97% coverage floor is enforced only post-merge; PR gate measures no coverage, contradicting CONTRIBUTING | low | S |
| `CICD-05` | Release-adjacent write-token workflows use unpinned mutable action tags while PR workflows are SHA-pinned | low | S |
| `CICD-06` | verify_attestation.yml setup-python pin comment drift (# v6.0.0 on a v6.2.0 SHA) | low | S |

## Findings

### CICD-01 · No CI test gate between tag push / workflow_dispatch and PyPI publish

**Severity:** high · **Effort:** M · **Location:** `.github/workflows/publish_on_pypi.yml:16-18,124-147, .github/workflows/pytest.yml:3-9`

**Evidence**

publish triggers include `push: tags: - "*.*.*"` and `workflow_dispatch` (publish_on_pypi.yml:16-18, 10-15). The build/publish jobs run no test suite — `build-distributions` only builds and twine-checks; `publish-pypi` runs whenever `github.event_name != 'pull_request' && needs.build-distributions.outputs.release-tag != ''` (:125). Meanwhile pytest.yml fires ONLY on `pull_request` (`on: pull_request: branches: ["main"]`, :3-5) — a tag push does NOT trigger it. The only pre-tag test gate lives in bumpver.yml (BL-42, :48-51) which is `workflow_dispatch`-only and thus skippable.

**Why it matters**

A maintainer who pushes a tag directly (e.g. `git tag 3.0.1 && git push --tags`) or runs the publish `workflow_dispatch` with a `release_tag` bypasses every test, lint, docs, and install-matrix check and publishes straight to PyPI. Because PyPI publishes are immutable, a broken or insecure artifact cannot be retracted — only yanked. The bumpver pre-tag test (BL-42) is the sole guard and is not on the release-cut path itself.

**Recommendation**

Add a test gate to the release-cut path. Two viable shapes:

1. (Preferred, minimal duplication) Refactor pytest.yml into a reusable workflow (`workflow_call`) exposing the `test` matrix + `base_install` + `install_combinations` jobs, then add a `needs:`-precedent `call-tests` job to publish_on_pypi.yml that invokes it on the `push:tags` and `workflow_dispatch` paths, gating `build-distributions` / `publish-pypi` behind it. This guarantees the same gates protecting PRs also protect releases.

2. (Lighter) Add an inline job to publish_on_pypi.yml that installs `-e ".[dev,geo,resilience,telemetry]"` and runs `python -m pytest -q -m "not network"` (mirroring BL-42), made a `needs:` of `build-distributions`. Run it against `ref: ${{ inputs.release_tag || github.ref }}` so it tests the exact commit being built.

Anti-recommendation / cautions:
- Do NOT include the live `network` or `stress` markers in the release gate — they require `--run-network` / `--run-stress` and hit external ArcGIS endpoints; a flaky upstream service would block legitimate releases. Mirror BL-42's `-m "not network"` scope.
- The build job pins Python 3.14 only; the test matrix runs 3.9–3.14. A release gate need not re-run the full 6-version matrix to be effective — a single-version `not network` run (as BL-42 already does) catches the catastrophic "broken artifact" case the finding describes. Re-running the whole matrix is defensible but adds latency; the cheap inline version is sufficient to close the gap.
- A strong, low-effort complement (or alternative) the team may already rely on: configure the GitHub `release` deployment environment (already referenced at publish_on_pypi.yml:130-132) with a required reviewer. That converts any tag-push/dispatch publish into a manual approval gate. This is repo-settings config, not visible in the tree, so it should be confirmed rather than assumed; if it is already set, the residual risk is materially lower than the finding's "publishes straight to PyPI" framing implies.

**Fix touches:** `.github/workflows/publish_on_pypi.yml`, `.github/workflows/pytest.yml`

---

### CICD-02 · CHANGELOG release gate passes on an empty section — 3.0.0 shipped with zero documented changes

**Severity:** medium · **Effort:** S · **Location:** `.github/workflows/publish_on_pypi.yml:85-102, CHANGELOG.md:6-8`

**Evidence**

The BL-41 gate does `header="## [${RELEASE_VERSION}]"; if ! grep -F -- "$header" CHANGELOG.md` (:97-98) — a pure header-presence check, no body assertion. At tag 3.0.0 the CHANGELOG is `## [3.0.0] - 2026-05-02` immediately followed by `## [2.0.0] - 2026-05-02` with the section between them EMPTY (verified `git show 3.0.0:CHANGELOG.md`); the gate `grep -F '## [3.0.0]'` PASSES. All the actual v3 changes are mislabeled under a second `## [2.0.0]` header (HEAD has two `## [2.0.0]` headers — `grep -cF '## [2.0.0]'` returns 2).

**Why it matters**

v3.0.0 — a Production/Stable major release with breaking changes (token transport flip, PaginationError no longer inherits RuntimeError, removed FIELDDOESNOTEXIST sentinel) — was published with an empty `## [3.0.0]` changelog section while the BL-41 "require CHANGELOG entry" gate reported green. Users reading the changelog at the released version see no documented changes; the duplicate `## [2.0.0]` header also breaks the [version]: link footer convention. The gate gives false assurance that consolidation happened.

**Recommendation**

Sound; tighten with care. (1) Strengthen the BL-41 gate (publish_on_pypi.yml:97-102) to assert the section body is non-empty: extract the lines strictly between `## [${RELEASE_VERSION}]` and the next `## [` header and fail if they are only blank/whitespace. An awk one-liner works, e.g. capture with `awk -v h="## [${RELEASE_VERSION}]" '$0 ~ "^"h {f=1;next} f && /^## \[/ {exit} f {print}'` then test that the captured text contains a non-blank line. This is safe: the step only runs when `steps.release_meta.outputs.raw != ''` (line 86), i.e. tag-push / workflow_dispatch — it never fires on PR runs or on the `## [Unreleased]` workflow, so the existing Unreleased-bullets convention (CONTRIBUTING.md:13-15,47-49) is untouched, and it is pure-CI with no impact on the light-core import boundary. Optionally also fail when more than one identically-named `## [X.Y.Z]` header exists, to catch the duplicate-header class directly. (2) Fix CHANGELOG.md: the misplaced section is line 8 `## [2.0.0] - 2026-05-02` (note: the real 2.0.0 at line 536 is dated 2026-04-20, so the 2026-05-02 duplicate is unambiguously the v3 content) — rename it to `## [3.0.0] - 2026-05-02`, delete the now-empty header at line 6, and add a `[3.0.0]: https://github.com/joshuasundance-swca/restgdf/compare/v2.0.0...v3.0.0` footer (the footer block at 592-593 only defines Unreleased and 2.0.0). Anti-recommendation: the gate change cannot retroactively repair the already-published 3.0.0 PyPI/GitHub release notes — that needs a manual GitHub-release edit; and note docs/changelog.md `{include}`s CHANGELOG.md verbatim, so the docs-site changelog inherits the same defect and is fixed by the same edit. Do not be tempted to make the gate auto-rename `## [Unreleased]`; keep it a fail-fast assertion so the human consolidation step stays explicit.

**Fix touches:** `.github/workflows/publish_on_pypi.yml`, `CHANGELOG.md`

---

### CICD-03 · bumpver release path is workflow_dispatch-only and CHANGELOG-blind, so the BL-41 publish gate is the last line

**Severity:** low · **Effort:** M · **Location:** `.github/workflows/bumpver.yml:3-4,39-55, .github/workflows/publish_on_pypi.yml:85-102`

**Evidence**

bumpver.yml runs only `on: workflow_dispatch` (:3-4) and does `bumpver update --commit --tag-commit --no-push` then pushes commit+tag (:39-55). It bumps pyproject/__init__/CITATION.cff (pyproject.toml:127-133) but never touches CHANGELOG.md — no rename of `## [Unreleased]` to `## [X.Y.Z]`. The pre-tag offline test (BL-42, :48-51) runs, but CHANGELOG consolidation is left entirely to the maintainer with no automation.

**Why it matters**

Because the only enforcement that CHANGELOG was consolidated is the publish-time header grep (which, per the prior finding, passes on an empty section), and bumpver does nothing for the changelog, the realistic failure mode is exactly what shipped in 3.0.0: tag cut, empty section, green gate. Tying changelog consolidation to the same automated step that stamps the version would prevent the drift at the source.

**Recommendation**

Sound, with one mechanical correction to the proposed fix. bumpver supports only a SINGLE `pre_commit_hook` path, and that slot is already occupied by `scripts/bumpver_stamp_date.py` (pyproject.toml:125). So you cannot add a literal "sibling" hook — instead either (a) extend the existing stamp script to also consolidate the changelog, or (b) factor a small dispatcher that runs both. Inside that hook: read the just-bumped version from pyproject.toml (already rewritten by the file_patterns step at hook time) or bumpver's hook env, rename `## [Unreleased]` → `## [{version}] - {YYYY-MM-DD}`, and insert a fresh `## [Unreleased]` stub plus refresh the compare link at the bottom. The hook runs between substitution and commit, touches only CHANGELOG.md, and does not cross the light-core import boundary or any public-API seam, so it is safe. The "at minimum, fail bumpver when the `## [Unreleased]` section has no body" fallback is the lower-risk option and would by itself have blocked the 3.0.0 empty-section ship. Note the deeper bug this protects against is ALSO present in the BL-41 publish-time gate, which uses `grep -F -- "## [${VERSION}]"` (publish_on_pypi.yml:97-98) — a header-presence check that passes on an empty section; fixing only bumpver still leaves that gate hollow, so harden both (e.g. require the section to contain at least one non-blank line before the next `## [` header).

**Fix touches:** `.github/workflows/bumpver.yml`, `scripts/bumpver_stamp_date.py`, `CHANGELOG.md`

---

### CICD-04 · 97% coverage floor is enforced only post-merge; PR gate measures no coverage, contradicting CONTRIBUTING

**Severity:** low · **Effort:** S · **Location:** `.github/workflows/pytest.yml:61-62, .github/workflows/coverage.yml:34-44, CONTRIBUTING.md:91,98, pyproject.toml:147`

**Evidence**

PR-gating pytest.yml runs `python -m pytest -q -m "not network"` (:62) with no `coverage run` / `--fail-under`. The 97% floor (`fail_under = 97`, pyproject.toml:147) is exercised only by coverage.yml's `coverage run` (:36) which runs on push to main, AFTER merge. CONTRIBUTING.md gate #2 lists `coverage report --fail-under=97` (:91) and asserts "CI will re-run the same gates" (:98).

**Why it matters**

A PR that drops coverage below 97% passes all PR checks and merges; the floor only trips on the post-merge coverage.yml run, where `coverage report -m --precision=2` failing exit code is the only signal and it cannot block the already-merged change. The documented contributor contract (CI re-runs the same gates, including coverage) is false, so contributors and the maintainer get a green PR that silently regresses the floor.

**Recommendation**

Add a coverage-enforcing step to the PR-gating pytest.yml `test` job (or a dedicated job) that mirrors CONTRIBUTING gate #2 exactly: `python -m coverage run -m pytest -q -m "not network" && python -m coverage report --fail-under=97`, and wire it into the `ci` aggregator's `needs`/result check (line 184-192) so a sub-97% PR cannot go green. Note two implementation details: (1) the `[tool.coverage.run] command_line = "-m pytest"` default (pyproject.toml:139) runs the FULL suite including network/stress markers, so to match gate #2 you must pass `-m pytest -q -m "not network"` explicitly on the PR job rather than the bare `coverage run` that coverage.yml uses. (2) Running across the full py3.9-3.14 matrix would measure coverage 6x redundantly; pin the fail-under check to a single Python version (e.g. 3.14, matching coverage.yml) to avoid version-skew noise on TYPE_CHECKING/py-version-gated branches. After this, coverage.yml's post-merge `coverage run` becomes badge-refresh + main-branch backstop, not the sole enforcement point. This is a pure-CI change with no impact on the light-core import boundary, public API, or any back-compat seam.

**Fix touches:** `.github/workflows/pytest.yml`, `CONTRIBUTING.md`

---

### CICD-05 · Release-adjacent write-token workflows use unpinned mutable action tags while PR workflows are SHA-pinned

**Severity:** low · **Effort:** S · **Location:** `.github/workflows/bumpver.yml:23,28, .github/workflows/coverage.yml:22,27,48, .github/workflows/readthedocs.yml:23,28,43`

**Evidence**

bumpver.yml uses `actions/checkout@v6` (:23), `actions/setup-python@v6` (:28); coverage.yml uses `actions/checkout@v6` (:22), `actions/setup-python@v6` (:27), `stefanzweifel/git-auto-commit-action@v7` (:48); readthedocs.yml mirrors this. These are the three workflows that hold `secrets.WORKFLOW_GIT_ACCESS_TOKEN` and `contents: write` and that create the release tag (bumpver) / push to main (coverage, readthedocs). By contrast pytest.yml and publish_on_pypi.yml pin every action to a full commit SHA with a version comment (e.g. `actions/checkout@de0fac2e...# v6.0.2`).

**Why it matters**

The highest-privilege workflows (write token, tag creation, direct main pushes) are the ones NOT SHA-pinned. A compromised or hijacked tag of `actions/checkout`, `setup-python`, or `git-auto-commit-action` would execute with the git access token in the bumpver tag-cut path — the exact supply-chain surface SHA-pinning exists to close. Dependabot's github-actions updater (dependabot.yml:17-24) keeps SHAs current, so pinning costs nothing in maintenance.

**Recommendation**

Pin the actions in bumpver.yml, coverage.yml, and readthedocs.yml to full commit SHAs with a trailing version comment, matching the pattern already used in pytest.yml / publish_on_pypi.yml / verify_attestation.yml (e.g. `actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd # v6.0.2`, `actions/setup-python@a309ff8b426b58ec0e2a45f0f869d46889d02405 # v6.2.0`). Prioritize the token-holding `actions/checkout` steps and `stefanzweifel/git-auto-commit-action@v7`. This is low-cost: the dependabot.yml github-actions updater (weekly, lines 17-24) already keeps SHA pins current and rewrites the version comment, so maintenance burden is unchanged. The fix is safe — it changes no behavior, touches no public API / import boundary / runtime code, and brings these three workflows into line with the repo's own established convention. Note for accurate scoping: the consumer-facing supply chain (PyPI artifact build, OIDC Trusted Publishing, Sigstore signing, PEP 740 attestation in publish_on_pypi.yml and verify_attestation.yml) is ALREADY fully SHA-pinned, and publish_on_pypi.yml independently validates that the release tag matches pyproject.toml version (lines 67-78) and requires a CHANGELOG entry (BL-41, lines 85-102). So a hijacked mutable tag in bumpver/coverage/readthedocs primarily threatens the repo's git contents and the WORKFLOW_GIT_ACCESS_TOKEN, not the signed PyPI artifact end users install — which is why this is hardening/consistency rather than an active hole. Avoid the anti-fix of pinning to a major branch or short SHA; use the full 40-char commit SHA.

**Fix touches:** `.github/workflows/bumpver.yml`, `.github/workflows/coverage.yml`, `.github/workflows/readthedocs.yml`

---

### CICD-06 · verify_attestation.yml setup-python pin comment drift (# v6.0.0 on a v6.2.0 SHA)

**Severity:** low · **Effort:** S · **Location:** `.github/workflows/verify_attestation.yml:46, .github/workflows/pytest.yml:33`

**Evidence**

verify_attestation.yml:46 reads `uses: actions/setup-python@a309ff8b426b58ec0e2a45f0f869d46889d02405 # v6.0.0` while the identical SHA is commented `# v6.2.0` in pytest.yml:33 and publish_on_pypi.yml:44. The SHA is the same, so behavior is identical — only the human-readable comment disagrees.

**Why it matters**

Harmless at runtime (same pin) but the comment is the only signal a reviewer/Dependabot reads to judge freshness; a stale comment invites a "downgrade" or confuses an audit. The header docstring also carries a stale `2.0.0` example version (verify_attestation.yml:17), reinforcing that this file lagged the v6.2.0 bump.

**Recommendation**

Change the comment on .github/workflows/verify_attestation.yml:46 from `# v6.0.0` to `# v6.2.0` so it matches the SHA and the other 8 occurrences. This is verifiably the correct direction: the pinned SHA `a309ff8b426b58ec0e2a45f0f869d46889d02405` actually corresponds to setup-python v6.2.0 (that commit itself bumps package.json to 6.2.0; the real v6.0.0 SHA is the unrelated `e797f83bcb11b83ae66e0230d6156d7c80228e7c`), so `# v6.0.0` is the stale outlier, not the others. The fix is comment-only and cannot affect Actions resolution. Treat the secondary `2.0.0` docstring suggestion (line 17) as optional and low-value: that `2.0.0` is a generic placeholder for a restgdf release version in a workflow_dispatch input description, not a setup-python version, so it does not actually evidence the setup-python comment lag. Updating it to a current illustrative version (e.g. 3.0.0) is harmless but not required, and the finding's framing of it as "reinforcing" the lag is an over-reach.

**Fix touches:** `.github/workflows/verify_attestation.yml`

---

## Minor notes (not adversarially verified)

These were flagged by the axis auditor but did NOT go through per-finding verification — treat as leads, not confirmed findings.

- **git-auto-commit COMMIT_MESSAGE key works by accident, not by spec (seed refuted)** — coverage.yml:46-48 and readthedocs.yml:41-43 pass `with: COMMIT_MESSAGE:` (uppercase). The action's declared input is `commit_message` (lowercase) in both v4 and v7 action.yml (verified against source). The seed hypothesis that the message is silently ignored is REFUTED: GitHub Actions maps any `with:` key to `INPUT_<UPPERCASE>`, so both `COMMIT_MESSAGE` and `commit_message` produce `INPUT_COMMIT_MESSAGE`, which is exactly what entrypoint.sh reads. Git history confirms the auto-commits read "Update coverage" (committer github-actions[bot]), so the message IS honored. Recommend lowercasing the key to `commit_message` anyway: relying on the env-var collision is fragile and would silently break to the "Apply automatic changes" default if the action ever stops reading the raw env var.
- **coverage.yml installs requirements.txt with --user alongside extras, plus a duplicate setuptools** — coverage.yml:33 does `pip install --user -r requirements.txt "setuptools>=61" ".[dev,geo,resilience,telemetry]"`. requirements.txt already pins the full dev/doc/geo closure (and intentionally omits setuptools, requirements.txt:242-244). Installing both the lock and the extras live-resolves on top of the pinned set, which can produce versions differing from the lock the coverage number is supposedly measured against. Minor, but the coverage badge/floor is then measured against a not-fully-deterministic environment.
- **build-distributions runs on pull_request but is a separate check from the ci aggregator** — publish_on_pypi.yml build-distributions triggers on `pull_request` (:4-9) and builds + twine-checks the wheel/sdist (good pre-merge packaging signal). However it is a separate workflow from pytest.yml's `ci` aggregator, so its result is an independent status check; if branch protection lists only `ci` as required, a packaging failure here would not block merge. Confirm the required-check list includes this workflow.
- **coverage.yml / readthedocs.yml skip on 'Bump version' commits by design** — Both guard with `if: "!contains(github.event.head_commit.message, 'Bump version')"` (coverage.yml:15, readthedocs.yml:16). bumpver's commit message is `Bump version {old} -> {new}` (pyproject.toml:113), so the bump commit correctly skips the badge/doc auto-commit loop. Intentional and working; noting only that the released commit's coverage badge is whatever the prior push left, never refreshed for the release commit itself.
- **dependabot docker ecosystem configured but the image is dev-only** — dependabot.yml:26-29 enables the `docker` updater for the base image (`python:3.14-slim-bookworm`). Given the Dockerfile never installs restgdf and is a dev sandbox (see finding), the docker updater's value is limited to base-image CVE bumps for local dev. Harmless, just low ROI versus the pip/github-actions updaters.
