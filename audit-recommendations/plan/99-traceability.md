# 99 — Traceability

> Bidirectional finding↔work-item map for the restgdf remediation plan · audit pinned `4673b08` · 2026-06-13. This is the anti-silent-drop ledger: **every** one of the 61 confirmed audit findings maps to at least one work item, and every work item traces back to a finding.

## Coverage summary

**61 / 61 findings allocated** to 55 work items across 6 workstreams. 0 findings deferred or dropped.

| Axis | Findings | Allocated | Work items covering them |
|------|----------|-----------|--------------------------|
| PAGINATION | 3 | 3/3 | W4-1, W4-2, W4-3, W6-6, W6-7 |
| AUTH | 4 | 4/4 | W2-1, W2-10, W2-11, W2-2, W3-1, W3-2, W4-5, W6-3, W6-4, W6-6 |
| CONFIG | 4 | 4/4 | W2-10, W2-11, W3-1, W3-3, W3-4, W3-5, W4-5, W5-14, W6-3, W6-4, W6-6 |
| CICD | 6 | 6/6 | W1-1, W1-3, W1-4, W1-5, W1-6, W1-8, W6-2, W6-5 |
| ERRTAX | 4 | 4/4 | W2-2, W2-3, W2-5, W2-9, W6-4, W6-5 |
| ASYNC | 3 | 3/3 | W2-4, W4-4, W5-1 |
| TRANSPORT | 2 | 2/2 | W2-13, W2-7 |
| ADAPTERS | 3 | 3/3 | W5-4, W5-5, W5-6 |
| API | 4 | 4/4 | W5-2, W5-3, W5-7, W5-8 |
| TYPING | 5 | 5/5 | W1-2, W4-6, W5-10, W5-11, W5-9 |
| TELEMETRY | 3 | 3/3 | W2-6, W5-12, W5-13, W6-4, W6-7 |
| OPTDEPS | 2 | 2/2 | W2-8, W6-4 |
| TESTS | 3 | 3/3 | W1-3, W1-7, W1-9 |
| PACKAGING | 3 | 3/3 | W6-1, W6-2, W6-3, W6-5 |
| DOCS | 12 | 12/12 | W3-6, W3-7, W6-1, W6-2, W6-3, W6-4, W6-5, W6-6, W6-7 |

## Forward map — finding → work item(s)

Findings mapped to more than one item are **split-ownership**: each owning item must state which part it owns (verified by the traceability critic).

