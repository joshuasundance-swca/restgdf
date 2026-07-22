# 07 — Remediation execution runbook

> **Operational source of truth for executing the audit remediation.** Snapshot reconciled
> 2026-07-22 against local Git, GitHub PRs/checks, the 61-finding audit, all six workstream
> specifications, `CONTRIBUTING.md`, `pyproject.toml`, pre-commit, and every workflow. The
> finding claims remain pinned to `4673b08`; re-verify them against the current tree before
> changing code.

## Verdict

Do not start the 55 audit work items directly. First raise the supported floor from end-of-life
Python 3.9 to Python 3.10, restore a trustworthy fresh-dependency CI baseline, dispose of the
existing human PR before it collides with auth/pagination work, preserve and merge the audit
artifacts, and make the aggregate CI job required. Then execute M1–M4 through three independent
writer lanes plus one integration coordinator, with the full gate at every PR head and milestone
boundary. Release 3.1.0 after M1 because the Python floor change does not belong in a patch;
release 3.2.0 after the behavior-heavy work and documentation reconciliation.

This runbook adds orchestration and present-day state to the item-level specifications. It does
not replace their behavioral acceptance criteria.

## Authority and conflict rules

Use this precedence in a fresh session:

1. live Git/GitHub state and observable code/test behavior;
2. repository policy (`AGENTS.md`, `CONTRIBUTING.md`, `pyproject.toml`, workflows);
3. this execution runbook for sequencing, integration, and current-state decisions;
4. `00-master-plan.md` and workstream files `01`–`06` for item-level scope and acceptance;
5. `99-traceability.md` and `findings.json` for completeness counts;
6. `checkpoint.local.md`, which is a disposable recall hint, never evidence.

When sources disagree, stop that item, record the discrepancy in its PR, test the real behavior,
and update the durable source that was wrong. Never silently choose the more convenient claim.

## Reconciled starting state (2026-07-22)

- `origin/main` and local `main`: `4673b08` (v3.0.0).
- Current clean local branch: `audit/comprehensive-review-2026-06`, four local commits ahead of
  `main`, no upstream. It contains the audit/plan plus agent and tooling documentation.
- Audit scope: 61 confirmed findings = 5 high + 20 medium + 36 low; 55 work items across six
  collision-domain workstreams; zero findings unassigned in the traceability ledger.
- GitHub: 9 open PRs, 0 open issues. PR #175 is the only human feature PR. PRs #176, #178, and
  #184–#189 are Dependabot work; #188 is a broad grouped Python update and #189 an Actions group.
- Current fresh CI is not trustworthy-green. Python 3.10–3.14 jobs fail four tests while Python
  3.9 passes. The observed failure is `aioresponses 0.7.8` constructing an aiohttp response
  without the newer `stream_writer` argument. Local `.venv` is Python 3.11 and its offline suite
  passed 1,163 tests with 4 skipped and 2 deselected, but that installed environment is older
  than fresh resolution. It is corroborating evidence, not the baseline.
- Local pre-commit previously exceeded a 244-second command limit. That is **UNVERIFIED**, not a
  failure and not a pass. Re-run it with an adequate timeout and retained log.
- No release is allowed until `W1-1` test-gates publishing and the full release candidate gate is
  green.
