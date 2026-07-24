> **02 — Token lifecycle, credentials & secret handling** · restgdf audit · **read-only** · no code was modified
> Commit `4673b08` · 2026-06-13 · Index: [README](README.md) · Machine-readable: [findings.json](findings.json)

## Assessment

The credential-confidentiality foundations are genuinely strong: `AGOLUserPass.password` is a `SecretStr` unwrapped only at the `/generateToken` POST boundary (`token.py:184`), the auth subtypes redact `SecretStr` in `__str__`/`__repr__` (`errors.py:249-265`), log `extra` envelopes scrub `?token=` (`_logging.py:91-109`), telemetry spans scrub the URL before recording (`_spans.py:26-35`), single-flight refresh (BL-03) and reactive 498/499 handling are correctly implemented, and the `expires_at` ms/s heuristic (`token.py:201`) is numerically sound. The serious risk is NOT in the library's own logs but on the wire: the documented `FeatureLayer(token=...)` / `data={"token": ...}` path serializes the token into the URL query string on short GET requests because the Gate-3 leak guard only inspects the *session's* transport mode and never the caller-supplied body token (so it misses plain `aiohttp.ClientSession` and default header-mode `ArcGISTokenSession`). Secondary risk is contract drift: two publicly-exported, documented auth exceptions are never raised, and `AuthConfig`'s three refresh-threshold knobs plus `TransportConfig.verify_ssl` are dead config never read by the token-refresh / data-request paths.

## Findings at a glance

| ID | Finding | Severity | Effort |
|----|---------|----------|--------|
| `AUTH-01` | Caller-supplied token leaks into URL query string on the documented FeatureLayer(token=...) / data={'token':...} path | high | S |
| `AUTH-02` | InvalidCredentialsError and TokenRequiredError are documented HTTP-401/499 contracts but have no raise site (dead taxonomy) | medium | M |
| `AUTH-03` | verify_ssl is honored only for the token POST, not for data requests — contradicts the MIGRATION.md claim and half-breaks verify_ssl=False sessions | medium | M |
| `AUTH-04` | AuthConfig's three refresh-threshold knobs are dead config — never read by the token-refresh path | low | M |

## Findings

### AUTH-01 · Caller-supplied token leaks into URL query string on the documented FeatureLayer(token=...) / data={'token':...} path

**Severity:** high · **Effort:** S · **Location:** `restgdf/utils/_http.py:117-123, restgdf/utils/_http.py:126-146, restgdf/_client/request.py:43-49, restgdf/utils/_query.py:69-78, restgdf/featurelayer/featurelayer.py:143-150`

**Evidence**

The Gate-3 leak guard inspects only the *session's* transport mode: `_session_requires_body_transport` walks `_transport`/`_inner` and returns True only for `transport in ('body','query')` (`_http.py:142-145`). A plain `aiohttp.ClientSession` has no `_transport`, and a default `ArcGISTokenSession` reports `_transport=='header'` (`token.py:205-209`), so the guard returns False and `_arcgis_request` falls through to `_choose_verb`, which picks GET for short requests and calls `session.get(url, params=_coerce_params_for_get(body))` (`_http.py:119-122`). The caller's token is in `body`: `build_conservative_query_data` explicitly copies it — `if "token" in caller_data: datadict["token"] = caller_data["token"]` (`request.py:47-48`) — and `get_metadata` does `if token is not None: data["token"] = token` (`_query.py:70-71`). `FeatureLayer.__init__` puts the public `token=` arg straight into that body: `self.datadict["token"] = token` (`featurelayer.py:149`). README:363 documents this exact path: "If you already have a token, you can pass it with `token="..."` or `data={"token": "..."}`." The Gate-3 regression test even hard-codes the wrong conclusion: `test_arcgis_request_still_uses_get_for_header_transport` comments "short requests can use GET without leaking credentials" (`test_gate3_fixes.py:88-97`) — true only because that test's body carries no token.

**Why it matters**

