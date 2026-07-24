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
     - Total HTTP timeout in seconds
   * - ``RESTGDF_TRANSPORT_USER_AGENT``
     - ``"restgdf/<version>"``
     - User-Agent header value
   * - ``RESTGDF_CONCURRENCY_MAX_CONCURRENT_REQUESTS``
     - ``8``
     - Global concurrency cap for parallel page fetches
   * - ``RESTGDF_RESILIENCE_ENABLED``
     - ``false``
     - Enable retry + rate limiting (requires ``restgdf[resilience]``)
   * - ``RESTGDF_RESILIENCE_RATE_PER_SERVICE_ROOT_PER_SECOND``
     - ``10.0``
     - Token-bucket refill rate per service root
   * - ``RESTGDF_RESILIENCE_RESPECT_RETRY_AFTER_MAX_S``
     - ``60``
     - Max seconds to honor from a server ``Retry-After`` header
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

Config model reference
----------------------

.. autopydantic_model:: restgdf.Config
   :model-show-json: false
   :model-show-config-summary: false

.. autofunction:: restgdf.get_config
