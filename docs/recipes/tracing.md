# Tracing & Observability

This recipe shows how to add structured observability to `restgdf` requests
using the resilience extra and Python's standard `logging` / `structlog`.

## Prerequisites

```bash
pip install "restgdf[resilience]"
```

## Enable resilience + logging

```python
import logging

from restgdf import Config, ResilienceConfig

logging.basicConfig(level=logging.DEBUG)

cfg = Config(
    resilience=ResilienceConfig(
        enabled=True,
        rate_per_service_root_per_second=10.0,
    ),
)
```

The `restgdf.resilience` module logs every retry attempt, 429 cooldown, and
error mapping through the `restgdf.retry` logger at **DEBUG** level:

- `retry scheduled: attempt=N wait=…s caused_by=…` before each retried attempt.
  The `wait` is the *scheduled* pre-jitter backoff — the actual sleep adds up
  to `ResilienceConfig.wait_jitter_s` (default `1.0` s) on top, so a logged
  `wait=0.500s` can be a 1.4 s sleep.
- `429 cooldown set: key=… seconds=…` whenever a 429 sets a cooldown deadline
  (the `key` is the service root, or the host when
  `ResilienceConfig.limiter_key="host"`)
- `retry exhausted: … mapped to <ExceptionType>` when retries give up and the
  underlying failure is mapped to a `restgdf.errors` type

Each record also carries structured `extra` fields — `limit_key` (the
rate-limit/cooldown key), `retry_attempt`, `retry_delay_s`, `limiter_wait_s`
and `exception_type` — for a structured-logging handler.

Retries cover the request up to *headers received*. A failure raised while
the response body is read (a truncated body, `aiohttp.ClientPayloadError`) is
outside the retry scope and is not logged here — it surfaces raw to the
caller.

Set the logger to `DEBUG` to see each event (the `logging.basicConfig` call
above already does this if the root logger is at `DEBUG`; use the line below
if you only want `restgdf.retry` at a finer level than the rest of your app):

```python
logging.getLogger("restgdf.retry").setLevel(logging.DEBUG)
```

## Tracing individual requests

The `ResilientSession` wrapper is transparent — you use it exactly like a
plain `aiohttp.ClientSession`, but retries and rate limits happen
automatically:

```python
import asyncio

from aiohttp import ClientSession
from restgdf.resilience import ResilientSession

async def traced_query():
    async with ClientSession() as raw:
        session = ResilientSession(raw, cfg.resilience)
        url = "https://maps1.vcgov.org/arcgis/rest/services/Beaches/MapServer/6/query"
        params = {"where": "1=1", "f": "json", "resultRecordCount": "1"}
        async with session.get(url, params=params) as resp:
            data = await resp.json()
            print(data)

asyncio.run(traced_query())
```

## Inspecting error attributes

When the retry wrapper raises, the exception carries structured attributes
populated automatically:

| Exception                | Attributes                                          |
| ------------------------ | --------------------------------------------------- |
| `RestgdfResponseError`   | `url`, `status_code`, `request_id`, `model_name`    |
| `TransportError`         | `url`, `status_code`                                |
| `RestgdfTimeoutError`    | `url`, `timeout_kind` (`"connect"`, `"read"`, `"total"`) |
| `RateLimitError`         | `url`, `status_code`, `retry_after`                 |

Example:

```python
from restgdf.errors import RateLimitError, RestgdfTimeoutError

async def query_with_error_detail(session, url, params):
    try:
        async with session.get(url, params=params) as resp:
            return await resp.json()
    except RateLimitError as exc:
        print(f"429 at {exc.url}, retry after {exc.retry_after}s")
    except RestgdfTimeoutError as exc:
        print(f"Timeout ({exc.timeout_kind}) for {exc.url}")
```

## Integrating with OpenTelemetry

For full distributed tracing with automatic span creation, install the
``restgdf[telemetry]`` extra — see the {doc}`/recipes/observability` recipe.
The example below shows how to add *manual* spans around resilience-wrapped
calls using the structured error attributes:

```python
from opentelemetry import trace

tracer = trace.get_tracer("restgdf-app")

async def otel_query(session, url, params):
    with tracer.start_as_current_span("arcgis.query", attributes={"url": url}) as span:
        try:
            async with session.get(url, params=params) as resp:
                span.set_attribute("http.status_code", resp.status)
                return await resp.json()
        except Exception as exc:
            span.set_status(trace.StatusCode.ERROR, str(exc))
            for attr in ("url", "status_code", "timeout_kind", "retry_after"):
                val = getattr(exc, attr, None)
                if val is not None:
                    span.set_attribute(f"restgdf.{attr}", val)
            raise
```

## Monitoring 429 cooldowns

The `CooldownRegistry` and `LimiterRegistry` are per-`ResilientSession`
(not process-global), so each session has independent rate-limit state.

When a 429 response is received, the retry wrapper:

1. Parses the `Retry-After` header (integer seconds or RFC 7231 HTTP-date).
2. Clamps the value to `ResilienceConfig.respect_retry_after_max_s` (default 60 s).
3. Sets a *cooldown deadline* keyed by `ResilienceConfig.limiter_key`
   (default `"service_root"` — subsequent requests to the same
   `FeatureServer`/`MapServer` wait until the deadline passes; `"host"`
   applies the same cooldown to every service on that host).
4. Stamina's exponential back-off then retries the request.

The cooldown is **separate** from the token-bucket limiter — a 429 does
*not* drain `AsyncLimiter` tokens.
