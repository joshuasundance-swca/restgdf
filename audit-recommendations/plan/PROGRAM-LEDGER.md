# Program state ledger — audit remediation

> Extracted from `07-execution-runbook.md` (2026-07-22) so phase-state updates have a durable
> home independent of the runbook's own PR lifecycle. Until the audit PR merges, update this
> file on the audit branch (P0B/P0C branches cut from `origin/main` cannot carry it); after the
> audit PR merges, update it in the same PR that changes a phase state. A phase is complete only
> when its exit evidence is linked or recorded.

| Phase | State | Exit evidence |
|------|-------|---------------|
| P0A Preserve the plan | main merged back; completes when PR #190 merges (this row rides in it) | audit branch published and audit PR merged |
| P0B Raise Python floor to 3.11 + repair fresh CI | **COMPLETE** (PR #191 → `0fa0332`, squash) | 3.11+ metadata/docs and 3.11–3.14 offline aggregate green |
| P0C Reconcile open PRs | 9 open (2026-07-22) | each PR merged, superseded, refreshed, or deliberately deferred |
| P0D Turn CI into policy | not started | offline aggregate required on `main`; `release` env reviewer set; ruleset exported |
| V0 Establish baseline | not started | fresh main clone passes the complete gate |
| M1 Validation/security | not started | M1 exit gate plus 3.1.0 release evidence |
| M2 High correctness | not started | all five high findings closed with regression evidence |
| M3 Medium correctness | not started | M3 item/decision gates green |
| M4 Docs/polish | not started | 61/61 findings closed or explicitly dispositioned |
| R32 Release 3.2.0 | not started | clean tag-to-PyPI-to-install verification |

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
