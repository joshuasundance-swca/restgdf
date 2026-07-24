> **03 — Configuration & settings resolution** · restgdf audit · **read-only** · no code was modified
> Commit `4673b08` · 2026-06-13 · Index: [README](README.md) · Machine-readable: [findings.json](findings.json)

## Assessment

The layered Config is well-built where it is actually wired: the env-resolution machinery in `Config.from_env` is clean (typed casters, `RestgdfResponseError` wrapping with raw/context, deterministic new-wins-over-alias precedence, deprecation warnings with correct stacklevel), the sub-configs are frozen/validated, and the `get_config`/`reset_config_cache` cache + bidirectional Settings cascade is correct and publicly documented. The real risk is a large gap between what Config advertises and what it controls: several validated sub-configs and their `RESTGDF_*` env vars (`TransportConfig.user_agent`/`verify_ssl`, the entire `AuthConfig`, `RetryConfig`, `LimiterConfig`) are never read by the request/auth code, so callers who set them get silent no-ops with no error. The documented Config precedence chain in `ARCHITECTURE.md` also lists two layers (`.env file` and `Config(...) instance passed explicitly`) that have no implementation anywhere. These are correctness/contract problems for a library consumer, not style nits; only consumed sub-configs (concurrency, `timeout.total_s`, telemetry, resilience) behave as documented.

## Findings at a glance

| ID | Finding | Severity | Effort |
|----|---------|----------|--------|
| `CONFIG-01` | TransportConfig.user_agent / verify_ssl are validated and env-settable but never applied to the main request paths (silent no-op) | high | M |
| `CONFIG-02` | AuthConfig is never wired into token sessions — its env vars and the whole sub-config are dead for the documented auth path | medium | L |
| `CONFIG-03` | Documented Config precedence layer 'Config(...) instance passed explicitly' has no implementation | low | M |
| `CONFIG-04` | Documented Config precedence layer '.env file in the working directory' is never loaded | low | S |

## Findings

### CONFIG-01 · TransportConfig.user_agent / verify_ssl are validated and env-settable but never applied to the main request paths (silent no-op)

**Severity:** high · **Effort:** M · **Location:** `restgdf/utils/_http.py:18-34, restgdf/_config.py:73-79,220-221, restgdf/utils/getgdf.py:90,327,510,612`

**Evidence**

Default request headers hardcode the UA: `DEFAULT_METADATA_HEADERS = {"Accept": "application/json,text/plain,*/*", "User-Agent": "Mozilla/5.0"}` and `default_headers()` merges only that constant. `get_config().transport` is never read anywhere (grep for `.transport.` / `verify_ssl` / `user_agent` across `restgdf/` finds only the model definition, the env spec, and the deprecated `get_settings` shim). Sessions are created bare: `session = session or ClientSession()` (`getgdf.py:510`) with no connector ssl and no UA override. The env spec wires `RESTGDF_TRANSPORT_USER_AGENT`→`transport.user_agent` and `RESTGDF_TRANSPORT_VERIFY_SSL`→`transport.verify_ssl` (`_config.py:220-221`), and the Settings field doc claims UA is the 'User-Agent header sent on ArcGIS REST requests' (`_settings.py:112`).

**Why it matters**

A consumer who sets `RESTGDF_TRANSPORT_USER_AGENT`, `RESTGDF_USER_AGENT`, or `RESTGDF_TRANSPORT_VERIFY_SSL` (or constructs `TransportConfig(verify_ssl=False)`) gets no effect on metadata/query/crawl/stream requests: outbound requests still send `User-Agent: Mozilla/5.0` and TLS verification is never disabled. `verify_ssl=False` is a common requirement for ArcGIS Enterprise behind self-signed certs; silently ignoring it means those calls fail with TLS errors despite the documented knob, and the spoofed Mozilla UA cannot be corrected. No error is raised — the value is accepted, validated, and cached, then ignored.

**Recommendation**

Wire `TransportConfig` into the library-owned request layer, but do it carefully — the naive "forward `ssl=` at every leaf call site" is dangerous.

1. `user_agent`: In `default_headers()` (`restgdf/utils/_http.py:32`), inject `get_config().transport.user_agent` as the `User-Agent` default instead of the hardcoded `"Mozilla/5.0"` in `DEFAULT_METADATA_HEADERS`. The existing merge order (`{**DEFAULT, **(headers or {})}`) already lets an explicit caller header win, so this is back-compat-safe. Note: the `"Mozilla/5.0"` string is a deliberate ArcGIS-compat UA, so swapping the default to `"restgdf/<version>"` is a behavior change worth a CHANGELOG note (some Esri WAFs sniff UA).

