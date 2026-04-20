"""Compatibility helpers for the 1.x → 2.x migration.

Downstream code that indexed the legacy dict-based public surface (for
example ``metadata["name"]``, ``crawl_result["services"]``) needs a
short-term way to keep working during its own upgrade window. These
helpers convert the 2.x pydantic models back into plain Python
structures on demand.

They are **migration aids**, not the primary API — prefer direct
attribute access (``metadata.name``) and ``model_dump()`` in new code.
These helpers will stay available for the 2.x series but may be removed
in 3.x.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

__all__ = ["as_dict", "as_json_dict"]


def as_dict(obj: Any) -> Any:
    """Return a plain Python dict view of a restgdf pydantic model.

    If ``obj`` is a :class:`pydantic.BaseModel` instance, returns
    ``obj.model_dump(mode="python", by_alias=False)`` — a dict keyed by
    the model's Python (snake_case) field names, with nested models
    also recursively dumped.

    If ``obj`` is anything else (already-a-dict, ``None``, primitive,
    list), it is returned unchanged. This lets migration code wrap
    heterogeneous values uniformly::

        for entry in report.services:
            row = as_dict(entry)   # dict whether entry is model or already dict
            save(row["name"], row.get("url"))

    This helper is intentionally conservative: it does not recurse into
    containers of models and does not coerce ``by_alias=True``. Callers
    that need the ArcGIS-native camelCase round-trip should call
    :meth:`~pydantic.BaseModel.model_dump` explicitly.
    """
    if isinstance(obj, BaseModel):
        return obj.model_dump(mode="python", by_alias=False)
    return obj


def as_json_dict(obj: Any) -> Any:
    """Return a JSON-safe dict view of a restgdf pydantic model.

    Like :func:`as_dict`, but uses ``model_dump(mode="json")`` so every
    nested value is a JSON-serializable primitive
    (``SecretStr`` → ``"**********"`` placeholder, ``datetime`` → ISO
    string, etc.). Handy for structured logging of a model without
    carrying unserializable objects into the log record.

    Non-model values are returned unchanged.
    """
    if isinstance(obj, BaseModel):
        return obj.model_dump(mode="json", by_alias=False)
    return obj
