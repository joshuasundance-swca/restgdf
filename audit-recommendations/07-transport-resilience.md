> **07 — HTTP transport, retry & rate-limiting** · restgdf audit · **read-only** · no code was modified
> Commit `4673b08` · 2026-06-13 · Index: [README](README.md) · Machine-readable: [findings.json](findings.json)

## Assessment

The transport layer is mostly well-engineered and clearly governed by docstrings/plan IDs. The GET/POST length router (`_choose_verb`, 8192-byte ceiling) is sound; the credential-leak guard (`_session_requires_body_transport`) correctly walks the `_inner` chain and is safe under BOTH wrapping orders; `_service_root` truncation is correct for all documented ArcGIS URL shapes including the embedded-`"FeatureServer"` substring trap; stamina is configured with `reraise=True` so the documented exception taxonomy is preserved on terminal failure; and the dual-interface `_RetriedCtx` correctly matches aiohttp's awaitable semantics with no connection leak on the library's `await`-then-`.json()` consumption pattern. The one real correctness hole is that the router's documented "byte-for-byte identical below the verb switch" invariant is FALSE: booleans and `None` are coerced to ArcGIS wire form only on the GET branch, so the same query sends different values once it crosses 8192 bytes onto POST. Secondary risks are robustness gaps under hostile/buggy `Retry-After` headers (NaN/Inf leak to a public attribute) and several public retry/limiter config knobs that are silently inert. Overall risk posture: one high-severity silent-divergence finding, the rest medium/low robustness and config-wiring gaps.

## Findings at a glance

| ID | Finding | Severity | Effort |
|----|---------|----------|--------|
| `TRANSPORT-01` | Public RetryConfig / LimiterConfig knobs are never wired into the resilience executor; ResilientSession hardcodes attempts/timeout/backoff | medium | M |
| `TRANSPORT-02` | `_parse_retry_after` accepts NaN/Inf, leaking non-finite values into `RateLimitError.retry_after` and the 429 cooldown | low | S |

## Findings

### TRANSPORT-01 · Public RetryConfig / LimiterConfig knobs are never wired into the resilience executor; ResilientSession hardcodes attempts/timeout/backoff

**Severity:** medium · **Effort:** M · **Location:** `restgdf/resilience/_retry.py:167-174; restgdf/_config.py:92-109, 225-229`

**Evidence**

The stamina executor hardcodes `@stamina.retry(on=retry_on, attempts=5, timeout=60.0, wait_initial=0.5, wait_max=10.0, wait_jitter=1.0)`. A repo-wide grep shows nothing reads `RetryConfig.max_attempts`/`max_delay_s` or `LimiterConfig.rate_per_host` (`config.retry`/`config.limiter` are referenced only in `_config.py` definitions/exports). Yet `_config.py` defines, validates, and env-binds them publicly: `('RESTGDF_RETRY_MAX_ATTEMPTS','retry.max_attempts',int)`, `('RESTGDF_RETRY_MAX_DELAY_S',...)`, `('RESTGDF_LIMITER_ENABLED',...)`, `('RESTGDF_LIMITER_RATE_PER_HOST',...)`. The resilience layer instead reads only `ResilienceConfig` (a separate sub-config). `RetryConfig`'s docstring defers wiring to 'phase-3a', but the knobs are shipped as accepted public env vars / `restgdf.RetryConfig`/`restgdf.LimiterConfig` exports today.

**Why it matters**

MIGRATION.md advertises ResilientSession as having "configurable max-attempts", but a consumer setting `RESTGDF_RETRY_MAX_ATTEMPTS=10` or constructing `RetryConfig(max_attempts=10, max_delay_s=120)` gets silently ignored — retries stay capped at 5 and 60s. The env var validates and the attribute reads back the set value, so the no-op is invisible. This is a silently-false config contract on a Production/Stable release; `RESTGDF_LIMITER_*` is likewise inert (rate limiting is driven only by `ResilienceConfig.rate_per_service_root_per_second`).

**Recommendation**

Prefer the documentation/warning fix (recommendation path b) as the immediate, low-risk resolution, and treat the wiring fix (path a) as a larger follow-up that needs a design decision first.

Path (b) — safe now: Align MIGRATION.md with the honest RetryConfig docstring. MIGRATION.md:290-291 advertises ResilientSession as having "configurable max-attempts" (false — `_retry.py:167-174` hardcodes `attempts=5`/`timeout=60.0`), and MIGRATION.md:372-373 presents `RetryConfig`/`LimiterConfig` as live "stamina knobs surfaced via the resilience extra" / "aiolimiter token-bucket knobs" with no deferral caveat. Add the "not yet honored; phase-3a" note that the RetryConfig docstring already carries (`_config.py:93`), drop or qualify the "configurable max-attempts" claim, and emit a one-time warning when `RESTGDF_RETRY_MAX_ATTEMPTS` / `RESTGDF_RETRY_MAX_DELAY_S` / `RESTGDF_LIMITER_*` are set but inert, so callers are not silently misled.

Path (a) — wiring, but watch the hazard: It is feasible (`_do_retried_request` already receives a config object), BUT the naive "just thread RetryConfig in" edit is dangerous because the executor today reads ResilienceConfig, not the aggregate Config, and there is a genuine semantic collision: `LimiterConfig.rate_per_host` vs `ResilienceConfig.rate_per_service_root_per_second` are two competing rate-limit knobs (host vs service-root granularity). Wiring both without deciding which owns the limiter would create ambiguous/duplicated rate limiting. So path (a) requires first deciding config ownership (consolidate the overlapping knobs or define precedence), then threading `max_attempts`→`attempts` and `max_delay_s`→`timeout`. Do not ship path (a) as a blind decorator edit.

