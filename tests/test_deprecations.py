"""Phase 6 naming-normalization deprecation contract.

Asserts that the snake_case canonical names exist AND that the legacy
camel-mashed names still work while emitting ``DeprecationWarning``.
The canonical implementations live in the private submodules; the
legacy names are thin wrappers that warn once and then delegate.
"""

from __future__ import annotations

import asyncio
import warnings
from unittest.mock import AsyncMock, patch

import pytest

from restgdf.utils import _metadata, _stats
from restgdf.utils import getinfo as getinfo_mod
from restgdf.featurelayer import featurelayer as fl_mod


SAMPLE_METADATA = {
    "fields": [
        {"name": "OBJECTID", "type": "esriFieldTypeOID"},
        {"name": "CITY", "type": "esriFieldTypeString"},
    ],
}


# ---------------------------------------------------------------------------
# Canonical (new) names exist on the private submodules.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name",
    ["get_fields", "get_fields_frame"],
)
def test_metadata_canonical_names(name):
    assert hasattr(_metadata, name)


@pytest.mark.parametrize(
    "name",
    ["get_unique_values", "get_value_counts", "nested_count"],
)
def test_stats_canonical_names(name):
    assert hasattr(_stats, name)


# ---------------------------------------------------------------------------
# Canonical names also re-exported from the ``getinfo`` shim.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name",
    [
        "get_fields",
        "get_fields_frame",
        "get_unique_values",
        "get_value_counts",
        "nested_count",
    ],
)
def test_getinfo_exposes_canonical_names(name):
    assert hasattr(getinfo_mod, name)
    assert name in getinfo_mod.__all__


# ---------------------------------------------------------------------------
# Canonical FeatureLayer method names.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name",
    [
        "get_oids",
        "sample_gdf",
        "head_gdf",
        "get_gdf",
        "get_unique_values",
        "get_value_counts",
        "get_nested_count",
    ],
)
def test_featurelayer_canonical_methods(name):
    assert callable(getattr(fl_mod.FeatureLayer, name, None))


# ---------------------------------------------------------------------------
# Legacy module-level names still resolve AND emit DeprecationWarning.
# ---------------------------------------------------------------------------


def test_legacy_getfields_warns_and_delegates():
    with pytest.warns(DeprecationWarning, match=r"get_fields"):
        result = _metadata.getfields(SAMPLE_METADATA)
    assert result == ["OBJECTID", "CITY"]


def test_legacy_getfields_df_warns_and_delegates():
    with pytest.warns(DeprecationWarning, match=r"get_fields_frame"):
        df = _metadata.getfields_df(SAMPLE_METADATA)
    assert list(df.columns) == ["name", "type"]
    assert len(df) == 2


def test_legacy_getuniquevalues_warns_and_delegates():
    loop = asyncio.new_event_loop()
    try:
        response = AsyncMock()
        response.json = AsyncMock(
            return_value={"features": [{"attributes": {"CITY": "A"}}]},
        )
        session = AsyncMock()
        session.post = AsyncMock(return_value=response)
        # T8 (R-74): short ``get_unique_values`` bodies now route to GET.
        session.get = AsyncMock(return_value=response)

        with pytest.warns(DeprecationWarning, match=r"get_unique_values"):
            result = loop.run_until_complete(
                _stats.getuniquevalues("http://x/0", "CITY", session=session),
            )
        assert result == ["A"]
    finally:
        loop.close()


def test_legacy_getvaluecounts_warns_and_delegates():
    loop = asyncio.new_event_loop()
    try:
        response = AsyncMock()
        response.json = AsyncMock(
            return_value={
                "features": [{"attributes": {"CITY": "A", "CITY_count": 1}}],
            },
        )
        session = AsyncMock()
        session.post = AsyncMock(return_value=response)
        # T8 (R-74): short ``get_value_counts`` bodies now route to GET.
        session.get = AsyncMock(return_value=response)

        with pytest.warns(DeprecationWarning, match=r"get_value_counts"):
            df = loop.run_until_complete(
                _stats.getvaluecounts("http://x/0", "CITY", session=session),
            )
        assert "CITY" in df.columns
    finally:
        loop.close()


def test_legacy_nestedcount_warns_and_delegates():
    loop = asyncio.new_event_loop()
    try:
        response = AsyncMock()
        response.json = AsyncMock(
            return_value={
                "features": [
                    {
                        "attributes": {
                            "CITY": "A",
                            "STATE": "X",
                            "CITY_count": 1,
                            "STATE_count": 1,
                        },
                    },
                ],
            },
        )
        session = AsyncMock()
        session.post = AsyncMock(return_value=response)
        # T8 (R-74): short ``nested_count`` bodies now route to GET.
        session.get = AsyncMock(return_value=response)

        with pytest.warns(DeprecationWarning, match=r"nested_count"):
            df = loop.run_until_complete(
                _stats.nestedcount(
                    "http://x/0",
                    ("CITY", "STATE"),
                    session=session,
                ),
            )
        assert "Count" in df.columns
    finally:
        loop.close()


