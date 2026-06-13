> **13 — Test-suite quality, coverage & warning gates** · restgdf audit · **read-only** · no code was modified
> Commit `4673b08` · 2026-06-13 · Index: [README](README.md) · Machine-readable: [findings.json](findings.json)

## Assessment

The suite is genuinely strong in breadth and discipline: ~111 files, `--strict-markers` + `asyncio_mode=strict`, a real public-API surface contract (`test_public_api.py` / `test_compat.py` enumerate every `__all__` name and patch target), dedicated isolated tests for the credential-leak verb routing (`test_gate3_fixes.py` uses per-verb mock counters and asserts `get.await_count == 0`, refuting the seed that `FakeSession` masks it), and a true verb pin in `test_choose_verb_live.py` with a recording session. The deprecation contract is exercised explicitly via `pytest.warns` throughout. The main risks are in the GATES rather than the tests themselves: (1) the `fail_under=97` coverage floor is enforced ONLY in a post-merge push-to-main job, never on a PR, so a coverage regression cannot block a merge; (2) the `filterwarnings` "deprecation escalation" gate cannot match restgdf's own deprecations in the common call path because they are emitted with `stacklevel=2/3` and attribute to the caller's module; and (3) the unified `FakeSession` quietly converts a set of "characterization" tests into verb-agnostic mirrors that can no longer detect a GET/POST flip or a `data`↔`params` interface regression — directly undercutting those tests' stated purpose. Net posture: low risk of shipping broken code (the functional suite is thorough and the verb behavior is pinned elsewhere), but the coverage/warning/characterization gates are weaker than they appear and could let a regression through unnoticed.

## Findings at a glance

| ID | Finding | Severity | Effort |
|----|---------|----------|--------|
| `TESTS-01` | Coverage floor (fail_under=97) is never a PR gate — only a post-merge job on main enforces it | low | M |
| `TESTS-02` | Unified FakeSession turns verb-pinning characterization tests into verb-agnostic mirrors | low | M |
| `TESTS-03` | coverage omit references a nonexistent file restgdf/app.py | low | S |

## Findings

### TESTS-01 · Coverage floor (fail_under=97) is never a PR gate — only a post-merge job on main enforces it

**Severity:** low · **Effort:** M · **Location:** `.github/workflows/pytest.yml:62, .github/workflows/coverage.yml:3-5,34-44, pyproject.toml:147,173`

**Evidence**

The only PR test job runs `python -m pytest -q -m "not network"` (`pytest.yml:62`) with NO coverage measurement. The coverage job is gated `on: push: branches: ["main"]` (`coverage.yml:3-5`) and runs `coverage run` / `coverage report` only AFTER merge, then auto-commits `COVERAGE.md` via `git-auto-commit-action` (`coverage.yml:45-48`). `pre-commit` has no coverage hook either. So `fail_under = 97` (`pyproject.toml:147`) and `ignore_errors = true` (`pyproject.toml:173`) can only fail a build on main, post-merge — a PR that drops coverage below 97% (e.g. by deleting a test or adding an untested branch) merges green, and the post-merge job then either fails on main (noisy, after the fact) or silently rewrites `COVERAGE.md` to the lower number.

**Why it matters**

The documented 97% coverage contract is decorative for the actual merge decision. A reviewer trusting "CI green" on a PR gets no coverage signal; regressions in test coverage land on main before anyone is alerted, and the auto-commit can quietly ratchet the recorded number down without a human noticing.

**Recommendation**

