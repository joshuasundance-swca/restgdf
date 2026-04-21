"""Helpers for loading optional pandas/geopandas/pyogrio dependencies."""

from __future__ import annotations

from importlib import import_module
from types import ModuleType
from typing import Any

GEO_EXTRA = "restgdf[geo]"
GEO_EXTRA_GUIDANCE = (
    f"Install `{GEO_EXTRA}` to enable pandas/geopandas/pyogrio-backed workflows. "
    "Core metadata/query/raw-record methods continue to work without it."
)


def _optional_dependency_error(
    feature: str,
    missing_module: str,
) -> ModuleNotFoundError:
    """Build a consistent user-facing error for optional dependency gates."""
    return ModuleNotFoundError(
        f"{feature} requires optional dependency '{missing_module}'. "
        f"{GEO_EXTRA_GUIDANCE}",
    )


def _import_optional_module(module_name: str, feature: str) -> ModuleType:
    """Import an optional dependency with a restgdf-specific error message."""
    try:
        return import_module(module_name)
    except ModuleNotFoundError as exc:
        missing_module = exc.name or module_name
        raise _optional_dependency_error(feature, missing_module) from exc


def require_pandas(feature: str) -> ModuleType:
    """Return the optional ``pandas`` module for a gated tabular feature."""
    return _import_optional_module("pandas", feature)


def require_geopandas(feature: str) -> ModuleType:
    """Return the optional ``geopandas`` module for a gated geo feature."""
    return _import_optional_module("geopandas", feature)


def require_pyogrio(feature: str) -> ModuleType:
    """Return the optional ``pyogrio`` module for a gated geo feature."""
    return _import_optional_module("pyogrio", feature)


def require_geo_stack(feature: str) -> None:
    """Validate that the full geo dependency stack is importable."""
    require_pandas(feature)
    require_geopandas(feature)
    require_pyogrio(feature)


def require_pandas_dataframe(feature: str) -> Any:
    """Return ``pandas.DataFrame`` for an optional pandas-backed feature."""
    return require_pandas(feature).DataFrame


def require_pandas_concat(feature: str) -> Any:
    """Return ``pandas.concat`` for an optional pandas-backed feature."""
    return require_pandas(feature).concat


def require_geodataframe(feature: str) -> Any:
    """Return ``geopandas.GeoDataFrame`` for an optional geo feature."""
    return require_geopandas(feature).GeoDataFrame


def require_geopandas_read_file(feature: str) -> Any:
    """Return ``geopandas.read_file`` for an optional geo feature."""
    return require_geopandas(feature).read_file


def require_pyogrio_list_drivers(feature: str) -> Any:
    """Return ``pyogrio.list_drivers`` for an optional geo feature."""
    return require_pyogrio(feature).list_drivers
