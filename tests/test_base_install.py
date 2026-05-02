from __future__ import annotations

import importlib
from types import ModuleType
from unittest.mock import AsyncMock, patch

import pytest

from restgdf.featurelayer.featurelayer import FeatureLayer
from restgdf.utils.getgdf import (
    get_gdf,
    get_query_data_batches,
    get_sub_gdf,
    row_dict_generator,
)
from restgdf.utils.getinfo import (
    get_fields_frame,
    get_unique_values,
    get_value_counts,
    nested_count,
)

SAMPLE_METADATA = {
    "name": "Test Layer",
    "type": "Feature Layer",
    "fields": [
        {"name": "OBJECTID", "type": "esriFieldTypeOID"},
        {"name": "CITY", "type": "esriFieldTypeString"},
        {"name": "STATUS", "type": "esriFieldTypeString"},
    ],
    "maxRecordCount": 2,
    "advancedQueryCapabilities": {"supportsPagination": False},
}


class JsonResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    async def json(self, content_type=None):
        return self._payload


class TextResponse:
    def __init__(self, text_payload: str):
        self._text_payload = text_payload

    async def text(self):
        return self._text_payload


class QuerySession:
    def __init__(self, responses: list[dict]):
        self.responses = list(responses)
        self.post_calls: list[tuple[str, dict]] = []
        # T8 (R-74): short ArcGIS requests now route through GET.
        # Alias get_calls onto post_calls so tests keep asserting
        # on ``post_calls`` regardless of the verb selected.
        self.get_calls = self.post_calls

    async def _record(self, url: str, kwargs: dict) -> JsonResponse:
        self.post_calls.append((url, kwargs))
        return JsonResponse(self.responses.pop(0))

    async def post(self, url: str, **kwargs):
        return await self._record(url, kwargs)

    async def get(self, url: str, **kwargs):
        # Mirror the body under the POST key so tests that inspect
        # ``kwargs["data"]`` keep passing when the call is now a GET.
        if "params" in kwargs and "data" not in kwargs:
            kwargs = {**kwargs, "data": kwargs["params"]}
        return await self._record(url, kwargs)


class RecordingTextSession:
    def __init__(self, response_text: str = "{}"):
        self.response_text = response_text
        self.post_calls: list[tuple[str, dict]] = []
        self.get_calls = self.post_calls

    async def _record(self, url: str, kwargs: dict) -> TextResponse:
        self.post_calls.append((url, kwargs))
        return TextResponse(self.response_text)

    async def post(self, url: str, **kwargs):
        return await self._record(url, kwargs)

    async def get(self, url: str, **kwargs):
        if "params" in kwargs and "data" not in kwargs:
            kwargs = {**kwargs, "data": kwargs["params"]}
        return await self._record(url, kwargs)


class RejectingSession:
    async def post(self, *args, **kwargs):
        raise AssertionError("should fail before requesting")

    async def get(self, *args, **kwargs):
        raise AssertionError("should fail before requesting")


class MockFeatureLayerSession:
    def __init__(
        self,
        *,
        metadata: dict,
        count: int,
        object_ids: list[int] | None = None,
    ):
        self.metadata = metadata
        self.count = count
        self.object_ids = object_ids or list(range(1, count + 1))
        self.get_calls: list[tuple[str, dict]] = []
        self.post_calls: list[tuple[str, dict]] = []

    async def get(self, url: str, **kwargs):
        copied_kwargs = {
            **kwargs,
            "params": dict(kwargs.get("params", {})),
        }
        self.get_calls.append((url, copied_kwargs))
        # T8 (R-74): short ArcGIS /query calls flip from POST to GET.
        # Reuse the same response routing as POST by interpreting
        # ``params`` the same way a POST ``data`` payload was interpreted.
        params = copied_kwargs["params"]
        if url.endswith("/query"):
            if params.get("returnCountOnly"):
                return JsonResponse({"count": self.count})
            if params.get("returnIdsOnly"):
                return JsonResponse(
                    {
                        "objectIdFieldName": "OBJECTID",
                        "objectIds": self.object_ids,
                    },
                )
            return JsonResponse({"features": []})
        return JsonResponse(self.metadata)

    async def post(self, url: str, **kwargs):
        copied_kwargs = {
            **kwargs,
            "data": dict(kwargs.get("data", {})),
        }
        self.post_calls.append((url, copied_kwargs))
        data = copied_kwargs["data"]

        if url.endswith("/query"):
            if data.get("returnCountOnly"):
                return JsonResponse({"count": self.count})
            if data.get("returnIdsOnly"):
                return JsonResponse(
                    {
                        "objectIdFieldName": "OBJECTID",
                        "objectIds": self.object_ids,
                    },
                )
            return JsonResponse({"features": []})

        return JsonResponse(self.metadata)


