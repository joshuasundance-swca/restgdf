Resilience
==========

The ``restgdf[resilience]`` extra adds automatic retry with exponential
back-off, configurable per-service-root or per-host rate limiting, and 429
cooldown handling. **Installing the extra does not change any request
behavior on its own** — ``FeatureLayer``/``Directory`` always take a
caller-owned session and never construct or wrap one for you. Opting in is
two explicit steps:

1. Install the extra and construct a ``restgdf.ResilienceConfig`` with
   ``enabled=True``.
2. Wrap your own :class:`~aiohttp.ClientSession` with
   :class:`~restgdf.resilience.ResilientSession` and pass *that* as the
   ``session=`` argument everywhere you would normally pass a plain
   ``aiohttp.ClientSession``.

.. code-block:: bash

   pip install "restgdf[resilience]"

.. code-block:: python

   from aiohttp import ClientSession
   from restgdf import Directory, ResilienceConfig
   from restgdf.resilience import ResilientSession

   resilience_cfg = ResilienceConfig(
       enabled=True,
       rate_per_service_root_per_second=5.0,
   )

   async def main():
       async with ClientSession() as raw:
           session = ResilientSession(raw, resilience_cfg)
           directory = await Directory.from_url(
               "https://maps1.vcgov.org/arcgis/rest/services",
               session=session,
           )
           return await directory.crawl()

``ResilientSession`` is transparent: it implements the same ``get``/``post``
shape as a plain ``aiohttp.ClientSession``, so every request issued through
it — by ``Directory``, ``FeatureLayer``, or a raw call — is rate-limited and
retried uniformly. ``ResilienceConfig.enabled`` is the sole gate; the other
fields only tune an already-enabled session.

For a crawl spanning many independent hosts — including how to pick
per-host vs. per-service-root rate-limit granularity, set a polite
User-Agent, and bound your own outer concurrency — see
:doc:`recipes/bulk_crawl`. See :doc:`recipes/tracing` for observing retries
and cooldowns via logging.

Environment variables vs. explicit config
-----------------------------------------

A ``ResilienceConfig`` you construct is read **only** by the
``ResilientSession`` you hand it to, and building one does not consult
``RESTGDF_RESILIENCE_*``. The example above therefore ignores the
environment by design. To honour it, build the session from the
process-global config instead:

.. code-block:: python

   from restgdf import get_config, reset_config_cache
   from restgdf.resilience import ResilientSession

   # reads RESTGDF_RESILIENCE_ENABLED / _MAX_ATTEMPTS / _LIMITER_KEY / ...
   session = ResilientSession(raw, get_config().resilience)

``get_config()`` is cached; call ``reset_config_cache()`` if you change a
variable mid-process. Note the asymmetry: resilience knobs are per-session
and passed explicitly, while the transport / concurrency / timeout knobs
(``RESTGDF_TRANSPORT_USER_AGENT``,
``RESTGDF_CONCURRENCY_MAX_CONCURRENT_REQUESTS``, ``RESTGDF_TIMEOUT_TOTAL_S``)
are process-global and read from ``get_config()`` at request time — a
``Config`` instance you build yourself is never threaded into the request
path (CONFIG-03).

restgdf.resilience
------------------

.. automodule:: restgdf.resilience
   :members:
   :undoc-members:
   :show-inheritance:
