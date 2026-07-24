# Polite Bulk / Multi-Host Crawl

This recipe is for the "crawl many independent ArcGIS servers" scenario —
discovering services across hundreds or thousands of government/enterprise
hosts, where each host is a small box that must not be hammered, while a
handful of large multi-tenant SaaS hosts need a very different rate.

It composes four things that exist in `restgdf` today but have no single
worked example anywhere else in the docs: a wrapped, rate-limited session;
the crawl entry point; a descriptive User-Agent; and your own outer
concurrency bound.

## Prerequisites

```bash
pip install "restgdf[resilience]"
```

`restgdf[resilience]` adds `stamina` (retry) and `aiolimiter` (token-bucket
rate limiting). Installing it does **not** change any crawl behavior on its
own — `Directory`/`FeatureLayer` always take a caller-owned session and never
construct or wrap one for you (`restgdf/directory/directory.py`,
`restgdf/resilience/_retry.py`). You opt in explicitly, in two steps.

## Step 1 — wrap your session

```python
from contextlib import asynccontextmanager

from aiohttp import ClientSession
from restgdf import ResilienceConfig
from restgdf.resilience import ResilientSession

resilience_cfg = ResilienceConfig(
    enabled=True,
    rate_per_service_root_per_second=0.5,  # sub-1.0 rates are valid (3.3)
    limiter_key="host",                    # one polite rate PER HOST
)

@asynccontextmanager
async def make_session():
    async with ClientSession() as raw:      # closes the inner session on exit
        yield ResilientSession(raw, resilience_cfg)
```

`ResilienceConfig.enabled` is the sole gate — the retry/rate-limit knobs
below only tune an *already-enabled* session; none of them can silently turn
resilience on or off on their own. `ResilientSession` is transparent: it
implements the same `get`/`post` shape as a plain `aiohttp.ClientSession`, so
it drops straight into `session=` on `Directory`/`FeatureLayer`.

### Two configuration mechanisms — know which one you are using

The knob table below has one "live" column, but the knobs reach the request
path by two different routes, and mixing them up is the single easiest way to
configure nothing at all:

- **Resilience knobs are per-session and passed explicitly.** A
  `ResilienceConfig` you construct is read only by the `ResilientSession` you
  hand it to. Constructing one does **not** consult
  `RESTGDF_RESILIENCE_*`. To honour the environment, build the session from
  the process-global config instead:

  ```python
  from restgdf import get_config
  from restgdf.resilience import ResilientSession

  session = ResilientSession(raw, get_config().resilience)  # honours RESTGDF_RESILIENCE_*
  ```

  (`get_config()` is cached; call `restgdf.reset_config_cache()` after
  changing an env var in-process.)
- **Transport / concurrency / timeout knobs are process-global env vars.**
  `RESTGDF_TRANSPORT_USER_AGENT`, `RESTGDF_CONCURRENCY_MAX_CONCURRENT_REQUESTS`
  and `RESTGDF_TIMEOUT_TOTAL_S` are read from `get_config()` at request time.
  A `Config(...)` instance you build yourself is **not** threaded into the
  request path (CONFIG-03) — passing one somewhere and expecting it to
  override the process global silently does nothing.

### Why `limiter_key="host"` for a bulk crawl

The default `limiter_key="service_root"` keys the token bucket (and the 429
cooldown) per ArcGIS *service*, not per host. A single government host
commonly exposes dozens of services under one directory — `limiter_key=
"service_root"` at `rate=0.5` still lets that host receive many times 0.5
req/s in aggregate, because each service gets its own independent bucket.
`limiter_key="host"` (added in 3.3) applies one shared rate across every
service on `scheme://host` — the actual politeness unit for "don't hammer
this box." The 429 cooldown always follows the same key you select, so a
host-level throttle produces a host-wide cooldown, not a per-service one.

**Exception — multi-tenant SaaS hosts.** A small number of hosts (Esri's own
`services*.arcgis.com` shards, for example) front many independent tenants
on shared infrastructure, not one government office's box. Host-keying those
at a polite single-host rate would starve a shard serving thousands of
unrelated services for no politeness benefit. Give SaaS-shaped hosts their
own `ResilientSession` (built from a separate `ResilienceConfig`, since
`limiter_key`/rate are per-session, not global) at `limiter_key="service_root"`
or a deliberately higher host rate, and record that choice — a `Resilience
Config` is cheap to build per shard.

