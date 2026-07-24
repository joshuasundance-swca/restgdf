# Executive summary

> Read-only audit of `restgdf` v3.0.0 at commit `4673b08`, 2026-06-13. 61 confirmed findings
> (5 high · 20 medium · 36 low; 0 critical). Full methodology and index in [README](README.md).

## Verdict

**restgdf is a well-engineered, disciplined library** — the audit's strongest signal is how
much it *refuted*. The light-core import boundary genuinely holds (base install pulls no
pandas/geopandas/OTel anywhere, backed by dedicated guarded-import tests); the public surface is
a clean PEP-562 lazy namespace with a tested graceful-removal path; credential material is
`SecretStr` end-to-end and scrubbed from the library's own logs and spans; the pagination
*planner* is byte-exact with hostile-input rejection; the exception MRO and back-compat patch
seams are pinned by tests; and the release plumbing uses OIDC Trusted Publishing + PEP 740
attestations + Sigstore signing. None of the 89 candidate findings was critical, and 29% were
refuted on inspection.

**The risk is not crashes — it is quiet contract-falseness.** The recurring shape across the
high- and medium-severity findings is *the library accepts/validates/documents something, then
silently doesn't do it*: configured knobs that are never read, documented exceptions that are
never raised, a flagship method that silently returns incomplete data, and CI/doc gates that
pass without enforcing what they claim. For a Production/Stable library these are arguably worse
than loud bugs, because consumers build on guarantees that don't hold and get no error.

## The 5 high-severity findings

| ID | Finding | Effort |
|----|---------|--------|
| [`AUTH-01`](02-auth-and-secrets.md) | A caller token passed via the documented `FeatureLayer(token=...)` / `data={"token":...}` path is serialized into the **GET URL query string** on short requests (the leak guard only inspects the *session's* transport, not the body) — landing live tokens in server/proxy/WAF access logs. | S |
| [`PAGINATION-01`](01-pagination-streaming.md) | The flagship `get_gdf()` (and `stream_gdf_chunks`) read pages via `get_sub_gdf`, which **never checks `exceededTransferLimit`** — a byte/geometry-size-capped page is silently concatenated and a GeoDataFrame **missing rows** is returned with no error or warning. | M |
| [`PAGINATION-02`](01-pagination-streaming.md) | Offset/count pagination is issued with **no `orderByFields`**; ArcGIS does not guarantee stable cross-request ordering, so rows can be silently **duplicated or dropped** across concurrently-fetched pages. | M |
| [`CONFIG-01`](03-configuration.md) | `TransportConfig.user_agent` / `verify_ssl` are validated and env-settable but **never read by any request path** — `verify_ssl=False` (load-bearing for self-signed ArcGIS Enterprise) is a silent no-op. | M |
| [`CICD-01`](04-cicd-supply-chain.md) | There is **no test gate between a tag push / `workflow_dispatch` and the PyPI publish** (`pytest.yml` is `pull_request`-only; the publish job runs only build + `twine check`). A tag push can ship an untested, immutable wheel. | M |

All five were re-verified against the code by the coordinator. Severities held at high; two were
downgraded from the auditor's initial *critical* because each is conditional (the recommended
`ArcGISTokenSession` header path avoids the leak; the silent truncation triggers on the byte/
geometry cap rather than every call).

## Systemic themes (where the leverage is)

1. **Advertised configuration that does nothing** *(the dominant pattern — `CONFIG-01/02/03/04`,
   `AUTH-04`, `TRANSPORT-01`, `DOCS-02`).* `TransportConfig` (UA/verify_ssl), the *entire*
   `AuthConfig`, `RetryConfig`/`LimiterConfig`, two documented `Config` precedence layers
   (`.env`, explicit instance), and four env vars in `configuration.rst` are validated/documented
   but never wired to the code they claim to govern. A consumer tuning these gets a silent no-op.
   **One coherent workstream** (wire the consumed-vs-dead sub-configs, or remove + document the
   gaps) closes most of this.

