# Program state ledger — audit remediation

> Extracted from `07-execution-runbook.md` (2026-07-22) so phase-state updates have a durable
> home independent of the runbook's own PR lifecycle. Until the audit PR merges, update this
> file on the audit branch (P0B/P0C branches cut from `origin/main` cannot carry it); after the
> audit PR merges, update it in the same PR that changes a phase state. A phase is complete only
> when its exit evidence is linked or recorded.

| Phase | State | Exit evidence |
|------|-------|---------------|
| P0A Preserve the plan | **COMPLETE** (PR #190 merged → `70ebe00`, 125 checks green) | audit branch published and audit PR merged |
| P0B Raise Python floor to 3.11 + repair fresh CI | **COMPLETE** (PR #191 → `0fa0332`, squash) | 3.11+ metadata/docs and 3.11–3.14 offline aggregate green |
| P0C Reconcile open PRs | **COMPLETE** 2026-07-24: #175 merged (`4633288`, post-review docs); #189 merged (supply-chain verified); #188→recreated #192 merged (`1bbfd23`, +2 maintainer fixes: lockfile consistency, docs nitpick-ignore; closes all 34 Dependabot alerts); singles #176/#178/#184–#187 closed superseded | each PR merged, superseded, refreshed, or deliberately deferred |
| P0D Turn CI into policy | **COMPLETE** 2026-07-23: `ci-offline` required on `main` (enforce_admins=false, no approval rule — solo-repo decision); `release` env reviewer = joshuasundance-swca; exports in git-excluded `scratch/p0d/*.json` | offline aggregate required on `main`; `release` env reviewer set; ruleset exported |
| V0 Establish baseline | **COMPLETE** 2026-07-23 (fresh clone @ `70ebe00` + fresh 3.11 venv: all gates green — pytest 1169/4/2, cov 98%, 34/34 hooks, sphinx, base_install 15, compat 50, build+twine; report `scratch/v0/`) | fresh main clone passes the complete gate |
| M1 Validation/security | **COMPLETE** 2026-07-24 (items: PRs #193 #194 #195 #196 #197 #198 #199 #200 — see log; 3.1.0 release evidence added on publish) | M1 exit gate plus 3.1.0 release evidence |
| M2 High correctness | **COMPLETE** 2026-07-24 (PRs #203–#207 + this PR; all five high findings closed with regression evidence — verifier-run census: AUTH-01 ×3, PAGINATION-01 ×7, PAGINATION-02 ×4, CONFIG-01/AUTH-03 ×8 test nodes green; CICD-01 = the structural release gate. verify_ssl proven end-to-end via real-connector introspection) | all five high findings closed with regression evidence |
| M3 Medium correctness | **COMPLETE** 2026-07-24 (3 batched PRs; W2-2/3/11, W3-2/3/4, W2-13 warn-now, W4-3/4, W1-9, W5-2/3/6/13/14; decision-closes with recorded owner+trigger: W2-5 NO-GO per plan recommendation, W5-13 dedup-key kept context-free per anti-spam decision; wave verifier CONFIRMED, deferral ratified by coordinator) | M3 item/decision gates green |
| M4 Docs/polish | **COMPLETE** 2026-07-24 (PRs #212 docs reconciliation [V-M4 CONFIRMED, 21 claims sampled clean] + #213/#214 census oracle; definitive census on main: **61 findings = 59 LANDED / 1 DECISION-CLOSED [DOCS-02 via W3-6 confirm-only] / 1 DEFERRED [ERRTAX-03, owner+trigger] / 0 GAP / 0 ORPHAN**, `scripts/audit_disposition.py` exit 0) | 61/61 findings closed or explicitly dispositioned |
| R32 Release 3.2.0 | **COMPLETE** 2026-07-24: tag `3.2.0` (bump `93625fe`), PyPI wheel+sdist confirmed via the JSON API, PEP 740 attestation-verify run 30102287027 SUCCESS (green on rerun after the known ~1-3 min index-propagation race), GitHub release published, clean-env `pip install restgdf==3.2.0` imports 3.2.0 | clean tag-to-PyPI-to-install verification |

## Log

- 2026-07-22 — Runbook committed (`95f402b`), then amended after a 5-lane adversarial validation
  (95 claims: 50 confirmed / 15 refuted / 25 adjusted / 5 unverified). Floor decision revised to
  Python >=3.11 (3.9 EOL 2025-10-31; 3.10 EOL 2026-10-31). No phase has started; nothing pushed.
- 2026-07-23 — **P0B complete.** PR #191 squash-merged to `main` as `0fa0332`: floor >=3.11
  (commit-level gate evidence in the PR body), aioresponses/aiohttp-3.14 `stream_writer` conftest
  shim + real-consumer-path regression (fresh resolution = aiohttp 3.14.3; matrix 3.11–3.14 each
  1169 passed/4 skipped/2 deselected in clean envs), `ci-offline` aggregate job added. Full PR CI
  green including advisory network/stress. 3 default-refute verifiers: CONFIRMED ×3, 0 mustFix.
  P0A: audit branch published as PR #190 (sanctioned red-at-open), repaired `main` merged back
  clean (zero conflicts). #175 adversarially reviewed (MERGE_WITH_CHANGES, 0 blocking —
  scratch/p0b/reports/pr175-review.md): P0C will carry CHANGELOG/MIGRATION bullets in the rebase;
  query-time Referer propagation noted for W2-10 (M2).
- 2026-07-24 — **P0C, P0D, V0, M1 complete; 3.1.0 release prepped.** M1 delivery (every
  substantive PR adversarially verified, default-refute): #193 quick wins (W1-5 W1-6 W3-7 W5-7
  W6-1) · #194 release-path test gate + CHANGELOG gate (W1-1 inline shape, W1-4; CONFIRMED 0
  mustFix) · #195 AUTH-01 red-first fix (W2-1; CONFIRMED 0 mustFix; 2-assertion characterization
  re-pin adjudicated, W1-9 owns full verb-separation in M3) · #196 W1-2 typing transition stack
  (deps-present mypy 16→0 errors, W4-6/W5-9/W5-10/W5-11 pulled forward; mypy job required via
  both aggregators; CONFIRMED 0 mustFix; W5-9 resolved via audit fallback — current aiohttp
  stubs preclude a static Protocol match) · #197 W1-8 bumpver fail-fast (CONFIRMED 0 mustFix) ·
  #198 3.0.0 narrative + 2.0.0 header dedupe + CLAUDE.md refresh (ADJUSTED, 2 mustFix applied) ·
  #199 W1-8b: coordinator-discovered release-gate deadlock (W1-8×W1-4 could never both pass —
  bumpver doesn't rewrite CHANGELOG); guard now asserts the just-bumped version's own section ·
  #200 W1-3 PR coverage gate + W1-7 + W6-2/PACKAGING-03; and the P0 finding that main's true
  coverage had been 96.9069% (sub-floor since #175, 7 silent post-merge failures — TESTS-01
  validated live) restored to **98.1271%** with real-shape `_geometry.py` tests (73.78%→100%,
  fixtures verified against the ArcGIS REST spec). Suite at M1 exit: 1213 passed / 4 skipped /
  4 deselected. Maintainer review items: #192 Snyk check red (auth-walled detail; pip-audit
  clean); referer query-time `Referer` header gap → W2-10; POST bool-coercion parity +
  FakeSession verb-mirror → W1-9.
- 2026-07-24 — **Census self-contamination, 3rd recurrence — structural fix, not another
  patch.** The fresh-env gate's definitive re-run of `scripts/audit_disposition.py` against
  merged `main` caught AUTH-01/PAGINATION-03 mislabeled DEFERRED again: PR #214's own squash
  commit (`05d3e34`) narrates the prior fix's bug history in its body using the trigger
  vocabulary ("owner"+"trigger"/"NO-GO"/"deferred") next to real item IDs, and its diff touches
  `findings.json`/`99-traceability.md` (files that same PR legitimately edited), so neither the
  dev-tooling-subject exclusion (recurrence 1, genesis commit `e65bf75`) nor the diff-confinement
  exclusion (recurrence 2, PR #213 squash `701ddbf`) covered it. Code-level truth independently
  re-verified: both items are genuinely landed; this was oracle-only. Fix (coordinator decision —
  no more whack-a-mole): removed free-text commit-body narration as deferral evidence ENTIRELY.
  Deferred and decision-closed dispositions now come from exactly one source, the curated
  "## Deliberate deferrals" section of `99-traceability.md` (`parse_deliberate_deferrals_
  section`) — the same durable record already used for decision-close. Commit scanning remains
  for LANDED evidence only (subject/bullet citations + file corroboration), unchanged. Dead
  prose-signal machinery (`build_prose_signals`, `is_dev_tooling_commit`,
  `is_self_referential_commit`, `paragraphs`) deleted along with its tests rather than stranded;
  a new regression fixture (a commit narrating the exact bug class, item IDs + trigger phrases +
  a diff touching the real audit-recommendations files) asserts zero deferral signal, proving no
  commit body can trigger this again by construction. Re-verified on this tree: **61 findings =
  59 LANDED / 1 DECISION-CLOSED [DOCS-02 via W3-6 confirm-only] / 1 DEFERRED [ERRTAX-03] / 0 GAP
  / 0 ORPHAN**, exit 0. Full offline suite green (1348 passed / 4 skipped / 4 deselected),
  targeted `test_audit_disposition.py` green (35 tests), pre-commit clean at a fixed point.
- 2026-07-24 — **PROGRAM COMPLETE.** All phases exited: P0A–P0D, V0, M1–M4, releases 3.1.0
  and 3.2.0 both live and verified. Definitive census on final `main`: 61 findings =
  59 LANDED / 1 DECISION-CLOSED / 1 DEFERRED (ERRTAX-03, owner+trigger) / 0 GAP / 0 ORPHAN.
  Remaining watch items (maintainer): #192 Snyk check detail (auth-walled; pip-audit clean);
  one unreproduced 45-min hosted `pytest (py3.13)` hang (add a `faulthandler_timeout` probe
  if it recurs); the warn-now inert retry/limiter knobs (TRANSPORT-01/W2-13) await their
  separately-scoped wiring design; ERRTAX-03 re-opens on its recorded trigger.