**Sub-1.0 rates now work.** Before 3.3, `rate_per_service_root_per_second`
below `1.0` raised a raw `ValueError` on the first request — exactly the
range a polite per-host rate needs (`0.5`, `0.2`, ...). That is fixed; rates
below 1.0 now pace correctly instead of crashing.

## Step 2 — pass the wrapped session to `Directory`

```python
from restgdf import Directory

async def crawl_one_host(url: str, session) -> list:
    directory = await Directory.from_url(url, session=session)
    return await directory.crawl()  # uses Directory.safe_crawl internally
```

Because the session is wrapped once and reused for every request `Directory`
issues, resilience applies uniformly to the whole crawl — service discovery,
per-folder metadata, and per-layer metadata all go through the same rate
limiter, cooldown, and retry policy. Prefer `Directory.crawl()` over the
legacy `fetch_all_data()` — it delegates to the module function
`restgdf.utils.crawl.safe_crawl` (not a `Directory` method), which contains a
failing service or folder as a `CrawlError` and keeps crawling the rest.

A single failing *layer* inside an otherwise-healthy service is also
contained (3.3): the service's surviving layers are returned, and the failed
layer stays in the list carrying a `layer_error` marker naming the exception,
instead of the whole service's inventory being discarded.

**Count your `layer_error`s.** A contained layer failure is deliberately
*not* a `CrawlError`, so it never reaches `CrawlReport.errors` — a service
whose every layer failed looks healthy if you only check
`len(report.errors)`. Each one does emit a `WARNING` on the `restgdf.crawl`
logger, and the markers are countable in the returned data:

```python
broken = [
    layer
    for entry in report.services
    for layer in (entry.metadata.layers if entry.metadata else [])
    if getattr(layer, "layer_error", None)
]
```

### What retry does and does not cover