On the most common base-install path (plain `ClientSession` + `token=`) and on a default header-mode `ArcGISTokenSession` when the caller also passes `data['token']`, the secret ArcGIS token is serialized into the GET request URL (e.g. `.../FeatureServer/0?f=json&token=<SECRET>` for metadata and `.../query?returnCountOnly=true&token=<SECRET>` for counts). Tokens then land in ArcGIS Server / IIS access logs, every forward/reverse proxy and WAF log, and Referer headers — exactly the exposure `test_token_transport_header_default.py:31` warns about ('query-string tokens ... can be exposed in logs/referers'). This is a real credential leak to the network on a documented public API.

**Recommendation**

Make the leak guard body-aware in `_arcgis_request` (`restgdf/utils/_http.py:117`): before `_choose_verb`, force POST whenever the outgoing body carries a credential key, e.g. `if _session_requires_body_transport(session) or (body and "token" in body): return await session.post(url, data=body, **kwargs)`. This complements (does not replace) the existing session-transport guard and is low risk: ArcGIS REST layer-metadata roots and `/query` already accept form-encoded POST bodies (the library POSTs to them today for long bodies and for body/query-transport sessions), and the change is pure routing logic inside the light core, so it touches no public-API or import-boundary contract. Prefer POST-the-body over the "strip token from params and move to an X-Esri-Authorization header" alternative: that alternative is riskier for plain-ClientSession callers whose server only honors body/query tokens, and it would silently change the auth scheme. Also update README:363 / README:328-329 to note that passing `token=`/`data["token"]` is sent in the request body (POST) rather than the URL, and fix the misleading comment block at `tests/test_gate3_fixes.py:88-97` (it is only "safe" because that test body carries no token). Recommend adding a regression test that asserts a body containing `token` routes via POST on a plain/header session.

**Fix touches:** `restgdf/utils/_http.py`, `restgdf/utils/_query.py`, `tests/test_gate3_fixes.py`, `README.md`

---

### AUTH-02 · InvalidCredentialsError and TokenRequiredError are documented HTTP-401/499 contracts but have no raise site (dead taxonomy)

**Severity:** medium · **Effort:** M · **Location:** `restgdf/errors.py:268-272, restgdf/errors.py:302-307, restgdf/utils/token.py:280-305, restgdf/__init__.py:50,61,89,110`

**Evidence**

Grep for `raise InvalidCredentialsError` / `InvalidCredentialsError(` and the same for `TokenRequiredError` returns ONLY the class definitions and `__all__`/import lines — no instantiation anywhere in `restgdf/`. Both are exported at top level (`__init__.py:50,61,89,110`) and documented as load-bearing: `ARCHITECTURE.md:71` `InvalidCredentialsError # HTTP 401`, `MIGRATION.md:145` `InvalidCredentialsError # HTTP 401`, and `MIGRATION.md:451` "Deterministic errors (invalid credentials...) propagate immediately." But `update_token` never produces them: a bad-credentials ArcGIS reply (HTTP 200 with `{"error":{"code":400}}`) is validated by the strict `TokenResponse` and surfaces as a generic `RestgdfResponseError` (`_drift.py:181-187`); an actual HTTP 400/401 makes `resp.raise_for_status()` (`token.py:280`) raise `aiohttp.ClientResponseError`, which is not in `_RETRYABLE_ERRORS` (`token.py:43`) so it hits `except Exception: raise` (`token.py:298-305`) and propagates raw. Neither path yields `InvalidCredentialsError`. 499 is handled by `AuthNotAttachedError` (`token.py:383-387`), never `TokenRequiredError`.

**Why it matters**

A caller following the documented taxonomy and writing `except InvalidCredentialsError:` to detect bad credentials, or `except TokenRequiredError:` for a 499, will NEVER match — bad credentials surface as a bare `aiohttp.ClientResponseError` (which is not even a `RestgdfError`/`AuthenticationError`, breaking `except RestgdfError`/`except PermissionError` too) or as a generic `RestgdfResponseError`. The documented contract is false and silently routes auth failures to the wrong (or no) handler.

**Recommendation**

Resolve the doc-vs-implementation divergence either way; the docstrings are the load-bearing problem, not just the `.md` files.

