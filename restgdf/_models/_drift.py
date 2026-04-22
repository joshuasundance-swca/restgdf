"""Shared drift adapter for pydantic response parsing.

This module defines the two response-model tiers used across the library:

* :class:`PermissiveModel` — ``extra="allow"``, accepts variant payloads, logs
  drift. Used for metadata, service, folder, and crawl shapes where ArcGIS
  vendor variance is expected. A top-level ArcGIS ``{"error": {...}}``
  envelope is still surfaced as :class:`RestgdfResponseError` instead of
  being treated as harmless drift.
* :class:`StrictModel` — ``extra="ignore"``, raises
  :class:`~restgdf._models.RestgdfResponseError` on validation failure.
  Used for operation-critical envelopes (count, object-ids, token,
  explicit error envelope).

The :func:`_parse_response` adapter is the single call-site that every
parser uses to convert a raw dict into a validated model. It dedupes
drift log records on ``(model_name, path, kind, value_type)`` so a
pathological server does not spam the log.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping
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


def _sample_at_path(raw: Any, loc: tuple[Any, ...]) -> Any:
    """Best-effort sample extraction for a pydantic error location."""
    sample = raw
    for part in loc:
        try:
            if isinstance(sample, dict):
                sample = sample[part]
            elif isinstance(sample, list) and isinstance(part, int):
                sample = sample[part]
            else:
                return sample
        except (IndexError, KeyError, TypeError):
            return sample
    return sample


def _is_arcgis_error_envelope(raw: Any) -> bool:
    """Return whether ``raw`` matches the ArcGIS top-level error envelope."""
    if not isinstance(raw, dict) or "error" not in raw:
        return False

    # Imported lazily to avoid a module cycle: responses -> _drift -> responses.
    from restgdf._models.responses import ErrorResponse

    try:
        ErrorResponse.model_validate(raw)
    except ValidationError:
        return False
    return True


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

    if _is_arcgis_error_envelope(raw):
        error = raw["error"]
        message = error.get("message") or "ArcGIS error response"
        code = error.get("code")
        code_suffix = f" (code={code})" if code is not None else ""
        raise RestgdfResponseError(
            f"{model_cls.__name__} received ArcGIS error envelope{code_suffix}: "
            f"{message}",
            model_name=model_cls.__name__,
            context=context,
            raw=raw,
        )

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
        top_level_removals: set[str] = set()
        nested_list_removals: dict[str, set[int]] = {}
        for error in exc.errors():
            loc = error.get("loc", ())
            if not loc:
                continue
            top = loc[0]
            if not isinstance(top, str) or top not in cleaned:
                continue
            sample = _sample_at_path(raw, tuple(loc))
            _log_drift(
                model_name=model_cls.__name__,
                path=".".join(str(p) for p in loc),
                kind="bad_type",
                sample=sample,
                level=logging.DEBUG,
            )
            if (
                len(loc) > 1
                and isinstance(loc[1], int)
                and isinstance(cleaned.get(top), list)
            ):
                nested_list_removals.setdefault(top, set()).add(loc[1])
                continue
            top_level_removals.add(top)
        for top, indexes in nested_list_removals.items():
            values = cleaned.get(top)
            if not isinstance(values, list):
                continue
            cleaned[top] = [
                value for idx, value in enumerate(values) if idx not in indexes
            ]
        for top in top_level_removals:
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


class FieldSetDriftObserver:
    """Observe attribute-key drift across feature-page batches (BL-27).

    Establishes an attribute-key baseline from the first ``learn_pages``
    pages delivered to :meth:`observe_page`, then on every later page
    emits deduped drift records via :func:`_log_drift` under
    ``model_name=f"FieldSetDriftObserver[{context}]"``:

    * ``kind="field_appeared"`` — key present in any feature on the
      current page and never seen on a baseline or prior page.
    * ``kind="field_disappeared"`` — key in the observed set that is
      present in *zero* features on the current page.

    Pages that yield zero mapping-shaped features (e.g. an empty
    response batch) are skipped entirely — no "disappeared" records are
    emitted, to avoid false-positive storms on transient empty pages.

    A feature is expected to be a mapping with an ``attributes`` sub-
    mapping; non-mapping feature entries and features whose
    ``attributes`` is missing or not a mapping are silently ignored for
    key-extraction purposes. The observer never raises and never mutates
    input; it is strictly observability.

    ``learn_pages`` is page-granular by design (``observe_page`` is the
    call-site surface). This is a deliberate simplification of the
    plan-domain §4.3 "first N features" phrasing — a feature-count
    threshold would require cross-page buffering with no observability
    benefit.

    Runtime wiring (invoking this observer from the pagination loop) is
    deferred; phase-2b ships the class definition only.

    Parameters
    ----------
    context
        Operator-visible label for the layer/service/call-site being
        observed. Rendered into the drift log's ``model_name`` so
        records stay self-describing.
    learn_pages
        Number of leading pages treated as baseline (default ``1``).
        Must be ``>= 1``.
    """

    def __init__(self, *, context: str, learn_pages: int = 1) -> None:
        if learn_pages < 1:
            raise ValueError("learn_pages must be >= 1")
        self._context = context
        self._model_name = f"FieldSetDriftObserver[{context}]"
        self._learn_pages = learn_pages
        self._pages_seen = 0
        self._observed: set[str] = set()

    @staticmethod
    def _page_keys(features: Iterable[Mapping[str, Any]]) -> set[str]:
        keys: set[str] = set()
        for feature in features:
            if not isinstance(feature, Mapping):
                continue
            attributes = feature.get("attributes")
            if not isinstance(attributes, Mapping):
                continue
            for name in attributes.keys():
                if isinstance(name, str):
                    keys.add(name)
        return keys

    def observe_page(self, features: Iterable[Mapping[str, Any]]) -> None:
        """Record the attribute-key set of a single feature page."""
        page_keys = self._page_keys(features)
        if not page_keys:
            # Empty page (no mapping-shaped features or no attributes).
            # Do not emit drift — an empty batch is not evidence that
            # previously-seen fields have been removed from the schema.
            return

        if self._pages_seen < self._learn_pages:
            self._observed.update(page_keys)
            self._pages_seen += 1
            return

        for appeared in page_keys - self._observed:
            _log_drift(
                model_name=self._model_name,
                path=appeared,
                kind="field_appeared",
                sample=appeared,
                level=logging.INFO,
            )
        for disappeared in self._observed - page_keys:
            _log_drift(
                model_name=self._model_name,
                path=disappeared,
                kind="field_disappeared",
                sample=disappeared,
                level=logging.INFO,
            )
        self._observed.update(page_keys)
        self._pages_seen += 1


__all__ = [
    "FieldSetDriftObserver",
    "PermissiveModel",
    "StrictModel",
    "_parse_response",
    "reset_drift_cache",
]