Reconcile the docs-vs-CI divergence rather than treating this as a pure CI gap. Two coherent options: (A) make the floor a real PR gate, or (B) fix the docs to stop overclaiming. Recommended fix (A): add a single dedicated PR coverage job (NOT a coverage step inside the existing `test` matrix — running `coverage report --fail-under=97` across all six 3.9-3.14 matrix legs is wasteful and risks spurious floor failures since branch counts can differ by interpreter). Mirror `coverage.yml`'s environment (Python 3.14 + `.[dev,geo,resilience,telemetry]`), run `coverage run && coverage report --fail-under=97`, and add that job to the `ci` aggregate's `needs:` list (`pytest.yml:184`) so branch protection's single `ci` required check actually blocks merges below 97%. Keep `coverage.yml` on main solely for badge/`COVERAGE.md` regeneration. Also update `CONTRIBUTING.md` line 98 ("CI will re-run the same gates") which is currently false for gate #2. NOTE the evidence's "silently rewrites `COVERAGE.md` to the lower number" claim is NOT accurate and should be dropped: in `coverage.yml` the `coverage report -m --precision=2` at line 39 runs BEFORE the `COVERAGE.md` write (line 40) and the `git-auto-commit` step (45-48); under GitHub Actions' default `set -e`, a sub-97% run fails line 39 and aborts the job, so the lowered `COVERAGE.md` is never committed — post-merge the main job fails loudly, not silently. So the auto-commit "ratchet-down" anti-recommendation is already moot.

**Fix touches:** `.github/workflows/pytest.yml`, `.github/workflows/coverage.yml`, `pyproject.toml`

---

### TESTS-02 · Unified FakeSession turns verb-pinning characterization tests into verb-agnostic mirrors

**Severity:** low · **Effort:** M · **Location:** `tests/conftest.py:142-163, tests/test_characterization.py:35-59,107-128, restgdf/utils/_query.py:44, restgdf/utils/_http.py:117-123`

**Evidence**

`FakeSession` aliases `post_responses`/`get_responses` and `post_calls`/`get_calls` onto single shared lists (`conftest.py:142-147`) and `_snapshot_kwargs` mirrors the body under both `data` and `params` (`conftest.py:160-162`). `test_characterization.py:35` `test_get_feature_count_sends_minimal_count_payload` asserts `len(fake_session.post_calls) == 1` and reads `kwargs["data"]`, but `get_feature_count` routes through `_arcgis_request` (`_query.py:44`) which for a short body calls `session.get(url, params=...)` (`_http.py:119-122`) — the real call is a GET recording `params`, and `kwargs["data"]` only resolves because of the mirror. `test_choose_verb_live.py` independently proves this exact call is GET (`verbs == ["GET"]`, reads `kwargs["params"]`).

**Why it matters**

These tests are marked `characterization` ('pin current behavior to guard refactors', module docstring 'assert on concrete, observable behavior... guarded against silent regressions') yet can no longer detect a GET↔POST verb flip or a `data`↔`params` interface change — the very behavior T8/R-74 changed. If a future refactor stopped sending the body under the verb-appropriate key, or flipped a verb incorrectly, these named-for-POST tests would still pass via the alias/mirror. The genuine verb pin survives only in `test_choose_verb_live.py`; the characterization layer is misleading.

**Recommendation**

Accept the finding but treat it as test-clarity, not safety: the verb/key dimension is already comprehensively pinned for the exact same functions in `tests/test_choose_verb_live.py` (`get_feature_count` short-where -> `verbs==["GET"]`, `kwargs["params"]`; long-where -> POST, `kwargs["data"]`; plus `get_object_ids`, `get_unique_values`, `_get_sub_features`, `_fetch_page_dict`). So the characterization layer's mirror only removes a *redundant* second guard, not the only one. Prefer the cheaper of the two offered fixes: rename the affected characterization tests so the name no longer implies POST (e.g. `*_sends_minimal_count_payload` -> `*_count_query_payload`), and assert on the verb-correct key (read `kwargs["params"]` for the GET helpers: count/object_ids/uniquevalues/valuecounts; keep `kwargs["data"]` only for genuinely-POST cases). These tests already carry honest `# T8 (R-74): short count queries ride on GET` comments, so they are not silently misleading today — the rename just removes the misnomer. If instead you split `FakeSession` back into separate `post_*`/`get_*` lists and drop the `_snapshot_kwargs` `data`<->`params` mirror (option 1), scope it carefully: per commit `3b94983` the same `.get` delegator + body-mirror pattern was also added to the legacy compat fakes (`MockFeatureLayerSession`, `RecordingSession`, `JsonSession`), so a desync there would break `tests/test_compat.py` — do NOT remove the mirror from the compat fakes without auditing each compat assertion. All changes are test-only and touch no public API, light-core import boundary, or documented runtime contract.

