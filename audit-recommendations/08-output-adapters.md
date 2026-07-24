> **08 — Output adapters (dict / pandas / geopandas / stream)** · restgdf audit · **read-only** · no code was modified
> Commit `4673b08` · 2026-06-13 · Index: [README](README.md) · Machine-readable: [findings.json](findings.json)

## Assessment

The adapter layer is well-structured and disciplined. Optional deps are gated correctly inside function bodies so base-install imports never pull pandas or geopandas; the dict and stream adapters are thin verbatim aliases over vetted core helpers; `resolve_domains` correctly avoids mutating its input and uses `replace` rather than `map` so unknown codes pass through; and the deliberate no-geometry-normalization-yet boundary is governed by plan IDs BL-27, BL-28, BL-35 and stated in docstrings and MIGRATION.md. The real risk concentrates in two spots. First, `resolve_domains` silently fails to substitute on a code-versus-column dtype mismatch, returning raw codes in a frame the API promises is resolved, and it crashes on malformed-but-real domain metadata. Second, the geopandas adapters' own docstrings contradict themselves by naming `stream_rows` and `iter_rows`, which yield raw ArcGIS geometry dicts, as the typical input while elsewhere requiring shapely-compatible geometry, a documented footgun that raises `TypeError`. Overall posture is medium: no unconditional silent data loss in the common path, but one common-path silent-wrong-result and one self-contradictory public contract.

## Findings at a glance

| ID | Finding | Severity | Effort |
|----|---------|----------|--------|
| `ADAPTERS-01` | `get_fields(types=True)`, `_field_rows` and `get_fields_frame` raise `KeyError` on permissive-tier fields missing `'name'`/`'type'` | medium | S |
| `ADAPTERS-02` | geopandas adapter docstrings name `stream_rows` and `iter_rows` as input but those rows raise `TypeError` | low | S |
| `ADAPTERS-03` | `resolve_domains` crashes on malformed-but-real domain metadata | low | S |

## Findings

### ADAPTERS-01 · `get_fields(types=True)`, `_field_rows` and `get_fields_frame` raise `KeyError` on permissive-tier fields missing `'name'`/`'type'`

**Severity:** medium · **Effort:** S · **Location:** `restgdf/utils/_metadata.py:144-157`

**Evidence**

`get_fields` with `types=True` does `{f["name"]: f["type"].replace("esriFieldType", "") for f in fields}` and `_field_rows` does `[(f["name"], f["type"].replace("esriFieldType", "")) for f in fields]`. The `fields` come from `_as_dict(...)['fields']` which originate from `FieldSpec` (a `PermissiveModel` where `name` and `type` are both `str | None = None`). `get_object_id_field` in the SAME module deliberately guards this (`if isinstance(field.get("name"), str)`, line 92), showing the maintainer knows fields can lack `name`; the stats/frame helpers do not.

**Why it matters**

A layer with a field entry lacking `name` or `type` (vendor variance the permissive tier is explicitly designed to tolerate, per the `FieldSpec` docstring) makes `get_fields(types=True)`/`get_fields_frame`/`get_fieldtypes` raise raw `KeyError` or `AttributeError` (`'NoneType' has no 'replace'`) instead of returning the resolvable subset — inconsistent with the permissive-tolerance contract the rest of the module honors.

**Recommendation**

Guard the field iterators with `.get()` and skip entries missing `name` (or with a non-str name), mirroring `get_object_id_field`'s `isinstance(field.get("name"), str)` filter at line 92. Concretely:
- `get_fields(types=False)`: `[f["name"] for f in fields if isinstance(f.get("name"), str)]`
- `get_fields(types=True)` / `_field_rows`: only emit a row when `name` is a `str`, and default a missing/`None` `type` so `.replace()` never runs on `None` — e.g. `(f["name"], (f.get("type") or "").replace("esriFieldType", ""))` for entries where `isinstance(f.get("name"), str)`.

