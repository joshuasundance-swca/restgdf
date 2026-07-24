> **10 — Type safety, mypy rigor & py.typed contract** · restgdf audit · **read-only** · no code was modified
> Commit `4673b08` · 2026-06-13 · Index: [README](README.md) · Machine-readable: [findings.json](findings.json)

## Assessment

The typing foundations are genuinely good in places: `py.typed` is present and packaged (pyproject.toml:10), `from __future__ import annotations` is used consistently, and the optional-dep adapters (adapters/pandas.py:19-20, adapters/geopandas.py:28-29, adapters/stream.py:28-29) correctly guard `DataFrame`/`GeoDataFrame`/`AsyncHTTPSession` behind `TYPE_CHECKING` so base-install import stays clean while inline types still resolve — the seed-4 hypothesis is refuted, that part is done right. The exception taxonomy in errors.py is carefully typed. HOWEVER, the overall risk posture for a `Typing :: Typed` package is high: the CI mypy gate is effectively non-functional (it runs with `--ignore-missing-imports` in an isolated env that has none of `aiohttp`/`pydantic`/`pandas`/`stamina` installed and no `pydantic.mypy` plugin), so it reports "Success: no issues found" while the published inline types actually contain 6 real type errors that any downstream consumer with the deps installed will hit — including a Protocol that does not match `aiohttp.ClientSession` despite its docstring claiming it does, two genuine bugs inside the supposedly-strict `_models` module, and a public symbol invisible to type checkers. The strict-mypy override covers only three internal module globs and excludes the entire public-facing surface.

## Findings at a glance

| ID | Finding | Severity | Effort |
|----|---------|----------|--------|
| `TYPING-01` | CI/pre-commit mypy gate is defanged: --ignore-missing-imports + no runtime deps + no pydantic plugin masks all real type errors | medium | M |
| `TYPING-02` | AsyncHTTPSession Protocol does not structurally match aiohttp.ClientSession; constructing FeatureLayer with a ClientSession is a mypy error | medium | M |
| `TYPING-03` | Genuine union-attr bug in strict-scoped _models/_drift.py masked by the gate | low | S |
| `TYPING-04` | get_gdf's `session: ClientSession | None` annotation contradicts the R-71 AsyncHTTPSession widening it sits beneath | low | S |
| `TYPING-05` | Misleading `list[FieldSpec]` annotation in _metadata._field_rows — value is actually list[dict] | low | S |

## Findings

### TYPING-01 · CI/pre-commit mypy gate is defanged: --ignore-missing-imports + no runtime deps + no pydantic plugin masks all real type errors

**Severity:** medium · **Effort:** M · **Location:** `.pre-commit-config.yaml:26-31, pyproject.toml:197-207`

**Evidence**

The only mypy invocation is the pre-commit hook with `additional_dependencies: [- types-requests]` and the mirrors-mypy default args `["--ignore-missing-imports", "--scripts-are-modules"]`. The active isolated env (verified in ~/.cache/pre-commit) contains only `mypy 1.20.1` + `types-requests` — NO aiohttp, pydantic, pandas, geopandas, stamina, aiolimiter. `[tool.mypy]` has NO `plugins = ["pydantic.mypy"]` and NO global config. Running that exact command (`mypy --ignore-missing-imports --scripts-are-modules restgdf/` with no deps) prints `Success: no issues found in 50 source files`, and `pre-commit run mypy --all-files` `Passed`. But running mypy with the deps present + pydantic plugin yields `Found 6 errors in 5 files`, two of them inside the strict-scoped `restgdf/_models/_drift.py`.

**Why it matters**

For a `Typing :: Typed` package the published inline types are the product. The gate gives maintainers false confidence (`Passed`) while 6 type errors ship in every release, including bugs in the supposedly-strict `_models` tier. The strict overrides (`disallow_untyped_*`, `warn_return_any`) are nearly inert because every aiohttp/pydantic type the strict modules touch collapses to `Any`. A downstream consumer who type-checks against restgdf sees errors the maintainers never can.

**Recommendation**