**Fix touches:** `tests/conftest.py`, `tests/test_characterization.py`

---

### TESTS-03 · coverage omit references a nonexistent file restgdf/app.py

**Severity:** low · **Effort:** S · **Location:** `pyproject.toml:138`

**Evidence**

`[tool.coverage.run] omit = ["*tests/*.py", "restgdf/app.py"]` (`pyproject.toml:138`). `ls restgdf/app.py` and a package-wide `find restgdf -name app.py` both return nothing — the file does not exist anywhere in the package.

**Why it matters**

Dead config. Harmless today, but it masks intent: if a real `restgdf/app.py` is ever added it would be silently excluded from coverage, and the stale entry suggests the omit list isn't reviewed. No current data-loss/correctness impact.

**Recommendation**

Delete the `"restgdf/app.py"` entry from the coverage omit list at `pyproject.toml:138`, leaving `omit = ["*tests/*.py"]`. Keep the `"*tests/*.py"` glob intact — it is load-bearing (excludes test files from coverage). The change is config-only with zero behavioral/import-boundary risk; it touches neither source, branch, nor `fail_under`. Safe to bundle with any other trivial config cleanup.

**Fix touches:** `pyproject.toml`

---

## Minor notes (not adversarially verified)

These were flagged by the axis auditor but did NOT go through per-finding verification — treat as leads, not confirmed findings.

- **Seed refuted: FakeSession does NOT mask the credential-leak verb tests** — The H1/Gate-3 token-leak tests in `tests/test_gate3_fixes.py:44-235` use their own `_FakeAuthSession` / `SimpleNamespace` doubles with separate `get` and `post` `AsyncMock`s and assert `session.get.await_count == 0` / `session.post.await_count == 1`. They never use the unified conftest `FakeSession`, so the `data`/`params` mirror cannot mask the 'token must not land in URL query' assertion. The credential-safety verb behavior is correctly and independently pinned.
- **Live-network coverage is exactly two tests** — Only `tests/test_Directory.py:11` (`test_directory`) and `tests/test_FeatureLayer.py:723` (`test_featurelayer`) carry `@pytest.mark.network`. The `pytest-network` CI job (`pytest.yml:123-138`) therefore exercises just two live integration paths against real ArcGIS endpoints. Adequate as a smoke check but thin if treated as integration coverage; this appears deliberate (network tests are opt-in via `--run-network`) so not flagged as a finding.
- **Stress/property tests are a single-file scaffold** — Only `tests/test_hypothesis_responses.py` is `@pytest.mark.stress`, and it's the only file importing `hypothesis` (verified repo-wide). Its docstring calls itself a 'BL-39 scaffold... Expand with additional strategies'. The marker correctly keeps hypothesis out of the default suite (no flake/slowdown leakage), but the property-based surface is currently minimal relative to the normalization/pagination logic that would benefit from it.
- **Manual event-loop construction in deprecation tests** — `tests/test_deprecations.py:111-188,216-328` repeatedly does `loop = asyncio.new_event_loop()` / `loop.run_until_complete(...)` / `loop.close()` in `finally` blocks instead of using the `pytest-asyncio` fixture used elsewhere (`@pytest.mark.asyncio`). It works, but it bypasses the suite's `asyncio_mode = strict` loop management and is more fragile (a raised assertion before `loop.close()` leaks a loop). Hygiene only.
- **COVERAGE.md is a generated artifact committed to the repo and can drift** — `COVERAGE.md` is regenerated and auto-committed by the post-merge coverage job (`coverage.yml:40,45-48`). It is current as of the v3.0.0 cycle (git log shows it updated 2026-05-03, same day as the version bump). Because it is only regenerated on main pushes that touch the matched paths, it can lag reality between releases; treat it as informational, not authoritative, when auditing coverage.