Anti-recommendation / cautions:
- Do NOT just swap `f["type"]` for `f.get("type")` without the `None`-guard — that converts the `KeyError` into the `AttributeError` `'NoneType' has no attribute 'replace'` already reproduced via the raw-dict path. The fix must handle both missing-key AND explicit-`None`.
- Decide skip-vs-default deliberately: dropping a field with no usable `name` is the right parallel to `get_object_id_field` (a nameless field has no addressable identity), but it changes the row/key set returned to a caller. Document the skip behavior in the docstrings so it is an intentional, contract-aligned decision rather than silent dropping. Keep `get_fields_frame`/`fieldtypes` and `get_fields` consistent (route both through the same guarded `_field_rows`-style helper) so the dict, list, and DataFrame views agree on which fields survive.
- Add a regression test feeding a field dict missing `type` (and one missing `name`) through `_parse_response(LayerMetadata, ...)` then `get_fields(types=True)`/`get_fields_frame`, asserting the resolvable subset is returned without raising.

**Fix touches:** `restgdf/utils/_metadata.py`

---

### ADAPTERS-02 · geopandas adapter docstrings name `stream_rows` and `iter_rows` as input but those rows raise `TypeError`

**Severity:** low · **Effort:** S · **Location:** `restgdf/adapters/geopandas.py:47-52,106-109,126-128`

**Evidence**

`rows_to_geodataframe` Parameters says rows are typically produced by `iter_rows` and that each geometry value must be shapely-compatible. `arows_to_geodataframe` Parameters says typically `stream_rows` or `iter_rows`, and its See Also describes `get_gdf` as equivalent to awaiting `arows_to_geodataframe` over `layer.stream_rows` with geometry normalization handled for you. But `stream_rows` and `iter_rows` yield attributes merged with the raw ArcGIS geometry dict via `_feature_to_row_dict` at `getgdf.py` lines 170-171. Verified that calling `rows_to_geodataframe` on a row whose geometry is an `x` and `y` dict raises `TypeError` about input not being valid geometry objects.

**Why it matters**

The docstrings are internally contradictory: one part names `stream_rows` and `iter_rows` as the canonical feed, another requires shapely-compatible geometry, and the See Also implies the `stream_rows` idiom merely lacks normalization rather than crashing outright. A developer following the "typically-stream_rows" guidance hits a hard `TypeError` with no hint that ArcGIS geometry dicts must first be converted to shapely.

**Recommendation**

Fix the docs (the actual defect); this is docs-only and touches no API/import-boundary/back-compat seam. Specifically in `restgdf/adapters/geopandas.py`: (1) In the Parameters of both `rows_to_geodataframe` (lines 47-52) and `arows_to_geodataframe` (lines 106-109), keep the "must be shapely-compatible" requirement but stop naming `stream_rows`/`iter_rows` as the "typical" feed without a caveat — these yield the RAW ArcGIS geometry dict verbatim (via `_feature_to_row_dict` at `restgdf/utils/getgdf.py:170-171`), which raises `TypeError` here. Add a one-line note that ArcGIS geometry dicts must be converted to shapely first, and point to `FeatureLayer.get_gdf` / `stream_gdf_chunks` (or `restgdf.adapters.stream.iter_gdf_chunks`) for the batteries-included path. (2) Correct/remove the See Also line at lines 126-128: `get_gdf` is NOT implemented as `await arows_to_geodataframe(layer.stream_rows())` — it builds the `GeoDataFrame` via `get_sub_gdf` -> `read_file(..., engine="pyogrio")` over the server's ESRIJSON/GeoJSON response (`restgdf/utils/getgdf.py:317-335`), so the "equivalent to ... with geometry normalization handled for you" wording is doubly wrong (that idiom crashes, and it is not the real implementation). Reword to "High-level accessor that returns the full layer as a single GeoDataFrame" (matching the `rows_to_geodataframe` See Also at lines 78-80). ANTI-RECOMMENDATION: do NOT implement the optional "raise `OutputConversionError` instead of the bare geopandas `TypeError`" suggestion by `try`/`except` around the geopandas call — the `TypeError` text/behavior is geopandas-version-specific (observed on 1.0.1), it adds catch logic to a deliberately thin adapter whose module Scope note (lines 10-18) defers geometry normalization to BL-27/BL-28/BL-35, and it would risk masking legitimate caller errors. Leave actual ArcGIS-dict-to-shapely conversion to that deferred work; here, fix only the contradictory docstrings.

**Fix touches:** `restgdf/adapters/geopandas.py`

---

### ADAPTERS-03 · `resolve_domains` crashes on malformed-but-real domain metadata