PREFERRED (lower risk): If these two types are not meant to be raised yet, fix the *docstrings*. `errors.py:269` currently asserts `InvalidCredentialsError` is "Raised on 400 / bad credentials from /generateToken" and `errors.py:303` asserts `TokenRequiredError` is "Raised when ArcGIS returns error code 499" — both are present-tense claims that no code fulfills, and `TokenRequiredError`'s 499 claim directly conflicts with `AuthNotAttachedError` (`errors.py:320`, the type actually raised at `token.py:383-387`). Change them to clearly mark "reserved / not currently raised by restgdf 3.0; bad credentials surface as `RestgdfResponseError` per `TokenResponse` strict-tier policy (`responses.py:278-284`); 499 surfaces as `AuthNotAttachedError`." Mirror that in `ARCHITECTURE.md:71-73` and `MIGRATION.md:145,147` so the `# HTTP 401` annotations stop advertising an unimplemented contract.

OR (wire it, if the taxonomy is meant to be live): In `update_token`, before the bare `except Exception: raise` (`token.py:298-305`), catch `aiohttp.ClientResponseError` with status in `{400,401}` and re-raise as `InvalidCredentialsError(..., cause=exc)`; and catch the strict-validation `RestgdfResponseError` ONLY when `_is_arcgis_error_envelope(exc.raw)` is true — do NOT reclassify on `RestgdfResponseError` type alone, or you will silently turn genuine token-schema drift (a malformed-but-non-error token payload) into a spurious auth error. This preserves `MIGRATION.md:451` "propagate immediately" (`InvalidCredentialsError` still propagates without retry). Either way, decide whether `TokenRequiredError` is canonical for 499 or demote it in favor of `AuthNotAttachedError` — do not leave two documented 499 types where only one fires.

ANTI-RECOMMENDATION: do not naively wrap the whole `except Exception: raise` in `InvalidCredentialsError` — that would mislabel timeouts, DNS failures, and TLS errors (which currently escape raw) as credential failures.

**Fix touches:** `restgdf/utils/token.py`, `restgdf/errors.py`, `ARCHITECTURE.md`, `MIGRATION.md`

---

### AUTH-03 · verify_ssl is honored only for the token POST, not for data requests — contradicts the MIGRATION.md claim and half-breaks verify_ssl=False sessions

**Severity:** medium · **Effort:** M · **Location:** `restgdf/utils/token.py:278, restgdf/utils/token.py:345-416, MIGRATION.md:465-467`

**Evidence**

`update_token` forwards `ssl=self.verify_ssl` on the `/generateToken` POST (`token.py:278`). `MIGRATION.md:465-467` states this is "plumbed through ... matching the existing behavior of other library-maintained request sites." But the data-request path `_call_with_auth_retry` builds `session_method(url, **{payload_key: request_payload}, headers=request_headers, **kwargs)` (`token.py:373-379, 403-408`) and never injects `ssl=self.verify_ssl`. `ArcGISTokenSession.get`/`post` (`token.py:418-450`) likewise don't add it. There is no other site that applies it: grep for `ssl=`/`verify_ssl` shows only `token.py:278` and config fields; the module-level `get_gdf` helper builds a bare `session or ClientSession()` (`getgdf.py:510`) with no connector. `TransportConfig.verify_ssl` (`config.py:78`) is never read by any session-construction path either.

**Why it matters**

The documented contract is false: data requests do NOT match the token POST's SSL behavior. A user configuring `ArcGISTokenSession(verify_ssl=False)` for an internal ArcGIS Enterprise with a self-signed cert (the explicitly-supported scenario per `credentials.py:48-56`) will authenticate successfully but then have every metadata/count/query data request fail with an SSL verification error — `verify_ssl=False` is half-applied. Conversely a `verify_ssl=True` intent provides no extra assurance on data requests beyond the session default.

**Recommendation**

Treat this primarily as a doc-vs-reality defect plus a half-wired feature, and fix in that order.