2. **Silent data loss / duplication in the geo & pagination paths** *(`PAGINATION-01/02`,
   `ASYNC-02`, `ADAPTERS-01/03`).* The flagship `get_gdf()` can silently truncate, paginate
   unstably, hand the same cached frame to concurrent callers by reference, or `KeyError` on
   permissive metadata. This is the highest-stakes cluster for data correctness.

3. **False error/exception contracts** *(`ERRTAX-01/02/03`, `AUTH-02`).* Documented, exported
   exceptions (`InvalidCredentialsError`, `TokenRequiredError`) are never raised; a
   `/generateToken` 4xx escapes the `RestgdfError` umbrella as a raw `aiohttp` error; and the
   `OSError` co-inheritance lets the retry filter swallow a deterministic auth failure. Callers'
   `except` clauses silently never fire.

4. **Gates that don't guard what they claim** *(`CICD-01/02/04`, `TESTS-01`, `TYPING-01`).* The
   release path has no test gate, the mypy CI gate runs with no dependencies installed (masking
   6 real type errors in the *shipped* inline types), and the coverage floor never blocks a PR.
   The protections look stronger than they are.

5. **Docs drifted past the 3.0 release, and they feed LLMs** *(`DOCS-01..12`, `PACKAGING-01/02`).*
   CHANGELOG `[3.0.0]` is empty, MIGRATION/README are 2.0-framed, SECURITY.md omits 3.x, and
   ARCHITECTURE.md asserts three things the code contradicts (`ErrorPayload`, the logger names,
   `FeatureLayer.close()`). These are published to readthedocs **and** `llms.txt`, so they
   mislead human and AI consumers alike.

## Priorities (by risk-reduction per effort)

1. **`AUTH-01`** (high / **S**) — real credential exposure, trivial fix (force POST when the body
   carries a `token`). Highest leverage on the board.
2. **`PAGINATION-01`** (high / M) — detect `exceededTransferLimit` in `get_sub_gdf` and raise by
   default, matching the raw-feature engine. Stops silent data loss on the headline method.
3. **`CONFIG-01`** (high / M) — wire `verify_ssl`/`user_agent` at the library-owned session
   seams (not per-request), unblocking on-prem Enterprise users.
4. **`CICD-01`** (high / M) — gate the release path on `pytest -m "not network"` (reuse the
   existing matrix via `workflow_call`); confirm whether the `release` environment already
   requires a reviewer.
5. **`PAGINATION-02`** (high / M) — default `orderByFields` to the resolved OID on multi-page
   plans, degrading gracefully if the OID can't be resolved.
6. **Theme 1 cleanup** (mostly M) — reconcile every advertised config knob: wire it or remove +
   document it. This single decision resolves ~7 findings.

## Quick wins (S effort, high clarity)

`AUTH-01` (token-in-URL) · `API-02` (add `FieldDoesNotExistError` to the `TYPE_CHECKING` block) ·
`PACKAGING-02` (add a 3.x row to SECURITY.md) · `TESTS-03` (drop the stale `restgdf/app.py`
coverage omit) · `CICD-04/05/06` (PR coverage note, pin the release-token action SHAs, fix the
setup-python pin comment) · most of `DOCS-05..12` (each is a localized prose/example fix). A
half-day pass clears roughly a third of the board and most of the public-facing embarrassments.

---

## Read-only proof

`git status --porcelain` immediately **before** the audit agents ran:

```
?? CLAUDE.md
```

`git status --porcelain` **after** the full report set was written:

```
?? CLAUDE.md
?? audit-recommendations/
```

`HEAD` was `4673b08f8fe47f5cac43e99ba59edc8dabc1d63a` before and after. The only delta is the
creation of `audit-recommendations/`; no tracked source file was created, modified, or deleted.
(`CLAUDE.md` is a separate, earlier deliverable, not part of this audit. The audit's analysis
agents — recon, auditors, verifiers, critic — had an explicit read-only mandate; only the
report-rendering writers wrote files, all inside `audit-recommendations/`.)

*Findings explicitly refuted during verification (26 of 89 candidates) were excluded from this
report set.*
