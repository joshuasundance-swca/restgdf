"""Backward-compatibility tests for preserved import and patch paths.

Phase 0 safety net: every symbol / module attribute currently used by
external code or by the existing test suite's ``patch("...")`` targets is
enumerated here. Later phases will move these symbols to new modules and
keep them re-exported (optionally with a ``DeprecationWarning``). These
tests must continue to pass throughout every phase of the refactor.
"""

from __future__ import annotations

import importlib

import pytest

pytestmark = pytest.mark.compat


# ---------------------------------------------------------------------------
# Public API surface at the package root
# ---------------------------------------------------------------------------


def test_restgdf_public_api_surface():
    import restgdf

    for name in ("AGOLUserPass", "ArcGISTokenSession", "Directory", "FeatureLayer"):
        assert hasattr(restgdf, name), f"restgdf.{name} must remain importable"
    assert hasattr(restgdf, "utils")
    assert set(restgdf.__all__) >= {
        "AGOLUserPass",
        "ArcGISTokenSession",
        "Directory",
        "FeatureLayer",
        "utils",
    }


# ---------------------------------------------------------------------------
# restgdf.utils.getinfo — every symbol the test suite imports or patches
# ---------------------------------------------------------------------------


_GETINFO_SYMBOLS = (
    "DEFAULTDICT",
    "DEFAULT_METADATA_HEADERS",
    "default_data",
    "default_headers",
    "get_feature_count",
    "get_max_record_count",
    "get_metadata",
    "get_name",
    "get_object_id_field",
    "get_object_ids",
    "get_offset_range",
    "getfields",
    "getfields_df",
    "get_fields",
    "get_fields_frame",
    "getuniquevalues",
    "getvaluecounts",
    "nestedcount",
    "get_unique_values",
    "get_value_counts",
    "nested_count",
    "service_metadata",
    "supports_pagination",
    # ClientSession is patched at this module path by existing tests.
    "ClientSession",
)


@pytest.mark.parametrize("name", _GETINFO_SYMBOLS)
def test_getinfo_symbol_importable(name):
    mod = importlib.import_module("restgdf.utils.getinfo")
    assert hasattr(mod, name), f"restgdf.utils.getinfo.{name} must remain available"


def test_getinfo_from_import_forms():
    # ``from restgdf.utils.getinfo import X`` must keep working for every symbol.
    ns: dict = {}
    exec(
        "from restgdf.utils.getinfo import (\n"
        + ",\n".join(f"    {n}" for n in _GETINFO_SYMBOLS)
        + ",\n)\n",
        ns,
    )
    for name in _GETINFO_SYMBOLS:
        assert name in ns


# ---------------------------------------------------------------------------
# restgdf.utils.getgdf patch targets
# ---------------------------------------------------------------------------


_GETGDF_SYMBOLS = (
    "chunk_generator",
    "chunk_values",
    "combine_where_clauses",
    "concat_gdfs",
    "default_data",
    "default_headers",
    "gdf_by_concat",
    "get_feature_count",
    "get_gdf",
    "get_gdf_list",
    "get_max_record_count",
    "get_metadata",
    "get_object_ids",
    "get_query_data_batches",
    "get_sub_gdf",
    "read_file",
    "row_dict_generator",
    "supported_drivers",
    "supports_pagination",
)


@pytest.mark.parametrize("name", _GETGDF_SYMBOLS)
def test_getgdf_symbol_importable(name):
    mod = importlib.import_module("restgdf.utils.getgdf")
    assert hasattr(mod, name), f"restgdf.utils.getgdf.{name} must remain available"


# ---------------------------------------------------------------------------
# Other module-level patch targets that must remain patchable
# ---------------------------------------------------------------------------


def test_crawl_patch_targets():
    mod = importlib.import_module("restgdf.utils.crawl")
    for name in ("get_metadata", "service_metadata", "fetch_all_data"):
        assert hasattr(mod, name)


def test_directory_patch_targets():
    mod = importlib.import_module("restgdf.directory.directory")
    for name in ("get_metadata", "fetch_all_data", "Directory"):
        assert hasattr(mod, name)


def test_featurelayer_patch_targets():
    mod = importlib.import_module("restgdf.featurelayer.featurelayer")
    for name in (
        "FeatureLayer",
        "get_gdf",
        "getuniquevalues",
        "getvaluecounts",
        "nestedcount",
        "get_unique_values",
        "get_value_counts",
        "nested_count",
        "row_dict_generator",
        "random",
    ):
        assert hasattr(mod, name)


def test_token_patch_targets():
    mod = importlib.import_module("restgdf.utils.token")
    for name in ("AGOLUserPass", "ArcGISTokenSession", "get_token", "requests"):
        assert hasattr(mod, name)


# ---------------------------------------------------------------------------
# Value-level guarantees (constants used by downstream code)
# ---------------------------------------------------------------------------


def test_defaultdict_contents():
    from restgdf.utils.getinfo import DEFAULTDICT

    assert DEFAULTDICT["where"] == "1=1"
    assert DEFAULTDICT["outFields"] == "*"
    assert DEFAULTDICT["returnGeometry"] is True
    assert DEFAULTDICT["returnCountOnly"] is False
    assert DEFAULTDICT["f"] == "json"
