# Observability with OpenTelemetry

`restgdf` ships an optional `[telemetry]` extra that integrates with
[OpenTelemetry](https://opentelemetry.io/) for distributed tracing and
log correlation.

## Installation

```bash
pip install restgdf[telemetry]
```

This pulls in `opentelemetry-api` and
`opentelemetry-instrumentation-aiohttp-client`.

## Quick start

```python
from restgdf.telemetry import RestgdfInstrumentor

# Instrument aiohttp client sessions (adds CLIENT spans for every HTTP call)
instrumentor = RestgdfInstrumentor()
instrumentor.instrument()
```

Enable the feature-layer stream span via configuration:

```python
import os
os.environ["RESTGDF_TELEMETRY_ENABLED"] = "true"
```

Or in code:

```python
from restgdf import Config
cfg = Config(telemetry={"enabled": True, "service_name": "my-etl"})
```

## Span hierarchy

When telemetry is enabled, `feature_layer_stream_span` produces a single
**INTERNAL** span named `feature_layer.stream` that acts as the parent for
all `aiohttp` CLIENT spans generated during pagination:

```
feature_layer.stream (INTERNAL)
├── GET /FeatureServer/0/query (CLIENT)
├── GET /FeatureServer/0/query (CLIENT)
└── ...
```

Custom attributes use the `restgdf.*` namespace:

| Attribute               | Description                   |
|-------------------------|-------------------------------|
| `restgdf.service_root`  | Scrubbed service URL          |
| `restgdf.layer_id`      | ArcGIS layer ID               |
| `restgdf.out_fields`    | Requested fields              |
| `restgdf.where`         | Query filter                  |

## Log correlation

`restgdf` automatically attaches a `_SpanContextFilter` to the root
`restgdf` logger. When an OTel span is active, every log record gains
`trace_id` and `span_id` attributes:

```python
import logging
fmt = "%(levelname)s [trace=%(trace_id)s span=%(span_id)s] %(message)s"
logging.basicConfig(format=fmt)
```

For non-restgdf loggers, use the convenience helper:

```python
from restgdf.telemetry import span_context_fields

fields = span_context_fields()
# {'trace_id': '00000000000000000000000000000001', 'span_id': '0000000000000001'}
```

## Disabling telemetry

Telemetry is **disabled by default** (`TelemetryConfig.enabled = False`).
Set `RESTGDF_TELEMETRY_ENABLED=false` or omit the env var entirely to
keep telemetry off.

## Base-install safety

`import restgdf.telemetry` always succeeds, even without OTel packages.
Functions that require OTel at runtime raise
{class}`~restgdf.errors.OptionalDependencyError` with a helpful install
hint.