1) Correct the two affirmatively-wrong docs (highest value, zero risk):
   - `MIGRATION.md:465-467` says the token POST forwards `ssl` "matching the existing behavior of other library-maintained request sites." That is the inverse of reality: `token.py:278` is the ONLY site that forwards `ssl=`; every data/metadata/query site relies on the session connector default. Rephrase to "the token POST forwards `ssl=self.verify_ssl`; data requests rely on the caller-supplied session's `TCPConnector` for TLS policy."
   - `CHANGELOG.md:530-531` is factually backwards: it claims `verify_ssl` "was honoured for feature / query requests but ignored during token refresh." Reality is the opposite — it is honoured ONLY for token refresh. Fix the wording.

2) If `verify_ssl` is intended as a library-level TLS knob (it is exposed as an `ArcGISTokenSession` field, a `TransportConfig.verify_ssl`, and a `RESTGDF_TRANSPORT_VERIFY_SSL` env var), make it actually load-bearing. The finding's Option A — `kwargs.setdefault('ssl', self.verify_ssl)` inside `_call_with_auth_retry` — is safe (`setdefault` won't clobber a caller-supplied `ssl=`) and is the right contained patch for `ArcGISTokenSession.get`/`post`, but note it is PARTIAL: it does NOT cover the bare-ClientSession data path (`get_gdf` builds `session or ClientSession()` with no connector, `getgdf.py:510`) and leaves `TransportConfig.verify_ssl` (`config.py:78`) still completely dead. The more complete fix is Option B: when restgdf owns the session, build `TCPConnector(ssl=verify_ssl)`; document that caller-provided sessions own their own TLS. Add a test asserting a `verify_ssl=False` data request forwards `ssl=False` (mirroring the existing token-only BL-05 test in `tests/test_verify_ssl_plumbing.py`).

Anti-recommendation: do NOT "fix" by stripping `ssl=` off the token POST to make the docs literally true — that would re-break the BL-05 self-signed-Enterprise token scenario the change was added for. Reconcile docs UP to the more-complete behavior, not down.

**Fix touches:** `restgdf/utils/token.py`, `restgdf/utils/getgdf.py`, `MIGRATION.md`

---

### AUTH-04 · AuthConfig's three refresh-threshold knobs are dead config — never read by the token-refresh path

**Severity:** low · **Effort:** M · **Location:** `restgdf/_config.py:135-137, restgdf/utils/token.py:119,138-140,164-166, restgdf/_models/credentials.py:78-79`

**Evidence**

`AuthConfig` (a top-level public export, `__init__.py:71`) declares `refresh_threshold_s=60.0`, `refresh_leeway_s=120.0`, `clock_skew_s=30.0` (`config.py:135-137`). Grep across `restgdf/` shows these are never read by any session: nothing constructs an `ArcGISTokenSession`/`TokenSessionConfig` from `Config`/`AuthConfig` (grep for `ArcGISTokenSession(`/`TokenSessionConfig(` finds only the class def and a docstring). The refresh window the session actually uses comes from `ArcGISTokenSession.token_refresh_threshold` (dataclass default 60, `token.py:119`) or, when a `TokenSessionConfig` is built in `__post_init__`, from `refresh_leeway_seconds(120)+clock_skew_seconds(30)=180` (`token.py:138-140`, `credentials.py:78-79`). Only `auth.token_url` is consumed downstream (via the legacy Settings shim, `_settings.py:272-276`) — the three threshold fields and the `RESTGDF_AUTH_REFRESH_THRESHOLD_S` env var (`config.py:236`) feed nothing.

**Why it matters**

A user who sets `RESTGDF_AUTH_REFRESH_THRESHOLD_S=300` or constructs `AuthConfig(refresh_leeway_s=300)` expecting earlier proactive refresh gets no effect — the session silently keeps its own default. Worse, the three representations disagree (60 vs 180 vs 60), so a caller migrating from the `token_refresh_threshold=60` dataclass arg to a `TokenSessionConfig` silently triples the refresh window (180s) with no diagnostic. This is a misleading public config surface for the highest-stakes auth timing knob.

**Recommendation**