**Fix touches:** `restgdf/resilience/_retry.py`, `restgdf/_config.py`

---

### TRANSPORT-02 · `_parse_retry_after` accepts NaN/Inf, leaking non-finite values into `RateLimitError.retry_after` and the 429 cooldown

**Severity:** low · **Effort:** S · **Location:** `restgdf/resilience/_errors.py:22-27; restgdf/resilience/_retry.py:194-200, 220-227`

**Evidence**

`_parse_retry_after` does `seconds = float(value); if seconds < 0: return None; return seconds`. Verified `_parse_retry_after('nan')` -> `nan`, `_parse_retry_after('inf')` -> `inf` (NaN/Inf both pass `< 0`). In `_retry.py`: `ra = _parse_retry_after(headers.get('Retry-After',''))` then `cd = min(ra, config.respect_retry_after_max_s) if ra else ...`. `bool(nan)` is True, `min(nan, 60.0)` returns `nan`, so `cooldown.set_cooldown(svc_root, nan)` stores a NaN deadline. On terminal 429, `retry_after = _parse_retry_after(exc.headers.get('Retry-After',''))` is attached to the public `RateLimitError(retry_after=...)`.

**Why it matters**

A buggy or hostile server sending `Retry-After: nan`/`inf` poisons restgdf state: the cooldown deadline becomes NaN (the `remaining > 0` guard then silently skips the wait, so the 429 back-off is effectively dropped), and the documented public attribute `RateLimitError.retry_after` is handed back as `nan`/`inf`. The tracing recipe explicitly tells callers to read `exc.retry_after` and sleep on it; `await asyncio.sleep(inf)` hangs forever and `nan` mis-schedules. This is a robustness/correctness gap on a documented public attribute reachable from untrusted server headers.

**Recommendation**

Sound and minimal: in `_parse_retry_after` (`restgdf/resilience/_errors.py`), after `seconds = float(value)`, replace `if seconds < 0: return None` with `if not math.isfinite(seconds) or seconds < 0: return None` (add `import math`). This rejects NaN/Inf/-Inf at the single source, fixing both the 429 cooldown deadline and the public `RateLimitError.retry_after` attribute. It is stdlib-only (no light-core import-boundary concern), aligns with the existing docstring contract ("Returns None for empty, unparsable, or negative values"), and does not regress the existing parametric tests (`'120'`->120.0, `'-5'`->None, garbage->None). Do NOT instead clamp NaN to a number in `_retry.py`'s `min(ra, ...)` expression — that would leave the public `retry_after` attribute poisoned and only patch one of the two sinks.

**Fix touches:** `restgdf/resilience/_errors.py`, `tests/test_resilience_retry.py`

---

## Minor notes (not adversarially verified)

These were flagged by the axis auditor but did NOT go through per-finding verification — treat as leads, not confirmed findings.

- **stamina timeout=60.0 is a between-attempts stop, not a wall-clock cancel** — In `_do_retried_request` the `timeout=60.0` maps to tenacity `stop_after_delay` (verified in `stamina._core`), which only prevents scheduling NEW attempts after the deadline; it does not interrupt an in-progress `wait_if_cooling` sleep (up to `respect_retry_after_max_s=60s`) or a hanging request. With a clamped 60s cooldown per attempt, a caller can be blocked well beyond the configured 60s "timeout". Consider documenting that the timeout is a soft, between-attempts cap.
- **Backoff cap diverges between inline fallback and stamina at high max_attempts** — BL-51 claims byte-for-byte semantics. They match at the only call's `max_attempts=3` (sleeps 0.1, 0.2, both under stamina's `wait_max=1.0`). But the inline loop sleeps an uncapped `0.1*2**attempt` while `bounded_retry_timeout` caps at `wait_max=1.0` (and adds no jitter either, so equal there). The divergence is latent because `_feature_count_with_timeout` hardcodes `max_attempts=3` and never exposes an override; if that ever changes the two installs would back off differently.
- **config.transport.verify_ssl / user_agent are not applied to the auto-created data ClientSession** — `get_gdf` creates a bare `ClientSession()` (`getgdf.py:510`) with no `TCPConnector`, so `RESTGDF_TRANSPORT_VERIFY_SSL=false` and the configured `user_agent` affect only the token-fetch leg (`token.py:278` passes `ssl=self.verify_ssl`), not actual data requests. This is partly CONFIG-axis (config wiring) so flagged here only as a note; `verify_ssl` being a security knob that is inert on the data path is worth a maintainer's attention.
- **Canonical ResilientSession/ArcGISTokenSession wrapping order is undocumented (though both orders are leak-safe)** — The credential guard walks `_inner` from the outermost session and works for both `ResilientSession(ArcGISTokenSession(...))` and the reverse, since `ArcGISTokenSession` exposes `_transport` directly and `ResilientSession` exposes none. MIGRATION.md/recipes only ever show `ResilientSession` outermost. No correctness bug found, but there is no stated/enforced canonical order and no test for the reverse nesting — worth a one-line doc note.
- **get_feature_count/get_metadata do not check resp.status on the base (non-resilience) path** — `_query.get_feature_count` goes straight to `await response.json(content_type=None)` with no status check; HTTP error status handling exists only inside `ResilientSession._do_retried_request`. So 5xx/429 are surfaced as taxonomy errors only when the resilience extra wraps the session — base installs rely on JSON-parse failure. This is mostly ERRTAX-owned but has a transport flavor; noting for cross-axis awareness.
