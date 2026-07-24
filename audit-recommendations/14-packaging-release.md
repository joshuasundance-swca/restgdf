> **14 — Packaging metadata, versioning & security policy** · restgdf audit · **read-only** · no code was modified
> Commit `4673b08` · 2026-06-13 · Index: [README](README.md) · Machine-readable: [findings.json](findings.json)

## Assessment

The build/release plumbing is genuinely strong: PEP 621 metadata is well-formed, version is single-sourced through bumpver across pyproject/`__init__`/CITATION.cff with a thoughtfully anchored CITATION pattern (and a date-stamp hook + drift test), classifiers/requires-python/test-matrix are mutually consistent (3.9-3.14), `py.typed` is shipped as package-data, the publish workflow uses Trusted Publishing + PEP 740 attestations + Sigstore with a tag-vs-version equality gate and a CHANGELOG-presence gate, and `twine check --strict` runs pre-publish. The residual risk is concentrated in human-edited release-hygiene surfaces that the automation does NOT cover: SECURITY.md's Supported-Versions table is stale (no 3.x row), CHANGELOG.md has a botched 2.0.0-to-3.0.0 promotion (empty 3.0.0 section, duplicate 2.0.0 headers, missing link reference) that the CI gate waves through, and requirements.txt has a hand-appended unpinned Snyk line that violates the pip-compile lockfile invariant the Dockerfile depends on. None of these ship broken code, but several publish misleading public metadata for a Production/Stable package and one undermines the only reproducible install surface.

## Findings at a glance

| ID | Finding | Severity | Effort |
|----|---------|----------|--------|
| `PACKAGING-01` | CHANGELOG 3.0.0 release was mis-promoted: empty 3.0.0 section, duplicate 2.0.0 headers, missing link ref - and the CI gate passes anyway | medium | S |
| `PACKAGING-02` | SECURITY.md Supported Versions table omits 3.x while the package is at 3.0.0 | medium | S |
| `PACKAGING-03` | ARCHITECTURE.md and CONTRIBUTING.md describe `restgdf[dev]` as including twine/build, but the dev extra ships neither | low | S |

## Findings

### PACKAGING-01 · CHANGELOG 3.0.0 release was mis-promoted: empty 3.0.0 section, duplicate 2.0.0 headers, missing link ref - and the CI gate passes anyway

**Severity:** medium · **Effort:** S · **Location:** `CHANGELOG.md:6-8, CHANGELOG.md:536, CHANGELOG.md:592-593, .github/workflows/publish_on_pypi.yml:85-102`

**Evidence**

CHANGELOG.md line 6 `## [3.0.0] - 2026-05-02` is immediately followed by line 8 `## [2.0.0] - 2026-05-02` — the 3.0.0 header has NO body; all the v3 content (`### Changed`, Gate-3 hardening, get_df, iter_pages, etc.) sits under the second header which is wrongly labelled `[2.0.0]`. The real 2.0.0 release header is at line 536 `## [2.0.0] - 2026-04-20`, so two `## [2.0.0]` headers exist with different dates. The link-reference block only defines `[Unreleased]: ...compare/v2.0.0...HEAD` (592) and `[2.0.0]: ...releases/tag/v2.0.0` (593) — there is NO `[3.0.0]` link target. The publish gate `header="## [${RELEASE_VERSION}]"; if ! grep -F -- "$header" CHANGELOG.md` (BL-41, publish_on_pypi.yml:97-98) only checks the header STRING exists — the empty `## [3.0.0]` header satisfies it, so the gate gives false confidence that the changelog was consolidated.

**Why it matters**

The 3.0.0 release on PyPI ships with an empty changelog section while a full release's worth of breaking changes (token-transport flip, PaginationError taxonomy, dropped RuntimeError inheritance) is filed under a header labelled 2.0.0 and dated identically to the real 2.0.0. Consumers reading the canonical Changelog URL cannot tell what changed in 3.0.0, and the BL-41 gate meant to catch exactly this skipped-consolidation case does not, because it tests header presence rather than non-empty content.

**Recommendation**

