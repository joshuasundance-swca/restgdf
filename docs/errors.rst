Error handling
==============

All runtime failures raise a subclass of :class:`~restgdf.errors.RestgdfError`.
The hierarchy lets callers catch broad categories (transport vs. service vs.
schema) without giving up precise handling when they want it.

Hierarchy
---------

.. code-block:: text

   RestgdfError
   ├── ConfigurationError (ValueError)
   │   └── OptionalDependencyError (ModuleNotFoundError)
   ├── RestgdfResponseError (ValueError)
   │   ├── SchemaValidationError
   │   │   └── FieldDoesNotExistError
   │   ├── ArcGISServiceError
   │   │   └── PaginationError (IndexError)
   │   └── AuthenticationError (PermissionError)
   │       ├── InvalidCredentialsError
   │       ├── TokenExpiredError
   │       ├── TokenRequiredError
   │       ├── TokenRefreshFailedError
   │       └── AuthNotAttachedError
   ├── TransportError
   │   ├── RestgdfTimeoutError (TimeoutError)
   │   └── RateLimitError
   └── OutputConversionError

Each exception co-inherits from a matching stdlib type (shown in parentheses)
so existing ``except ValueError:`` or ``except TimeoutError:`` clauses
continue to catch restgdf errors without code changes.

Common patterns
---------------

**Handling pagination failures:**

.. code-block:: python

   from restgdf.errors import PaginationError

   try:
       gdf = await layer.get_gdf()
   except PaginationError as exc:
       print(f"Page {exc.batch_index} failed (page_size={exc.page_size})")
       # Retry with smaller pages or use stream_rows(on_truncation="split")

**Handling auth errors:**

.. code-block:: python

   from restgdf.errors import AuthenticationError, TokenExpiredError

   try:
       layer = await FeatureLayer.from_url(url, session=token_session)
   except TokenExpiredError:
       # Token refresh failed after retries
       pass
   except AuthenticationError as exc:
       print(f"Auth failed: {exc.url} → HTTP {exc.status_code}")

**Handling missing dependencies:**

.. code-block:: python

   from restgdf.errors import OptionalDependencyError

   try:
       gdf = await layer.get_gdf()
   except OptionalDependencyError as exc:
       print(exc)  # "geopandas required — pip install 'restgdf[geo]'"

**Handling rate limits (with resilience extra):**

.. code-block:: python

   from restgdf.errors import RateLimitError

   try:
       data = await session.get(url)
   except RateLimitError as exc:
       print(f"429 at {exc.url}, retry after {exc.retry_after}s")

**Broad catch for all restgdf errors:**

.. code-block:: python

   from restgdf.errors import RestgdfError

   try:
       result = await layer.get_gdf()
   except RestgdfError as exc:
       logger.error("restgdf operation failed", exc_info=exc)

Structured attributes
---------------------

Many exceptions carry structured metadata for programmatic recovery:

.. list-table::
   :header-rows: 1

   * - Exception
     - Attributes
   * - ``RestgdfResponseError``
     - ``url``, ``status_code``, ``request_id``, ``model_name``, ``raw``
   * - ``TransportError``
     - ``url``, ``status_code``
   * - ``RestgdfTimeoutError``
     - ``url``, ``timeout_kind`` (``"connect"``, ``"read"``, ``"total"``)
   * - ``RateLimitError``
     - ``url``, ``status_code``, ``retry_after``
   * - ``PaginationError``
     - ``batch_index``, ``page_size``
   * - ``FieldDoesNotExistError``
     - ``field``, ``context``

See also
--------

- :doc:`restgdf` — full API reference for all exception classes
- :doc:`recipes/tracing` — resilience extra error attributes in context