def _missing_optional_import(name: str) -> ModuleNotFoundError:
    exc = ModuleNotFoundError(f"No module named '{name}'")
    exc.name = name
    return exc


def _optional_import_side_effect(
    *,
    missing: str,
    provided: dict[str, ModuleType] | None = None,
):
    provided = provided or {}

    def _side_effect(module_name: str):
        if module_name == missing:
            raise _missing_optional_import(missing)
        if module_name in provided:
            return provided[module_name]
        return importlib.import_module(module_name)

    return _side_effect


@pytest.mark.asyncio
async def test_get_query_data_batches_chunks_object_ids_when_pagination_disabled():
    with patch(
        "restgdf.utils.getgdf.get_feature_count",
        new=AsyncMock(return_value=5),
    ), patch(
        "restgdf.utils.getgdf.get_metadata",
        new=AsyncMock(return_value=SAMPLE_METADATA),
    ), patch(
        "restgdf.utils.getgdf.get_object_ids",
        new=AsyncMock(return_value=("OBJECTID", [1, 2, 3, 4, 5])),
    ):
        result = await get_query_data_batches(
            "https://example.com/layer/0",
            object(),
            data={"where": "CITY = 'DAYTONA'"},
        )

    assert result == [
        {"where": "(CITY = 'DAYTONA') AND (OBJECTID In (1, 2))"},
        {"where": "(CITY = 'DAYTONA') AND (OBJECTID In (3, 4))"},
        {"where": "(CITY = 'DAYTONA') AND (OBJECTID In (5))"},
    ]


@pytest.mark.asyncio
async def test_row_dict_generator_yields_rows_without_geo_stack():
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
            {
                "features": [
                    {
                        "attributes": {"CITY": "ORMOND"},
                    },
                ],
            },
        ],
    )

    with patch(
        "restgdf.utils.getgdf.get_query_data_batches",
        new=AsyncMock(return_value=[{"where": "1=1"}, {"where": "OBJECTID > 5"}]),
    ), patch(
        "restgdf.utils.getgdf.get_sub_gdf",
        new=AsyncMock(
            side_effect=AssertionError(
                "row_dict_generator should not require geopandas",
            ),
        ),
    ):
        rows = [
            row
            async for row in row_dict_generator(
                "https://example.com/layer/0",
                session,
            )
        ]

    assert [row["CITY"] for row in rows] == ["DAYTONA", "ORMOND"]
    assert rows[0]["geometry"] == {"x": 0, "y": 0}


@pytest.mark.asyncio
async def test_row_dict_generator_uses_query_batch_data_without_duplicate_kwargs():
    session = QuerySession(
        [
            {
                "features": [
                    {
                        "attributes": {"CITY": "DAYTONA"},
                    },
                ],
            },
        ],
    )

    with patch(
        "restgdf.utils.getgdf.get_query_data_batches",
        new=AsyncMock(
            return_value=[
                {
                    "where": "CITY = 'DAYTONA'",
                    "outFields": "CITY",
                },
            ],
        ),
    ):
        rows = [
            row
            async for row in row_dict_generator(
                "https://example.com/layer/0",
                session,
                data={"outFields": "CITY"},
            )
        ]

    assert rows == [{"CITY": "DAYTONA"}]
    assert len(session.post_calls) == 1
    post_url, post_kwargs = session.post_calls[0]
    assert post_url == "https://example.com/layer/0/query"
    assert post_kwargs["data"] == {
        "where": "CITY = 'DAYTONA'",
        "outFields": "CITY",
    }
    assert post_kwargs["headers"]["Accept"] == "application/json,text/plain,*/*"
    assert post_kwargs["headers"]["User-Agent"] == "Mozilla/5.0"