# ---------------------------------------------------------------------------
# Legacy FeatureLayer methods still resolve AND emit DeprecationWarning.
# ---------------------------------------------------------------------------


def _make_layer_skeleton():
    """Build a FeatureLayer without running prep(); required by method tests."""
    layer = fl_mod.FeatureLayer.__new__(fl_mod.FeatureLayer)
    layer.url = "http://x/0"
    layer.session = AsyncMock()
    layer.wherestr = "1=1"
    layer.kwargs = {"data": {}}
    layer.datadict = {"where": "1=1"}
    layer.uniquevalues = {}
    layer.valuecounts = {}
    layer.nestedcount = {}
    layer.gdf = None
    layer.fields = ("OBJECTID", "CITY", "STATE")
    layer.object_id_field = "OBJECTID"
    layer.metadata = {"fields": SAMPLE_METADATA["fields"]}
    layer.name = "x"
    layer.count = 0
    return layer


def test_legacy_method_getgdf_warns():
    loop = asyncio.new_event_loop()
    try:
        layer = _make_layer_skeleton()
        with patch.object(
            fl_mod.FeatureLayer,
            "get_gdf",
            new=AsyncMock(return_value="gdf-sentinel"),
        ):
            with pytest.warns(DeprecationWarning, match=r"get_gdf"):
                result = loop.run_until_complete(layer.getgdf())
        assert result == "gdf-sentinel"
    finally:
        loop.close()


def test_legacy_method_getoids_warns():
    loop = asyncio.new_event_loop()
    try:
        layer = _make_layer_skeleton()
        with patch.object(
            fl_mod.FeatureLayer,
            "get_oids",
            new=AsyncMock(return_value=[1, 2]),
        ):
            with pytest.warns(DeprecationWarning, match=r"get_oids"):
                result = loop.run_until_complete(layer.getoids())
        assert result == [1, 2]
    finally:
        loop.close()


def test_legacy_method_samplegdf_warns():
    loop = asyncio.new_event_loop()
    try:
        layer = _make_layer_skeleton()
        with patch.object(
            fl_mod.FeatureLayer,
            "sample_gdf",
            new=AsyncMock(return_value="sample-sentinel"),
        ):
            with pytest.warns(DeprecationWarning, match=r"sample_gdf"):
                result = loop.run_until_complete(layer.samplegdf(3))
        assert result == "sample-sentinel"
    finally:
        loop.close()


def test_legacy_method_headgdf_warns():
    loop = asyncio.new_event_loop()
    try:
        layer = _make_layer_skeleton()
        with patch.object(
            fl_mod.FeatureLayer,
            "head_gdf",
            new=AsyncMock(return_value="head-sentinel"),
        ):
            with pytest.warns(DeprecationWarning, match=r"head_gdf"):
                result = loop.run_until_complete(layer.headgdf(3))
        assert result == "head-sentinel"
    finally:
        loop.close()


def test_legacy_method_getuniquevalues_warns():
    loop = asyncio.new_event_loop()
    try:
        layer = _make_layer_skeleton()
        with patch.object(
            fl_mod.FeatureLayer,
            "get_unique_values",
            new=AsyncMock(return_value=["A", "B"]),
        ):
            with pytest.warns(DeprecationWarning, match=r"get_unique_values"):
                result = loop.run_until_complete(layer.getuniquevalues("CITY"))
        assert result == ["A", "B"]
    finally:
        loop.close()


def test_legacy_method_getvaluecounts_warns():
    loop = asyncio.new_event_loop()
    try:
        layer = _make_layer_skeleton()
        sentinel = object()
        with patch.object(
            fl_mod.FeatureLayer,
            "get_value_counts",
            new=AsyncMock(return_value=sentinel),
        ):
            with pytest.warns(DeprecationWarning, match=r"get_value_counts"):
                result = loop.run_until_complete(layer.getvaluecounts("CITY"))
        assert result is sentinel
    finally:
        loop.close()


def test_legacy_method_getnestedcount_warns():
    loop = asyncio.new_event_loop()
    try:
        layer = _make_layer_skeleton()
        sentinel = object()
        with patch.object(
            fl_mod.FeatureLayer,
            "get_nested_count",
            new=AsyncMock(return_value=sentinel),
        ):
            with pytest.warns(DeprecationWarning, match=r"get_nested_count"):
                result = loop.run_until_complete(
                    layer.getnestedcount(("CITY", "STATE")),
                )
        assert result is sentinel
    finally:
        loop.close()


# ---------------------------------------------------------------------------
# Canonical names do NOT emit warnings (sanity).
# ---------------------------------------------------------------------------


def test_canonical_getfields_no_warning():
    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        result = _metadata.get_fields(SAMPLE_METADATA)
    assert result == ["OBJECTID", "CITY"]


def test_canonical_get_fields_frame_no_warning():
    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        df = _metadata.get_fields_frame(SAMPLE_METADATA)
    assert list(df.columns) == ["name", "type"]
