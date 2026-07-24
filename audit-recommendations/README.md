# restgdf — comprehensive code audit

> **REMEDIATION COMPLETE (2026-07-24).** All 61 findings are terminally dispositioned —
> 59 landed, 1 decision-closed, 1 deferred with owner+trigger, 0 gaps (re-derive any time
> with `python scripts/audit_disposition.py`). Delivered across releases **3.1.0** and
> **3.2.0**; the authoritative phase record is [`plan/PROGRAM-LEDGER.md`](plan/PROGRAM-LEDGER.md).
> Finding line numbers below remain pinned to the audit commit and are historical.
>
> **Read-only audit.** No source file was modified to produce this report set. Pinned to
> commit `4673b08` (`main`, v3.0.0). Generated 2026-06-13.

This directory is a multi-axis, adversarially-verified audit of [`restgdf`](https://github.com/joshuasundance-swca/restgdf),
a public OSS async Esri/ArcGIS REST client published to PyPI. Each finding cited a code
location and then survived an independent skeptical re-check against the code; findings that
did not hold were discarded and are not published.

## How to read this

- **[`00-executive-summary.md`](00-executive-summary.md)** — start here: the verdict, the
  systemic themes, and a priority-ordered shortlist.
- **`NN-<axis>.md`** — one report per axis, each with an Assessment (what is good first), a
  findings-at-a-glance table, and a detailed entry per finding (Evidence / Why it matters /
  Recommendation).
- **[`findings.json`](findings.json)** — the machine-readable index (one entry per finding:
  `id, axis, title, severity, effort, governance, location, files`). This is the contract a
  remediation plan consumes; **re-verify cited line numbers before acting — they are
  perishable, the claims are not.**
- **[`plan/07-execution-runbook.md`](plan/07-execution-runbook.md)** — the durable operational
  sequence: current-state prerequisites, safe parallel lanes, gates, rollback rules, releases,
  and the bootstrap procedure for a fresh session.

Finding IDs are axis-prefixed and stable (e.g. `AUTH-01`). Severities reflect the verifier's
calibrated value, which sometimes differs from the auditor's initial grade.

## Severity & effort legend (calibrated for a public, pip-installed library)

| Severity | Meaning |
|----------|---------|
| **critical** | Silent data loss/corruption returned to the caller; credential leak to logs/URL/network; remote-exploitable; or a public API that silently does the wrong thing. |
| **high** | Silent wrong results in a common path; a documented contract callers rely on that is false; a security weakness under specific conditions; or a release/supply-chain gap that could ship broken/insecure artifacts. |
| **medium** | Correctness/robustness issue in a less-common path; an API/typing inconsistency hurting DX; or a bug that bites under concurrency/edge inputs. |
| **low** | Minor inconsistency, hygiene, or doc drift with low user impact. |

| Effort | Meaning |
|--------|---------|
| **S** | Localized, < ~1h. |
| **M** | A few files, needs tests. |
| **L** | Cross-cutting / design change / migration. |

## Index

61 confirmed findings: **5 high · 20 medium · 36 low** (0 critical).

| # | Axis report | Published | High | Notable |
|---|-------------|-----------|------|---------|
| 01 | [Pagination & streaming](01-pagination-streaming.md) | 3 | 2 | `get_gdf` silently drops rows; offset paging without `orderByFields` |
| 02 | [Auth & secrets](02-auth-and-secrets.md) | 4 | 1 | token leaks into URL query string on `token=` path |
| 03 | [Configuration](03-configuration.md) | 4 | 1 | `TransportConfig.user_agent`/`verify_ssl` are silent no-ops |
| 04 | [CI/CD & supply chain](04-cicd-supply-chain.md) | 6 | 1 | no test gate between tag push and PyPI publish |
| 05 | [Error taxonomy](05-error-taxonomy.md) | 4 | 0 | documented exceptions that are never raised |
| 06 | [Async & concurrency](06-async-concurrency.md) | 3 | 0 | reactive 498 double-refresh; cached frames shared by reference |
| 07 | [Transport & resilience](07-transport-resilience.md) | 2 | 0 | GET/POST bool/None coercion divergence; `RetryConfig` inert |
| 08 | [Output adapters](08-output-adapters.md) | 3 | 0 | `resolve_domains` silent dtype-mismatch; self-contradicting geo docstrings |
| 09 | [Public API surface](09-public-api-surface.md) | 4 | 0 | stats calls clobbered by instance datadict; surface-sync drift |
| 10 | [Typing & py.typed](10-typing.md) | 5 | 0 | mypy CI gate is defanged, masking 6 real type errors |
| 11 | [Telemetry & logging](11-telemetry-logging.md) | 3 | 0 | log-correlation recipe errors outside a span; drift dedup masks services |
| 12 | [Optional deps & extras](12-optional-deps-extras.md) | 2 | 0 | `require_*` misses broken-but-present deps; no `restgdf[pandas]` extra |
| 13 | [Test suite & gates](13-test-suite.md) | 3 | 0 | coverage floor never gates a PR; characterization tests defanged |
| 14 | [Packaging & release](14-packaging-release.md) | 3 | 0 | SECURITY.md omits 3.x; CHANGELOG 3.0.0 mis-promoted |
| 15 | [Docs accuracy](15-docs-accuracy.md) | 12 | 0 | config docs invent unwired env vars; ARCHITECTURE.md code-contradicting claims |

## Methodology

**Pipeline (all analysis agents were read-only):**

1. **Recon** — 6 parallel readers mapped the subsystems and surfaced file-cited *hypotheses*.
2. **Audit** — 15 axis auditors, each given its axis scope plus the recon hypotheses as
   *unverified leads to confirm/refute/extend* (not rubber-stamp). Cap 15 findings/axis.
3. **Verify** — one independent skeptical verifier per finding (105 agents total across the
   audit phase), each instructed to **refute by default** and to attack the recommendation as
   well as the claim. A finding survived only if the verifier confirmed it against the code.
4. **Completeness critic** — one agent hunting for what the per-axis auditors missed; its
   candidates were verified the same way and routed to their best-fit axis.
5. **Coordinator** — re-verified **every high-severity finding** against the code first-hand,
   assigned stable IDs, consolidated 2 exact cross-axis duplicates, and authored this index +
   the executive summary. Per-axis report bodies were rendered mechanically from the
   verified-and-finalized finding records (no agent could invent, drop, or re-grade a finding).

**Counts:** 89 candidate findings were raised (83 by axis auditors + 6 by the critic).
**26 were refuted (29%)** during verification and are not published. **63 were confirmed**;
2 exact cross-axis duplicates were consolidated, leaving **61 published**. Every candidate
received a verdict — **0 were left unverified**. Refutation was healthy on the high-density
correctness axes (ERRTAX 4/8 refuted, TRANSPORT 3/5, TYPING 3/8) and zero on axes where the
leads were already concrete (AUTH 0/5, DOCS 0/12).

**The most valuable negative results** (suspected issues the verifiers *refuted*): the
`_REMOVED_EXPORTS` graceful-removal path is wired **and** tested (not dead code); the
credential-leak verb guard is safe under **both** session-wrapping orders; the `_service_root`
rate-limit truncation handles the embedded-"FeatureServer" substring trap; `build_pagination_plan`
tail math is byte-exact with NaN/inf/bool rejection; base-install import safety is complete
across every reachable module; and `compat.as_dict`'s snake_case choice is a documented
decision, not a bug.

**Not covered / limits of this audit:**

- **No code was executed against live ArcGIS services** — runtime behavior against real
  servers (e.g. the exact `exceededTransferLimit` trigger conditions) is reasoned from code,
  not observed. The `-m network` test tier was not run.
- **Line numbers are pinned to `4673b08` and are perishable** — re-verify before editing.
- **Severity is calibrated for a library consumer**, not an internal deployment; there is no
  end-user UI or server surface to assess.
- **No governance flag** is applied — restgdf has PR review + CODEOWNERS but no formal
  change-approval process, so none was invented.
- Cross-axis overlaps (e.g. the empty CHANGELOG `[3.0.0]` surfaces under CI/CD, Packaging, and
  Docs as distinct lenses) are **kept as separate findings on purpose**; a remediation plan
  consolidates them via its finding→work-item map.

## Read-only proof

The repository working tree was snapshotted (`git status --porcelain`) immediately before the
audit agents ran (`?? CLAUDE.md`) and again after this report set was written
(`?? CLAUDE.md` + `?? audit-recommendations/`). `HEAD` was `4673b08` throughout. The only delta
is the creation of this `audit-recommendations/` directory; no tracked source file was created,
modified, or deleted. The exact snapshots are in the
[executive-summary footer](00-executive-summary.md#read-only-proof).
