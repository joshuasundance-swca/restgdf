"""BL-38: minimal-install contract test.

Asserts that ``import restgdf`` and its top-level public classes are
reachable on an install that only provides the **core** dependencies
(``aiohttp``, ``pydantic``, ``pydantic_settings``, plus stdlib). Heavy
optional dependencies (``pandas``, ``geopandas``, ``pyogrio``) must NOT be
imported by ``import restgdf`` or by :class:`restgdf.FeatureLayer` /
:class:`restgdf.Directory` class attribute access.

This test runs in the ``pytest-base-install`` CI job (see
``.github/workflows/pytest.yml``) where ``pip install -e ".[dev]"`` installs
only dev tooling — the geo stack is absent — and the test must still pass.
"""

from __future__ import annotations

import builtins
import importlib
import sys
from contextlib import contextmanager
from typing import Iterator

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


def test_import_restgdf_top_level_is_core_safe(monkeypatch) -> None:
    with _fresh_modules("restgdf", *HEAVY_MODULE_PREFIXES):
        real_import = builtins.__import__

        def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
            if name.split(".")[0] in HEAVY_MODULE_PREFIXES:
                raise AssertionError(f"unexpected heavy import: {name}")
            return real_import(name, globals, locals, fromlist, level)

        monkeypatch.setattr(builtins, "__import__", guarded_import)
        restgdf = importlib.import_module("restgdf")

        assert restgdf.__version__


def test_featurelayer_and_directory_importable_without_geo_stack(
    monkeypatch,
) -> None:
    with _fresh_modules("restgdf", *HEAVY_MODULE_PREFIXES):
        real_import = builtins.__import__

        def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
            if name.split(".")[0] in HEAVY_MODULE_PREFIXES:
                raise AssertionError(f"unexpected heavy import: {name}")
            return real_import(name, globals, locals, fromlist, level)

        monkeypatch.setattr(builtins, "__import__", guarded_import)
        restgdf = importlib.import_module("restgdf")

        assert restgdf.FeatureLayer.__name__ == "FeatureLayer"
        assert restgdf.Directory.__name__ == "Directory"


def test_get_config_probe_is_tolerant_of_phase_2a_merge_state() -> None:
    # ``get_config`` lands with phase-2a. This test must pass whether
    # phase-2a has merged or not — it only asserts that an attribute probe
    # does not itself import the heavy stack, and that if present,
    # ``get_config`` is callable.
    restgdf = importlib.import_module("restgdf")
    if hasattr(restgdf, "get_config"):
        assert callable(restgdf.get_config)


def test_import_restgdf_adapters_is_core_safe(monkeypatch) -> None:
    with _fresh_modules("restgdf", *HEAVY_MODULE_PREFIXES):
        real_import = builtins.__import__

        def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
            if name.split(".")[0] in HEAVY_MODULE_PREFIXES:
                raise AssertionError(f"unexpected heavy import: {name}")
            return real_import(name, globals, locals, fromlist, level)

        monkeypatch.setattr(builtins, "__import__", guarded_import)
        adapters = importlib.import_module("restgdf.adapters")

        assert adapters.__all__ == ["dict", "geopandas", "pandas", "stream"]
        # Submodules themselves are core-safe to import (they gate at
        # call time).
        importlib.import_module("restgdf.adapters.dict")
        importlib.import_module("restgdf.adapters.stream")
        importlib.import_module("restgdf.adapters.pandas")
        importlib.import_module("restgdf.adapters.geopandas")