Add the pydantic mypy plugin and make the gate type-check against real dependency types, then fix the 6 errors it surfaces. Concretely: (1) Add `[tool.mypy] plugins = ["pydantic.mypy"]` to pyproject.toml. (2) Either (a) extend the pre-commit mypy hook's `additional_dependencies` with the runtime/type packages (aiohttp, pydantic, plus pandas-stubs/types for the geo paths and stamina/aiolimiter for resilience), or (b) preferred for a layered light-core/extras package: add a dedicated CI mypy job that does `pip install -e ".[geo,resilience,telemetry,dev]"` so all extras' types are present — this also keeps the isolated pre-commit env lean. ANTI-RECOMMENDATION: do NOT pair this with a blanket global `--strict` / removal of `ignore_missing_imports` across the board. aiohttp's `ClientSession` deliberately does not conform to the `AsyncHTTPSession` Protocol (BL-17), and several optional-extra modules intentionally treat un-installed deps as untyped; a global strict flip will surface large numbers of intended-`Any` boundaries and the session-Protocol seam, breaking the gate noisily. Instead keep `ignore_missing_imports` scoped per-module for genuinely-untyped third-party deps, and fix the 6 real errors: the two `_models/_drift.py:85` `validation_alias.choices` union-attr errors (narrow with `isinstance(choices, AliasChoices)` instead of relying on the runtime try/except so the strict `_models` tier is actually sound), the `utils/_metadata.py:157` FieldSpec-not-indexable, the `resilience/_bounded_retry.py:62` stamina `on=` BaseException-vs-Exception mismatch, and the `getgdf.py:522`/`featurelayer.py:300` ClientSession-vs-AsyncHTTPSession argument mismatches.

**Fix touches:** `.pre-commit-config.yaml`, `pyproject.toml`, `.github/workflows/pytest.yml`

---

### TYPING-02 · AsyncHTTPSession Protocol does not structurally match aiohttp.ClientSession; constructing FeatureLayer with a ClientSession is a mypy error

**Severity:** medium · **Effort:** M · **Location:** `restgdf/_client/_protocols.py:22-74, restgdf/featurelayer/featurelayer.py:91-98`

**Evidence**

The docstring asserts the Protocol "Matches :class:`aiohttp.ClientSession`" (lines 24-25). But `get`/`post` are declared with explicit keyword-only params `def get(self, url: str, *, params, headers, ssl, timeout, **kwargs) -> Any`. Modern aiohttp stubs define `def get(self, url: str | URL, **kwargs: **_RequestOptions) -> _BaseRequestContextManager[...]`. mypy (deps present) reports: `Argument 2 to "FeatureLayer" has incompatible type "ClientSession"; expected "AsyncHTTPSession" [arg-type] ... Following member(s) of "ClientSession" have conflicts`. I reproduced this with the natural public call `FeatureLayer("https://.../MapServer/0", aiohttp.ClientSession())`. Even a minimal `get(self, url: str, **kwargs: Any)` protocol fails to match because of the typed `**_RequestOptions` unpack.

**Why it matters**

`FeatureLayer`'s primary documented constructor parameter is `session: AsyncHTTPSession`. A downstream user passing `aiohttp.ClientSession` (the canonical usage shown in README/docstrings) gets a spurious `arg-type` error under mypy/pyright. The runtime `isinstance` works, so the failure is purely a published-type contract violation that contradicts the Protocol's own docstring — exactly the kind of false contract a Typed package must not ship.

**Recommendation**

Confirmed but narrower than stated, and the naive fix is partly ineffective. Three coupled actions:

1. GATE FIRST (load-bearing): add `aiohttp` (and ideally `pydantic`) to the pre-commit mypy hook's `additional_dependencies` in .pre-commit-config.yaml. Today that hook runs in an isolated venv with only `types-requests`, so `aiohttp` resolves to `import-not-found`, `ClientSession` collapses to `Any`, and NO arg-type error surfaces. This is why CI is green while a downstream typed user hits the error. Until the gate sees aiohttp, NO Protocol fix can be verified and pre-existing internal inconsistencies stay hidden.

2. Fix the internal type bidirectionality exposed once aiohttp is visible: `get_gdf` is typed `session: ClientSession | None` (concrete) while `gdf_by_concat` and `FeatureLayer.session` use `AsyncHTTPSession`, so the library's own code fails to type-check against itself (getgdf.py:522 and featurelayer.py:300). Pick one direction (widen `get_gdf` to `AsyncHTTPSession | None`) and apply it consistently.

3. ANTI-RECOMMENDATION on the proposed Protocol change: simply rewriting `get`/`post` to `(self, url: str, **kwargs: Any) -> Any` is NOT guaranteed to make `aiohttp.ClientSession` structurally assignable — the finding itself notes a minimal `**kwargs: Any` protocol still fails against aiohttp's typed `**_RequestOptions` unpack and `_BaseRequestContextManager` return. Verify any signature change against real aiohttp stubs (post-step 1) before claiming it resolves the conflict; you may need `url: str | URL` plus matching the return type, or accept that a runtime-checkable Protocol cannot be a drop-in static supertype of ClientSession and instead correct the misleading docstring (lines 26 "Matches aiohttp.ClientSession" / 30-31 "signature details are advisory") to scope the "advisory" claim to runtime isinstance only.

Also correct the user-facing scope: the README's canonical example uses `FeatureLayer.from_url(url, session=session)`, and `from_url(cls, url, **kwargs)` is untyped, so that documented path does NOT error for users. The spurious arg-type error only fires via the direct `FeatureLayer(url, session)` constructor, which the docstring itself flags as the non-preferred entry point.

**Fix touches:** `restgdf/_client/_protocols.py`, `restgdf/featurelayer/featurelayer.py`

---

### TYPING-03 · Genuine union-attr bug in strict-scoped _models/_drift.py masked by the gate

**Severity:** low · **Effort:** S · **Location:** `restgdf/_models/_drift.py:82-89`

**Evidence**

`choices = info.validation_alias` has pydantic type `str | AliasPath | AliasChoices | None`; the code then does `for choice in choices.choices:`. mypy (deps present) reports `Item "str" of "str | AliasPath | AliasChoices" has no attribute "choices" [union-attr]` and the same for `AliasPath`. Only `AliasChoices` has `.choices`. The code is wrapped in `try/except AttributeError: pass` so it is correct at runtime, but the type access is unsound. This module is inside the `restgdf._models.*` strict override (pyproject.toml:200) yet the error never fires in CI because pydantic is `Any` there.

**Why it matters**

Demonstrates the strict tier is not actually enforced on its own modules. If pydantic ever changed `AliasChoices.choices` or a refactor removed the try/except, this would become a runtime `AttributeError` silently widening into the drift cache being mis-keyed (FieldSpec/alias detection) — affecting which keys are treated as known vs drift. It is a latent correctness hazard the strict gate was specifically meant to prevent.

**Recommendation**

Two-part, and order matters. (1) The real defect is the gate, not this line: the pre-commit mirrors-mypy hook declares only `additional_dependencies: [types-requests]`, so its isolated env has no pydantic/aiohttp, and the hook's default (un-overridden) args `--ignore-missing-imports --scripts-are-modules` turn every third-party symbol into `Any`. That is why the `restgdf._models.*` strict override (pyproject.toml:199-207) catches nothing that touches a typed third-party API. Add the runtime deps mypy needs (e.g. `additional_dependencies: [pydantic, aiohttp, types-requests]`, plus aiolimiter/stamina/opentelemetry/pandas-stubs/types-geopandas as needed) OR run mypy in CI from the installed venv instead of the isolated hook. Caveat: doing so will surface ~16 currently-masked errors (responses.py:527 call-arg, getgdf.py:522/300 AsyncHTTPSession vs ClientSession arg-type, _metadata.py:157 FieldSpec index, _bounded_retry.py:62, and this union-attr) that must be triaged before the gate can be green again — so land it as its own remediation, not a drive-by. (2) Independently, fix this line for type-soundness and clarity: `from pydantic import AliasChoices` (already a hard dep — light-core safe) then `if isinstance(choices, AliasChoices): for choice in choices.choices: ...`, dropping the broad try/except. Verified: only `AliasChoices` exposes `.choices`; `str`/`AliasPath` do not. This fix alone is invisible in CI until part (1) lands.

