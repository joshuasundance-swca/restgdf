Configuration
=============

``restgdf`` uses a layered configuration system based on
`Pydantic Settings <https://docs.pydantic.dev/latest/concepts/pydantic_settings/>`_.
Values resolve in this order (highest precedence first):

1. **Explicit constructor arguments** — e.g. ``FeatureLayer.from_url(timeout=…)``
2. **``Config(...)`` instance** passed explicitly
3. **Process environment variables** (``RESTGDF_*``)
4. **``.env`` file** in the working directory
5. **Library defaults**

Quick start
-----------

.. code-block:: python

   from restgdf import Config, get_config

   # Read from environment + defaults
   cfg = get_config()

   # Override explicitly
   cfg = Config(
       transport={"timeout_total": 120},
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
   * - ``RESTGDF_TRANSPORT_TIMEOUT_TOTAL``
     - ``300``
     - Total HTTP timeout in seconds
   * - ``RESTGDF_TRANSPORT_USER_AGENT``
     - ``"restgdf/<version>"``
     - User-Agent header value
   * - ``RESTGDF_CONCURRENCY_MAX_CONCURRENT_REQUESTS``
     - ``10``
     - Global concurrency cap for parallel page fetches
   * - ``RESTGDF_AUTH_TRANSPORT``
     - ``"header"``
     - Token delivery method: ``"header"`` or ``"body"``
   * - ``RESTGDF_AUTH_REFRESH_LEEWAY_SECONDS``
     - ``120``
     - Seconds before expiry to trigger proactive refresh
   * - ``RESTGDF_AUTH_CLOCK_SKEW_SECONDS``
     - ``30``
     - Clock skew tolerance for token expiry comparison
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

Config model reference
----------------------

.. autopydantic_model:: restgdf.Config
   :model-show-json: false
   :model-show-config-summary: false

.. autofunction:: restgdf.get_config