2. `verify_ssl`: Do NOT blanket-inject `ssl=get_config().transport.verify_ssl` into every `_arcgis_request` kwargs. Per-request `ssl=` conflicts with callers who supply their own `ClientSession` built on a connector with a custom SSL context, and aiohttp's per-request-vs-connector TLS interplay is fragile. Instead apply `verify_ssl` at the two library-owned session-creation/forwarding seams: (a) the bare `session = session or ClientSession()` at `getgdf.py:510` — build it with a `TCPConnector(ssl=get_config().transport.verify_ssl)`; (b) `ArcGISTokenSession._call_with_auth_retry` (`token.py:373-379, 403-408`), which currently forwards everything EXCEPT `ssl=` — it should forward `ssl=self.verify_ssl` to match the `/generateToken` POST at `token.py:278`. Leave caller-supplied sessions untouched (their connector owns TLS).

3. Reconcile the two disconnected `verify_ssl` fields. `token.py` applies `self.verify_ssl`, which comes from `TokenSessionConfig`/`credentials.py:80` — NOT from `get_config().transport.verify_ssl`. Decide on one source of truth (likely: `AuthConfig`/`TokenSessionConfig.verify_ssl` should default-from or override-by `TransportConfig.verify_ssl`) so a single knob governs both token and data paths.

4. Minimum (if full wiring is deferred): the doc-vs-reality divergence must be fixed regardless. `_settings.py:112` ("User-Agent header sent on ArcGIS REST requests") and `README:113` assert behavior that does not happen — correct those, and either remove the `RESTGDF_TRANSPORT_USER_AGENT`/`RESTGDF_TRANSPORT_VERIFY_SSL` env wiring or document the fields as not-yet-applied. Also note `CHANGELOG.md:530-531` claims `verify_ssl` "was honoured for feature/query requests" — that is only true if the caller's underlying `ClientSession` connector was built with `ssl=False`; the library never does so from config, so that line overstates current behavior.

**Fix touches:** `restgdf/utils/_http.py`, `restgdf/utils/getgdf.py`, `restgdf/_config.py`, `restgdf/_models/_settings.py`

---

### CONFIG-02 · AuthConfig is never wired into token sessions — its env vars and the whole sub-config are dead for the documented auth path

**Severity:** medium · **Effort:** L · **Location:** `restgdf/_config.py:119-166,235-236,267-273, restgdf/utils/token.py:104-166, restgdf/featurelayer/featurelayer.py:91-98,212`

**Evidence**

`ArcGISTokenSession.__post_init__` builds exclusively from `TokenSessionConfig` (`credentials.py`) or dataclass kwargs — `token.py:132-166` never references `get_config()` or `AuthConfig`. Grep for `AuthConfig` usage finds only the model definition, the Config field default, and the `get_settings` shim reading `cfg.auth.token_url`/`cfg.auth.refresh_threshold_s` (`_settings.py:272-276`). `FeatureLayer.__init__`/`from_url` accept no `config`/`auth`/`AuthConfig` parameter (`featurelayer.py:91-98, 212`). Yet docs present `AuthConfig` as operative: `README.md:89` 'set `AuthConfig.transport="body"` to restore the old behavior' and `MIGRATION.md:110` 'set `AuthConfig(transport="body")`'.

**Why it matters**

Setting `RESTGDF_AUTH_TOKEN_URL`, `RESTGDF_AUTH_REFRESH_THRESHOLD_S`, the deprecated `RESTGDF_TOKEN_URL`/`RESTGDF_REFRESH_THRESHOLD`, or constructing `AuthConfig(transport="body", token_url=..., refresh_threshold_s=...)` has zero effect on any token session — the documented remediation ('set `AuthConfig(transport="body")`') does not work because nothing reads `AuthConfig`. Operators following `MIGRATION.md` to revert to body transport are silently left on header transport. The fields validate and cache successfully, so there is no error to alert them.

**Recommendation**

Prefer the low-risk doc fix over auto-wiring. Concretely: (1) Correct `README.md:89` and `MIGRATION.md:109` so the operative remediation is `TokenSessionConfig(transport="body")` (the path that actually works and that the credential-leak guard `_session_requires_body_transport` keys off), and stop presenting bare `AuthConfig(transport="body")` as if it self-applies. `MIGRATION.md:109` already lists `TokenSessionConfig(transport="body")` as an alternative, so `README.md:89` just needs to match. (2) Add a deferral/inertness note to `AuthConfig`'s docstring (`_config.py:119-126`) exactly as `RetryConfig` (line 93 "phase-3a wires the executor") and `LimiterConfig` already do — e.g. "`AuthConfig` is a validated namespace for `RESTGDF_AUTH_*` env vars; it is NOT auto-applied to `ArcGISTokenSession`. Construct `TokenSessionConfig(transport=...)` and pass it explicitly." ANTI-RECOMMENDATION: do NOT naively make `ArcGISTokenSession.__post_init__` read `get_config().auth` as a default. `get_config()` is a process-wide LRU-cached singleton; silently sourcing `transport`/`token_url`/`refresh` from it would make a single env var flip transport for every session in the process and could interact badly with the `_http._session_requires_body_transport` GET->POST credential guard and with explicit-config precedence. If wiring is ever desired, do it as an opt-in classmethod (e.g. `ArcGISTokenSession.from_config(session, credentials, config=get_config().auth)`) that derives a `TokenSessionConfig`, never as an implicit default in `__post_init__`.