| Finding | Sev | Title | Work item(s) | Split? |
|---------|-----|-------|--------------|--------|
| `PAGINATION-01` | high | GeoDataFrame path (get_gdf / stream_gdf_chunks) silently drops rows on exceededTransferL… | `W4-1`, `W6-6`, `W6-7` | **yes** |
| `PAGINATION-02` | high | Offset/count pagination issued without orderByFields — unstable ordering can silently du… | `W4-2` | — |
| `PAGINATION-03` | low | on_truncation='split' builds unbounded nested OID IN-lists, making it unusable on large … | `W4-3` | — |
| `AUTH-01` | high | Caller-supplied token leaks into URL query string on the documented FeatureLayer(token=.… | `W2-1`, `W6-6` | **yes** |
| `AUTH-02` | medium | InvalidCredentialsError and TokenRequiredError are documented HTTP-401/499 contracts but… | `W2-2`, `W6-3`, `W6-4` | **yes** |
| `AUTH-03` | medium | verify_ssl is honored only for the token POST, not for data requests — contradicts the M… | `W2-10`, `W3-1`, `W4-5`, `W6-4` | **yes** |
| `AUTH-04` | low | AuthConfig's three refresh-threshold knobs are dead config — never read by the token-ref… | `W2-11`, `W3-2`, `W6-4` | **yes** |
| `CONFIG-01` | high | TransportConfig.user_agent / verify_ssl are validated and env-settable but never applied… | `W2-10`, `W3-1`, `W4-5` | **yes** |
| `CONFIG-02` | medium | AuthConfig is never wired into token sessions — its env vars and the whole sub-config ar… | `W2-11`, `W3-3`, `W5-14`, `W6-4`, `W6-6` | **yes** |
| `CONFIG-03` | low | Documented Config precedence layer 'Config(...) instance passed explicitly' has no imple… | `W3-4`, `W5-14`, `W6-3` | **yes** |
| `CONFIG-04` | low | Documented Config precedence layer '.env file in the working directory' is never loaded | `W3-5`, `W6-3` | **yes** |
| `CICD-01` | high | No CI test gate between tag push / workflow_dispatch and PyPI publish | `W1-1` | — |
| `CICD-02` | medium | CHANGELOG release gate passes on an empty section — 3.0.0 shipped with zero documented c… | `W1-4`, `W6-5` | **yes** |
| `CICD-03` | low | bumpver release path is workflow_dispatch-only and CHANGELOG-blind, so the BL-41 publish… | `W1-8`, `W6-5` | **yes** |
| `CICD-04` | low | 97% coverage floor is enforced only post-merge; PR gate measures no coverage, contradict… | `W1-3`, `W6-2` | **yes** |
| `CICD-05` | low | Release-adjacent write-token workflows use unpinned mutable action tags while PR workflo… | `W1-5` | — |
| `CICD-06` | low | verify_attestation.yml setup-python pin comment drift (# v6.0.0 on a v6.2.0 SHA) | `W1-6` | — |
| `ERRTAX-01` | medium | A 400/401 from /generateToken escapes the RestgdfError umbrella as a raw aiohttp.ClientR… | `W2-2` | — |
| `ERRTAX-02` | medium | AuthenticationError (and RestgdfTimeoutError) co-inherit OSError, so token retry's excep… | `W2-3` | — |
| `ERRTAX-03` | low | 498/499 auth conditions are detected only by HTTP status code, not by the in-body ArcGIS… | `W2-5` | — |
| `ERRTAX-04` | low | Documented 'will be dropped in 3.1+' ValueError co-inheritance is a semver-breaking chan… | `W2-9`, `W6-4`, `W6-5` | **yes** |
| `ASYNC-01` | medium | Reactive 498 refresh fires a redundant /generateToken per concurrent requester, breaking… | `W2-4` | — |
| `ASYNC-02` | medium | Cached DataFrame/GeoDataFrame returned by reference to every (possibly concurrent) caller… | `W5-1` | — |
| `ASYNC-03` | low | on_truncation='split' sub-fetches bypass the max_concurrent_pages accounting, so peak in… | `W4-4` | — |
| `TRANSPORT-01` | medium | Public RetryConfig / LimiterConfig knobs are never wired into the resilience executor; R… | `W2-13` | — |
| `TRANSPORT-02` | low | _parse_retry_after accepts NaN/Inf, leaking non-finite values into RateLimitError.retry_… | `W2-7` | — |
| `ADAPTERS-01` | medium | get_fields(types=True), _field_rows and get_fields_frame raise KeyError on permissive-ti… | `W5-4` | — |
| `ADAPTERS-02` | low | geopandas adapter docstrings name stream_rows and iter_rows as input but those rows rais… | `W5-5` | — |
| `ADAPTERS-03` | low | resolve_domains crashes on malformed-but-real domain metadata | `W5-6` | — |
| `API-01` | medium | FeatureLayer.get_value_counts / get_nested_count send returnGeometry=True and outFields=… | `W5-2` | — |
| `API-02` | low | FieldDoesNotExistError exported at runtime but absent from the TYPE_CHECKING block — `fr… | `W5-7` | — |
| `API-03` | low | No test asserts the three public-surface sources of truth stay set-equal, so the TYPE_CH… | `W5-8` | — |
| `API-04` | low | get_nested_count documents 'two or more fields' but nested_count hardcodes fields[0]/fie… | `W5-3` | — |
| `TYPING-01` | medium | CI/pre-commit mypy gate is defanged: --ignore-missing-imports + no runtime deps + no pyd… | `W1-2` | — |
| `TYPING-02` | medium | AsyncHTTPSession Protocol does not structurally match aiohttp.ClientSession; construction… | `W5-9` | — |
| `TYPING-03` | low | Genuine union-attr bug in strict-scoped _models/_drift.py masked by the gate | `W5-10` | — |
| `TYPING-04` | low | get_gdf's `session: ClientSession | None` annotation contradicts the R-71 AsyncHTTPSessi… | `W4-6` | — |
| `TYPING-05` | low | Misleading `list[FieldSpec]` annotation in _metadata._field_rows — value is actually lis… | `W5-11` | — |
| `TELEMETRY-01` | medium | Documented log-correlation recipe raises logging errors on every record emitted outside … | `W5-12`, `W6-7` | **yes** |
| `TELEMETRY-02` | low | Schema-drift dedup key excludes service context, silently masking per-service drift in m… | `W5-13`, `W6-4` | **yes** |
| `TELEMETRY-03` | low | Auth module bypasses the get_logger factory, so restgdf.auth never receives a NullHandler | `W2-6` | — |
| `OPTDEPS-01` | low | `require_*` catches only `ModuleNotFoundError`, so a broken (present-but-unimportable) g… | `W2-8` | — |
| `OPTDEPS-02` | low | MIGRATION.md documents a non-existent `extra="pandas"` on OptionalDependencyError and th… | `W6-4` | — |
| `TESTS-01` | low | Coverage floor (fail_under=97) is never a PR gate — only a post-merge job on main enforc… | `W1-3` | — |
| `TESTS-02` | low | Unified FakeSession turns verb-pinning characterization tests into verb-agnostic mirrors | `W1-9` | — |
| `TESTS-03` | low | coverage omit references a nonexistent file restgdf/app.py | `W1-7` | — |
| `PACKAGING-01` | medium | CHANGELOG 3.0.0 release was mis-promoted: empty 3.0.0 section, duplicate 2.0.0 headers, … | `W6-5` | — |
| `PACKAGING-02` | medium | SECURITY.md Supported Versions table omits 3.x while the package is at 3.0.0 | `W6-1` | — |
| `PACKAGING-03` | low | ARCHITECTURE.md and CONTRIBUTING.md describe `restgdf[dev]` as including twine/build, bu… | `W6-2`, `W6-3` | **yes** |
| `DOCS-01` | medium | Published CHANGELOG has an empty `## [3.0.0]` header and MIGRATION.md is framed entirely… | `W6-4`, `W6-5` | **yes** |
| `DOCS-02` | medium | configuration.rst documents four RESTGDF_* env vars that are not wired into Config.from_… | `W3-6`, `W6-7` | **yes** |
| `DOCS-03` | medium | ARCHITECTURE.md claims FeatureLayer/Directory own a session and expose close(); they do … | `W6-3` | — |
| `DOCS-04` | medium | configuration.rst and authentication.rst claim `.env`-file / pydantic-settings support t… | `W6-3`, `W6-7` | **yes** |
| `DOCS-05` | low | configuration.rst Config(...) example uses fields that raise (extra='forbid'/frozen) and… | `W6-7` | — |
| `DOCS-06` | low | ARCHITECTURE.md documents a structured detail type `ErrorPayload` that does not exist | `W6-3` | — |
| `DOCS-07` | low | ARCHITECTURE.md logger-hierarchy names contradict the enforced LOGGER_SUFFIXES allowlist | `W6-3` | — |
| `DOCS-08` | low | CONTRIBUTING.md targets the stale `integration/3.0-rewrite` branch and references unship… | `W6-2` | — |
| `DOCS-09` | low | docs/errors.rst documents FieldDoesNotExistError attribute as `field`; the real attribute… | `W6-7` | — |
| `DOCS-10` | low | README 2.0 collapsible and SECURITY.md supported-versions are stale for the shipped v3.0.0 | `W6-1`, `W6-6` | **yes** |
| `DOCS-11` | low | _config.py module docstring says "Seven" sub-configs; there are eight | `W3-7`, `W6-5` | **yes** |
| `DOCS-12` | low | docs/quickstart.md light-core example uses the deprecated row_dict_generator | `W6-7` | — |

## Reverse map — work item → finding(s) & milestone

| Item | WS | Milestone | Sev | Eff | Audit refs | Title |
|------|----|-----------|-----|-----|------------|-------|
| `W1-1` | W1 | M1 | high | M | `CICD-01` | Gate the release path on the test suite |
| `W1-2` | W1 | M1 | medium | M | `TYPING-01` | Un-defang the mypy gate (install runtime deps + pydantic plugin) |
| `W1-3` | W1 | M1 | low | M | `TESTS-01`, `CICD-04` | Run the coverage floor on PRs, not only post-merge |
| `W1-4` | W1 | M1 | medium | S | `CICD-02` | Reject an empty CHANGELOG section in the publish gate |
| `W1-5` | W1 | M1 | low | S | `CICD-05` | SHA-pin the release-adjacent write-token workflow actions |
| `W1-6` | W1 | M1 | low | S | `CICD-06` | Fix the verify_attestation setup-python pin comment |
| `W1-7` | W1 | M1 | low | S | `TESTS-03` | Remove the stale restgdf/app.py coverage omit |
| `W1-8` | W1 | M2 | low | M | `CICD-03` | Harden the bumpver release path (CHANGELOG-aware) |
| `W1-9` | W1 | M3 | low | M | `TESTS-02` | Restore verb separation in FakeSession / characterization tests |
| `W2-1` | W2 | M1 | high | S | `AUTH-01` | Force POST when the request body carries a token (body-aware leak gu… |
| `W2-10` | W2 | M2 | high | M | `CONFIG-01`, `AUTH-03` | Apply user_agent + verify_ssl at the token/_http request seams (veri… |
| `W2-4` | W2 | M2 | medium | S | `ASYNC-01` | Double-check token_needs_update in the reactive 498 path (single-fli… |
| `W2-6` | W2 | M2 | low | S | `TELEMETRY-03` | Route the restgdf.auth logger through the get_logger factory |
| `W2-7` | W2 | M2 | low | S | `TRANSPORT-02` | Reject NaN/Inf in _parse_retry_after |
| `W2-8` | W2 | M2 | low | S | `OPTDEPS-01` | Broaden require_* to catch broken-but-present optional deps (ImportE… |
| `W2-11` | W2 | M3 | low | M | `AUTH-04`, `CONFIG-02` | Make token sessions read the AuthConfig refresh-threshold knobs (con… |
| `W2-13` | W2 | M3 | medium | M | `TRANSPORT-01` | Wire RetryConfig/LimiterConfig into the resilience executor |
| `W2-2` | W2 | M3 | medium | M | `AUTH-02`, `ERRTAX-01` | Raise InvalidCredentialsError on /generateToken 4xx (stop raw-aiohtt… |
| `W2-3` | W2 | M3 | medium | S | `ERRTAX-02` | Stop the token retry filter from swallowing deterministic auth errors |
| `W2-5` | W2 | M3 | low | M | `ERRTAX-03` | Detect 498/499 from the in-body ArcGIS error envelope, not only HTTP… |
| `W2-9` | W2 | M4 | low | S | `ERRTAX-04` | Decide & track the ValueError co-inheritance removal (semver) |
| `W3-7` | W3 | M1 | low | S | `DOCS-11` | Fix the _config.py module docstring (Seven->eight sub-configs) |
| `W3-1` | W3 | M2 | high | M | `CONFIG-01`, `AUTH-03` | Establish the TransportConfig user_agent/verify_ssl source of truth … |
| `W3-5` | W3 | M2 | low | S | `CONFIG-04` | Implement .env loading or remove the documented layer |
| `W3-6` | W3 | M2 | medium | S | `DOCS-02` | Reconcile the 4 documented-but-unwired RESTGDF_* env vars (code part) |
| `W3-2` | W3 | M3 | low | M | `AUTH-04` | Wire or retire the AuthConfig refresh-threshold knobs (config part) |
| `W3-3` | W3 | M3 | medium | L | `CONFIG-02` | Expose AuthConfig for token-session construction (config part) |
| `W3-4` | W3 | M3 | low | M | `CONFIG-03` | Implement the documented explicit-Config-instance precedence (config… |
| `W4-1` | W4 | M2 | high | M | `PAGINATION-01` | Detect exceededTransferLimit in the GeoDataFrame path and raise |
| `W4-2` | W4 | M2 | high | M | `PAGINATION-02` | Default orderByFields to the resolved OID on multi-page plans |
| `W4-5` | W4 | M2 | high | S | `CONFIG-01`, `AUTH-03` | Build the get_gdf bare session with the configured ssl connector (ve… |
| `W4-6` | W4 | M2 | low | S | `TYPING-04` | Fix get_gdf session annotation to the AsyncHTTPSession contract |
| `W4-3` | W4 | M3 | low | M | `PAGINATION-03` | Bound the on_truncation='split' OID IN-lists & reuse the parent slice |
| `W4-4` | W4 | M3 | low | M | `ASYNC-03` | Count split sub-fetches against max_concurrent_pages |
| `W5-7` | W5 | M1 | low | S | `API-02` | Add FieldDoesNotExistError to the TYPE_CHECKING block |
| `W5-1` | W5 | M2 | medium | S | `ASYNC-02` | Return cached frames as copies (or document the shared-reference con… |
| `W5-10` | W5 | M2 | low | S | `TYPING-03` | Fix the union-attr bug in _models/_drift.py |
| `W5-11` | W5 | M2 | low | S | `TYPING-05` | Fix the misleading list[FieldSpec] annotation in _metadata |
| `W5-12` | W5 | M2 | medium | S | `TELEMETRY-01` | Make the log-correlation filter not error outside an active span |
| `W5-4` | W5 | M2 | medium | S | `ADAPTERS-01` | Tolerate permissive-tier fields missing name/type in get_fields |
| `W5-8` | W5 | M2 | low | S | `API-03` | Add a set-equality test for __all__/_LAZY_EXPORTS/TYPE_CHECKING |
| `W5-9` | W5 | M2 | medium | M | `TYPING-02` | Reconcile AsyncHTTPSession Protocol with aiohttp.ClientSession |
| `W5-13` | W5 | M3 | low | M | `TELEMETRY-02` | Scope schema-drift dedup per service context |
| `W5-14` | W5 | M3 | medium | M | `CONFIG-02`, `CONFIG-03` | FeatureLayer/Directory from_config construction (consume part) |
| `W5-2` | W5 | M3 | medium | M | `API-01` | Stop the instance datadict clobbering stats-only query flags |
| `W5-3` | W5 | M3 | low | S | `API-04` | Enforce nested_count arity (>= 2 fields) |
| `W5-6` | W5 | M3 | low | S | `ADAPTERS-03` | Make resolve_domains robust to malformed domain metadata |
| `W5-5` | W5 | M4 | low | S | `ADAPTERS-02` | Fix the self-contradicting geopandas adapter docstrings |
| `W6-1` | W6 | M1 | medium | S | `PACKAGING-02`, `DOCS-10` | SECURITY.md: add the 3.x supported row |
| `W6-2` | W6 | M1 | low | S | `DOCS-08`, `CICD-04`, `PACKAGING-03` | CONTRIBUTING.md: fix stale branch, coverage claim, dev-extra claim |
| `W6-3` | W6 | M2 | medium | M | `DOCS-03`, `DOCS-04`, `DOCS-06`, `DOCS-07`, `CONFIG-03`, `CONFIG-04`, `PACKAGING-03`, `AUTH-02` | ARCHITECTURE.md: remove code-contradicting claims |
| `W6-4` | W6 | M4 | medium | M | `DOCS-01`, `AUTH-02`, `AUTH-03`, `AUTH-04`, `CONFIG-02`, `ERRTAX-04`, `OPTDEPS-02`, `TELEMETRY-02` | MIGRATION.md: refresh for 3.0 and correct claims |
| `W6-5` | W6 | M4 | medium | M | `PACKAGING-01`, `DOCS-01`, `DOCS-11`, `CICD-02`, `CICD-03`, `ERRTAX-04` | CHANGELOG.md: fix the botched 3.0.0 promotion and populate it |
| `W6-6` | W6 | M4 | low | M | `DOCS-10`, `AUTH-01`, `CONFIG-02`, `PAGINATION-01` | README.md: 2.0->3.0 refresh + token-in-body + truncation notes |
| `W6-7` | W6 | M4 | medium | M | `DOCS-02`, `DOCS-04`, `DOCS-05`, `DOCS-09`, `DOCS-12`, `TELEMETRY-01`, `PAGINATION-01` | Sphinx .rst/.md docs: config env vars, .env, Config example, errors … |

## Split-ownership ledger

21 findings are split across multiple items (code part vs application-seam part vs doc part). Each owning item carries a `Split-ownership:` statement naming the other parts.

| Finding | Owning items |
|---------|--------------|
| `AUTH-01` | `W2-1`, `W6-6` |
| `AUTH-02` | `W2-2`, `W6-3`, `W6-4` |
| `AUTH-03` | `W2-10`, `W3-1`, `W4-5`, `W6-4` |
| `AUTH-04` | `W2-11`, `W3-2`, `W6-4` |
| `CICD-02` | `W1-4`, `W6-5` |
| `CICD-03` | `W1-8`, `W6-5` |
| `CICD-04` | `W1-3`, `W6-2` |
| `CONFIG-01` | `W2-10`, `W3-1`, `W4-5` |
| `CONFIG-02` | `W2-11`, `W3-3`, `W5-14`, `W6-4`, `W6-6` |
| `CONFIG-03` | `W3-4`, `W5-14`, `W6-3` |
| `CONFIG-04` | `W3-5`, `W6-3` |
| `DOCS-01` | `W6-4`, `W6-5` |
| `DOCS-02` | `W3-6`, `W6-7` |
| `DOCS-04` | `W6-3`, `W6-7` |
| `DOCS-10` | `W6-1`, `W6-6` |
| `DOCS-11` | `W3-7`, `W6-5` |
| `ERRTAX-04` | `W2-9`, `W6-4`, `W6-5` |
| `PACKAGING-03` | `W6-2`, `W6-3` |
| `PAGINATION-01` | `W4-1`, `W6-6`, `W6-7` |
| `TELEMETRY-01` | `W5-12`, `W6-7` |
| `TELEMETRY-02` | `W5-13`, `W6-4` |

## Deliberate deferrals

None. All 61 confirmed findings are allocated to at least one work item. (Decision-required items may, at the maintainer's choice, resolve to *doc-only* fixes — e.g. CONFIG-03/04 — but the finding is still addressed, not dropped; see the master plan's decision record.)