Do NOT do the naive "remove the fields / remove the alias" fix: `RESTGDF_AUTH_REFRESH_THRESHOLD_S` and its `RESTGDF_REFRESH_THRESHOLD` alias plus `Settings.refresh_threshold_seconds` are a documented (`MIGRATION.md` L402, L760) back-compat seam pinned by tests (`test_settings.py:113`, `test_settings_deprecation.py:96`, `test_config.py`); deleting them breaks the published deprecation contract. Also do NOT claim a `from_auth_config()` factory makes the env var "actually drive refresh timing" automatically — the library never constructs the token session itself (the caller always builds `ArcGISTokenSession` explicitly, per README/docs/authentication.rst), so there is no chokepoint to auto-wire; a factory only helps callers who opt in. Sound fix: (1) add a docstring note on `AuthConfig` that `refresh_threshold_s`/`refresh_leeway_s`/`clock_skew_s` are config holders not auto-applied to sessions, naming the caller-constructs-the-session model; (2) optionally add a documented `TokenSessionConfig.from_auth_config(get_config().auth)` convenience factory so the field/env var can be threaded by callers who want it; (3) reconcile the default split — note that a bare `TokenSessionConfig` yields `refresh_leeway(120)+clock_skew(30)=150`, while the `ArcGISTokenSession` dataclass default is 60 — so a `from_auth_config` path is internally consistent. This is a doc/DX clarification, not a behavior change.

**Fix touches:** `restgdf/_config.py`, `restgdf/utils/token.py`, `restgdf/_models/credentials.py`, `MIGRATION.md`

---

## Minor notes (not adversarially verified)

These were flagged by the axis auditor but did NOT go through per-finding verification — treat as leads, not confirmed findings.

- **_redact_secret_str is narrowly type-name-gated; latent leak if a future cause stringifies a plaintext secret** — `errors.py:210-216` redacts only when `type(value).__name__ == 'SecretStr'`; `__str__`/`__repr__` render `cause` via `str(self.cause)` (`errors.py:256,261`). Today no auth `cause` carries a plaintext secret (network errors / `aiohttp.ClientResponseError` don't echo the request body, and the token payload `SecretStr` is unwrapped to a local only at `token.py:184`), so this is not currently exploitable. But it is fragile: if a future code path sets `cause` to an exception whose message embeds an unwrapped password/token (e.g. wrapping `token_request_payload`), the name-only check would pass it straight through to tracebacks/logs. Consider scrubbing by value (regex for token-like params) rather than by exact type name.
- **expires_at ms/s heuristic boundary is sound — verified, not a finding** — `token.py:201` `epoch = self.expires/1000 if self.expires > 1e11 else self.expires`. `1e11` corresponds to year 1973 if interpreted as ms and year ~5138 as seconds, so any real ArcGIS expiry (seconds ~1.7e9, ms ~1.7e12) is classified correctly. No realistic value is misread. Confirmed safe.
- **TokenResponse stores the token as a plain str and RestgdfResponseError.raw keeps the full token payload** — `responses.py:287` `token: str = Field(...)` (not `SecretStr`); `token.py:283` `self.token = envelope.token`. The plaintext token is necessarily held on the session to attach to requests, so this is expected, but note that on a validation failure of a token-bearing payload, `_parse_response` attaches `raw=raw` to the `RestgdfResponseError` (`_drift.py:182-187`), and that exception's default str/repr would render `raw` (a dict possibly containing a token). For bad credentials the envelope has no token, so impact is low, but operator logging of `exc.raw` on a partially-valid token envelope could surface a token.
- **get_token() deprecated sync helper hardcodes arcgis.com and posts password in body over HTTPS** — `token.py:82-100` builds `data` with `password.get_secret_value()` and POSTs to a hardcoded `https://www.arcgis.com/.../generateToken` with `timeout=30`. Body-over-HTTPS is correct (no URL leak) and it is deprecated, but it ignores the configured `token_url` and `verify_ssl`, so it can't be used against ArcGIS Enterprise. Acceptable for a deprecated shim; flagged only for completeness.
- **token_request_payload referer/client selection is correct but referer is not validated** — `token.py:178-188` sets `client='referer'` and adds `payload['referer']` when `config.referer` is set, else `client='requestip'`. `AGOLUserPass.referer` / `TokenSessionConfig.referer` are plain `str | None` with no validation (`credentials.py:42,76`). Not a confidentiality issue, but a malformed referer silently yields a token scoped to an unexpected origin.
