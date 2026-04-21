from __future__ import annotations

import builtins
import importlib
import sys
import types
from collections.abc import Iterator
from contextlib import contextmanager

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


def test_import_restgdf_does_not_eagerly_import_geo_stack(monkeypatch) -> None:
    with _fresh_modules("restgdf", *HEAVY_MODULE_PREFIXES):
        real_import = builtins.__import__

        def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
            if name.split(".")[0] in HEAVY_MODULE_PREFIXES:
                raise AssertionError(f"unexpected heavy import: {name}")
            return real_import(name, globals, locals, fromlist, level)

        monkeypatch.setattr(builtins, "__import__", guarded_import)
        module = importlib.import_module("restgdf")

        assert module.__version__
        assert "restgdf.featurelayer.featurelayer" not in sys.modules
        assert "restgdf.utils" not in sys.modules


def test_import_restgdf_utils_is_package_only(monkeypatch) -> None:
    with _fresh_modules("restgdf", *HEAVY_MODULE_PREFIXES):
        real_import = builtins.__import__

        def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
            if name.split(".")[0] in HEAVY_MODULE_PREFIXES:
                raise AssertionError(f"unexpected heavy import: {name}")
            return real_import(name, globals, locals, fromlist, level)

        monkeypatch.setattr(builtins, "__import__", guarded_import)
        module = importlib.import_module("restgdf.utils")

        assert module.__all__ == ["crawl", "getgdf", "getinfo", "utils"]
        assert "restgdf.utils.crawl" not in sys.modules
        assert "restgdf.utils.getgdf" not in sys.modules
        assert "restgdf.utils.getinfo" not in sys.modules
        assert "restgdf.utils.utils" not in sys.modules


def test_featurelayer_is_loaded_on_first_access() -> None:
    with _fresh_modules("restgdf"):
        module = importlib.import_module("restgdf")
        assert "restgdf.featurelayer.featurelayer" not in sys.modules

        feature_layer = module.FeatureLayer

        assert feature_layer.__name__ == "FeatureLayer"
        assert "restgdf.featurelayer.featurelayer" in sys.modules


def test_utils_submodule_is_loaded_on_first_access() -> None:
    with _fresh_modules("restgdf"):
        module = importlib.import_module("restgdf.utils")
        assert "restgdf.utils.utils" not in sys.modules

        utils_mod = module.utils

        assert utils_mod.__name__ == "restgdf.utils.utils"
        assert "restgdf.utils.utils" in sys.modules


def test_settings_default_user_agent_does_not_depend_on_package_root(
    monkeypatch,
) -> None:
    with _fresh_modules("restgdf"):
        settings_mod = importlib.import_module("restgdf._models._settings")
        stub_package = types.ModuleType("restgdf")
        stub_package.__path__ = []
        monkeypatch.setitem(sys.modules, "restgdf", stub_package)

        settings = settings_mod.Settings()

        assert settings.user_agent.startswith("restgdf/")