The resilient retry path wraps each request up to *headers received*. A
connection failure at dispatch (server disconnect, reset, DNS, connect
timeout) is retried and surfaces as `restgdf.errors.TransportError`. A
failure raised while the response **body** is read — the truncated-body
`aiohttp.ClientPayloadError`, or a mid-body disconnect — is outside that
scope: it is not retried and reaches you as the raw aiohttp exception. On
flaky estates, catch `aiohttp.ClientPayloadError` alongside
`restgdf.errors.TransportError` (a crawl that treats either as "retry this
host later" needs both).

## Step 3 — set a descriptive, contactable User-Agent

```bash
export RESTGDF_TRANSPORT_USER_AGENT="mycrawler/1.0 (contact: you@example.org)"
```

or, to set it from inside the process:

```python
import os
from restgdf import reset_config_cache

os.environ["RESTGDF_TRANSPORT_USER_AGENT"] = "mycrawler/1.0 (contact: you@example.org)"
reset_config_cache()  # get_config() is cached; re-read the environment
```

```{warning}
Building `Config(transport=TransportConfig(user_agent=...))` does **not**
set the crawl User-Agent. The wire header is read from the *process-global*
`get_config()` at request time, and a directly constructed `Config` is never
threaded into the request path (CONFIG-03) — it is test-only. Use the
environment variable, as above.
```

A descriptive User-Agent identifying the crawl and a contact point is bulk-
crawl etiquette, and it is the **only** effective lever on the metadata/crawl
path:

- The env var is live — every metadata/crawl request reads
  `get_config().transport.user_agent` on every call, so `reset_config_cache()`
  (if you change the variable mid-process) takes effect immediately.
- A **session-level** `aiohttp.ClientSession(headers={"User-Agent": ...})`
  does **not** survive on this path — `get_metadata` (the primitive behind
  `Directory`/`safe_crawl`) always supplies its own per-request `User-Agent`
  header, and aiohttp's per-request headers win over the session default.
- **Per-request `headers={"User-Agent": ...}` override still wins — but only
  on the feature/query surfaces** (`get_feature_count`, `get_object_ids`,
  the streaming/`get_gdf`/stats helpers), which accept a `headers=`/`**kwargs`
  passthrough. `get_metadata` — the sole primitive behind `Directory.crawl`,
  `Directory.safe_crawl`, and `Directory.prep` — takes no `headers` argument
  at all, so per-request override is not available on the crawl path. The
  config/env lever above is the only way to set the UA for crawl traffic.

## Step 4 — bound your own outer concurrency

`ConcurrencyConfig.max_concurrent_requests` (default `8`, env
`RESTGDF_CONCURRENCY_MAX_CONCURRENT_REQUESTS`) caps in-flight requests
**per `safe_crawl`/`Directory.crawl` call**, not process-wide. If you crawl
`N` hosts by launching `N` concurrent `Directory.crawl()` calls, you get up
to `8 × N` in-flight requests, not a shared budget of 8. Bound your own
outer concurrency explicitly — for example, one `Directory.crawl()` in
flight per host at a time, gated by your own `asyncio.Semaphore`:

```python
import asyncio

host_sem = asyncio.Semaphore(50)  # your own outer bound, tuned to your fleet

async def crawl_bounded(url: str, session):
    async with host_sem:
        return await crawl_one_host(url, session)
```

`RESTGDF_TIMEOUT_TOTAL_S` (default `30` seconds) applies a per-request
timeout to every metadata call, so one black-holing host cannot hang the
crawl indefinitely — but one `Directory.crawl()` call still walks its
*folders* serially (one `get_metadata` per folder, in a plain loop), so a
directory with many slow folders/services accumulates those timeouts inside
that single call. That is another reason to bound your own outer concurrency
across hosts rather than relying on the per-call cap alone.

**Cap `max_attempts` on flaky estates.** Layer-failure containment (3.3)
means every layer of a dead service is now dispatched instead of the first
failure cancelling its siblings — measured at 3.1× the per-layer requests
against a 50-layer dead service. That composes with the broadened retried
set: at the default `max_attempts=5`, one dead service goes from ~80 attempts
to ~250. The token bucket and 429 cooldown still pace the *rate*, so this is
volume and wall-clock, not a politeness violation — but on an estate with
many dead or half-dead hosts, lower `ResilienceConfig.max_attempts` (2–3) or
`retry_budget_s` so a dead service is written off quickly.

If you are aggregating `Directory.report` (`CrawlReport`) across many hosts,
note that `CrawlError.exception` retains the live exception object (and its
traceback) for re-raise support — drop reports (or clear
`report.errors[*].exception`) between shards on a very large, long-running
aggregate crawl to avoid holding onto tracebacks longer than you need to.

## Live vs. inert vs. deprecated knobs (3.3)

"Live" means the knob is read at runtime — but by which route depends on the
knob: the `ResilienceConfig.*` rows are read from the config object you hand
to a `ResilientSession` (their `RESTGDF_RESILIENCE_*` env forms apply only if
you build the session from `get_config().resilience`), while the bare
`RESTGDF_*` rows at the bottom are process-global and read from `get_config()`
at request time. See [Two configuration mechanisms](#two-configuration-mechanisms-know-which-one-you-are-using).

| Knob | Status | Notes |
|---|---|---|
| `ResilienceConfig.enabled` / `RESTGDF_RESILIENCE_ENABLED` | live | sole retry/limiter gate |
| `ResilienceConfig.rate_per_service_root_per_second` / `RESTGDF_RESILIENCE_RATE_PER_SERVICE_ROOT_PER_SECOND` | live | sub-1.0 valid (3.3) |
| `ResilienceConfig.limiter_key` / `RESTGDF_RESILIENCE_LIMITER_KEY` | live (new 3.3) | `"service_root"` (default) or `"host"` |
| `ResilienceConfig.respect_retry_after_max_s` / `RESTGDF_RESILIENCE_RESPECT_RETRY_AFTER_MAX_S` | live | caps an honoured `Retry-After` |
| `ResilienceConfig.fallback_retry_after_seconds` / `RESTGDF_RESILIENCE_FALLBACK_RETRY_AFTER_SECONDS` | live | used when a 429 has no `Retry-After` |
| `ResilienceConfig.max_attempts` / `RESTGDF_RESILIENCE_MAX_ATTEMPTS` | live (new 3.3) | default `5` |
| `ResilienceConfig.retry_budget_s` / `RESTGDF_RESILIENCE_RETRY_BUDGET_S` | live (new 3.3) | total wall-clock budget, default `60.0` |
| `ResilienceConfig.wait_initial_s` / `RESTGDF_RESILIENCE_WAIT_INITIAL_S` | live (new 3.3) | default `0.5` |
| `ResilienceConfig.wait_max_s` / `RESTGDF_RESILIENCE_WAIT_MAX_S` | live (new 3.3) | default `10.0` |
| `ResilienceConfig.wait_jitter_s` / `RESTGDF_RESILIENCE_WAIT_JITTER_S` | live (new 3.3) | default `1.0` |
| `ResilienceConfig.backend` / `RESTGDF_RESILIENCE_BACKEND` | **deprecated** (3.3) | `"stamina"` is the only backend; setting the env var now warns |
| `RetryConfig.max_attempts` / `RESTGDF_RETRY_MAX_ATTEMPTS` | inert + deprecated | superseded by `ResilienceConfig.max_attempts`; still warns |
| `RetryConfig.max_delay_s` / `RESTGDF_RETRY_MAX_DELAY_S` | inert + deprecated | superseded by `ResilienceConfig.retry_budget_s`; still warns |
| `LimiterConfig.rate_per_host` / `RESTGDF_LIMITER_RATE_PER_HOST` | inert + deprecated | superseded by `rate_per_service_root_per_second` + `limiter_key="host"`; still warns |
| `RESTGDF_TRANSPORT_USER_AGENT` | live | the sanctioned crawl-path UA lever (Step 3) |
| `RESTGDF_CONCURRENCY_MAX_CONCURRENT_REQUESTS` | live | per-call, not process-wide (Step 4) |
| `RESTGDF_TIMEOUT_TOTAL_S` | live | per-request timeout (Step 4) |

Setting an inert or deprecated `RESTGDF_*` knob emits a one-time
`InertConfigWarning`/`DeprecationWarning` naming its live replacement — see
{doc}`/configuration`.

### Budget vs. cooldown, briefly

`retry_budget_s` is a *total* wall-clock budget for one request's retry
loop, and an honoured 429 `Retry-After` cooldown sleeps *inside* that budget
— it is not extra time on top. If `respect_retry_after_max_s` (default
`60.0`) is at or above `retry_budget_s` (default `60.0`), one long cooldown
can consume the whole budget, collapsing "5 attempts" down to roughly one
cooldown cycle before the request gives up. The two are equal by default
deliberately; lower `respect_retry_after_max_s` below `retry_budget_s` if
you want more than one real retry to survive a 429.

## Putting it together

```python
import asyncio
import os

from aiohttp import ClientSession
from restgdf import Directory, ResilienceConfig, reset_config_cache
from restgdf.resilience import ResilientSession

HOST_URLS = [
    "https://gis1.example-county.gov/arcgis/rest/services",
    "https://gis.example-city.gov/arcgis/rest/services",
    # ... many more small government hosts
]

# Process-global transport knob: must go through the environment, and must be
# set before the first request (or followed by reset_config_cache()).
os.environ["RESTGDF_TRANSPORT_USER_AGENT"] = "mycrawler/1.0 (contact: you@example.org)"
reset_config_cache()

# Per-session knob: read only by the ResilientSession it is handed to.
polite_resilience = ResilienceConfig(
    enabled=True,
    rate_per_service_root_per_second=0.5,
    limiter_key="host",
    max_attempts=3,  # write off dead hosts quickly on a large estate
)

host_sem = asyncio.Semaphore(50)

async def crawl_host(url: str) -> list:
    async with ClientSession() as raw, host_sem:
        session = ResilientSession(raw, polite_resilience)
        directory = await Directory.from_url(url, session=session)
        return await directory.crawl()

async def main():
    return await asyncio.gather(*(crawl_host(u) for u in HOST_URLS))

asyncio.run(main())
```

For a known multi-tenant SaaS shard, build a second `ResilienceConfig` with
`limiter_key="service_root"` (or a higher host rate) and route that shard's
hosts through a session wrapped with it instead — one `ResilienceConfig` per
politeness policy, not one for the whole crawl.

## See also

- {doc}`/resilience` — the `ResilienceConfig`/`ResilientSession` reference
  and a minimal wrapping example.
- {doc}`/configuration` — the full `RESTGDF_*` environment variable table.
- {doc}`tracing` — set `logging.getLogger("restgdf.retry")` to `DEBUG` to
  observe scheduled retries, 429 cooldowns, and exhaustion mapping live
  during a crawl.
