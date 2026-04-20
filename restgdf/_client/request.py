"""Request-body construction helpers for ArcGIS REST calls.

The helpers here capture the exact merge semantics observed in the
legacy call sites in :mod:`restgdf.utils.getinfo`. They are intentionally
narrow: one helper per distinct merge policy. Do not add a generic "merge
policy" parameter. If a new call site needs different semantics, add a new
helper rather than overloading an existing one.
"""

from __future__ import annotations


from collections.abc import Mapping


def build_conservative_query_data(
    base: Mapping[str, object],
    caller_data: Mapping[str, object] | None = None,
) -> dict:
    """Return a POST body for a ``returnCountOnly`` / ``returnIdsOnly`` /
    ``returnDistinctValues`` ArcGIS REST request.

    The returned dict starts as a shallow copy of ``base``. Only two keys
    from ``caller_data`` are ever forwarded: ``where`` and ``token``.
    Every other caller-supplied key is intentionally dropped so the
    operation-specific flags in ``base`` (``returnCountOnly``, ``f=json``,
    etc.) cannot be clobbered by an accidental caller override.

    Semantics (matches pre-refactor behavior in
    :func:`restgdf.utils.getinfo.get_feature_count`,
    :func:`restgdf.utils.getinfo.get_object_ids`, and
    :func:`restgdf.utils.getinfo.getuniquevalues`):

    * If ``caller_data`` is falsy (``None`` or empty), ``base`` is returned
      unchanged (as a new dict).
    * If ``caller_data`` is truthy, ``where`` is overwritten with
      ``caller_data.get("where", "1=1")``. This means a truthy caller_data
      without a ``where`` key still resets ``where`` to ``"1=1"`` — a
      deliberate no-op when ``base`` already has that default but a
      behavioral quirk to preserve.
    * If ``caller_data`` contains ``token``, it is copied through.
    """
    datadict: dict = dict(base)
    if not caller_data:
        return datadict
    datadict["where"] = caller_data.get("where", "1=1")
    if "token" in caller_data:
        datadict["token"] = caller_data["token"]
    return datadict
