> **11 — Telemetry, logging & schema-drift observability** · restgdf audit · **read-only** · no code was modified
> Commit `4673b08` · 2026-06-13 · Index: [README](README.md) · Machine-readable: [findings.json](findings.json)

## Assessment

The telemetry layer is well-architected for an optional integration: import-gating is clean (base install imports `restgdf.telemetry` without OTel; helpers no-op when telemetry is disabled and raise `OptionalDependencyError` only when enabled-but-absent), the `restgdf.*` logger namespace is governed by a deliberate `LOGGER_SUFFIXES` allowlist with idempotent NullHandler/`_SpanContextFilter` attachment, and the generator-safe span lifetime (`start_feature_layer_stream_span` + `finally: span.end()` under `aclosing`) is a thoughtful fix for OTel context-detach bugs, backed by an R-61 import-guard test. The drift-logging design (dedup, permissive-vs-strict tiers, `FieldSetDriftObserver`) is documented and tested. Residual risk is concentrated in two spots that contradict their own docs: (1) the published log-correlation recipe produces stderr logging errors on every record emitted outside an active span, and (2) drift dedup is not scoped per service, so multi-service crawls silently mask per-service schema-drift incidents. Both are correctness/DX issues, not credential leaks; overall posture is solid.

## Findings at a glance

| ID | Finding | Severity | Effort |
|----|---------|----------|--------|
| `TELEMETRY-01` | Documented log-correlation recipe raises logging errors on every record emitted outside an active span | medium | S |
| `TELEMETRY-02` | Schema-drift dedup key excludes service context, silently masking per-service drift in multi-service crawls | low | M |
| `TELEMETRY-03` | Auth module bypasses the get_logger factory, so restgdf.auth never receives a NullHandler | low | S |

## Findings

### TELEMETRY-01 · Documented log-correlation recipe raises logging errors on every record emitted outside an active span

**Severity:** medium · **Effort:** S · **Location:** `docs/recipes/observability.md:68-72, restgdf/_logging.py:171-182`

**Evidence**

The recipe tells users to configure the stdlib root with `fmt = "%(levelname)s [trace=%(trace_id)s span=%(span_id)s] %(message)s"` then `logging.basicConfig(format=fmt)`. But `_SpanContextFilter.filter` only sets the attributes when a span is active: `if ctx is not None and ctx.is_valid: record.trace_id = ...; record.span_id = ...` (no else / no default). The companion test `tests/test_telemetry_log_span_correlation.py:60-67` pins this as intentional: `assert not hasattr(record, "trace_id")` outside a span. Most restgdf records (e.g. `auth.refresh.start` DEBUG, the pagination `exceededTransferLimit` warning, the `maxRecordCountFactor clamp` warning) are emitted with NO active stream span.

**Why it matters**

A consumer who follows the documented recipe gets `ValueError: Formatting field not found in record: 'trace_id'` swallowed by logging into a `--- Logging error ---` dump on stderr for every restgdf log record that isn't inside a `feature_layer.stream` span (i.e. the common case). The advertised log-correlation feature is unusable as documented, and the noise can mask the actual log message. The usual stdlib mitigation `logging.Formatter(defaults=...)` is Python 3.10+, but the package declares `requires-python = ">=3.9"`, so there is no version-portable escape hatch shown.

**Recommendation**

Prefer option (a): make `_SpanContextFilter.filter` ALWAYS stamp `record.trace_id`/`record.span_id`, defaulting when no valid span (e.g. `record.trace_id = format(ctx.trace_id, "032x") if (ctx is not None and ctx.is_valid) else ""` and likewise for span_id). This makes the documented `%(trace_id)s/%(span_id)s` recipe work for ALL restgdf records (the filter is already attached across the whole `restgdf.*` tree via `_install_span_context_filter`, so transport/auth/pagination records are covered). You MUST update the one contradicting pin `tests/test_telemetry_log_span_correlation.py:60-67` (`test_restgdf_log_record_outside_span_has_no_trace_id`) to assert the sentinel instead of `not hasattr`. This does NOT affect `span_context_fields()` nor `test_span_context_fields_empty_outside_span` (that helper returns `{}` and is independent of the filter), so the public helper contract is preserved. Minor caveat: an empty-string default is indistinguishable from a degenerate all-zero context, but that is cosmetic. If you prefer not to change behavior, option (b) also works — fix the recipe in `docs/recipes/observability.md` to a custom `Formatter` using `getattr(record, "trace_id", "-")` and note the raw `%()s` form only renders inside an active span; do NOT recommend `logging.Formatter(defaults=...)` since that is Python 3.10+ and the package declares `requires-python = ">=3.9"`. Note this is purely a logging/DX defect: no returned-data corruption, no credential leak, no API/semver break.

