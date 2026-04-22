"""Public adapter surface for converting ArcGIS responses to user-facing shapes.

The ``restgdf.adapters`` subpackage provides a thin, user-facing facade over
the existing conversion helpers in :mod:`restgdf.utils.getgdf`. It adds **no**
new logic and duplicates no code — the adapters simply surface the existing
helpers under stable, discoverable names that mirror the plan-of-record output
taxonomy (``dict``, ``stream``, ``pandas``, ``geopandas``).

Pydantic-model output is intentionally not a separate adapter module: callers
who need a plain-dict view of a validated pydantic model use
:func:`restgdf.compat.as_dict` / :func:`restgdf.compat.as_json_dict` or call
``.model_dump()`` directly.

Dependency gating
-----------------
Importing this package — and any of its four submodules — is safe on a
**base** install of restgdf. Heavy optional dependencies (``pandas``,
``geopandas``, ``pyogrio``) are imported **inside** adapter function bodies,
not at module import time. Adapter functions that require them raise
:class:`restgdf.errors.OptionalDependencyError` (via
:func:`restgdf.utils._optional.require_pandas` /
:func:`restgdf.utils._optional.require_geo_stack`) at call time.

Subpackage layout
-----------------
``dict``
    Core-install safe row-shaped dict helpers.
``stream``
    Core-install safe async iterators over rows and feature batches; geo
    chunks are gated at call time.
``pandas``
    Pandas-gated ``DataFrame`` materialization.
``geopandas``
    Geopandas-gated ``GeoDataFrame`` materialization.

The submodules are loaded lazily via :pep:`562`'s module ``__getattr__`` so
``import restgdf.adapters`` does not pull in ``restgdf.adapters.pandas`` (or
its transitive imports) until a caller actually touches that submodule.
"""

from __future__ import annotations

import importlib
from types import ModuleType
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - import-time only
    from . import dict, geopandas, pandas, stream  # noqa: F401

__all__ = ["dict", "geopandas", "pandas", "stream"]

_SUBMODULES: tuple[str, ...] = ("dict", "geopandas", "pandas", "stream")


def __getattr__(name: str) -> ModuleType:
    if name in _SUBMODULES:
        module = importlib.import_module(f"{__name__}.{name}")
        globals()[name] = module
        return module
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
