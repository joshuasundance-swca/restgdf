"""Q-S6: ``FeatureLayer.get_df`` is base-install-compatible.

Asserts the new pandas-only tabular accessor on :class:`restgdf.FeatureLayer`:

* On a pandas-bearing install, ``await layer.get_df()`` returns a
  ``pandas.DataFrame`` built from the row-shaped dict stream.
* On a pandas-free install, ``await layer.get_df()`` raises
  :class:`restgdf.errors.OptionalDependencyError` with the canonical
  ``restgdf[geo]`` guidance — and it does so **without** attempting to import
  ``geopandas`` or ``pyogrio`` (the ``get_gdf`` path is not taken).
"""

from __future__ import annotations

import importlib
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from restgdf.errors import OptionalDependencyError
from restgdf.featurelayer.featurelayer import FeatureLayer


SAMPLE_METADATA = {
    "name": "Test Layer",
    "type": "Feature Layer",
    "fields": [
        {"name": "OBJECTID", "type": "esriFieldTypeOID"},
        {"name": "CITY", "type": "esriFieldTypeString"},
    ],
    "maxRecordCount": 2,
    "advancedQueryCapabilities": {"supportsPagination": False},
}


class JsonResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    async def json(self, content_type=None):
        return self._payload


class QuerySession:
    def __init__(self, responses: list[dict]):
        self.responses = list(responses)
        self.post_calls: list[tuple[str, dict]] = []

    async def post(self, url: str, **kwargs):
        self.post_calls.append((url, kwargs))
        return JsonResponse(self.responses.pop(0))

    async def get(self, url, **kwargs):
        if "params" in kwargs and "data" not in kwargs:
            kwargs = {**kwargs, "data": kwargs["params"]}
        return await self.post(url, **kwargs)


@pytest.mark.asyncio
async def test_get_df_returns_pandas_dataframe_when_pandas_available() -> None:
    pd = pytest.importorskip("pandas")

    session = QuerySession(
        [
            {
                "features": [
                    {
                        "attributes": {"CITY": "DAYTONA"},
                        "geometry": {"x": 0, "y": 0},
                    },
                ],
            },
            {"features": [{"attributes": {"CITY": "ORMOND"}}]},
        ],
    )

    layer = FeatureLayer(
        "https://example.com/arcgis/rest/services/Test/FeatureServer/0",
        session=session,  # type: ignore[arg-type]
    )

    with patch(
        "restgdf.utils.getgdf.get_query_data_batches",
        new=AsyncMock(return_value=[{"where": "1=1"}, {"where": "OBJECTID > 5"}]),
    ), patch(
        "restgdf.utils.getgdf.get_sub_gdf",
        new=AsyncMock(
            side_effect=AssertionError(
                "get_df must not require geopandas via get_sub_gdf",
            ),
        ),
    ):
        df = await layer.get_df()

    assert isinstance(df, pd.DataFrame)
    assert df["CITY"].tolist() == ["DAYTONA", "ORMOND"]


@pytest.mark.asyncio
async def test_get_df_raises_optional_dependency_error_without_pandas(
    monkeypatch,
) -> None:
    # Simulate a pandas-free install by making the lazy helper raise.
    def _missing(module_name: str) -> Any:
        exc = ModuleNotFoundError(f"No module named '{module_name}'")
        exc.name = module_name
        raise exc

    monkeypatch.setattr(
        "restgdf.utils._optional.import_module",
        _missing,
    )
    # Reload the adapter module so its ``require_pandas`` resolves against
    # the patched ``import_module``.
    from restgdf.adapters import pandas as pandas_adapter

    importlib.reload(pandas_adapter)

    session = QuerySession(
        [
            {"features": [{"attributes": {"CITY": "DAYTONA"}}]},
        ],
    )
    layer = FeatureLayer(
        "https://example.com/arcgis/rest/services/Test/FeatureServer/0",
        session=session,  # type: ignore[arg-type]
    )

    with patch(
        "restgdf.utils.getgdf.get_query_data_batches",
        new=AsyncMock(return_value=[{"where": "1=1"}]),
    ), pytest.raises(OptionalDependencyError) as excinfo:
        await layer.get_df()

    message = str(excinfo.value)
    assert "pandas" in message
    assert "restgdf[geo]" in message
