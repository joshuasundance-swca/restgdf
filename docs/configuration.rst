Configuration
=============

``restgdf`` uses a layered, environment-variable + explicit-argument
configuration system. Values resolve in this order (highest precedence first):

1. **Explicit constructor / aiohttp keyword arguments** — e.g.
   ``FeatureLayer.from_url(timeout=…)``, applied per call
2. **Process environment variables** (``RESTGDF_*``), read by
   ``Config.from_env`` and exposed process-globally through the
   size-1-cached ``get_config()``
3. **Library defaults**

``restgdf`` does not read a ``.env`` file itself — ``Config.from_env()`` resolves values
from the process environment (``os.environ``) only, and ``python-dotenv`` is not a
``restgdf`` dependency. If you want ``.env``-file support, load it explicitly and pass
the merged mapping in:

.. code-block:: python

   from dotenv import dotenv_values
   from restgdf import Config
   import os

   cfg = Config.from_env(env={**dotenv_values(".env"), **os.environ})

Quick start
-----------

.. code-block:: python

   from restgdf import Config, get_config

   # Resolve from the environment + defaults — this is the instance the
   # request path reads.
   cfg = get_config()

   # Build an explicit Config object (for tests, or an
   # ``ArcGISTokenSession(config=...)``); a directly built Config is not
   # injected into the FeatureLayer/Directory request path.
   cfg = Config(
       timeout={"total_s": 120},
       concurrency={"max_concurrent_requests": 8},
   )

Environment variables
---------------------

All environment variables use the ``RESTGDF_`` prefix followed by
``<CATEGORY>_<FIELD>`` in uppercase. Legacy flat names (without category)
are supported with a ``DeprecationWarning``.

.. list-table::
   :header-rows: 1
   :widths: 40 15 45

   * - Variable
     - Default
     - Description
   * - ``RESTGDF_TIMEOUT_TOTAL_S``
     - ``30``
     - Total HTTP timeout in seconds, applied per request on the metadata/crawl and query paths
   * - ``RESTGDF_TRANSPORT_USER_AGENT``
     - ``"restgdf/<version>"``
     - User-Agent header value. This is the sanctioned lever for bulk/crawl
       traffic (see :doc:`recipes/bulk_crawl`) — a per-request
       ``headers={"User-Agent": ...}`` override still wins, but only on the
       feature/query surfaces, not on the metadata/``Directory``/crawl path,
       and a session-level ``ClientSession(headers=...)`` User-Agent does not
       survive there either.
   * - ``RESTGDF_CONCURRENCY_MAX_CONCURRENT_REQUESTS``
     - ``8``
     - Concurrency cap for parallel page/layer fetches **within one**
       top-level call (``safe_crawl``/``Directory.crawl``/streaming) — not a
       process-wide budget. Concurrent top-level calls each get their own
       cap; bound your own outer concurrency across calls (see
       :doc:`recipes/bulk_crawl`).
   * - ``RESTGDF_RESILIENCE_ENABLED``
     - ``false``
     - Sole gate for retry + rate limiting on a ``ResilientSession``
       (requires ``restgdf[resilience]``); setting it alone does not apply
       resilience unless a session is explicitly wrapped with
       ``ResilientSession`` and passed to ``FeatureLayer``/``Directory``.
   * - ``RESTGDF_RESILIENCE_LIMITER_KEY``
     - ``"service_root"``
     - Rate-limit/cooldown key granularity: ``"service_root"`` (default,
       one bucket per ArcGIS service) or ``"host"`` (one bucket per
       ``scheme://host`` — the polite choice when many services share a
       host)
   * - ``RESTGDF_RESILIENCE_RATE_PER_SERVICE_ROOT_PER_SECOND``
     - unset (limiter disabled)
     - Token-bucket refill rate, enforced at ``RESTGDF_RESILIENCE_LIMITER_KEY``
       granularity; sub-1.0 rates (e.g. ``0.5``) are valid
   * - ``RESTGDF_RESILIENCE_RESPECT_RETRY_AFTER_MAX_S``
     - ``60``
     - Max seconds to honor from a server ``Retry-After`` header
   * - ``RESTGDF_RESILIENCE_FALLBACK_RETRY_AFTER_SECONDS``
     - ``5``
     - Cooldown used for a 429 with no ``Retry-After`` header
   * - ``RESTGDF_RESILIENCE_MAX_ATTEMPTS``
     - ``5``
     - Retry attempts before exhaustion
   * - ``RESTGDF_RESILIENCE_RETRY_BUDGET_S``
     - ``60``
     - Total wall-clock retry budget (in-attempt cooldown sleeps count
       against it — see :doc:`recipes/bulk_crawl`)
   * - ``RESTGDF_RESILIENCE_WAIT_INITIAL_S``
     - ``0.5``
     - Initial exponential-backoff wait
   * - ``RESTGDF_RESILIENCE_WAIT_MAX_S``
     - ``10``
     - Max exponential-backoff wait
   * - ``RESTGDF_RESILIENCE_WAIT_JITTER_S``
     - ``1``
     - Max random jitter added to each backoff wait
   * - ``RESTGDF_RESILIENCE_BACKEND``
     - ``"stamina"``
     - **Deprecated (3.3), removed in 4.0.** Dead config — ``"stamina"`` is
       the only implementation; setting this now emits a
       ``DeprecationWarning``.
   * - ``RESTGDF_RETRY_MAX_ATTEMPTS`` / ``RESTGDF_RETRY_MAX_DELAY_S``
     - n/a
     - **Inert + deprecated (3.3), removed in 4.0.** Superseded by
       ``RESTGDF_RESILIENCE_MAX_ATTEMPTS`` / ``RESTGDF_RESILIENCE_RETRY_BUDGET_S``;
       setting either emits ``InertConfigWarning``.
   * - ``RESTGDF_LIMITER_RATE_PER_HOST``
     - n/a
     - **Inert + deprecated (3.3), removed in 4.0.** Superseded by
       ``RESTGDF_RESILIENCE_RATE_PER_SERVICE_ROOT_PER_SECOND`` with
       ``RESTGDF_RESILIENCE_LIMITER_KEY=host``; setting it emits
       ``InertConfigWarning``.
   * - ``RESTGDF_TELEMETRY_ENABLED``
     - ``false``
     - Enable OpenTelemetry spans (requires ``restgdf[telemetry]``)
   * - ``RESTGDF_TELEMETRY_SERVICE_NAME``
     - ``"restgdf"``
     - OTel service name for emitted spans

The token-session knobs ``AuthConfig.transport``, ``refresh_leeway_s``, and
``clock_skew_s`` are **not** driven by dedicated ``RESTGDF_AUTH_*`` environment
variables. Set them on an explicit ``Config`` instead — for example
``Config(auth=AuthConfig(transport="body", refresh_leeway_s=180, clock_skew_s=45))``.

For a full worked example composing the resilience + concurrency + User-Agent
knobs above for a bulk, multi-host crawl, see :doc:`recipes/bulk_crawl`.

Config model reference
----------------------

.. autopydantic_model:: restgdf.Config
   :model-show-json: false
   :model-show-config-summary: false

.. autofunction:: restgdf.get_config
