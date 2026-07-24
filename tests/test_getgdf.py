from __future__ import annotations

import asyncio
import importlib
import io
from unittest.mock import AsyncMock, call, patch

import pytest
from geopandas import GeoDataFrame

from restgdf._models import RestgdfResponseError
from restgdf.errors import PaginationError
from tests.pagination_fixtures import load_pagination_fixture

from restgdf.utils.getgdf import (
    _feature_batch_generator,
    chunk_generator,
    chunk_values,
    combine_where_clauses,
    get_gdf,
    get_gdf_list,
    get_query_data_batches,
    get_sub_features,
    get_sub_gdf,
    row_dict_generator,
)


class RecordingSession:
    def __init__(self, response_text: str = "{}"):
        self.response_text = response_text
        self.post_calls: list[tuple[str, dict]] = []
        self._closed = False

    @property
    def closed(self) -> bool:
        return self._closed

    async def close(self) -> None:
        self._closed = True

    async def post(self, url: str, **kwargs):
        self.post_calls.append((url, kwargs))

        class Response:
            def __init__(self, text_payload: str):
                self._text_payload = text_payload

            async def text(self):
                return self._text_payload

        return Response(self.response_text)

    async def get(self, url: str, **kwargs):
        # Translate params→data so the recorded kwargs snapshot matches
        # the legacy POST shape. T8 (R-74): short GETs now hit call sites
        # that used to issue POST; preserving the POST-shaped record keeps
        # existing assertions intact.
        if "params" in kwargs:
            params = kwargs.pop("params")
            kwargs.setdefault("data", params)
        return await self.post(url, **kwargs)


class JsonSession:
    def __init__(self, payloads: list[dict]):
        self.payloads = list(payloads)
        self.post_calls: list[tuple[str, dict]] = []

    async def post(self, url: str, **kwargs):
        self.post_calls.append((url, kwargs))

        class Response:
            def __init__(self, payload: dict):
                self._payload = payload

            async def json(self, content_type=None):
                return self._payload

        return Response(self.payloads.pop(0))

    async def get(self, url: str, **kwargs):
        if "params" in kwargs:
            params = kwargs.pop("params")
            kwargs.setdefault("data", params)
        return await self.post(url, **kwargs)


def _missing_optional_import(target: str):
    def _side_effect(module_name: str):
        if module_name == target:
            exc = ModuleNotFoundError(f"No module named '{target}'")
            exc.name = target
            raise exc
        return importlib.import_module(module_name)

    return _side_effect


@pytest.mark.parametrize(
    ("base_where", "extra_where", "expected"),
    [
        (None, "OBJECTID In (1, 2)", "OBJECTID In (1, 2)"),
        ("", "OBJECTID In (1, 2)", "OBJECTID In (1, 2)"),
        ("1=1", "OBJECTID In (1, 2)", "OBJECTID In (1, 2)"),
        (
            "CITY = 'DAYTONA'",
            "OBJECTID In (1, 2)",
            "(CITY = 'DAYTONA') AND (OBJECTID In (1, 2))",
        ),
    ],
)
def test_combine_where_clauses(base_where, extra_where, expected):
    assert combine_where_clauses(base_where, extra_where) == expected


def test_chunk_values_splits_evenly():
    assert chunk_values([1, 2, 3, 4, 5], 2) == [[1, 2], [3, 4], [5]]


@pytest.mark.asyncio
async def test_get_query_data_batches_returns_single_request_when_under_limit():
    with patch(
        "restgdf.utils.getgdf.get_feature_count",
        new=AsyncMock(return_value=2),
    ), patch(
        "restgdf.utils.getgdf.get_metadata",
        new=AsyncMock(return_value={"maxRecordCount": 5}),
    ):
        result = await get_query_data_batches(
            "https://example.com/layer/0",
            object(),
            data={"where": "CITY = 'DAYTONA'", "token": "abc"},
        )

    assert result == [{"where": "CITY = 'DAYTONA'", "token": "abc"}]


