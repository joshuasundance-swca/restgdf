"""Characterization tests pinning current restgdf behavior.

These tests are part of the Phase 0 safety net for the TDD refactor. They
intentionally assert on concrete, observable behavior of the *current*
implementation (request body shape, call precedence, batch boundaries,
caching semantics, crawl error-swallowing) so that subsequent refactors are
guarded against silent regressions.

If one of these tests fails during a refactor, treat it as a deliberate
decision point: either update the test (documenting the intended behavior
change) or fix the regression.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from pandas import DataFrame

from restgdf.featurelayer.featurelayer import FeatureLayer
from restgdf.utils import crawl as crawl_mod
from restgdf.utils import getgdf as getgdf_mod
from restgdf.utils import getinfo as getinfo_mod

pytestmark = pytest.mark.characterization


# ---------------------------------------------------------------------------
# getinfo: request body (datadict) shape
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_feature_count_sends_minimal_count_payload(fake_session):
    """get_feature_count posts only where / returnCountOnly / f=json by default."""

    fake_session.post_responses.append({"count": 42})

    count = await getinfo_mod.get_feature_count(
        "https://example.com/service/0",
        fake_session,
    )

    assert count == 42
    assert len(fake_session.post_calls) == 1
    url, kwargs = fake_session.post_calls[0]
    assert url == "https://example.com/service/0/query"
    assert kwargs["data"] == {
        "where": "1=1",
        "returnCountOnly": True,
        "f": "json",
    }
    # default_headers are merged in
    assert kwargs["headers"]["Accept"] == "application/json,text/plain,*/*"
    assert kwargs["headers"]["User-Agent"] == "Mozilla/5.0"


@pytest.mark.asyncio
async def test_get_feature_count_propagates_where_and_token_from_data(fake_session):
    """When ``data=`` is supplied, only its where+token (not outFields etc.) leak through."""

    fake_session.post_responses.append({"count": 7})

    await getinfo_mod.get_feature_count(
        "https://example.com/service/0",
        fake_session,
        data={
            "where": "STATUS = 'OPEN'",
            "token": "abc",
            # outFields should NOT be forwarded into the count payload.
            "outFields": "CITY",
        },
    )

    _, kwargs = fake_session.post_calls[0]
    assert kwargs["data"] == {
        "where": "STATUS = 'OPEN'",
        "returnCountOnly": True,
        "f": "json",
        "token": "abc",
    }
    assert "outFields" not in kwargs["data"]


@pytest.mark.asyncio
async def test_get_metadata_uses_get_with_params_and_token(fake_session):
    """get_metadata issues a GET with params={'f':'json', 'token': ...}."""

    fake_session.get_responses.append({"name": "L", "fields": []})

    await getinfo_mod.get_metadata(
        "https://example.com/service/0",
        fake_session,
        token="tok",
    )

    assert len(fake_session.get_calls) == 1
    url, kwargs = fake_session.get_calls[0]
    assert url == "https://example.com/service/0"
    assert kwargs["params"] == {"f": "json", "token": "tok"}


@pytest.mark.asyncio
async def test_get_object_ids_preserves_where_and_returns_tuple(fake_session):
    """get_object_ids posts returnIdsOnly and returns (field_name, ids)."""

    fake_session.post_responses.append(
        {"objectIdFieldName": "OBJECTID", "objectIds": [1, 2, 3]},
    )

    field, ids = await getinfo_mod.get_object_ids(
        "https://example.com/service/0",
        fake_session,
        data={"where": "A=1", "token": "t"},
    )

    assert (field, ids) == ("OBJECTID", [1, 2, 3])
    _, kwargs = fake_session.post_calls[0]
    assert kwargs["data"] == {
        "where": "A=1",
        "returnIdsOnly": True,
        "f": "json",
        "token": "t",
    }


@pytest.mark.asyncio
async def test_getuniquevalues_sends_distinct_payload_string_field(fake_session):
    fake_session.post_responses.append(
        {"features": [{"attributes": {"CITY": "A"}}, {"attributes": {"CITY": "B"}}]},
    )

    result = await getinfo_mod.getuniquevalues(
        "https://example.com/service/0",
        "CITY",
        fake_session,
    )

    assert result == ["A", "B"]
    _, kwargs = fake_session.post_calls[0]
    assert kwargs["data"] == {
        "where": "1=1",
        "f": "json",
        "returnGeometry": False,
        "returnDistinctValues": True,
        "outFields": "CITY",
    }


@pytest.mark.asyncio
async def test_getvaluecounts_builds_statistics_payload(fake_session):
    fake_session.post_responses.append(
        {
            "features": [
                {"attributes": {"CITY": "A", "CITY_count": 5}},
                {"attributes": {"CITY": "B", "CITY_count": 2}},
            ],
        },
    )

    df = await getinfo_mod.getvaluecounts(
        "https://example.com/service/0",
        "CITY",
        fake_session,
    )

    assert isinstance(df, DataFrame)
    # Result is sorted by CITY_count desc.
    assert list(df["CITY"]) == ["A", "B"]
    _, kwargs = fake_session.post_calls[0]
    data = kwargs["data"]
    assert data["groupByFieldsForStatistics"] == "CITY"
    assert data["outFields"] == "CITY"
    assert data["f"] == "json"
    assert data["returnGeometry"] is False
    assert '"onStatisticField":"CITY"' in data["outStatistics"]
    assert '"outStatisticFieldName":"CITY_count"' in data["outStatistics"]


# ---------------------------------------------------------------------------
# getgdf: batching semantics
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_batches_single_when_count_within_max_record():
    with patch(
        "restgdf.utils.getgdf.get_feature_count",
        new=AsyncMock(return_value=5),
    ), patch(
        "restgdf.utils.getgdf.get_metadata",
        new=AsyncMock(return_value={"maxRecordCount": 10}),
    ):
        batches = await getgdf_mod.get_query_data_batches(
            "https://example.com/0",
            session=object(),
        )

    assert batches == [{}]


@pytest.mark.asyncio
async def test_batches_use_pagination_offsets_when_supported():
    with patch(
        "restgdf.utils.getgdf.get_feature_count",
        new=AsyncMock(return_value=25),
    ), patch(
        "restgdf.utils.getgdf.get_metadata",
        new=AsyncMock(
            return_value={
                "maxRecordCount": 10,
                "advancedQueryCapabilities": {"supportsPagination": True},
            },
        ),
    ):
        batches = await getgdf_mod.get_query_data_batches(
            "https://example.com/0",
            session=object(),
        )

    assert batches == [
        {"resultOffset": 0, "resultRecordCount": 10},
        {"resultOffset": 10, "resultRecordCount": 10},
        {"resultOffset": 20, "resultRecordCount": 5},
    ]


@pytest.mark.asyncio
async def test_batches_fall_back_to_object_id_chunks_without_pagination():
    object_ids = list(range(1, 26))  # 25 ids
    with patch(
        "restgdf.utils.getgdf.get_feature_count",
        new=AsyncMock(return_value=25),
    ), patch(
        "restgdf.utils.getgdf.get_metadata",
        new=AsyncMock(
            return_value={
                "maxRecordCount": 10,
                "advancedQueryCapabilities": {"supportsPagination": False},
            },
        ),
    ), patch(
        "restgdf.utils.getgdf.get_object_ids",
        new=AsyncMock(return_value=("OBJECTID", object_ids)),
    ):
        batches = await getgdf_mod.get_query_data_batches(
            "https://example.com/0",
            session=object(),
        )

    # Chunks of size 10 -> 3 batches.
    assert len(batches) == 3
    # All batches carry an OBJECTID In (...) where clause.
    for batch in batches:
        assert "OBJECTID In" in batch["where"]


# ---------------------------------------------------------------------------
# FeatureLayer: caching semantics
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_featurelayer_getuniquevalues_caches_per_key(feature_layer_metadata):
    layer = FeatureLayer("https://example.com/0", session=object())
    layer.metadata = feature_layer_metadata
    layer.fields = ("OBJECTID", "CITY", "STATUS")

    call_count = {"n": 0}

    async def fake_get_unique_values(url, fields, session, sortby=None, **kwargs):
        call_count["n"] += 1
        return ["A", "B"]

    with patch(
        "restgdf.featurelayer.featurelayer.get_unique_values",
        side_effect=fake_get_unique_values,
    ):
        first = await layer.get_unique_values("CITY")
        second = await layer.get_unique_values("CITY")

    assert first == second == ["A", "B"]
    # Second call must be served from the cache (no extra network call).
    assert call_count["n"] == 1
    assert ("CITY", None) in layer.uniquevalues


# ---------------------------------------------------------------------------
# crawl: error-swallowing shape
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_all_data_swallows_base_metadata_errors():
    boom = RuntimeError("boom")

    with patch(
        "restgdf.utils.crawl.get_metadata",
        new=AsyncMock(side_effect=boom),
    ):
        result = await crawl_mod.fetch_all_data(
            session=object(),
            base_url="https://example.com/rest",
        )

    # Current contract: errors bubble up as a {"error": e} sentinel dict.
    assert result == {"error": boom}


# ---------------------------------------------------------------------------
# Token: explicit token in request body is not overridden by session token
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_arcgistokensession_post_preserves_explicit_token_in_data():
    from restgdf.utils.token import ArcGISTokenSession

    captured: dict[str, dict | None] = {"data": None, "headers": None}

    class _InnerSession:
        async def post(self, url, data=None, headers=None, **kwargs):
            captured["data"] = data
            captured["headers"] = headers
            return "OK"

    session = ArcGISTokenSession(session=_InnerSession(), token="session-tok")

    result = await session.post(
        "https://example.com/q",
        data={"token": "explicit-tok", "where": "1=1"},
    )

    assert result == "OK"
    # Explicit token in data wins; session token must not overwrite it.
    assert captured["data"] == {"token": "explicit-tok", "where": "1=1"}
    # And no Authorization header is injected when explicit body token is present.
    assert "Authorization" not in (captured["headers"] or {})
