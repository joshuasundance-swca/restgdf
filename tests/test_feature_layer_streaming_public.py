"""Q-A11 red tests: public streaming API on :class:`FeatureLayer`.

Covers:

* ``stream_features`` == ``iter_features`` (alias)
* ``stream_feature_batches`` yields batch lists
* ``stream_rows`` yields row-shaped dicts
* ``stream_gdf_chunks`` yields GeoDataFrames
* ``row_dict_generator`` is a deprecated shim emitting
  ``DeprecationWarning`` and delegating to ``stream_rows``
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from restgdf.featurelayer.featurelayer import FeatureLayer


class _JsonResp:
    def __init__(self, payload):
        self._payload = payload

    async def json(self, content_type=None):
        return self._payload


class _ScriptedSession:
    def __init__(self, payloads):
        self.payloads = list(payloads)
        self.post_calls: list[tuple[str, dict]] = []

    async def post(self, url: str, **kwargs):
        self.post_calls.append((url, kwargs))
        return _JsonResp(self.payloads.pop(0))

    async def get(self, url, **kwargs):
        if "params" in kwargs and "data" not in kwargs:
            kwargs = {**kwargs, "data": kwargs["params"]}
        return await self.post(url, **kwargs)


def _make_layer():
    layer = FeatureLayer(
        "https://example.com/arcgis/rest/services/Svc/FeatureServer/0",
        session=object(),
    )
    layer.fields = ("OBJECTID", "CITY")
    layer.object_id_field = "OBJECTID"
    return layer


@pytest.mark.asyncio
async def test_stream_features_is_iter_features_alias():
    assert FeatureLayer.stream_features is FeatureLayer.iter_features


@pytest.mark.asyncio
async def test_stream_features_yields_flat_feature_dicts():
    layer = _make_layer()
    layer.session = _ScriptedSession(
        [
            {"features": [{"attributes": {"OBJECTID": 1}}]},
            {
                "features": [
                    {"attributes": {"OBJECTID": 2}},
                    {"attributes": {"OBJECTID": 3}},
                ],
            },
        ],
    )
    with patch(
        "restgdf.utils.getgdf.get_query_data_batches",
        new=AsyncMock(return_value=[{"resultOffset": 0}, {"resultOffset": 1}]),
    ):
        features = [f async for f in layer.stream_features(order="request")]

    oids = [f["attributes"]["OBJECTID"] for f in features]
    assert oids == [1, 2, 3]


@pytest.mark.asyncio
async def test_stream_feature_batches_yields_lists():
    layer = _make_layer()
    layer.session = _ScriptedSession(
        [
            {"features": [{"attributes": {"OBJECTID": 1}}]},
            {"features": [{"attributes": {"OBJECTID": 2}}]},
        ],
    )
    with patch(
        "restgdf.utils.getgdf.get_query_data_batches",
        new=AsyncMock(return_value=[{"resultOffset": 0}, {"resultOffset": 1}]),
    ):
        batches = [b async for b in layer.stream_feature_batches(order="request")]

    assert all(isinstance(b, list) for b in batches)
    flat = [f["attributes"]["OBJECTID"] for b in batches for f in b]
    assert flat == [1, 2]


@pytest.mark.asyncio
async def test_stream_rows_yields_row_shaped_dicts():
    layer = _make_layer()
    layer.session = _ScriptedSession(
        [
            {
                "features": [
                    {"attributes": {"OBJECTID": 1, "CITY": "DAYTONA"}},
                ],
            },
            {
                "features": [
                    {"attributes": {"OBJECTID": 2, "CITY": "ORMOND"}},
                ],
            },
        ],
    )
    with patch(
        "restgdf.utils.getgdf.get_query_data_batches",
        new=AsyncMock(return_value=[{"resultOffset": 0}, {"resultOffset": 1}]),
    ):
        rows = [r async for r in layer.stream_rows(order="request")]

    assert rows == [
        {"OBJECTID": 1, "CITY": "DAYTONA"},
        {"OBJECTID": 2, "CITY": "ORMOND"},
    ]


@pytest.mark.asyncio
async def test_stream_gdf_chunks_yields_geodataframes():
    pytest.importorskip("pandas")
    pytest.importorskip("geopandas")
    pytest.importorskip("pyogrio")

    layer = _make_layer()
    sentinel = [object(), object()]

    async def _fake_chunk_gen(url, session, **kwargs):
        for s in sentinel:
            yield s

    with patch(
        "restgdf.featurelayer.featurelayer.chunk_generator",
        side_effect=_fake_chunk_gen,
    ):
        chunks = [c async for c in layer.stream_gdf_chunks()]

    assert chunks == sentinel


@pytest.mark.asyncio
async def test_row_dict_generator_is_deprecated_alias():
    layer = _make_layer()
    layer.session = _ScriptedSession(
        [{"features": [{"attributes": {"OBJECTID": 1, "CITY": "DAYTONA"}}]}],
    )
    with patch(
        "restgdf.utils.getgdf.get_query_data_batches",
        new=AsyncMock(return_value=[{"resultOffset": 0}]),
    ):
        with pytest.warns(DeprecationWarning, match="row_dict_generator"):
            rows = [r async for r in layer.row_dict_generator()]

    assert rows == [{"OBJECTID": 1, "CITY": "DAYTONA"}]
