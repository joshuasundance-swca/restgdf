# Streaming features

`restgdf` 3.0 exposes four streaming shapes on every
{class}`~restgdf.FeatureLayer`. Three of them (`stream_features`,
`stream_feature_batches`, `stream_rows`) are built on top of the same
low-level `iter_pages` primitive and share its knobs. The fourth
(`stream_gdf_chunks`) is the legacy `GeoDataFrame`-per-page shape
backed by `chunk_generator`; it yields in completion order, does not
accept `on_truncation` / `order` / `max_concurrent_pages`, and does
not emit the R-61 `feature_layer.stream` parent span. All four are
safe to use on a base install unless explicitly noted.

| Method                              | Yields                             | Install |
| ----------------------------------- | ---------------------------------- | ------- |
| `stream_features`                   | one raw ArcGIS feature dict        | base    |
| `stream_feature_batches`            | one `list[feature_dict]` per page  | base    |
| `stream_rows`                       | one row-shaped dict (attrs+geom)   | base    |
| `stream_gdf_chunks`                 | one `GeoDataFrame` per page        | `restgdf[geo]` |

`iter_pages` is the raw generator underneath — yields full response
envelopes (`features`, `objectIdFieldName`, `exceededTransferLimit`, …).
Reach for it when you need the wire shape.

## The three streaming shapes

### `stream_features` — one feature at a time

```python
import asyncio
from aiohttp import ClientSession
from restgdf import FeatureLayer

URL = "https://maps1.vcgov.org/arcgis/rest/services/Beaches/MapServer/6"

async def main():
    async with ClientSession() as session:
        layer = await FeatureLayer.from_url(URL, session=session)
        n = 0
        async for feature in layer.stream_features():
            n += 1
        return n

asyncio.run(main())
```

`stream_features` and `iter_features` are deliberate aliases — use
`stream_features` in new code; `iter_features` remains the lower-level
iterator primitive for introspection.

### `stream_feature_batches` — page boundaries preserved

```python
async def main():
    async with ClientSession() as session:
        layer = await FeatureLayer.from_url(URL, session=session)
        async for batch in layer.stream_feature_batches():
            # `batch` is exactly one page's features; use for backpressure,
            # per-page normalization, or bulk DB inserts.
            print(f"page of {len(batch)}")
```

### `stream_gdf_chunks` — one `GeoDataFrame` per page (requires `restgdf[geo]`)

```python
async def main():
    async with ClientSession() as session:
        layer = await FeatureLayer.from_url(URL, session=session)
        async for gdf_chunk in layer.stream_gdf_chunks():
            # `gdf_chunk.attrs["spatial_reference"]` is populated from
            # layer metadata (R-65) — same on every chunk.
            print(gdf_chunk.shape, gdf_chunk.attrs.get("spatial_reference"))
```

Install the extra first:

```bash
pip install "restgdf[geo]"
```

:::{note}
`stream_gdf_chunks` is backed by the legacy `chunk_generator`
pipeline, **not** `iter_pages`. It yields chunks in **completion
order** and does not accept `on_truncation`, `order`, or
`max_concurrent_pages`, and it does not emit the
`feature_layer.stream` parent span. If you need those knobs on geo
output, compose `stream_rows` or `stream_features` with your own
geometry assembly, or call `get_gdf` / `get_gdf_list` for a single-
shot batch.
:::

`stream_rows` is the row-shaped sibling of `stream_features`: each item
is `{**feature["attributes"], "geometry": feature.get("geometry")}`. Use
it to feed the pandas/geopandas adapters without loading an entire layer
into memory.

## Truncation handling: `on_truncation`

ArcGIS responses can set `exceededTransferLimit=true` when the server
could not pack every matching feature into a single page. The three
`stream_features`, `stream_feature_batches`, `stream_rows`, and
`iter_pages` accept `on_truncation`:

```python
# Default: raise — safest for correctness-sensitive pipelines.
async for feat in layer.stream_features(on_truncation="raise"):
    ...
# Raises RestgdfResponseError(context='exceededTransferLimit') if any
# page is truncated.

# Log + continue — best when you know the server always truncates and
# your downstream pipeline is OK with partial pages.
async for feat in layer.stream_features(on_truncation="ignore"):
    ...
# Emits a structured warning on the `restgdf.pagination` logger.

# Bisect + recurse — fetch the missing records by splitting the OID list.
async for feat in layer.stream_features(on_truncation="split"):
    ...
# Up to 32 levels of recursion; irreducible partitions raise.
```

`"split"` requires an OID field on the layer and one additional
`get_object_ids` round-trip per split. It is the right choice when you
need completeness and cannot pre-compute page sizes.

## Ordering: `order="request"` vs `order="completion"`

```python
# Default: yield in submit order. Deterministic, easy to reason about.
async for batch in layer.stream_feature_batches(order="request"):
    ...

# Yield as fetches complete — may interleave; throughput > ordering.
async for batch in layer.stream_feature_batches(order="completion"):
    ...
```

Caveat: `order="completion"` **does not** preserve pagination order. If
your downstream logic assumes ascending `objectIds` or append-only
semantics (e.g. writing to a sorted file, computing running aggregates),
stick with `"request"`.

## Throughput: `max_concurrent_pages`

```python
# Unbounded (default). Easy to overwhelm slow services.
async for feat in layer.stream_features():
    ...

# Cap concurrent in-flight page fetches.
async for feat in layer.stream_features(max_concurrent_pages=4):
    ...
```

`max_concurrent_pages` is in addition to
`ConcurrencyConfig.max_concurrent_requests` (which caps fan-out at
the top-level orchestration layer) — the more restrictive of the two
wins.

## What about `iter_pages`?

`iter_pages` is the low-level generator that the three
`iter_pages`-based shapes (`stream_features`, `stream_feature_batches`,
`stream_rows`) compose on top of. Reach for it when you need the full
response envelope (`exceededTransferLimit`, pagination tokens, or
server-side warnings):

```python
async for page in layer.iter_pages(on_truncation="ignore"):
    if page.get("exceededTransferLimit"):
        # Custom handling here instead of the built-in split/raise.
        ...
    for feature in page.get("features", []):
        yield feature
```

## Deprecated: `FeatureLayer.row_dict_generator`

`row_dict_generator` still works but now emits a `DeprecationWarning`.
Migrate to `stream_rows`:

```python
# Before
async for row in layer.row_dict_generator():
    ...

# After
async for row in layer.stream_rows():
    ...
```

Behavior is equivalent; `stream_rows` gains the streaming knobs
(`order`, `max_concurrent_pages`, `on_truncation`) and the R-61 parent
span.

## Observability

When telemetry is enabled (`restgdf[telemetry]` +
`RESTGDF_TELEMETRY_ENABLED=1`), every `iter_pages` call emits exactly
one INTERNAL parent span named `feature_layer.stream` wrapping the
per-page loop. No per-page child spans are emitted. See
{doc}`tracing` for the full span wiring, logger names, and
OpenTelemetry integration.