**Fix touches:** `restgdf/_models/_drift.py`

---

### TYPING-04 · get_gdf's `session: ClientSession | None` annotation contradicts the R-71 AsyncHTTPSession widening it sits beneath

**Severity:** low · **Effort:** S · **Location:** `restgdf/utils/getgdf.py:501-525, 489-498`

**Evidence**

`get_gdf(url, session: ClientSession | None = None, ...)` (line 503) calls `gdf_by_concat(url, session, ...)` whose signature is `gdf_by_concat(url, session: AsyncHTTPSession, **kwargs)` (line 491). mypy (deps present) flags both directions: at getgdf.py:522 `Argument 2 to "gdf_by_concat" has incompatible type "ClientSession"; expected "AsyncHTTPSession"`, and at featurelayer.py:300 `Argument 2 to "get_gdf" has incompatible type "AsyncHTTPSession"; expected "ClientSession | None"` (`FeatureLayer.session` is typed `AsyncHTTPSession`, passed straight into `get_gdf`). The _protocols.py docstring states call sites "were widened to AsyncHTTPSession in R-71 (v3 follow-up T7)" — `get_gdf` was missed.

**Why it matters**

Internal type inconsistency: `FeatureLayer.get_gdf` (public) passes an `AsyncHTTPSession` into a function still typed `ClientSession | None`, and that function then narrows it back. Both ends are unsound under a working gate. Because `get_gdf` is not in any public `__all__` this is internal, but it blocks tightening the gate (finding #1) and shows R-71's widening was incomplete. Tied to the same root cause as finding #2 (the Protocol itself can't represent ClientSession).

**Recommendation**

Recommendation is sound and correctly ordered: change `get_gdf`'s parameter to `session: AsyncHTTPSession | None = None` to complete the R-71 widening, but ONLY after fixing the Protocol (#2). The dependency is real, not optional — under deps-present mypy, `ClientSession` does NOT satisfy `AsyncHTTPSession` because the Protocol's `get`/`post` are declared with explicit keyword params (params/headers/ssl/timeout) while aiohttp's real signature is `def get(self, url: str | URL, **kwargs: **_RequestOptions)`. So if you widen `get_gdf`'s param without first fixing #2, line 510 `session = session or ClientSession()` would itself fail (assigning a `ClientSession` to an `AsyncHTTPSession`-typed name), merely relocating the error rather than removing it. ANTI-RECOMMENDATION: do not "fix" this by adding a `# type: ignore` or by reverting `gdf_by_concat` back to `ClientSession` — that would un-do R-71 and re-fragment the transport seam that `ArcGISTokenSession` + adapters depend on. Lowest-risk path: fix #2 (relax the Protocol's `get`/`post` to structurally accept aiohttp's signature, e.g. `def get(self, url: str | URL, **kwargs: Any) -> Any`), then widen `get_gdf`, then optionally tighten the base `[tool.mypy]` scope so the utils/featurelayer modules are actually checked with deps present (today they are not — see notes).

**Fix touches:** `restgdf/utils/getgdf.py`

---

### TYPING-05 · Misleading `list[FieldSpec]` annotation in _metadata._field_rows — value is actually list[dict]

**Severity:** low · **Effort:** S · **Location:** `restgdf/utils/_metadata.py:153-157, 55`

**Evidence**

`_field_rows` annotates `fields: list[FieldSpec] = layer_metadata.get("fields") or []` then indexes `f["name"]`, `f["type"]`. But `layer_metadata` has just been passed through `_as_dict()` (line 155), which returns a plain `dict` (signature `_as_dict(metadata) -> dict`, line 55), so `fields` is really `list[dict]`. mypy reports `Value of type "FieldSpec" is not indexable [index]`. The same pattern recurs in `get_fields` (line 149: `f["name"]`). Runtime is fine because they are dicts; the annotation is simply wrong.

**Why it matters**

Incorrect inline annotation: anyone reading the types (or a future strict-scope extension per finding #4) is misled about the element type, and the `[index]` error blocks tightening mypy on `restgdf.utils`. Low user impact today since it's a private helper, but it's exactly the annotation drift a Typed package should not carry.

**Recommendation**

Annotate `fields: list[dict[str, Any]]` in `_field_rows` (line 156) — this matches the post-`_as_dict()` reality and silences the mypy `[index]` error while keeping the dict-indexing code unchanged. Do NOT take the finding's alternative suggestion of switching to attribute access (`f.name`, `f.type`) on `LayerMetadata.fields`: `_as_dict()` deliberately calls `model_dump(by_alias=True, exclude_none=True)` (line 62-64), so by the time `fields` is read it is already a list of plain dicts, not `FieldSpec` instances — `f.name` would raise `AttributeError` at runtime, and bypassing `_as_dict` to keep typed models would break the documented case-insensitive extras-preservation behavior that the whole `_metadata` module relies on (`get_name`, `get_max_record_count` regex-scan dict keys). The `or []` fallback should also keep `# type: ignore`-free typing: `list[dict[str, Any]]` covers both branches cleanly. Optionally add the same annotation to `get_fields` (line 147, currently unannotated) for consistency, but that is a clarification, not a correction.

**Fix touches:** `restgdf/utils/_metadata.py`

---

## Minor notes (not adversarially verified)

These were flagged by the axis auditor but did NOT go through per-finding verification — treat as leads, not confirmed findings.

- **resilience _bounded_retry on= arg-type mismatch with stamina** — restgdf/resilience/_bounded_retry.py:62 passes `on=_TIMEOUT_EXCS` (typed `tuple[type[BaseException], ...]`) to `stamina.retry`, which expects `type[Exception] | tuple[type[Exception], ...] | Callable[...]`. mypy (with stamina present) flags `arg-type`. Narrow `_TIMEOUT_EXCS` to `tuple[type[Exception], ...]`. Only bites consumers using the `resilience` extra; masked by the gate (stamina is Any).
- **Several unused `# type: ignore` comments under deps-present mypy** — With runtime deps installed, mypy --warn-unused-ignores flags unused ignores at restgdf/_logging.py:180-181, restgdf/telemetry/_spans.py:90,160, _instrumentor.py:31,48, _correlation.py:17, _compat.py:28. These are stale because the gate runs without the deps that originally produced the errors. They are NOT in the strict-scoped modules so `warn_unused_ignores` does not catch them. The featurelayer.py `type: ignore[type-var]` at lines 398/428/453 ARE still needed (verified not unused).
- **py.typed present and packaged correctly** — restgdf/py.typed exists (empty marker) and pyproject.toml:9-10 declares `[tool.setuptools.package-data] restgdf = ["py.typed"]`, so the marker ships in the wheel. The `Typing :: Typed` classifier (pyproject.toml:44) is backed. This part of the contract is sound — the gap is the rigor behind the marker, not the marker itself.
- **Optional-dep adapter type guards are correct (seed-4 refuted)** — adapters/pandas.py:19-20, adapters/geopandas.py:28-29, and adapters/stream.py:28-29 all import DataFrame/GeoDataFrame/AsyncHTTPSession under `if TYPE_CHECKING:` with `from __future__ import annotations`, so base-install import never touches pandas/geopandas yet the return-type annotations still resolve for type checkers. The seed-4 hypothesis (unsafe adapter signatures) does not hold.
- **FeatureLayer instance-attribute annotations declared without initialization** — featurelayer.py:162-166 declares `self.metadata: LayerMetadata`, `self.name: str`, etc. as bare annotations set only in `prep()`. Accessing them before `prep()` raises `AttributeError` at runtime but type checkers treat them as always-present non-Optional — a mild type/runtime mismatch. The code guards with `hasattr(self, "metadata")` in several places (e.g. line 205, 759), acknowledging they may be absent, so the annotations slightly overstate availability. Low impact given `from_url()` is the documented constructor.
