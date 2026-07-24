"""Characterization tests pinning current restgdf behavior.

These tests are part of the Phase 0 safety net for the TDD refactor. They
intentionally assert on concrete, observable behavior of the *current*
implementation (request body shape, call precedence, batch boundaries,
caching semantics, crawl error-swallowing) so that subsequent refactors are
guarded against silent regressions.

If one of these tests fails during a refactor, treat it as a deliberate
decision point: either update the test (documenting the intended behavior
change) or fix the regression.

W1-9 (TESTS-02) verb separation
--------------------------------
The GET-vs-POST choice for every ArcGIS call in this module is made by
``restgdf.utils._http._arcgis_request``/``_choose_verb``: short, tokenless
bodies ride a length-based ``GET`` (params coerced to ArcGIS wire strings
by ``_coerce_params_for_get`` -- booleans become ``"true"``/``"false"``,
``None`` becomes ``""``); a body carrying a ``token`` key is ALWAYS forced
onto ``POST`` regardless of length (AUTH-01/W2-1), and ``POST`` forwards
the body untouched -- raw ``bool``/``None`` values ride through as-is. This
is a COORDINATOR-PINNED invariant for M3: raw-bool POST bodies are the
correct, permanent behavior (the ``_arcgis_request`` body-untouched
contract) -- do NOT add coercion on the POST path to make it match GET's
stringified booleans.

Each test below is named for, and asserts against, the verb it ACTUALLY
exercises (``get_calls``/``kwargs["params"]`` for the GET helpers,
``post_calls``/``kwargs["data"]`` for the genuinely-POST cases), and
additionally asserts the OTHER call list stayed empty. Before W1-9,
``FakeSession`` aliased ``post_calls``/``get_calls`` onto one shared list
and mirrored the recorded body under both ``data`` and ``params`` keys, so
a test that read the "wrong" key for the request's actual verb still
passed silently (e.g. ``test_get_metadata_uses_get_with_params_and_token``
asserted on ``get_calls``/``params`` for a call the AUTH-01 fix had
already flipped to POST). ``tests/conftest.py``'s ``FakeSession`` no
longer mirrors across verbs, so a real GET<->POST regression now empties
the list a renamed test asserts against instead of silently matching.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from pandas import DataFrame

from restgdf import get_config
from restgdf.featurelayer.featurelayer import FeatureLayer
from restgdf.utils import crawl as crawl_mod
from restgdf.utils import getgdf as getgdf_mod
from restgdf.utils import getinfo as getinfo_mod

pytestmark = pytest.mark.characterization


# ---------------------------------------------------------------------------
# getinfo: request body (datadict) shape
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_feature_count_sends_minimal_count_query_payload(fake_session):
    """get_feature_count GETs only where / returnCountOnly / f=json by default.

    W1-9: renamed from ``*_sends_minimal_count_payload`` -- the call has no
    token and is short, so it rides GET, not POST; this was the "GET-named
    token test now riding POST" family's mirror image (a GET call read
    through the wrong ``post_calls``/``data`` key).
    """

    fake_session.get_responses.append({"count": 42})

    count = await getinfo_mod.get_feature_count(
        "https://example.com/service/0",
        fake_session,
    )

    assert count == 42
    assert len(fake_session.get_calls) == 1
    assert fake_session.post_calls == []
    url, kwargs = fake_session.get_calls[0]
    assert url == "https://example.com/service/0/query"
    # T8 (R-74): short count queries ride on GET, and bool/None values
    # are coerced to ArcGIS wire strings ("true"/"false") so yarl/aiohttp
    # will accept them as query-string parameters.
    assert kwargs["params"] == {
        "where": "1=1",
        "returnCountOnly": "true",
        "f": "json",
    }
    # default_headers are merged in
    assert kwargs["headers"]["Accept"] == "application/json,text/plain,*/*"
    # W2-10: default UA now sourced from get_config().transport.user_agent
    # (was the hardcoded "Mozilla/5.0"); this characterizes the new default.
    assert kwargs["headers"]["User-Agent"] == get_config().transport.user_agent


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

    assert fake_session.get_calls == []
    _, kwargs = fake_session.post_calls[0]
    # AUTH-01 (W2-1): token-bearing bodies are now forced onto POST, which
    # forwards the body untouched -- the raw bool rides through instead of
    # the GET path's coerced "true" string. Pinned post-fix behavior.
    assert kwargs["data"] == {
        "where": "STATUS = 'OPEN'",
        "returnCountOnly": True,
        "f": "json",
        "token": "abc",
    }
    assert "outFields" not in kwargs["data"]


@pytest.mark.asyncio
async def test_get_metadata_with_token_forces_post_body_untouched(fake_session):
    """get_metadata with a token issues a POST with the body untouched.

    W1-9: renamed from ``test_get_metadata_uses_get_with_params_and_token``
    -- AUTH-01 (W2-1) forces POST whenever the outgoing body carries a
    ``token`` key, and ``get_metadata(..., token=...)`` always puts the
    token in the body, so this call has ridden POST since AUTH-01 landed.
    The old name/assertions (``get_calls``/``kwargs["params"]``) were the
    exact case this item exists to fix: the FakeSession mirror let a POST
    call satisfy a "GET" assertion because ``get_calls`` was the same list
    as ``post_calls`` and the body was copied onto ``params`` too.
    """

    fake_session.post_responses.append({"name": "L", "fields": []})

    await getinfo_mod.get_metadata(
        "https://example.com/service/0",
        fake_session,
        token="tok",
    )

    assert len(fake_session.post_calls) == 1
    assert fake_session.get_calls == []
    url, kwargs = fake_session.post_calls[0]
    assert url == "https://example.com/service/0"
    assert kwargs["data"] == {"f": "json", "token": "tok"}


@pytest.mark.asyncio
async def test_get_metadata_without_token_uses_get_with_params(fake_session):
    """get_metadata with NO token still rides GET -- verb separation intact.

    W1-9: companion to the token-forces-POST case above, proving the two
    verbs are genuinely distinguishable through this fixture (not just
    incidentally identical because of a mirror).
    """

    fake_session.get_responses.append({"name": "L", "fields": []})

    await getinfo_mod.get_metadata(
        "https://example.com/service/0",
        fake_session,
    )

    assert len(fake_session.get_calls) == 1
    assert fake_session.post_calls == []
    url, kwargs = fake_session.get_calls[0]
    assert url == "https://example.com/service/0"
    assert kwargs["params"] == {"f": "json"}


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
    assert fake_session.get_calls == []
    _, kwargs = fake_session.post_calls[0]
    # AUTH-01 (W2-1): token-bearing bodies are now forced onto POST, which
    # forwards the body untouched (raw bool, not the GET-coerced "true").
    assert kwargs["data"] == {
        "where": "A=1",
        "returnIdsOnly": True,
        "f": "json",
        "token": "t",
    }


@pytest.mark.asyncio
async def test_getuniquevalues_sends_distinct_query_payload_string_field(fake_session):
    """W1-9: renamed from ``*_sends_distinct_payload_string_field`` -- no
    token, short body -> GET, not POST (the coerced "true"/"false" string
    values below are themselves only correct for the GET path)."""

    fake_session.get_responses.append(
        {"features": [{"attributes": {"CITY": "A"}}, {"attributes": {"CITY": "B"}}]},
    )

    result = await getinfo_mod.getuniquevalues(
        "https://example.com/service/0",
        "CITY",
        fake_session,
    )

    assert result == ["A", "B"]
    assert fake_session.post_calls == []
    _, kwargs = fake_session.get_calls[0]
    assert kwargs["params"] == {
        "where": "1=1",
        "f": "json",
        "returnGeometry": "false",
        "returnDistinctValues": "true",
        "outFields": "CITY",
    }


@pytest.mark.asyncio
async def test_getvaluecounts_builds_statistics_query_payload(fake_session):
    """W1-9: renamed from ``*_builds_statistics_payload`` -- no token, short
    body -> GET, not POST."""

    fake_session.get_responses.append(
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
    assert fake_session.post_calls == []
    _, kwargs = fake_session.get_calls[0]
    data = kwargs["params"]
    assert data["groupByFieldsForStatistics"] == "CITY"
    assert data["outFields"] == "CITY"
    assert data["f"] == "json"
    # T8 (R-74): bool coerced to the ArcGIS wire string for GET params.
    assert data["returnGeometry"] == "false"
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
