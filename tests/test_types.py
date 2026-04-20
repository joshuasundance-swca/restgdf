"""Deprecation contract for :mod:`restgdf._types`.

The TypedDicts that used to live in this module are replaced by pydantic
models in :mod:`restgdf._models`. ``restgdf._types`` is retained as a
lazy-deprecation shim: importing any legacy name emits a
``DeprecationWarning`` and returns the pydantic replacement.
"""

from __future__ import annotations

import importlib
import warnings

import pytest

pytestmark = pytest.mark.compat


_LEGACY_NAMES = (
    "FieldSpec",
    "LayerMetadata",
    "ServiceInfo",
    "CountResponse",
    "ObjectIdsResponse",
    "Feature",
    "FeaturesResponse",
    "ErrorInfo",
    "ErrorResponse",
    "CrawlError",
    "CrawlServiceEntry",
    "CrawlReport",
)


def test_types_module_importable() -> None:
    import restgdf._types as t  # noqa: F401


@pytest.mark.parametrize("name", _LEGACY_NAMES)
def test_legacy_name_emits_deprecation_warning(name: str) -> None:
    import restgdf._types as t

    with pytest.warns(DeprecationWarning, match=rf"restgdf\._types\.{name}"):
        obj = getattr(t, name)
    assert obj is not None


@pytest.mark.parametrize("name", _LEGACY_NAMES)
def test_legacy_name_resolves_to_pydantic_model(name: str) -> None:
    from pydantic import BaseModel

    import restgdf._types as t

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        obj = getattr(t, name)
    assert isinstance(obj, type)
    assert issubclass(obj, BaseModel)


def test_unknown_attribute_raises_attribute_error() -> None:
    import restgdf._types as t

    with pytest.raises(AttributeError):
        _ = t.DoesNotExist  # type: ignore[attr-defined]


def test_legacy_names_match_public_api_models() -> None:
    """Every legacy alias must resolve to the canonical public-API class."""
    import restgdf
    import restgdf._types as t

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        for name in _LEGACY_NAMES:
            legacy = getattr(t, name)
            canonical = getattr(restgdf, name)
            assert legacy is canonical, f"{name}: legacy alias drifted"


def test_module_all_lists_legacy_names() -> None:
    mod = importlib.import_module("restgdf._types")
    assert set(mod.__all__) == set(_LEGACY_NAMES)
