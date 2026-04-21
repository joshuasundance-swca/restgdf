from __future__ import annotations

from unittest.mock import AsyncMock, call, patch

import pytest
from geopandas import GeoDataFrame

from restgdf.utils.getgdf import (
    chunk_generator,
    chunk_values,
    combine_where_clauses,
    get_gdf,
    get_gdf_list,
    get_query_data_batches,
    get_sub_gdf,
    row_dict_generator,
)


class RecordingSession:
    def __init__(self, response_text: str = "{}"):
        self.response_text = response_text
        self.post_calls: list[tuple[str, dict]] = []

    async def post(self, url: str, **kwargs):
        self.post_calls.append((url, kwargs))

        class Response:
            def __init__(self, text_payload: str):
                self._text_payload = text_payload

            async def text(self):
                return self._text_payload

        return Response(self.response_text)


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
    with (
        patch(
            "restgdf.utils.getgdf.get_feature_count",
            new=AsyncMock(return_value=2),
        ),
        patch(
            "restgdf.utils.getgdf.get_metadata",
            new=AsyncMock(return_value={"maxRecordCount": 5}),
        ),
    ):
        result = await get_query_data_batches(
            "https://example.com/layer/0",
            object(),
            data={"where": "CITY = 'DAYTONA'", "token": "abc"},
        )

    assert result == [{"where": "CITY = 'DAYTONA'", "token": "abc"}]


@pytest.mark.asyncio
async def test_get_query_data_batches_uses_result_offsets_when_supported():
    with (
        patch(
            "restgdf.utils.getgdf.get_feature_count",
            new=AsyncMock(return_value=5),
        ),
        patch(
            "restgdf.utils.getgdf.get_metadata",
            new=AsyncMock(
                return_value={
                    "maxRecordCount": 2,
                    "advancedQueryCapabilities": {"supportsPagination": True},
                },
            ),
        ),
    ):
        result = await get_query_data_batches(
            "https://example.com/layer/0",
            object(),
            data={"where": "CITY = 'DAYTONA'"},
        )

    assert result == [
        {"where": "CITY = 'DAYTONA'", "resultOffset": 0},
        {"where": "CITY = 'DAYTONA'", "resultOffset": 2},
        {"where": "CITY = 'DAYTONA'", "resultOffset": 4},
    ]


@pytest.mark.asyncio
async def test_get_query_data_batches_chunks_object_ids_when_pagination_disabled():
    with (
        patch(
            "restgdf.utils.getgdf.get_feature_count",
            new=AsyncMock(return_value=5),
        ),
        patch(
            "restgdf.utils.getgdf.get_metadata",
            new=AsyncMock(
                return_value={
                    "maxRecordCount": 2,
                    "advancedQueryCapabilities": {"supportsPagination": False},
                },
            ),
        ),
        patch(
            "restgdf.utils.getgdf.get_object_ids",
            new=AsyncMock(return_value=("OBJECTID", [1, 2, 3, 4, 5])),
        ),
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
async def test_get_sub_gdf_uses_geojson_driver_when_esrijson_missing(
    sample_feature_gdf,
):
    session = RecordingSession(response_text='{"features": []}')

    with (
        patch(
            "restgdf.utils.getgdf.supported_drivers",
            new={"GeoJSON": "rw"},
        ),
        patch(
            "restgdf.utils.getgdf.read_file",
            return_value=sample_feature_gdf,
        ) as mock_read_file,
    ):
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
async def test_get_gdf_list_builds_tasks_from_batches(sample_feature_gdf):
    session = object()
    with (
        patch(
            "restgdf.utils.getgdf.get_query_data_batches",
            new=AsyncMock(return_value=[{"where": "1=1"}, {"where": "OBJECTID > 5"}]),
        ),
        patch(
            "restgdf.utils.getgdf.get_sub_gdf",
            new=AsyncMock(
                side_effect=[sample_feature_gdf, sample_feature_gdf.iloc[[0]]]
            ),
        ) as mock_get_sub_gdf,
    ):
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
async def test_chunk_generator_yields_each_chunk(sample_feature_gdf):
    with (
        patch(
            "restgdf.utils.getgdf.get_query_data_batches",
            new=AsyncMock(return_value=[{"where": "1=1"}, {"where": "OBJECTID > 5"}]),
        ),
        patch(
            "restgdf.utils.getgdf.get_sub_gdf",
            new=AsyncMock(
                side_effect=[sample_feature_gdf, sample_feature_gdf.iloc[[0]]]
            ),
        ),
    ):
        chunks = [
            chunk
            async for chunk in chunk_generator("https://example.com/layer/0", object())
        ]

    assert len(chunks) == 2
    assert all(isinstance(chunk, GeoDataFrame) for chunk in chunks)


@pytest.mark.asyncio
async def test_row_dict_generator_yields_rows(sample_feature_gdf):
    with patch(
        "restgdf.utils.getgdf.chunk_generator",
        return_value=None,
    ) as mock_chunk_generator:

        async def fake_chunk_generator(*args, **kwargs):
            yield sample_feature_gdf.iloc[[0]]
            yield sample_feature_gdf.iloc[[1]]

        mock_chunk_generator.side_effect = fake_chunk_generator
        rows = [
            row
            async for row in row_dict_generator("https://example.com/layer/0", object())
        ]

    assert [row["CITY"] for row in rows] == ["DAYTONA", "ORMOND"]


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