- Maintainer decision (2026-07-22): Python 3.9 support ends now. It reached upstream end-of-life
  on 2025-10-31 and no longer receives security updates (official
  [Python 3.9.25 release notice](https://www.python.org/downloads/release/python-3925/)). Set
  `requires-python = ">=3.10"` and test 3.10–3.14. Do not silently drop 3.10 while upstream still
  supports it; schedule a support-floor review before Python 3.10's upstream end-of-life.

Re-run the inventory commands below at the start of every phase. Counts above are a dated
snapshot, not an evergreen claim.

```powershell
git status --short --branch
git fetch --prune origin
git rev-parse HEAD
git rev-parse origin/main
git log --oneline --decorate --graph -12
gh pr list --state open --limit 100
gh issue list --state open --limit 100
gh run list --limit 20
```

Fetching is read-only. Pushing, opening/closing/merging PRs, changing repository settings, and
publishing releases remain permission-gated outward actions.

## Program state ledger

Update this table in the same PR that changes a phase state. A phase is complete only when its
exit evidence is linked or recorded in the commit/PR.

| Phase | Initial state | Exit evidence |
|------|---------------|---------------|
| P0A Preserve the plan | local-only | audit branch published and audit PR merged |
| P0B Raise Python floor and repair fresh CI | blocked/red | 3.10+ metadata/docs and 3.10–3.14 aggregate `ci` green |
| P0C Reconcile open PRs | 9 open | each PR merged, superseded, refreshed, or deliberately deferred |
| V0 Establish baseline | not started | fresh main clone passes the complete gate |
| M1 Validation/security | not started | M1 exit gate plus 3.1.0 release evidence |
| M2 High correctness | not started | all five high findings closed with regression evidence |
| M3 Medium correctness | not started | M3 item/decision gates green |
| M4 Docs/polish | not started | 61/61 findings closed or explicitly dispositioned |
| R32 Release 3.2.0 | not started | clean tag-to-PyPI-to-install verification |

## Phase P0 — make the work safe to begin

### P0A · Preserve and land the audit plan

1. Commit this runbook and its consistency corrections locally on
   `audit/comprehensive-review-2026-06` after the documentation checks below pass.
2. With explicit permission, push the branch and open an audit-only PR. Do not mix runtime fixes
   into it. Expect fresh CI to expose the current dependency/test-double failure.
3. Land P0B on a new branch from `origin/main`; do not repair CI on the audit branch.
4. Rebase the audit branch onto the repaired `main`, re-run its gate, and merge the audit PR.
5. Preserve both local and remote branches until the audit PR is merged and its commit is on
   `main`. Never delete the only copy of planning history.

### P0B · Raise the Python floor and repair fresh-dependency CI (`W0`, prerequisite work)

This is a newly discovered prerequisite, not one of the original 55 items. It combines an explicit
maintainer support-policy decision with the CI repair that decision simplifies. Treat the test
fixture as the first suspect; do not infer a runtime incompatibility from a mocked-response
constructor.

1. From current `origin/main`, create `build/drop-py39-and-fix-fresh-ci`.
2. Make the support-floor change as one reviewable commit:
   - set `requires-python = ">=3.10"`, remove the 3.9 classifier, and change tool targets from
     `py39` to `py310` where they describe generated/accepted syntax;
   - remove Python 3.9 from every CI matrix and add/retain 3.10–3.14 explicitly;
   - update README, quickstart, architecture/contribution claims, CHANGELOG `Unreleased`, and
     MIGRATION with the exact floor and the upstream-EOL rationale;
   - inspect and remove only compatibility code proven unreachable on 3.10+ (notably the Python
     3.9 `contextlib.aclosing` fallback), with tests proving the supported path;
   - build wheel/sdist and assert their `Requires-Python` metadata is `>=3.10`; prove installation
     rejection on 3.9 from the built artifact if a 3.9 interpreter is available.
3. In repo-local `scratch/`, create clean environments for every available supported interpreter.
   Record interpreter version, `pip freeze`, and `pip check`. Never mutate `.venv` for this probe.
4. Reproduce the four failing tests under the same unconstrained install used by CI. Retain raw
   output and exact resolved versions. A parser summary is not sufficient evidence.
5. Test the smallest candidate matrix:
   - Python 3.10–3.14 with `aioresponses 0.7.9` and current `aiohttp`;
   - the exact four failures first, then their full modules, then offline pytest.
6. Select the remedy from evidence, in this order:
   - prefer a compatible test dependency release; `aioresponses 0.7.9` is now admissible because
     it shares the new Python >=3.10 floor;
   - otherwise add the smallest local test-double adaptation or a **dev/test-only** compatible
     bound with an expiry comment and tracking issue;
   - do not add a runtime-core `aiohttp` upper bound unless real client behavior also fails and a
     supported upstream range requires it.
7. Add a regression that exercises the real fixture path responsible for the failure. Verify the
   guard fires through the consumer path, not by directly constructing an internal marker.
8. Run the full local gate and the hosted Python 3.10–3.14 matrix. Merge only when the aggregate
   `ci` check is green. Capture exact test counts per interpreter with a script.

If the first candidate fails, that is useful evidence, not a reason to weaken the matrix. Record
the attempted versions and raw exception before choosing the fallback.

### P0C · Reconcile the existing PR queue

Never treat May/June green checks as current. Every surviving PR must be updated onto CI-repaired
`main` and rerun.

1. Review #175 first. It changes spatial-filter geometry behavior and overlaps the auth,
   `getgdf`, and pagination collision domains. Rebase it, inspect all behavior and test changes,
   run the complete gate, then either merge it **before W2/W4 begins** or explicitly close/defer
   it. Leaving it open while those workstreams proceed creates avoidable semantic and merge risk.
2. After #175's disposition, re-verify affected audit line references and acceptance tests. The
   finding IDs stay stable; locations may move.
3. Refresh grouped Python PR #188 after P0B. Compare its dependency set mechanically with #176,
   #178, and #184–#187. Prefer one reviewed grouped update; close individual PRs as superseded
   only after the replacement has merged. Do not merge a stale green individual merely to reduce
   the count.
4. Refresh Actions group #189 separately. Review permissions, action SHAs/tags, and workflow
   behavior; dependency green does not prove supply-chain intent.
5. For every PR, record one of: merged commit, superseding PR, deferred reason/owner/date, or
   closed reason. The exit condition is a fully explained queue, not necessarily zero PRs.

### P0D · Turn CI into policy

After the repaired aggregate job exists and has succeeded on `main`, request/obtain permission to:

- require the aggregate `ci` status on `main`;
- require one approval and dismissal of stale approvals (recommended for a public library);
- apply the rule to administrators unless the repository has a documented emergency exception;
- add an environment reviewer to the release environment;
- prohibit a release while required checks are pending or red.

Export or screenshot the resulting ruleset. A workflow named `ci` is not a gate until GitHub
actually requires it.

## Phase V0 — establish the baseline oracle

Start from a fresh clone/worktree of repaired `main`, not from the long-lived `.venv`. Install the
documented full extras, record resolved dependencies, and run every gate. Do not begin M1 while
V0 is red or unverified.

```powershell
.\.venv\Scripts\python.exe -m pytest -q -m "not network"
.\.venv\Scripts\python.exe -m coverage run -m pytest -q -m "not network"
.\.venv\Scripts\python.exe -m coverage report --fail-under=97
.\.venv\Scripts\python.exe -m pre_commit run --all-files
.\.venv\Scripts\python.exe -m sphinx -n -W --keep-going -b html docs docs/_build/html
.\.venv\Scripts\python.exe -m pytest -q tests/test_base_install.py
.\.venv\Scripts\python.exe -m pytest -q tests/test_compat.py
.\.venv\Scripts\python.exe -m build
.\.venv\Scripts\python.exe -m twine check --strict dist/*
```

Also verify that the pre-commit command actually invokes ruff, mypy, black, bandit, gitleaks,
typos, and actionlint. Retain long output under ignored `scratch/gates/<sha>/`; a timeout or crash
is UNVERIFIED. Run network/stress tiers only under their documented opt-in flags, record the run
ID, monitor to completion, and never leave them silently running.

## Parallel execution model

Use at most four active roles: one integration coordinator and three writer lanes. Parallelism is
by disjoint file set, not by topic. Future agent delegation requires explicit user permission;
this layout remains valid for humans or sequential sessions.

- **Coordinator:** owns branch inventory, collision reservations, central gate, traceability
  counts, checkpoint, and merges. It does not edit a file reserved by a writer.
- **Lane A — CI/tooling:** `.github/**`, `pyproject.toml`, pre-commit/tool config. One writer.
- **Lane B — auth/config:** token transport, `_http`, config, and their tests. One writer because
  the seams are tightly coupled.
- **Lane C — pagination/surface/docs:** only one hot-file sublane at a time; disjoint docs may run
  while code is active. `getgdf.py`, `featurelayer.py`, and public-export files each have a single
  owner until their PR merges.

Before starting an item, reserve its files in `checkpoint.local.md`. If two items need the same
file, dependency order wins; do not rely on later conflict resolution to reconcile behavior.
Lane-local tests are provisional because sibling work may change integration behavior. Run the
full gate once centrally after all selected lane heads are integrated.

### Branch and commit contract

- Branch every item or tightly coupled stack from the latest green `origin/main`.
- Keep PRs small enough to revert independently; stack only when a gate cannot sensibly become
  required before its known failures are repaired.
- For behavior changes, commit the failing regression first, confirm it fails for the intended
  reason, then commit the minimum fix. The red and green commits travel in the same PR; never
  merge the red commit alone. The targeted red command is expected to fail, while every PR head
  and every merge commit must pass the full gate.
- Add a CHANGELOG bullet under `Unreleased` for runtime-visible behavior in the same PR.
- Commit subjects are Conventional Commits, imperative, <=72 characters. Never bypass hooks.
- Push/open/merge remains permission-gated. No force-push; update branches with ordinary rebase
  only before publication, or merge `main` afterward if collaborators may rely on the history.

## Milestone execution graph

The item specifications remain in files `01`–`06`. The sequences below override only their
integration order where present-day dependencies make that necessary.

### M1 · Validation spine, security fix, and release truth

Run these lanes concurrently only when their file reservations do not overlap:

- Lane A serial spine: `W1-1 -> W1-4 -> W1-3 -> W1-7`; `W1-5` and `W1-6` may be separate
  disjoint reviews. Implement `W1-8` as fail-fast-only unless new evidence justifies auto-format.
- Lane B: `W2-1` (AUTH-01) red-first. This is the highest-priority runtime fix.
- Lane C quick wins: `W3-7`, `W6-1`, then `W6-2` after `W1-3` defines the truthful coverage
  behavior.

`W1-2` (real mypy) is a transition stack, not a knowingly red standalone merge. First capture
the six real type failures. Repair its coupled items (`W4-6`, `W5-9`, `W5-10`, `W5-11`) on a
coordinated integration branch or ordered stack, then make the strict gate required in the final
PR. Each repair gets targeted tests/type evidence; the stack head gets the complete gate.

Pull the historical 3.0.0 correction and a valid nonempty `Unreleased` section from `W6-5`
forward into 3.1.0 release preparation. A release validator cannot truthfully bless the currently
empty 3.0.0 narrative.

M1 exits only when W1-1/W1-2/W1-3 are real and green, AUTH-01 is fixed, the full local/hosted gate
is green, and required-check configuration is verified. At that point release **3.1.0** with the
Python >=3.10 floor, security fix, CI/release safeguards, corrected release metadata, and explicit
migration notice. Do not label this 3.0.1: raising `Requires-Python` is a compatibility-policy
change and must not be hidden in a patch. Do not pull unfinished M2 behavior into this release.

### M2 · All remaining high-severity correctness

After #175 is resolved and the typing transition lands:

- Config/auth lane: `W3-1 -> W2-10`; then prove `verify_ssl=False` and user-agent propagation
  through the real request consumer. `W2-7` and `W2-8` may run in parallel if disjoint.
- Pagination lane, serial in `getgdf.py`: `W4-6 -> W4-5 -> W4-1 -> W4-2`. For W4-1, test
  excluded/truncated rows through the real GeoDataFrame path and raise `PaginationError`.
- Surface/adapters lane: `W5-1`, `W5-4`, and `W5-12` may be separate disjoint PRs; `W5-8` follows
  the extras decision. The typing fixes already landed in M1's transition stack.
- Config/docs lane: `W3-5` records the `.env` doc-down decision in M2; `W3-6` follows the actual
  config shape. `W6-3` waits until M3 to finalize all architecture decisions.

M2 exits only when all five high findings are closed with regressions and the verify-SSL chain
(`W3-1`, `W2-10`, `W4-5`) is observed end to end.

### M3 · Medium correctness and explicit design decisions

- Auth/error lane: `W2-2 -> W2-3`; make the `W2-5` cross-layer exception decision before code;
  then `W2-11`. For inert retry/limiter/auth-refresh knobs, warn now (`W2-13`) and schedule real
  wiring separately rather than silently preserving false config.
- Config lane: `W3-2 -> W3-3 -> W3-4`. Adopt the already recommended opt-in
  `ArcGISTokenSession.from_config` hybrid. Document down nonexistent explicit-`Config` and `.env`
  precedence unless a separately scoped feature is approved.
- Pagination lane: `W4-3`; `W4-4` remains documentation/design-only until an implementation is
  justified.
- Surface lane: `W5-2 -> W5-3`; then `W5-6`, `W5-13`, and `W5-14`. W5-3 exposes exactly the two
  audited stats methods. W5-13 adds context to emitted messages but not to the dedup key. Under
  the doc-down config decision, close W5-14 as an evidenced no-op.
- Documentation lane: finalize `W6-3` only after the config/auth/session decisions above land.

Every decision-only close requires a durable rationale and proof that docs/code no longer promise
the rejected behavior. “Deferred” without an owner and trigger is not closed.

### M4 · Low-severity polish and narrative reconciliation

Disjoint doc files can proceed in parallel after their code dependencies land:

- `W6-4` MIGRATION, `W6-5` CHANGELOG remainder, `W6-6` README, and `W6-7` reference docs;
- `W2-9` exception naming/docs cleanup;
- `W5-5` adapter docstrings and remaining low surface work.

Run a terminology and link scan across README, ARCHITECTURE, CONTRIBUTING, MIGRATION, CHANGELOG,
SECURITY, and Sphinx docs. Code is the source of truth. M4 exits only after a script reports
61/61 findings with a terminal disposition and zero orphan work items, and the complete gate is
green from a fresh environment.

## Release 3.2.0

Cut only from a clean, protected `main` after M4. If the project chooses to release the whole
program only once instead of shipping 3.1.0 after M1, this becomes 3.1.0; never publish an empty
version solely to preserve the numbering in this document.

1. verify version, nonempty changelog section, migration notes, and supported-version policy;
2. run the full gate from the exact release commit and record counts/artifact hashes;
3. build once, `twine check --strict`, inspect wheel/sdist contents, and publish those exact bits;
4. require the release environment approval and green test-gated publish workflow;
5. verify GitHub release, PyPI metadata/provenance, and installation/import in a clean environment;
6. record rollback guidance. Published artifacts are immutable—fix forward with a new version,
   never replace a release file.

## Evidence packet required for every PR

Include:

- base/head SHAs and the work/finding IDs;
- files reserved and collision check;
- re-verification of the cited real producer/consumer path;
- exact red command and raw failure reason (behavior changes);
- exact green commands, mechanically captured counts, and environment versions;
- full-gate results at PR head, including what each wrapper actually invoked;
- public API, compatibility, optional-dependency, docs, and CHANGELOG impact;
- risk, rollback/revert boundary, and any remaining unknown;
- hosted check links and required-check state.

Use scripts for counts. Never hand-count tests, findings, PRs, or terminal dispositions.

## Recovery and stop rules

- Preserve user/agent artifacts; archive curated state before deletion. Revert a bad commit rather
  than rewriting shared history.
- If a check crashes or times out, mark it UNVERIFIED and retain output. Fix the probe before
  judging the subject.
- If baseline or central integration turns red, stop new merges, identify the first bad commit,
  and revert or repair within that collision domain. Other read-only review may continue.
- Stop for maintainer direction before an API-breaking choice, runtime dependency ceiling,
  outward GitHub change, release, or expansion beyond the audited scope.
- Security regressions, credential exposure, silent data loss, required-check removal, or coverage
  below 97% are hard stops.

## Fresh-session bootstrap

A new session should do exactly this before implementation:

1. Read `AGENTS.md`/repo instructions, this file in full, then `00-master-plan.md`, the relevant
   workstream file, and `99-traceability.md` in full.
2. Read `checkpoint.local.md` if present, then distrust and reconcile it with Git/disk/GitHub.
3. Run the inventory commands under “Reconciled starting state”; update this runbook snapshot or
   ledger when durable state has changed.
4. Confirm current phase, predecessor exit evidence, open collision reservations, and required
   permissions. Do not skip P0/V0 because a local venv happens to be green.
5. Branch from latest green `origin/main`, re-verify the finding's real path and item acceptance
   criteria, and write the red test before behavior code.
6. Keep `checkpoint.local.md` at <=40 lines and overwrite it at each merge/milestone with: date,
   branch/SHA, phase/item, verified gates, open reservations, exact blocker, and next safe command.
7. End only with a completed outcome or a precise blocker. Update the program ledger and
   traceability status in the same durable change that establishes the evidence.

## Known plan discrepancies resolved here

- `99-traceability.md` previously labeled W6-3 M2 while the master plan and W6 specification moved
  it to M3. M3 is authoritative because architecture prose depends on M3 config/auth decisions.
- W3-5's **decision and code/config truth** occur in M2; W6-3's final architecture prose occurs in
  M3. This resolves the apparent M2/M3 conflict without delaying the source-of-truth decision.
- `05-featurelayer-adapters-surface.md` had an empty decision section. Its defaults are now
  explicit there and in M3 above.
- Red-first and green-commit requirements are reconciled by keeping red+green commits in one PR:
  the targeted red commit demonstrates the net; the PR head and every merge remain fully green.
- Python support policy is now explicit: drop 3.9 in P0B because upstream ended support on
  2025-10-31; retain 3.10 until a separately recorded review changes the floor. This supersedes
  every older plan sentence that assumes Python >=3.9.
