Migration from 1.x to 2.0
=========================

restgdf 2.0 is a major release built on pydantic 2.13. The full
breaking-changes table, migration recipes, and troubleshooting guide
live in ``MIGRATION.md`` at the root of the repository:

  https://github.com/joshuasundance-swca/restgdf/blob/main/MIGRATION.md

Highlights
----------

- ``FeatureLayer.metadata`` and ``Directory.metadata`` are
  :class:`~restgdf.LayerMetadata` (pydantic ``BaseModel``) instead of
  plain ``dict``. Use attribute access::

      fl.metadata.name              # was fl.metadata["name"]
      fl.metadata.max_record_count  # was fl.metadata["maxRecordCount"]

- ``Directory.services`` and ``Directory.crawl(...)`` return
  ``list[CrawlServiceEntry]``. ``Directory.report`` is the full
  :class:`~restgdf.CrawlReport` (services + errors + root metadata)
  from the most recent crawl.

- Strict envelopes (:class:`~restgdf.CountResponse`,
  :class:`~restgdf.ObjectIdsResponse`,
  :class:`~restgdf.TokenResponse`) surface malformed payloads as
  :class:`~restgdf.RestgdfResponseError` with ``model_name``,
  ``context``, and ``raw`` attributes.

- :class:`~restgdf.AGOLUserPass` stores ``password`` as
  ``pydantic.SecretStr``. Call ``creds.password.get_secret_value()``
  only at the HTTP-POST boundary.

- The ``restgdf.schema_drift`` logger is silent by default; attach a
  handler to observe vendor variance in permissive payloads.

- :class:`~restgdf.Settings` / :func:`~restgdf.get_settings` centralize
  runtime configuration; override via ``RESTGDF_*`` environment
  variables.

- ``restgdf._types`` is a deprecated shim that re-exports the new
  pydantic models and emits ``DeprecationWarning``. It will be removed
  in 3.x.

Migration helpers
-----------------

``restgdf.compat.as_dict(model)`` and
``restgdf.compat.as_json_dict(model)`` convert a pydantic model back to
a plain dict for consumers that need the 1.x shape during a transitional
window. Non-model inputs pass through unchanged.

See :doc:`models` for the full typed surface.