Consolidate the v3 content under `## [3.0.0]`: delete the empty stub at line 6 and rename line 8's `## [2.0.0] - 2026-05-02` to `## [3.0.0] - 2026-05-02` (the genuine 2.0.0 release stays at line 536, `## [2.0.0] - 2026-04-20`). Add a `[3.0.0]: https://github.com/joshuasundance-swca/restgdf/releases/tag/v3.0.0` link reference and bump `[Unreleased]` to compare `v3.0.0...HEAD`. Re-add a fresh empty `## [Unreleased]` section at the top so the documented PR workflow ("add a bullet under `## [Unreleased]`", CONTRIBUTING.md:47) still has a target — the current file has no Unreleased section, only the link ref, which is its own minor drift. Strengthen the BL-41 gate (publish_on_pypi.yml:97-98) to assert the matched section contains at least one non-blank, non-header line before the next `## [` (e.g. `awk` between the header and the next `## [` and grep for a non-empty line) rather than testing header presence; the current `grep -F -- "## [3.0.0]"` matches the empty stub and gives false confidence. NOTE on scope/anti-rec: this is a docs/packaging-hygiene fix with zero code impact — `docs/changelog.md` just `{include}`s CHANGELOG.md verbatim, so editing headers/link-refs cannot break the Sphinx build or any runtime contract. The actual v3 breaking-change content is already present in the file and MIGRATION.md remains the authoritative breaking-changes reference, so this corrects presentation, not behavior. Don't gold-plate the gate into rejecting legitimately content-light patch releases — "at least one content line" is the right bar, not a minimum-bullet count.

**Fix touches:** `CHANGELOG.md`, `.github/workflows/publish_on_pypi.yml`

---

### PACKAGING-02 · SECURITY.md Supported Versions table omits 3.x while the package is at 3.0.0

**Severity:** medium · **Effort:** S · **Location:** `SECURITY.md:5-12, pyproject.toml:14`

**Evidence**

SECURITY.md:5 states "Only the latest minor release line of `restgdf` receives security updates." and the table lists only `| 2.x | :white_check_mark: |`, `| 1.x | :x: |`, `| < 1.0 | :x: |` (lines 9-11). pyproject.toml:14 is `version = "3.0.0"`. There is no 3.x row, so per the table's own rule the supported line (2.x) is NOT the latest release line.

**Why it matters**

A vulnerability reporter consulting the public security policy is told 2.x is supported and 3.x is unlisted/unsupported — the opposite of reality. They may file against the wrong major, expect a patch for 2.x, or conclude the current release is out of support. For a Production/Stable PyPI package this is a public-trust and triage-correctness defect in the one document explicitly governing vuln intake.

**Recommendation**

Sound and safe (doc-only edit, no code/import-boundary impact). Update the table to add `| 3.x | :white_check_mark: |` and demote 2.x to `:x:` (or document the real support window if 2.x is still patched). Better still, make the policy self-maintaining instead of version-pinned: replace the table's hard-coded rows with a rule like "the current major release line (currently 3.x) receives security updates" so it can't silently rot on the next bump. Add a SECURITY.md-review line to the release gate (CONTRIBUTING.md:88-96 has gates 1-7 but none touches SECURITY.md). Note: bumpver file_patterns (pyproject.toml:127-133) only stamp version strings in pyproject/__init__/CITATION.cff, so wiring the X.x table into bumpver is awkward (it uses MAJOR.MINOR.PATCH literal substitution, not an "X.x" major token) — prefer a checklist item or a wording change over trying to auto-stamp the table.

**Fix touches:** `SECURITY.md`

---

### PACKAGING-03 · ARCHITECTURE.md and CONTRIBUTING.md describe `restgdf[dev]` as including twine/build, but the dev extra ships neither

**Severity:** low · **Effort:** S · **Location:** `ARCHITECTURE.md:177, CONTRIBUTING.md:52-53, pyproject.toml:87-98`

**Evidence**

ARCHITECTURE.md:177 documents the matrix as `restgdf[dev]  # + pytest, pre-commit, sphinx, twine, build`. CONTRIBUTING.md:52-53 instructs `python -m build && python -m twine check --strict dist/*` as a contributor step. But the `dev` extra in pyproject.toml:87-98 lists only `aioresponses, bumpver, coverage, hypothesis, opentelemetry-instrumentation-aiohttp-client, opentelemetry-sdk, pre-commit, pytest, pytest-asyncio, setuptools` — no `twine`, no `build`, and no `sphinx` (sphinx is in the separate `doc` extra at 100-108).

**Why it matters**

A contributor following the documented `pip install -e ".[dev]"` then running the CONTRIBUTING-prescribed `python -m build && twine check` gets `No module named build` / `twine`. The doc asserts a contract the extra does not satisfy. Minor because CI installs build/twine explicitly, so it only bites local contributors.

**Recommendation**

Fix the documentation/implementation divergence. Two sound, non-breaking options: (1) Make the `dev` extra deliver what the docs promise — add `build` and `twine`, and pull in the doc tooling either by adding `sphinx` or, cleaner, by having `dev` compose `restgdf[doc]` (e.g. include `"restgdf[doc]"` in `dev`) so `doc` remains the single source of truth for the sphinx pins and the `dev`/`doc` split stops being redundant. (2) Leave the extras as-is and correct the prose: change ARCHITECTURE.md:177 to drop `sphinx, twine, build` (or note they're installed separately), and adjust CONTRIBUTING.md:30/109 to stop claiming `.[dev]` covers docs/packaging, plus add `doc` and `build twine` to the Quick Start (line 26) so a contributor who follows it can actually run gates 4 and 7. Either is safe for the light-core import boundary — build/twine/sphinx are dev-only tools never imported by `restgdf` runtime, so no shipped-wheel or import-boundary impact. Do NOT add these to a runtime/core dependency list or to a shipped extra (geo/resilience/telemetry); they belong only in the dev/contributor surface.

**Fix touches:** `pyproject.toml`, `ARCHITECTURE.md`, `CONTRIBUTING.md`

---

## Minor notes (not adversarially verified)

These were flagged by the axis auditor but did NOT go through per-finding verification — treat as leads, not confirmed findings.

- **CITATION.cff date-released (2026-05-03) disagrees with CHANGELOG 3.0.0 date (2026-05-02)** — CITATION.cff:16 `date-released: "2026-05-03"` vs CHANGELOG.md:6 `## [3.0.0] - 2026-05-02`. The bumpver hook (scripts/bumpver_stamp_date.py) stamps CITATION at bump time but the CHANGELOG date is hand-edited (BL-41), so the two date sources drift by a day as seen here. Low impact (cosmetic citation metadata); a maintainer may want a single source of truth. Could not confirm which is canonical without the tag commit date.
- **bumpver file_patterns do not stamp CHANGELOG, leaving release-notes consolidation entirely manual** — `tool.bumpver.file_patterns` (pyproject.toml:127-133) stamps pyproject, `__init__`, and CITATION.cff, plus a pre_commit_hook for CITATION date — but nothing touches CHANGELOG.md. The `## [Unreleased]` -> `## [X.Y.Z] - <date>` promotion is a documented manual BL-41 step (publish_on_pypi.yml:93-96). The botched 3.0.0 promotion is the realized cost of this gap. Consider a bumpver hook that renames the Unreleased header so it can't be skipped.
- **verify_attestation.yml comments its setup-python SHA as v6.0.0 while pytest/publish comment the identical SHA as v6.2.0** — verify_attestation.yml:46 `actions/setup-python@a309ff8...# v6.0.0` vs pytest.yml:33 and publish_on_pypi.yml:44 which pin the same SHA `a309ff8...` commented `# v6.2.0`. Same SHA, conflicting human-readable version tag — a comment-drift hygiene nit that confuses dependabot/audit review of pinned actions. Partly CICD-owned; noted only for the version-metadata consistency angle.
- **MIGRATION.md lists 2.x resilience pins (stamina>=24.2, aiolimiter>=1.1) that disagree with pyproject (stamina>=25.1.0, aiolimiter>=1.2.1)** — MIGRATION.md:317 documents the resilience extra as `stamina>=24.2`, `aiolimiter>=1.1`; pyproject.toml:77-80 ships `stamina>=25.1.0`, `aiolimiter>=1.2.1`. Doc drift in the historical 2.0 migration section — low impact since it's retrospective, but a reader sizing the extra gets stale floors.
