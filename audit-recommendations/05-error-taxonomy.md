> **05 — Exception taxonomy & error contracts** · restgdf audit · **read-only** · no code was modified
> Commit `4673b08` · 2026-06-13 · Index: [README](README.md) · Machine-readable: [findings.json](findings.json)

## Assessment

The hierarchy is well-designed and well-documented: a single `RestgdfError` root, a coherent transport/service/schema/auth/config split, deliberate stdlib co-inheritance documented per-class with plan IDs, and credential redaction in `_AuthSubtypeBase.__str__`/`__repr__`. MRO and attribute contracts are enforced by tests (`test_error_mro.py`, `test_exception_taxonomy.py`). The real risk is a gap between the advertised discriminator contract and the actual raise sites: several leaf classes that the docs (`ARCHITECTURE.md`, `MIGRATION.md`, docstrings) explicitly tell callers to catch are never raised, so discriminating `except` clauses silently never match; `PaginationError` violates the attribute contract of its own base; auth co-inheritance with `OSError` interacts badly with a retry filter; and a common `/generateToken` 4xx escapes the `RestgdfError` umbrella entirely as a raw aiohttp error. These are contract-falseness issues (callers write handlers that don't fire) rather than crashes, which makes them high-impact-but-quiet for a library.

## Findings at a glance

| ID | Finding | Severity | Effort |
|----|---------|----------|--------|
| `ERRTAX-01` | A 400/401 from /generateToken escapes the RestgdfError umbrella as a raw aiohttp.ClientResponseError; InvalidCredentialsError is never raised | medium | M |
| `ERRTAX-02` | AuthenticationError (and RestgdfTimeoutError) co-inherit OSError, so token retry's except (OSError,...) swallows a deterministic auth error and mislabels it as a transient refresh failure | medium | S |
| `ERRTAX-03` | 498/499 auth conditions are detected only by HTTP status code, not by the in-body ArcGIS error envelope ArcGIS commonly returns | low | M |
| `ERRTAX-04` | Documented 'will be dropped in 3.1+' ValueError co-inheritance is a semver-breaking change with no tracked deprecation path | low | S |

## Findings

### ERRTAX-01 · A 400/401 from /generateToken escapes the RestgdfError umbrella as a raw aiohttp.ClientResponseError; InvalidCredentialsError is never raised

**Severity:** medium · **Effort:** M · **Location:** `restgdf/utils/token.py:280,287-305; restgdf/errors.py:268-272`

**Evidence**

In `update_token`, `resp.raise_for_status()` (`token.py:280`) raises `aiohttp.ClientResponseError` on a 4xx token response. Confirmed `aiohttp.ClientResponseError.__mro__` is `(ClientResponseError, ClientError, Exception, ...)` — NOT an `OSError` and NOT a `RestgdfError`. The retry filter `except _RETRYABLE_ERRORS` (= `(OSError, asyncio.TimeoutError, ConnectionError)`, `token.py:43`) does not catch it, so the `except Exception: ... raise` clause (`token.py:298-305`) re-raises it UNWRAPPED. A grep for `raise InvalidCredentialsError`/`raise TokenRequiredError` returns zero matches — both leaf classes have no raise site anywhere. Yet `InvalidCredentialsError` docstring (`errors.py:269`) states "Raised on 400 / bad credentials from /generateToken", and `ARCHITECTURE.md:57` promises "All runtime failures raise a subclass of `restgdf.RestgdfError`".

**Why it matters**

The most common auth failure (wrong username/password → HTTP 400/401 from generateToken) propagates to callers as a raw `aiohttp.ClientResponseError`. `except restgdf.AuthenticationError:` and even the umbrella `except restgdf.RestgdfError:` both miss it, breaking the headline contract and forcing callers to import aiohttp and catch a transport-library exception to handle a credentials error. `InvalidCredentialsError` and `TokenRequiredError` are dead classes despite being publicly exported and documented.

**Recommendation**

Keep the fix narrowly scoped to the true-HTTP-4xx edge and DO NOT alter the dominant path. In `update_token`, wrap only the `raise_for_status()` boundary: `try: resp.raise_for_status() except aiohttp.ClientResponseError as exc:` then map `exc.status` in `(400, 401, 403)` -> `InvalidCredentialsError` (or `RestgdfResponseError`) and other non-2xx -> `RestgdfResponseError`, chaining `from exc`, and raise it inside the retryable loop's deterministic branch so it is NOT retried. Critically, leave the existing HTTP-200 + JSON-error-envelope path untouched: that path is already correct and tested (`raise_for_status` no-ops on 200; `_parse_response(TokenResponse, ...)` rejects the `{"error":{...}}` envelope and raises `RestgdfResponseError` under the umbrella). Anti-recommendation: do NOT replace `raise_for_status` with blanket status handling that re-parses the body as creds-error on every non-2xx — that risks misclassifying the 200-envelope path and double-handling. Separately, reconcile the docs to match reality: either wire `InvalidCredentialsError` into the 4xx-status branch (and/or the 200-envelope `code==400` path) so the `errors.py:269` docstring and `ARCHITECTURE.md:71` label stop being aspirational, or amend those docs to state that AGOL bad-creds surface as `RestgdfResponseError(model_name="TokenResponse")`. As written, `InvalidCredentialsError`/`TokenRequiredError` are exported+documented but never raised.

**Fix touches:** `restgdf/utils/token.py`

---

### ERRTAX-02 · AuthenticationError (and RestgdfTimeoutError) co-inherit OSError, so token retry's except (OSError,...) swallows a deterministic auth error and mislabels it as a transient refresh failure

**Severity:** medium · **Effort:** S · **Location:** `restgdf/utils/token.py:43,272-312,172-177; restgdf/errors.py:201,352`

**Evidence**

`_RETRYABLE_ERRORS = (OSError, asyncio.TimeoutError, ConnectionError)` (`token.py:43`). `AuthenticationError(RestgdfResponseError, PermissionError)` → `PermissionError` → `OSError` (confirmed at runtime: `issubclass(AuthenticationError, OSError) == True`; also asserted in `test_error_mro.py:160-161`). Inside `update_token`'s try block, `data=self.token_request_payload` (`token.py:275`) raises `AuthenticationError` when `self.credentials` is `None` (`token.py:172` `raise AuthenticationError('Credentials are required...')`). Because `AuthenticationError` is an `OSError`, `except _RETRYABLE_ERRORS` (`token.py:287`) catches it as transient, sleeps/backs off, loops 3x, then `raise TokenRefreshFailedError(...)` (`token.py:307`). The `update_token` docstring (`token.py:254-255`) and `MIGRATION.md:451-452` both promise "Deterministic errors (bad credentials...) are re-raised immediately". The 498-retry path (`token.py:393-394`) calls `update_token()` unconditionally inside the lock, so a None-credentials session that hits a 498 also lands here.

**Why it matters**

A deterministic "no credentials configured" error is retried with backoff (added latency) and then surfaced as `TokenRefreshFailedError` — the wrong class — instead of propagating `AuthenticationError` immediately as documented. The documented contract is false; operators triaging see a refresh-exhaustion error masking a configuration mistake.

**Recommendation**

Add `except RestgdfError: raise` (or the narrower `except AuthenticationError: raise`) as a handler BEFORE `except _RETRYABLE_ERRORS` at `restgdf/utils/token.py:287`, so restgdf's own deterministic errors are never swept into the `OSError` retry bucket. This is safe: nothing raised inside the try (the None-credentials `AuthenticationError` from `token_request_payload`, or a `RestgdfResponseError` from `_parse_response`) is ever a transient condition that should be retried, so adding the guard cannot suppress legitimate backoff behavior. The alternative — hoisting `self.token_request_payload` to a local computed once before the loop — also works and is arguably cleaner (it avoids re-unwrapping the `SecretStr` each attempt), but the explicit `except RestgdfError: raise` is more robust because it also covers any future restgdf exception that happens to inherit an `OSError`/`TimeoutError` builtin. Do NOT widen `_RETRYABLE_ERRORS` or narrow it by removing `OSError` — `OSError` is intentionally retryable for genuine socket-layer transients; the fix belongs in handler ordering, not the tuple. After fixing, add a regression test (none exists today) asserting a None-credentials `update_token()` raises `AuthenticationError` immediately with zero `asyncio.sleep` calls, to lock the `MIGRATION.md:451` contract.

**Fix touches:** `restgdf/utils/token.py`

---

### ERRTAX-03 · 498/499 auth conditions are detected only by HTTP status code, not by the in-body ArcGIS error envelope ArcGIS commonly returns

**Severity:** low · **Effort:** M · **Location:** `restgdf/utils/token.py:381-414; restgdf/errors.py:275-276,302-303,320-326`

**Evidence**

`_call_with_auth_retry` resolves `status = getattr(resp, 'status', 200)` (`token.py:381`) and branches purely on `status == 499` / `status == 498` (`token.py:383,389`). ArcGIS REST very commonly returns auth failures as HTTP 200 with a JSON body `{"error":{"code":498,"message":"Invalid token"}}` (or 499) rather than as an HTTP status. The `TokenExpiredError` docstring (`errors.py:280-282`) and `AuthNotAttachedError` docstring (`errors.py:321`) frame these as "Esri error code 498/499", i.e. the in-body code, but the code only ever inspects the HTTP status.

**Why it matters**

When the server returns the 498/499 condition inside a 200-status envelope (the typical ArcGIS behavior), the single-flight refresh + retry for 498 never triggers, and the 499 `AuthNotAttachedError` is never raised. The response flows downstream and is later parsed by `_parse_response`, surfacing as a generic `RestgdfResponseError` with no token refresh and no auth-specific class — defeating the reactive-498 design (R-14) for the common wire shape.

**Recommendation**

Treat this as a DOCUMENTED-SCOPE enhancement, not a bug fix, because the HTTP-status-only design is the documented contract in CHANGELOG (BL-11), `MIGRATION.md` (R-14 narrative), and `ARCHITECTURE.md` ("# HTTP 498/499"). If extending to the in-body envelope, do NOT naively read `resp.json()` inside `_call_with_auth_retry`: callers downstream (`get_feature_count`, `get_metadata`, `get_object_ids`, etc.) all call `await resp.json(content_type=None)` themselves, so consuming the body in the retry helper would break the response stream for every caller. Any in-body inspection must buffer the body once and hand the buffered payload to callers (a non-trivial refactor of the resp-returning contract), or move the auth-code detection into `_parse_response` / a shared helper that the existing parse call-sites already own. Concretely: (1) add a shared `_arcgis_auth_code(payload) -> int | None` helper; (2) have `_parse_response` map in-body code 498 -> `TokenExpiredError` and 499 -> `AuthNotAttachedError` (instead of the current generic `RestgdfResponseError` at `_drift.py:189-200`) so callers narrowly catching the auth subclasses work for both transports; (3) for the 498 auto-refresh-and-retry to actually fire on the in-body shape, the refresh/retry must live where the body is available, i.e. lift it above `_parse_response` or into the parse layer — it cannot stay purely in `_call_with_auth_retry`. (4) Update `errors.py` docstrings, the three governance docs, and CHANGELOG to state both transports are handled, since this changes documented behavior. Note the 499 in-body case currently degrades to `RestgdfResponseError` (whose subclass `AuthenticationError` it is NOT — it stays the generic parent), so callers catching `RestgdfResponseError` already catch it; only callers catching `TokenExpiredError`/`AuthNotAttachedError` specifically miss the in-body shape. No data is silently lost today, so this is a resilience/ergonomics improvement, not a correctness emergency.

**Fix touches:** `restgdf/utils/token.py`

---

### ERRTAX-04 · Documented 'will be dropped in 3.1+' ValueError co-inheritance is a semver-breaking change with no tracked deprecation path

**Severity:** low · **Effort:** S · **Location:** `restgdf/errors.py:62-64; restgdf/errors.py:11-21; MIGRATION.md:489-494`

**Evidence**

`ConfigurationError` docstring states "Multi-inherits `ValueError` through 3.x so existing `except ValueError` callers continue to catch misconfiguration. The `ValueError` base will be dropped in 3.1+." (`errors.py:62-64`). The same removal is implied for `RestgdfResponseError(RestgdfError, ValueError)` (`errors.py:18-19`). Removing a base class from a publicly exported exception is a breaking change for any `except ValueError` caller, yet there is no `DeprecationWarning`, no CHANGELOG/MIGRATION entry tracking the 3.1 removal, and no test pinning the deprecation. The MIGRATION 3.x upgrade checklist (`489-494`) tells callers to widen clauses but does not warn that `ValueError`-catching will stop working in 3.1.

**Why it matters**

Callers relying on the documented `except ValueError` compatibility shim (the entire reason the co-inheritance exists) will silently break on the 3.1 minor bump unless the removal is announced and deprecation-warned. A removal-in-a-minor of a catchable base is a semver hazard that is currently untracked.

**Recommendation**

Align the `errors.py` docstring with the project's own already-stated policy rather than building new minor-version deprecation machinery. Concretely: in `restgdf/errors.py:62-64` replace "The `ValueError` base will be dropped in 3.1+." with wording consistent with `MIGRATION.md:361-363` — e.g. "The `ValueError` base is a back-compat shim and will only be removed in a future major release (>=4.0), preceded by a `DeprecationWarning`." This single-source-of-truth fix resolves the contradiction with zero behavior change and no import-boundary risk (docstring text only). PREFER this over the finding's alternative of adding a 3.1-targeted `DeprecationWarning` + version-pinning test: introducing an actual deprecation-warning path on the `ValueError` base is both more work and would itself be the breaking signal you are trying to avoid promising in a minor; and a test pinning "removal in 3.1" would codify the very semver violation. If maintainers genuinely want a minor-version drop, they must first downgrade the `CHANGELOG.md` semver claim and rewrite `MIGRATION.md:361-363` — a much larger and unjustified change. Anti-recommendation: do NOT just add a CHANGELOG note announcing a 3.1 removal; that legitimizes a SemVer-breaking minor and contradicts the documented "removal only in a major release" guarantee that covers every other deprecated surface.

**Fix touches:** `restgdf/errors.py`, `MIGRATION.md`, `CHANGELOG.md`

---

## Minor notes (not adversarially verified)

These were flagged by the axis auditor but did NOT go through per-finding verification — treat as leads, not confirmed findings.

- **ErrorPayload referenced in ARCHITECTURE.md does not exist (already-known drift)** — `ARCHITECTURE.md:88` says "Detail types in `restgdf.errors` (e.g. `ErrorPayload`, `RateLimitError.retry_after`, `PaginationError.batch_index`)". A repo-wide grep finds no `ErrorPayload` symbol anywhere in `restgdf/`. This is explicitly listed as known doc drift in `CLAUDE.md:28` and catalogued under `audit-recommendations/`, so per the constitution rule it is a documented decision, not a fresh finding — noting it only for completeness in the ERRTAX surface.
- **_AuthSubtypeBase re-assigns self.context after super().__init__ already set it** — `errors.py:237-243`: `super().__init__` passes `context=context or ''` to `RestgdfResponseError.__init__` (which sets `self.context`), then line 243 sets `self.context` again to the same value with an explicit `: str` annotation. Harmless redundancy; the annotation is the only reason it is not pure dead code. Low value to change.
- **TokenExpiredError(498) carries a .code attribute but the sibling 499/AuthNotAttachedError has no symmetric .code** — `errors.py:284-299` gives `TokenExpiredError` a `code: int = 498` attribute; `AuthNotAttachedError` (499) and `TokenRequiredError` (also 499 per docstring) carry no `.code`. A caller doing `exc.code` for symmetric numeric dispatch across auth subtypes will `AttributeError` on the 499 classes. Minor DX inconsistency in the auth subtype contract.
- **_resolve_page raises generic RestgdfResponseError where _get_sub_features raises PaginationError for the same exceededTransferLimit condition** — `getgdf.py:96` raises `PaginationError` for `exceededTransferLimit` in the batch path, but the newer streaming primitive `getgdf.py:672/681/696` raises `RestgdfResponseError` (`context='exceededTransferLimit'`) for the same `on_truncation='raise'`/`'split'` truncation condition. Two different exception classes for the same semantic failure across two code paths; a caller catching `except PaginationError` for truncation will miss the `iter_pages` path. Borderline ERRTAX/PAGINATION; flagging as a note for the maintainer to reconcile the class used for truncation.