**Severity:** low · **Effort:** S · **Location:** `restgdf/adapters/pandas.py:98-105`

**Evidence**

Line 100 calls the `get` method on `domain` after only checking `domain` is truthy at line 98, not that it is a dict; verified that a string `domain` value raises `AttributeError` because a `str` has no `get` method. Line 105 builds the map guarding only that `code` is present in `cv`; verified a `codedValue` entry with `code` but no `name` raises `KeyError` on `name`. `resolve_domains` is a public documented helper that accepts `FieldSpec` instances or raw dicts and is exercised standalone in `tests/test_resolve_domains.py`.

**Why it matters**

A documented public helper crashes mid-conversion on real-world vendor metadata variance instead of degrading gracefully, contradicting its own stated philosophy that unknown or absent data passes through unchanged. Via `FeatureLayer.get_df` the `FieldSpec` model constrains `domain` to `dict` or `None`, but a coded value missing its `name` is still unguarded and aborts the whole DataFrame build.

**Recommendation**

Add an `isinstance` guard on `domain` and a stricter coded-value comprehension. Concretely, at `restgdf/adapters/pandas.py:98-105` change the domain handling to skip non-dict domains (`if not isinstance(domain, dict): continue` before `domain.get("type")`) and build the map only from well-formed entries: `mapping = {cv["code"]: cv["name"] for cv in coded_values if isinstance(cv, dict) and "code" in cv and "name" in cv}`. CRITICAL anti-recommendation: do NOT take the finding's offered `"or use cv.get"` shortcut for the `name`. `cv.get("name")` returns `None` for a name-less coded value, which would map that code to `None` and silently REPLACE the real code with `None`/NaN in the output column — that violates the documented pass-through contract ("codes absent from the table pass through unchanged") far more harmfully (silent data corruption) than the current loud `KeyError`. The `"name" in cv` membership guard is required so unresolvable codes are left untouched by `Series.replace`. The `isinstance(domain)` guard is safe and aligns with `FieldSpec.domain` being typed `dict | None`; it does not touch the light-core import boundary or any back-compat seam.

**Fix touches:** `restgdf/adapters/pandas.py`, `tests/test_resolve_domains.py`

---

## Minor notes (not adversarially verified)

These were flagged by the axis auditor but did NOT go through per-finding verification — treat as leads, not confirmed findings.

- **`get_df` and `arows_to_dataframe` materialize the entire layer before building the DataFrame** — `FeatureLayer.get_df` awaits `arows_to_dataframe` over `self.stream_rows`, and `arows_to_dataframe` materializes the full async iterable into a list at `pandas.py` line 199 before constructing the DataFrame. Peak memory is the full layer, same as `get_gdf`. This is not a contract violation: the `arows_to_dataframe` docstring says it consumes the async iterable to completion, and the README attributes the process-millions-without-buffering claim only to the streaming generators, not to `get_df`. Worth a one-line note in the `get_df` docstring so large-layer callers reach for `stream_rows` plus chunked writes instead.
- **Mixed-geometry batches do NOT produce ragged columns (seed refuted)** — Seed hypothesis was that `_feature_to_row_dict` adding geometry only when present at `getgdf.py` lines 170-171 yields ragged DataFrame columns. Verified false: pandas `DataFrame` from a list of dicts fills missing keys with `NaN`, so a batch mixing geometry-present and geometry-absent features produces a single consistent geometry column with `NaN` where absent. No corruption; standard pandas alignment. Not a finding.
- **`rows_to_geodataframe` accepts `None` geometry for tabular-only flows as documented** — Verified that rows whose geometry is `None` build a `GeoDataFrame` with a geometry-dtype column of `None`s and do not raise, matching the docstring guidance to leave the field empty for tabular-only flows. The geo-normalization gap only bites when raw ArcGIS coordinate dicts are passed; null or empty is handled. Confirms the documented boundary holds for the empty case.
- **`resolve_domains` range-domain pass-through is intentional and matches docstring** — Range domains are deliberately not validated or coerced at `pandas.py` lines 100-103, which skip any non-`codedValue` type, and the docstring states this explicitly. Per the constitution rule this is a documented decision, not a finding; noted only to record it was checked and reality matches the doc.