**Fix touches:** `restgdf/_config.py`, `restgdf/utils/token.py`, `restgdf/featurelayer/featurelayer.py`, `README.md`, `MIGRATION.md`

---

### CONFIG-03 · Documented Config precedence layer 'Config(...) instance passed explicitly' has no implementation

**Severity:** low · **Effort:** M · **Location:** `ARCHITECTURE.md:113-119, restgdf/_config.py:415-423, restgdf/featurelayer/featurelayer.py:91-98,212`

**Evidence**

`ARCHITECTURE.md` lists precedence highest-first: '1. Explicit constructor arguments ... 2. `Config(...)` instance passed explicitly. 3. Process environment variables ... 4. `.env` file ... 5. Library defaults.' But config is resolved only process-globally: `get_config()` (`lru_cache` size-1) calls `Config.from_env()` reading `os.environ`; no public API (`FeatureLayer.from_url`, `Directory`, token session) accepts a `Config` instance. Grep for `config=`/`Config(` in `featurelayer`/`directory` finds no constructor parameter. There is no mechanism to 'pass a `Config(...)` instance explicitly' so its consumed sub-configs take effect.

**Why it matters**

A consumer who constructs `Config(timeout=TimeoutConfig(total_s=5))` (per the docstring's 'direct instantiation is useful for tests', `_config.py:298-299`) and expects it to be honored at request time has no way to inject it — the request layer always calls the global `get_config()`. The only way to change runtime config is mutating env + `reset_config_cache`, contradicting documented precedence level 2 and surprising library consumers writing isolated/concurrent code.

**Recommendation**

Prefer the doc-side fix: reword/remove `ARCHITECTURE.md:116` precedence level 2 so the listed layers match reality. Runtime config IS resolvable per the documented level-3 path (`RESTGDF_*` env + `reset_config_cache()`), and `Config(...)` direct instantiation is correctly scoped in the `_config.py:298-299` docstring as "useful for tests" only — so the honest doc is: precedence is constructor/aiohttp kwargs (e.g. `timeout=`) > env vars > `.env` > defaults, resolved process-globally via the size-1-cached `get_config()`; a freshly built `Config(...)` is not injectable into the request path. ANTI-RECOMMENDATION: do not take the naive "add `config=` to `FeatureLayer.from_url`" route as a quick fix. It is not a one-liner — every runtime consumer calls the no-arg global `get_config()` (`restgdf/utils/_http.py:213`, `utils/getgdf.py:112/345/402`, `utils/getinfo.py:202`, `utils/crawl.py:44/156`, `telemetry/_spans.py:85/154`), several of which are reached far below the public constructor with no `Config` in scope, so honoring an injected instance means threading it through transport/streaming/telemetry or introducing a `ContextVar`. That is a net-new feature on a Production/Stable library, not a bug fix, and risks the light-core import boundary; it should be a deliberate design proposal, not an audit remediation. Note the separate `TokenSessionConfig` injection (`ArcGISTokenSession(config=...)`) already works and is intentionally session-scoped (`ARCHITECTURE.md:125-127`) — it does not satisfy and should not be conflated with global Config level-2.

**Fix touches:** `ARCHITECTURE.md`, `restgdf/_config.py`, `restgdf/featurelayer/featurelayer.py`

---

### CONFIG-04 · Documented Config precedence layer '.env file in the working directory' is never loaded

**Severity:** low · **Effort:** S · **Location:** `ARCHITECTURE.md:118, restgdf/_config.py:344, restgdf/_models/_settings.py:197`

**Evidence**

`ARCHITECTURE.md` precedence step 4: '`.env` file in the working directory, if present.' But `Config.from_env` reads only the process environment: `source: Mapping[str, str] = os.environ if env is None else env` (`_config.py:344`); identical pattern in `Settings.from_env` (`_settings.py:197`). A repo-wide grep for `dotenv|load_dotenv|\.env` over `*.py` returns no dotenv loading anywhere, and `python-dotenv` is not a dependency.

**Why it matters**

A consumer who follows `ARCHITECTURE.md` and drops a `.env` file with `RESTGDF_TIMEOUT_TOTAL_S=...` into their working directory gets silently ignored config — the documented layer between env vars and library defaults simply does not exist. Misleads users into believing values are applied when they are not.

**Recommendation**

Treat this as a docs-only drift fix (DOCS owns the prose; code is the documented source of truth). Remove or correct the ".env file" precedence layer in ALL THREE published locations, not just `ARCHITECTURE.md:118` — the finding under-reports scope:

1. `ARCHITECTURE.md:118` — delete precedence step 4 (and renumber 5→4).
2. `docs/configuration.rst:11` — delete step 4 (Sphinx-published page; higher consumer visibility than `ARCHITECTURE.md`).
3. `docs/authentication.rst:101-107` — the most misleading: it tells users to "use a .env file (supported by pydantic-settings)" for CREDENTIALS, which is flatly false (`Config`/`AGOLUserPass` are plain `BaseModel`, not `BaseSettings`). Replace with the `os.environ` pattern already shown just above it.

Do NOT take the alternative "implement dotenv loading" path naively: `Config` is a plain `pydantic.BaseModel`, not `pydantic_settings.BaseSettings`, and the documented architecture invariant is that config resolves ONLY from `RESTGDF_*` env vars via `get_config()`. Adding implicit cwd `.env` reading would (a) introduce surprising filesystem/CWD-dependent behavior into a library that other apps embed, (b) risk loading a consumer's app-level `.env` into restgdf's namespace, and (c) require adding `python-dotenv` as a hard runtime dep (it is currently only transitive via `pydantic-settings`, which itself is not a declared dependency in `pyproject.toml` — only `pydantic>=2.13.3,<3` is). If opt-in `.env` is ever desired it should be an explicit, documented helper (e.g. `Config.from_env(env={**dotenv_values(path), **os.environ})`), not implicit magic. Docs fix is the correct and low-effort resolution.

**Fix touches:** `ARCHITECTURE.md`, `restgdf/_config.py`

---

## Minor notes (not adversarially verified)

These were flagged by the axis auditor but did NOT go through per-finding verification — treat as leads, not confirmed findings.

- **AuthConfig.token_url (HttpUrl) vs TokenSessionConfig.token_url (startswith http) divergence is real but only on malformed URLs** — `AuthConfig._check_token_url_scheme` validates via `TypeAdapter(HttpUrl)` (`_config.py:145-156`) while `TokenSessionConfig._check_token_url_scheme` only checks `startswith(('http://','https://'))` (`credentials.py:82-92`). Tested: realistic on-prem URLs (`http://arcgis-internal/...`, `http://10.0.0.5/server/tokens`, `http://localhost:6443/...`) PASS both, refuting the seed's 'rejects on-prem internal-HTTP' concern. They diverge only on malformed inputs `HttpUrl` rejects but `startswith` accepts: `'http://'` (empty host), `'https://host:99999/x'` (invalid port). Since `AuthConfig.token_url` is never wired into a session anyway (see finding 2), the practical divergence is negligible. Labeled-unverified as a contract issue; included for completeness.
- **get_settings() truncates refresh_threshold_s float to int — faithful to legacy field type, not a real loss** — `_settings.py:276` does `int(cfg.auth.refresh_threshold_s)`, so `RESTGDF_AUTH_REFRESH_THRESHOLD_S=60.9` surfaces as `60` through the shim. This is consistent: `Settings.refresh_threshold_seconds` is typed `int` (`ge=0`) and always was, so the shim faithfully represents the legacy flat field. Not a finding — the seed's 'mis-represents values' concern doesn't bite because the destination field is integer by contract.
- **Settings.default_headers_json is stored but never merged by the library** — `default_headers_json` is accepted/validated and exposed on `Settings` (`_settings.py:146-152, 290-292`) but grep shows no `json.loads` or header merge anywhere in `restgdf/`. The field description says 'Consumers parse this string at the HTTP boundary' — i.e. the library deliberately does NOT consume it; that's the consumer's job. Per the constitution rule this is by-design (doc matches behavior), so not a finding. Worth a maintainer glance only because it's a config value that looks like it should do something.
- **RetryConfig / LimiterConfig env vars accepted but unconsumed (likely intended deferral)** — `RESTGDF_RETRY_*` and `RESTGDF_LIMITER_*` are wired in `_NEW_ENV_SPEC` (`_config.py:225-229`) and validate into `RetryConfig`/`LimiterConfig`, but grep finds no consumer of `.retry.`/`.limiter.`/`rate_per_host`/`max_delay_s`/`max_attempts` in request code (the resilience extra uses `ResilienceConfig` instead). `RetryConfig` docstring says 'disabled by default; phase-3a wires the executor' (`_config.py:93`) and `LimiterConfig` 'disabled by default', so this appears to be a documented deferral, not a live bug — distinct from `TransportConfig`/`AuthConfig` which docs present as active. Flagging as a watch item: the two parallel retry/limiter config surfaces (`RetryConfig`/`LimiterConfig` vs `ResilienceConfig`) risk consumer confusion about which knobs are live.
