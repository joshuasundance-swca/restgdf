# Program state ledger — audit remediation

> Extracted from `07-execution-runbook.md` (2026-07-22) so phase-state updates have a durable
> home independent of the runbook's own PR lifecycle. Until the audit PR merges, update this
> file on the audit branch (P0B/P0C branches cut from `origin/main` cannot carry it); after the
> audit PR merges, update it in the same PR that changes a phase state. A phase is complete only
> when its exit evidence is linked or recorded.

| Phase | State | Exit evidence |
|------|-------|---------------|
| P0A Preserve the plan | published; PR #190 open (sanctioned red-at-open) | audit branch published and audit PR merged |
| P0B Raise Python floor to 3.11 + repair fresh CI | blocked/red | 3.11+ metadata/docs and 3.11–3.14 offline aggregate green |
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