@pytest.mark.asyncio
async def test_featurelayer_row_dict_generator_merges_data_kwargs():
    layer = FeatureLayer(
        "https://example.com/arcgis/rest/services/Secured/FeatureServer/0",
        session=object(),
        where="CITY = 'DAYTONA'",
        token="saved-token",
    )

    async def fake_row_dict_generator(url, session, **kwargs):
        assert kwargs["data"]["where"] == "CITY = 'DAYTONA'"
        assert kwargs["data"]["token"] == "saved-token"
        assert kwargs["data"]["outFields"] == "CITY"
        yield {"ok": True}

    with patch(
        "restgdf.featurelayer.featurelayer.row_dict_generator",
        side_effect=fake_row_dict_generator,
    ):
        rows = [
            row async for row in layer.row_dict_generator(data={"outFields": "CITY"})
        ]

    assert rows == [{"ok": True}]


@pytest.mark.asyncio
async def test_get_unique_values_single_field_stays_pure_python():
    session = QuerySession(
        [
            {
                "features": [
                    {"attributes": {"City": "DAYTONA"}},
                    {"attributes": {"City": "ORMOND"}},
                ],
            },
        ],
    )

    with patch(
        "restgdf.utils._stats.require_pandas_dataframe",
        side_effect=AssertionError(
            "single-field unique values should stay pure-python",
        ),
    ):
        result = await get_unique_values("test", "City", session=session)

    assert result == ["DAYTONA", "ORMOND"]


def test_get_fields_frame_requires_geo_extra_message():
    with patch(
        "restgdf.utils._optional.import_module",
        side_effect=_optional_import_side_effect(missing="pandas"),
    ):
        with pytest.raises(
            ModuleNotFoundError,
            match=r"get_fields_frame\(\).*pandas.*restgdf\[geo\]",
        ):
            get_fields_frame(SAMPLE_METADATA)


@pytest.mark.asyncio
async def test_get_unique_values_multi_field_requires_geo_extra_before_request():
    with patch(
        "restgdf.utils._optional.import_module",
        side_effect=_optional_import_side_effect(missing="pandas"),
    ):
        with pytest.raises(
            ModuleNotFoundError,
            match=r"get_unique_values\(\) with multiple fields.*restgdf\[geo\]",
        ):
            await get_unique_values(
                "test",
                ("City", "Status"),
                session=RejectingSession(),
            )


@pytest.mark.asyncio
async def test_get_value_counts_requires_geo_extra_before_request():
    with patch(
        "restgdf.utils._optional.import_module",
        side_effect=_optional_import_side_effect(missing="pandas"),
    ):
        with pytest.raises(
            ModuleNotFoundError,
            match=r"get_value_counts\(\).*restgdf\[geo\]",
        ):
            await get_value_counts("test", "City", RejectingSession())


@pytest.mark.asyncio
async def test_nested_count_requires_geo_extra_before_request():
    with patch(
        "restgdf.utils._optional.import_module",
        side_effect=_optional_import_side_effect(missing="pandas"),
    ):
        with pytest.raises(
            ModuleNotFoundError,
            match=r"nested_count\(\).*restgdf\[geo\]",
        ):
            await nested_count("test", ("City", "Status"), RejectingSession())