**Fix touches:** `restgdf/_logging.py`, `docs/recipes/observability.md`, `tests/test_telemetry_log_span_correlation.py`

---

### TELEMETRY-02 · Schema-drift dedup key excludes service context, silently masking per-service drift in multi-service crawls

**Severity:** low · **Effort:** M · **Location:** `restgdf/_models/_drift.py:93-122, restgdf/directory/directory.py:75, MIGRATION.md:790-792`

**Evidence**

`_log_drift` dedups on `key: _DriftKey = (model_name, path, kind, sample_type)` where `model_name` is just the model class name (e.g. `"LayerMetadata"`) — there is no `context`/service-root component. `_parse_response` always calls it with `model_name=model_cls.__name__`. Directory crawl validates every service's metadata with the same class: `LayerMetadata.model_validate(raw)` (`directory.py:75`). Corroborating: `FieldSetDriftObserver` deliberately works around this by folding context into the name — `self._model_name = f"FieldSetDriftObserver[{context}]"` (`_drift.py:317`) — so per-service observer drift is NOT masked, but `_parse_response` drift is. `MIGRATION.md:790-792` frames the dedup only as 'repeated calls against the same drifty server'.

**Why it matters**

In a `Directory` crawl (the library's multi-service use case) or any process touching many services, a bad-type or unknown-extra field on `LayerMetadata`/`ServiceInfo` from service B is silenced for the whole process once service A logged the same `(model, field, kind, type)` tuple. Operators triaging a vendor incident on one service get no record because an unrelated service already 'used up' the dedup slot — exactly the per-service signal observability is supposed to provide. The masking is process-global (`_seen_drift` is a module-level set) and not acknowledged by the docs.

**Recommendation**

Do NOT blindly adopt the proposed key change. Adding the full `context` (which for `_parse_response` is the full per-layer/per-service URL, `getinfo.py:245` and `_query.py:80`, not a service-name) to `_DriftKey` would regress the documented anti-spam guarantee (`MIGRATION.md:790-792`): a single drifty server with 500 layers would emit 500 identical records instead of 1, because every layer URL is distinct. The observer's `FieldSetDriftObserver[{context}]` pattern works only because its context is a coarse layer/service label, not a per-layer URL.

The more material gap is that the drift log MESSAGE itself omits `context` entirely (`_drift.py:113-122` logs model_name/path/kind/sample_type/sample but never the URL), so even the first, non-deduped occurrence does not tell an operator which service produced it. Prefer: (1) thread `context` into the log message/record (e.g. add an `extra={"context": context}` field or include it in the format string) so the first emission is attributable, while leaving the dedup key context-free to preserve anti-spam; or (2) if per-service dedup is genuinely wanted, key on a coarse SERVICE-ROOT derived from context, not the raw URL, and document the new behavior in `MIGRATION.md` + the docstrings + a dedup test. Either way, since the drift logger is opt-in and silent by default, this is an observability-richness refinement, not a correctness fix.

**Fix touches:** `restgdf/_models/_drift.py`, `MIGRATION.md`, `tests/test_models_primitives.py`

---

### TELEMETRY-03 · Auth module bypasses the get_logger factory, so restgdf.auth never receives a NullHandler

**Severity:** low · **Effort:** S · **Location:** `restgdf/utils/token.py:37, restgdf/_logging.py:24-33,56-79`

**Evidence**

`token.py:37`: `_auth_logger = logging.getLogger("restgdf.auth")` — a raw stdlib call, even though `"auth"` is a valid suffix in `LOGGER_SUFFIXES` (`_logging.py:30`) and `get_logger("auth")` is the documented factory (BL-25; 'new loggers require an explicit ledger entry'). `get_logger` is what attaches the NullHandler (`_logging.py:76-77`); the import-time `_install_span_context_filter()` only adds the `_SpanContextFilter` to `restgdf.auth`, not a NullHandler. `MIGRATION.md:417-420` documents all named loggers including `restgdf.auth` as 'All attached with a NullHandler'. No code calls `get_logger("")`, so the `restgdf` root has no NullHandler either.

**Why it matters**

`restgdf.auth` (and the root `restgdf`) lack the documented NullHandler. Today the auth logger only emits at DEBUG (`auth.refresh.start/success/failure`), below stdlib's WARNING `lastResort`, so output is not actually leaked — but the implementation diverges from the documented 'NullHandler attached' contract, and any future WARNING+ auth record (or a consumer who sets the auth logger to DEBUG without adding a handler and relies on propagation being muted) would fall through to `lastResort`/stderr unexpectedly. The bypass also defeats the allowlist's stated purpose of routing every logger through one ledgered factory.

**Recommendation**

Replace `_auth_logger = logging.getLogger("restgdf.auth")` at `restgdf/utils/token.py:37` with `from restgdf._logging import get_logger` and `_auth_logger = get_logger("auth")`. This is safe and correct: `"auth"` is a valid suffix (`restgdf/_logging.py:29`), and `get_logger`'s NullHandler attach (lines 76-77) and span-filter attach (line 78) are both idempotent, so no duplicate handler/filter results even though `_install_span_context_filter()` already added a `_SpanContextFilter` to `restgdf.auth` at import time. No light-core boundary concern: `_logging.py` is pure stdlib (logging/re/urllib) and is already imported by `_retry.py`, `getgdf.py`, `_pagination.py`. Do NOT also try to "fix" the root `restgdf` NullHandler gap as part of this change — the finding correctly notes the root never gets a NullHandler (no production caller invokes `get_logger("")`), but that is a separate, broader item the one-line auth swap does not and should not address; conflating them risks scope creep. Optionally add an assertion to the taxonomy contract test that the actual module-level `token._auth_logger` carries a NullHandler (current test only exercises the factory, not the real logger object), to lock the fix.

**Fix touches:** `restgdf/utils/token.py`

---

## Minor notes (not adversarially verified)

These were flagged by the axis auditor but did NOT go through per-finding verification — treat as leads, not confirmed findings.

- **Pagination clamp warning bypasses the build_log_extra envelope contract** — `restgdf/utils/_pagination.py:105-111` logs with a raw `extra={"requested_factor":..., "advertised_factor":...}`. Those keys are not in `LOG_EXTRA_KEYS` (`_logging.py:35-47`) and the record carries no `service_root`/`operation`, so it is inconsistent with the BL-26 `build_log_extra` envelope every other structured record uses. No data leak — just a structured-logging consistency gap that makes this record harder to filter/parse uniformly.
- **Pagination 'ignore' warning logs the layer URL unscrubbed** — `restgdf/utils/getgdf.py:663-667` emits `get_logger("pagination").warning(... url=%s ..., url)` with the raw layer URL, not passed through `_scrub_url`. In normal use the ArcGIS token travels in headers/body/query params (`token.py` update_headers/update_dict), not baked into `self.url`, so this is low risk — but a consumer who constructs `FeatureLayer(url="...FeatureServer/0?token=SECRET")` would have the token logged verbatim. Consider scrubbing via `_scrub_url(url)` for defense in depth.
- **_scrub_url only redacts a query param literally named 'token'** — `restgdf/_logging.py:49-52,91-109` — `_TOKEN_PARAM_RE = r"([?&])(token)=[^&#]*"` only matches the `token` query key (case-insensitive). Tokens in path segments, alternative param names, or other URL positions are not redacted. ArcGIS uses `token` exclusively so this matches the real wire format, and `_service_root_for_telemetry` further strips the query entirely for span attrs — but the scrubber is narrower than a generic 'no secrets in logs' guarantee, worth a docstring note that it is ArcGIS-`token`-specific.
- **span_out_fields typed Any but span attr documented as str** — `restgdf/utils/getgdf.py:743` declares `span_out_fields: Any`, fed from `self.datadict.get("outFields")` (`featurelayer.py:360`) which may be a list. The span helper docstring (`_spans.py:131-132`) and `observability.md:59` type `restgdf.out_fields` as a string ('Requested fields'). OTel tolerates `list[str]` attributes, but a non-str/non-sequence value (or mixed list) would be dropped or warned by the SDK. Low impact; mostly a doc/typing nit straddling TYPING axis.
- **Module docstring/MIGRATION call the dedup tuple value_type while code uses sample_type** — `restgdf/_models/_drift.py:17` and `MIGRATION.md:722,791` name the 4th dedup component `value_type`, while the implementation uses local `sample_type = type(sample).__name__` (`_drift.py:108-109`). Same semantics, different label — not a behavioral divergence, just naming drift that could confuse a maintainer matching docs to code.