@pytest.mark.asyncio
async def test_get_query_data_batches_uses_result_offsets_when_supported():
    with patch(
        "restgdf.utils.getgdf.get_feature_count",
        new=AsyncMock(return_value=5),
    ), patch(
        "restgdf.utils.getgdf.get_metadata",
        new=AsyncMock(
            return_value={
                "maxRecordCount": 2,
                "advancedQueryCapabilities": {"supportsPagination": True},
            },
        ),
    ):
        result = await get_query_data_batches(
            "https://example.com/layer/0",
            object(),
            data={"where": "CITY = 'DAYTONA'"},
        )

    assert result == [
        {"where": "CITY = 'DAYTONA'", "resultOffset": 0, "resultRecordCount": 2},
        {"where": "CITY = 'DAYTONA'", "resultOffset": 2, "resultRecordCount": 2},
        {"where": "CITY = 'DAYTONA'", "resultOffset": 4, "resultRecordCount": 1},
    ]


@pytest.mark.asyncio
async def test_get_query_data_batches_chunks_object_ids_when_pagination_disabled():
    with patch(
        "restgdf.utils.getgdf.get_feature_count",
        new=AsyncMock(return_value=5),
    ), patch(
        "restgdf.utils.getgdf.get_metadata",
        new=AsyncMock(
            return_value={
                "maxRecordCount": 2,
                "advancedQueryCapabilities": {"supportsPagination": False},
            },
        ),
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
async def test_get_query_data_batches_uses_object_id_chunks_for_missing_pagination_flag_fixture():
    metadata = load_pagination_fixture("metadata_missing_supports_pagination.json")

    with patch(
        "restgdf.utils.getgdf.get_feature_count",
        new=AsyncMock(return_value=2001),
    ), patch(
        "restgdf.utils.getgdf.get_metadata",
        new=AsyncMock(return_value=metadata),
    ), patch(
        "restgdf.utils.getgdf.get_object_ids",
        new=AsyncMock(return_value=("OBJECTID", list(range(1, 2002)))),
    ):
        result = await get_query_data_batches(
            "https://example.com/layer/0",
            object(),
            data={"where": "CITY = 'DAYTONA'"},
        )

    assert len(result) == 3
    assert all("resultOffset" not in batch for batch in result)
    assert result[0]["where"].startswith("(CITY = 'DAYTONA') AND (OBJECTID In (1, 2, 3")


@pytest.mark.asyncio
async def test_get_query_data_batches_should_not_assume_offsets_when_paging_flag_is_missing():
    metadata = load_pagination_fixture("metadata_missing_supports_pagination.json")

    with patch(
        "restgdf.utils.getgdf.get_feature_count",
        new=AsyncMock(return_value=2001),
    ), patch(
        "restgdf.utils.getgdf.get_metadata",
        new=AsyncMock(return_value=metadata),
    ), patch(
        "restgdf.utils.getgdf.get_object_ids",
        new=AsyncMock(return_value=("OBJECTID", list(range(1, 2002)))),
    ) as mock_get_object_ids:
        result = await get_query_data_batches(
            "https://example.com/layer/0",
            object(),
            data={"where": "CITY = 'DAYTONA'"},
        )

    mock_get_object_ids.assert_awaited_once()
    assert len(result) == 3
    assert all("resultOffset" not in batch for batch in result)
    assert result[0]["where"].startswith("(CITY = 'DAYTONA') AND (OBJECTID In (1, 2, 3")


@pytest.mark.asyncio
async def test_get_query_data_batches_uses_object_id_chunks_for_pagination_false_fixture():
    metadata = load_pagination_fixture("metadata_supports_pagination_false.json")

    with patch(
        "restgdf.utils.getgdf.get_feature_count",
        new=AsyncMock(return_value=2001),
    ), patch(
        "restgdf.utils.getgdf.get_metadata",
        new=AsyncMock(return_value=metadata),
    ), patch(
        "restgdf.utils.getgdf.get_object_ids",
        new=AsyncMock(return_value=("OBJECTID", list(range(1, 2002)))),
    ):
        result = await get_query_data_batches(
            "https://example.com/layer/0",
            object(),
            data={"where": "CITY = 'DAYTONA'"},
        )

    assert len(result) == 3
    assert all("resultOffset" not in batch for batch in result)
    assert result[0]["where"].startswith("(CITY = 'DAYTONA') AND (OBJECTID In (1, 2, 3")
    assert result[-1]["where"].endswith("2001))")


@pytest.mark.asyncio
async def test_get_sub_gdf_uses_geojson_driver_when_esrijson_missing(
    sample_feature_gdf,
):
    session = RecordingSession(response_text='{"features": []}')

    with patch(
        "restgdf.utils.getgdf.supported_drivers",
        new={"GeoJSON": "rw"},
    ), patch(
        "restgdf.utils.getgdf.read_file",
        return_value=sample_feature_gdf,
    ) as mock_read_file:
        result = await get_sub_gdf(
            "https://example.com/layer/0",
            session,
            query_data={"where": "1=1"},
            data={"ignored": True},
            headers={"X-Test": "yes"},
            timeout=12,
        )

    assert result.equals(sample_feature_gdf)
    assert session.post_calls == [
        (
            "https://example.com/layer/0/query",
            {
                "data": {"where": "1=1", "f": "GeoJSON"},
                "headers": {
                    "Accept": "application/json,text/plain,*/*",
                    "User-Agent": "Mozilla/5.0",
                    "X-Test": "yes",
                },
                "timeout": 12,
            },
        ),
    ]
    mock_read_file.assert_called_once()


@pytest.mark.asyncio
async def test_get_sub_gdf_passes_file_like_geojson_to_reader(sample_feature_gdf):
    geojson_text = '{"type":"FeatureCollection","features":[]}'
    session = RecordingSession(response_text=geojson_text)

    def _fake_read_file(source, *args, **kwargs):
        assert isinstance(source, io.StringIO)
        assert source.getvalue() == geojson_text
        return sample_feature_gdf

    with patch(
        "restgdf.utils.getgdf.supported_drivers",
        new={"GeoJSON": "rw"},
    ), patch(
        "restgdf.utils.getgdf.read_file",
        side_effect=_fake_read_file,
    ) as mock_read_file:
        result = await get_sub_gdf(
            "https://example.com/layer/0",
            session,
            query_data={"where": "1=1"},
        )

    assert result.equals(sample_feature_gdf)
    mock_read_file.assert_called_once()


@pytest.mark.asyncio
async def test_get_gdf_list_builds_tasks_from_batches(sample_feature_gdf):
    session = object()
    with patch(
        "restgdf.utils.getgdf.get_query_data_batches",
        new=AsyncMock(return_value=[{"where": "1=1"}, {"where": "OBJECTID > 5"}]),
    ), patch(
        "restgdf.utils.getgdf.get_sub_gdf",
        new=AsyncMock(side_effect=[sample_feature_gdf, sample_feature_gdf.iloc[[0]]]),
    ) as mock_get_sub_gdf:
        result = await get_gdf_list("https://example.com/layer/0", session)

    assert len(result) == 2
    assert mock_get_sub_gdf.await_args_list == [
        call(
            "https://example.com/layer/0",
            session,
            query_data={"where": "1=1"},
        ),
        call(
            "https://example.com/layer/0",
            session,
            query_data={"where": "OBJECTID > 5"},
        ),
    ]


@pytest.mark.asyncio
async def test_get_gdf_list_cancels_sibling_tasks_on_failure() -> None:
    gate = asyncio.Event()
    sibling_cancelled = asyncio.Event()
    session = RecordingSession()

    async def fake_get_sub_gdf(url, session, query_data, **kwargs):
        if query_data["where"] == "boom":
            raise RuntimeError("boom")
        try:
            await gate.wait()
        except asyncio.CancelledError:
            sibling_cancelled.set()
            raise
        return GeoDataFrame()

    with patch(
        "restgdf.utils.getgdf.get_query_data_batches",
        new=AsyncMock(return_value=[{"where": "boom"}, {"where": "slow"}]),
    ), patch(
        "restgdf.utils.getgdf.get_sub_gdf",
        new=fake_get_sub_gdf,
    ):
        with pytest.raises(RuntimeError, match="boom"):
            await get_gdf_list("https://example.com/layer/0", session)

    assert sibling_cancelled.is_set()


@pytest.mark.asyncio
async def test_chunk_generator_yields_each_chunk(sample_feature_gdf):
    with patch(
        "restgdf.utils.getgdf.get_query_data_batches",
        new=AsyncMock(return_value=[{"where": "1=1"}, {"where": "OBJECTID > 5"}]),
    ), patch(
        "restgdf.utils.getgdf.get_sub_gdf",
        new=AsyncMock(side_effect=[sample_feature_gdf, sample_feature_gdf.iloc[[0]]]),
    ):
        chunks = [
            chunk
            async for chunk in chunk_generator("https://example.com/layer/0", object())
        ]

    assert len(chunks) == 2
    assert all(isinstance(chunk, GeoDataFrame) for chunk in chunks)


@pytest.mark.asyncio
async def test_row_dict_generator_yields_rows(sample_feature_gdf):
    del sample_feature_gdf
    with patch(
        "restgdf.utils.getgdf.chunk_generator",
        return_value=None,
    ) as mock_chunk_generator, patch(
        "restgdf.utils.getgdf.get_query_data_batches",
        new=AsyncMock(return_value=[{"where": "1=1"}, {"where": "OBJECTID > 5"}]),
    ), patch(
        "restgdf.utils.getgdf.get_sub_gdf",
        side_effect=AssertionError("row_dict_generator should not require geopandas"),
    ):

        class Session:
            def __init__(self):
                self.responses = [
                    {
                        "features": [
                            {
                                "attributes": {"CITY": "DAYTONA"},
                                "geometry": {"x": 0, "y": 0},
                            },
                        ],
                    },
                    {"features": [{"attributes": {"CITY": "ORMOND"}}]},
                ]

            async def post(self, url: str, **kwargs):
                class Response:
                    def __init__(self, payload):
                        self._payload = payload

                    async def json(self, content_type=None):
                        return self._payload

                return Response(self.responses.pop(0))

            async def get(self, url: str, **kwargs):
                if "params" in kwargs and "data" not in kwargs:
                    kwargs = {**kwargs, "data": kwargs["params"]}
                return await self.post(url, **kwargs)

        rows = [
            row
            async for row in row_dict_generator(
                "https://example.com/layer/0",
                Session(),
            )
        ]

    assert [row["CITY"] for row in rows] == ["DAYTONA", "ORMOND"]
    assert rows[0]["geometry"] == {"x": 0, "y": 0}
    mock_chunk_generator.assert_not_called()


@pytest.mark.asyncio
async def test_feature_batch_generator_caps_scheduled_tasks_and_cancels_on_close():
    gate = asyncio.Event()
    created: list[asyncio.Task] = []
    orig_create_task = asyncio.create_task

    async def fake_get_sub_features(*args, **kwargs):
        await gate.wait()
        return []

    def spy_create_task(coro):
        task = orig_create_task(coro)
        created.append(task)
        return task

    cfg = type(
        "Cfg",
        (),
        {"concurrency": type("Conc", (), {"max_concurrent_requests": 2})()},
    )()

    with patch(
        "restgdf.utils.getgdf.get_query_data_batches",
        new=AsyncMock(return_value=[{"resultOffset": i} for i in range(25)]),
    ), patch(
        "restgdf.utils.getgdf.get_sub_features",
        new=fake_get_sub_features,
    ), patch(
        "restgdf.utils.getgdf.get_config",
        return_value=cfg,
    ), patch(
        "asyncio.create_task",
        new=spy_create_task,
    ):
        agen = _feature_batch_generator("https://example.com/layer/0", object())
        consumer = orig_create_task(agen.__anext__())
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert len(created) == 2
        consumer.cancel()
        with pytest.raises(asyncio.CancelledError):
            await consumer
        await agen.aclose()
        await asyncio.sleep(0)
        assert all(task.done() for task in created)
        gate.set()


@pytest.mark.asyncio
async def test_get_sub_features_should_reject_truncated_empty_feature_page():
    session = JsonSession(
        [load_pagination_fixture("query_exceeded_transfer_limit_empty_features.json")],
    )

    with pytest.raises(PaginationError, match="exceededTransferLimit"):
        await get_sub_features(
            "https://example.com/layer/0",
            session,
            query_data={"where": "1=1"},
        )


@pytest.mark.asyncio
async def test_chunk_generator_caps_scheduled_tasks_and_cancels_on_close():
    gate = asyncio.Event()
    created: list[asyncio.Task] = []
    orig_create_task = asyncio.create_task

    async def fake_get_sub_gdf(*args, **kwargs):
        await gate.wait()
        return GeoDataFrame()

    def spy_create_task(coro):
        task = orig_create_task(coro)
        created.append(task)
        return task

    cfg = type(
        "Cfg",
        (),
        {"concurrency": type("Conc", (), {"max_concurrent_requests": 2})()},
    )()

    with patch(
        "restgdf.utils.getgdf.get_query_data_batches",
        new=AsyncMock(return_value=[{"resultOffset": i} for i in range(25)]),
    ), patch(
        "restgdf.utils.getgdf.get_sub_gdf",
        new=fake_get_sub_gdf,
    ), patch(
        "restgdf.utils.getgdf.get_metadata",
        new=AsyncMock(return_value={}),
    ), patch(
        "restgdf.utils.getgdf.get_config",
        return_value=cfg,
    ), patch(
        "asyncio.create_task",
        new=spy_create_task,
    ):
        agen = chunk_generator("https://example.com/layer/0", object())
        consumer = orig_create_task(agen.__anext__())
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert len(created) == 2
        consumer.cancel()
        with pytest.raises(asyncio.CancelledError):
            await consumer
        await agen.aclose()
        await asyncio.sleep(0)
        assert all(task.done() for task in created)
        gate.set()


@pytest.mark.asyncio
async def test_get_sub_features_should_reject_truncated_short_feature_page():
    session = JsonSession(
        [load_pagination_fixture("query_exceeded_transfer_limit_short_page.json")],
    )

    with pytest.raises(PaginationError, match="exceededTransferLimit"):
        await get_sub_features(
            "https://example.com/layer/0",
            session,
            query_data={"where": "1=1"},
        )


@pytest.mark.asyncio
async def test_get_sub_features_raises_on_arcgis_error_envelope():
    session = JsonSession(
        [
            {
                "error": {
                    "code": 400,
                    "message": "Unable to perform query.",
                    "details": ["where clause is invalid"],
                },
            },
        ],
    )

    with pytest.raises(RestgdfResponseError, match="ArcGIS error envelope"):
        await get_sub_features(
            "https://example.com/layer/0",
            session,
            query_data={"where": "CITY = 'DAYTONA'"},
        )


@pytest.mark.asyncio
async def test_get_gdf_forwards_token_and_detects_conflicts():
    session = object()
    with patch(
        "restgdf.utils.getgdf.gdf_by_concat",
        new=AsyncMock(return_value="sentinel"),
    ) as mock_gdf_by_concat:
        result = await get_gdf(
            "https://example.com/layer/0",
            session=session,
            where="CITY = 'DAYTONA'",
            token="abc",
        )

    assert result == "sentinel"
    mock_gdf_by_concat.assert_awaited_once_with(
        "https://example.com/layer/0",
        session,
        data={
            "where": "CITY = 'DAYTONA'",
            "outFields": "*",
            "returnGeometry": True,
            "returnCountOnly": False,
            "f": "json",
            "token": "abc",
        },
    )

    with pytest.raises(ValueError):
        await get_gdf(
            "https://example.com/layer/0",
            session=object(),
            token="abc",
            data={"token": "different"},
        )


@pytest.mark.asyncio
async def test_get_gdf_closes_internally_created_session():
    with patch(
        "restgdf.utils.getgdf.gdf_by_concat",
        new=AsyncMock(return_value="sentinel"),
    ) as mock_gdf_by_concat:
        result = await get_gdf("https://example.com/layer/0", session=None)

    assert result == "sentinel"
    created_session = mock_gdf_by_concat.await_args.args[1]
    assert created_session.closed is True


@pytest.mark.asyncio
async def test_get_gdf_requires_geo_extra_before_batch_queries():
    with patch(
        "restgdf.utils._optional.import_module",
        side_effect=_missing_optional_import("pyogrio"),
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
    session = RecordingSession(response_text='{"features": []}')

    with patch("restgdf.utils.getgdf.supported_drivers", new=None), patch(
        "restgdf.utils._optional.import_module",
        side_effect=_missing_optional_import("pyogrio"),
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
