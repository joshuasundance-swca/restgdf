from __future__ import annotations

import builtins
import importlib
import sys
from contextlib import contextmanager
from typing import Iterator

import pytest

HEAVY_MODULE_PREFIXES = ("geopandas", "pandas", "pyogrio")


def _matches_prefix(name: str, prefixes: tuple[str, ...]) -> bool:
    return any(name == prefix or name.startswith(f"{prefix}.") for prefix in prefixes)


@contextmanager
def _fresh_modules(*prefixes: str) -> Iterator[None]:
    saved = {
        name: module
        for name, module in sys.modules.items()
        if _matches_prefix(name, prefixes)
    }
    for name in saved:
        sys.modules.pop(name, None)
    try:
        yield
    finally:
        for name in list(sys.modules):
            if _matches_prefix(name, prefixes):
                sys.modules.pop(name, None)
        sys.modules.update(saved)


def test_feature_to_row_flattens_attributes_and_geometry() -> None:
    from restgdf.adapters.dict import feature_to_row

    feature = {
        "attributes": {"CITY": "DAYTONA", "POP": 72},
        "geometry": {"x": 1.0, "y": 2.0},
    }

    row = feature_to_row(feature)

    assert row == {"CITY": "DAYTONA", "POP": 72, "geometry": {"x": 1.0, "y": 2.0}}


def test_feature_to_row_preserves_extra_top_level_keys() -> None:
    from restgdf.adapters.dict import feature_to_row

    feature = {
        "attributes": {"CITY": "ORMOND"},
        "foo": "bar",
    }

    row = feature_to_row(feature)

    assert row == {"CITY": "ORMOND", "foo": "bar"}


def test_features_to_rows_materializes_iterable() -> None:
    from restgdf.adapters.dict import features_to_rows

    features = iter(
        [
            {"attributes": {"A": 1}},
            {"attributes": {"A": 2}, "geometry": {"x": 0, "y": 0}},
        ],
    )

    rows = features_to_rows(features)

    assert rows == [{"A": 1}, {"A": 2, "geometry": {"x": 0, "y": 0}}]


def test_features_to_rows_empty() -> None:
    from restgdf.adapters.dict import features_to_rows

    assert features_to_rows([]) == []


def test_as_dict_and_as_json_dict_re_exported() -> None:
    from restgdf import compat
    from restgdf.adapters import dict as dict_adapter

    assert dict_adapter.as_dict is compat.as_dict
    assert dict_adapter.as_json_dict is compat.as_json_dict


def test_dict_adapter_import_does_not_load_heavy_deps(monkeypatch) -> None:
    with _fresh_modules("restgdf", *HEAVY_MODULE_PREFIXES):
        real_import = builtins.__import__

        def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
            if name.split(".")[0] in HEAVY_MODULE_PREFIXES:
                raise AssertionError(f"unexpected heavy import: {name}")
            return real_import(name, globals, locals, fromlist, level)

        monkeypatch.setattr(builtins, "__import__", guarded_import)
        module = importlib.import_module("restgdf.adapters.dict")

        assert hasattr(module, "feature_to_row")
        assert hasattr(module, "features_to_rows")


def test_adapters_package_lazy_loads_submodules() -> None:
    with _fresh_modules("restgdf"):
        adapters = importlib.import_module("restgdf.adapters")
        # Submodules not yet materialized.
        assert "restgdf.adapters.dict" not in sys.modules
        _ = adapters.dict  # trigger lazy load
        assert "restgdf.adapters.dict" in sys.modules


def test_adapters_package_rejects_unknown_submodule() -> None:
    adapters = importlib.import_module("restgdf.adapters")
    with pytest.raises(AttributeError):
        _ = adapters.does_not_exist


def test_adapters_dir_is_sorted_and_includes_all_submodules() -> None:
    adapters = importlib.import_module("restgdf.adapters")
    exported = dir(adapters)
    for submodule in ("dict", "geopandas", "pandas", "stream"):
        assert submodule in exported
    assert exported == sorted(set(exported))