@pytest.mark.asyncio
async def test_get_gdf_requires_geo_extra_before_batch_queries():
    with patch(
        "restgdf.utils._optional.import_module",
        side_effect=_optional_import_side_effect(missing="pandas"),
    ), patch(
        "restgdf.utils.getgdf.gdf_by_concat",
        new=AsyncMock(side_effect=AssertionError("should fail before querying")),
    ):
        with pytest.raises(
            ModuleNotFoundError,
            match=r"get_gdf\(\).*restgdf\[geo\]",
        ):
            await get_gdf("https://example.com/layer/0", session=object())


@pytest.mark.asyncio
async def test_get_sub_gdf_requires_geo_dependencies_on_demand():
    session = RecordingTextSession('{"features": []}')

    with patch("restgdf.utils.getgdf.supported_drivers", new=None), patch(
        "restgdf.utils._optional.import_module",
        side_effect=_optional_import_side_effect(
            missing="pyogrio",
            provided={
                "pandas": ModuleType("pandas"),
                "geopandas": ModuleType("geopandas"),
            },
        ),
    ):
        with pytest.raises(
            ModuleNotFoundError,
            match=r"get_sub_gdf\(\).*pyogrio.*restgdf\[geo\]",
        ):
            await get_sub_gdf(
                "https://example.com/layer/0",
                session,
                query_data={"where": "1=1"},
            )

    assert session.post_calls == []


@pytest.mark.asyncio
async def test_featurelayer_prep_defers_fieldtypes_until_requested():
    session = MockFeatureLayerSession(metadata=SAMPLE_METADATA, count=7)
    layer = FeatureLayer(
        "https://example.com/arcgis/rest/services/Secured/FeatureServer/0",
        session=session,
    )

    with patch(
        "restgdf.featurelayer.featurelayer.get_fields_frame",
        side_effect=AssertionError("fieldtypes should be lazy"),
    ):
        await layer.prep()

    with patch(
        "restgdf.utils._optional.import_module",
        side_effect=_optional_import_side_effect(missing="pandas"),
    ):
        with pytest.raises(
            ModuleNotFoundError,
            match=r"get_fields_frame\(\).*restgdf\[geo\]",
        ):
            _ = layer.fieldtypes


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method_name", "args"),
    [("sample_gdf", (10,)), ("head_gdf", (2,))],
)
async def test_featurelayer_geo_helpers_require_geo_extra_before_oid_queries(
    method_name,
    args,
):
    layer = FeatureLayer(
        "https://example.com/arcgis/rest/services/Secured/FeatureServer/0",
        session=MockFeatureLayerSession(metadata=SAMPLE_METADATA, count=7),
    )
    layer.object_id_field = "OBJECTID"
    layer.fields = ("OBJECTID",)

    with patch(
        "restgdf.utils._optional.import_module",
        side_effect=_optional_import_side_effect(missing="pandas"),
    ), patch(
        "restgdf.featurelayer.featurelayer.get_unique_values",
        new=AsyncMock(side_effect=AssertionError("should fail before fetching ids")),
    ):
        with pytest.raises(
            ModuleNotFoundError,
            match=rf"FeatureLayer\.{method_name}\(\).*restgdf\[geo\]",
        ):
            await getattr(layer, method_name)(*args)


@pytest.mark.asyncio
async def test_featurelayer_get_gdf_requires_geo_extra_before_query():
    layer = FeatureLayer(
        "https://example.com/arcgis/rest/services/Secured/FeatureServer/0",
        session=MockFeatureLayerSession(metadata=SAMPLE_METADATA, count=7),
    )

    with patch(
        "restgdf.utils._optional.import_module",
        side_effect=_optional_import_side_effect(missing="pandas"),
    ), patch(
        "restgdf.featurelayer.featurelayer.get_gdf",
        new=AsyncMock(side_effect=AssertionError("should fail before querying")),
    ):
        with pytest.raises(
            ModuleNotFoundError,
            match=r"FeatureLayer\.get_gdf\(\).*restgdf\[geo\]",
        ):
            await layer.get_gdf()
