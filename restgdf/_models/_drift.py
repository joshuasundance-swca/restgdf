"""Shared drift adapter for pydantic response parsing.

This module defines the two response-model tiers used across the library:

* :class:`PermissiveModel` — ``extra="allow"``, accepts any payload, logs
  drift. Used for metadata, service, folder, and crawl shapes where ArcGIS
  vendor variance is expected.
* :class:`StrictModel` — ``extra="ignore"``, raises
  :class:`~restgdf._models.RestgdfResponseError` on validation failure.
  Used for operation-critical envelopes (count, object-ids, token,
  error envelope, feature response envelope).

The :func:`_parse_response` adapter is the single call-site that every
parser uses to convert a raw dict into a validated model. It dedupes
drift log records on ``(model_name, path, kind, value_type)`` so a
pathological server does not spam the log.
"""

from __future__ import annotations

import logging
from typing import Any, TypeVar

from pydantic import BaseModel, ConfigDict, ValidationError

from restgdf._logging import get_drift_logger
from restgdf._models._errors import RestgdfResponseError

_DriftKey = tuple[str, str, str, str]

_seen_drift: set[_DriftKey] = set()


def reset_drift_cache() -> None:
    """Clear the per-process drift dedupe cache.

    Tests that exercise drift-log assertions should call this in a
    fixture so each test sees a fresh dedupe state.
    """
    _seen_drift.clear()


class PermissiveModel(BaseModel):
    """Base for ArcGIS payloads where vendor variance is expected.

    Extra keys are kept on the model (``extra="allow"``) and consumed
    fields are declared as ``Optional`` so missing-field drift never
    raises. The :func:`_parse_response` adapter additionally catches
    :class:`~pydantic.ValidationError` on fields that fail type coercion,
    logs the offending field as drift, and returns a partially-filled
    instance instead of raising.
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True)


class StrictModel(BaseModel):
    """Base for operation-critical ArcGIS envelopes.

    Validation failures are wrapped in
    :class:`~restgdf._models.RestgdfResponseError` with the original
    payload and request context attached so operators can triage ArcGIS
    vendor incidents.
    """

    model_config = ConfigDict(extra="ignore", populate_by_name=True)


_M = TypeVar("_M", bound=BaseModel)


def _known_keys(model_cls: type[BaseModel]) -> set[str]:
    """Return the set of attribute names and aliases the model declares."""
    names: set[str] = set()
    for name, info in model_cls.model_fields.items():
        names.add(name)
        if info.alias:
            names.add(info.alias)
        choices = info.validation_alias
        if choices is not None:
            try:
                for choice in choices.choices:
                    if isinstance(choice, str):
                        names.add(choice)
            except AttributeError:
                pass
    return names


def _log_drift(
    *,
    model_name: str,
    path: str,
    kind: str,
    sample: Any,
    level: int,
) -> None:
    """Emit a deduped drift log record.

    Dedupe key is ``(model_name, path, kind, type(sample).__name__)`` so
    repeated occurrences of the same drift against the same model do not
    spam the log; semantically-distinct drift (different field or
    different observed type) still logs.
    """
    sample_type = type(sample).__name__
    key: _DriftKey = (model_name, path, kind, sample_type)
    if key in _seen_drift:
        return
    _seen_drift.add(key)
    logger = get_drift_logger()
    logger.log(
        level,
        "schema drift on %s: field=%r kind=%s observed_type=%s sample=%r",
        model_name,
        path,
        kind,
        sample_type,
        sample,
    )


def _parse_response(
    model_cls: type[_M],
    raw: Any,
    *,
    context: str,
) -> _M:
    """Validate ``raw`` against ``model_cls`` honoring the tier contract.

    Parameters
    ----------
    model_cls
        A :class:`PermissiveModel` or :class:`StrictModel` subclass.
    raw
        The JSON-decoded payload. For permissive parsing non-mapping
        input is treated as an empty mapping with drift logged; strict
        parsing raises :class:`RestgdfResponseError` unchanged.
    context
        Operator-visible identifier (URL, helper name) surfaced on any
        :class:`RestgdfResponseError` raised by strict parsing.
    """
    is_strict = issubclass(model_cls, StrictModel)
    if is_strict:
        try:
            instance: _M = model_cls.model_validate(raw)
            return instance
        except ValidationError as exc:
            raise RestgdfResponseError(
                f"{model_cls.__name__} validation failed: {exc.errors()!r}",
                model_name=model_cls.__name__,
                context=context,
                raw=raw,
            ) from exc

    cleaned: dict[str, Any] = dict(raw) if isinstance(raw, dict) else {}
    if not isinstance(raw, dict):
        _log_drift(
            model_name=model_cls.__name__,
            path="<root>",
            kind="not_a_mapping",
            sample=raw,
            level=logging.WARNING,
        )

    try:
        instance = model_cls.model_validate(cleaned)
    except ValidationError as exc:
        # Strip failing fields, log each as drift, and revalidate.
        for error in exc.errors():
            loc = error.get("loc", ())
            if not loc:
                continue
            top = loc[0]
            if not isinstance(top, str) or top not in cleaned:
                continue
            _log_drift(
                model_name=model_cls.__name__,
                path=".".join(str(p) for p in loc),
                kind="bad_type",
                sample=cleaned[top],
                level=logging.DEBUG,
            )
            cleaned.pop(top, None)
        instance = model_cls.model_validate(cleaned)

    # Detect unknown extras (keys present in raw but not declared on model).
    if isinstance(raw, dict):
        known = _known_keys(model_cls)
        for extra_key, extra_val in raw.items():
            if extra_key in known:
                continue
            _log_drift(
                model_name=model_cls.__name__,
                path=extra_key,
                kind="unknown_extra",
                sample=extra_val,
                level=logging.DEBUG,
            )

    result: _M = instance
    return result


__all__ = [
    "PermissiveModel",
    "StrictModel",
    "_parse_response",
    "reset_drift_cache",
]
