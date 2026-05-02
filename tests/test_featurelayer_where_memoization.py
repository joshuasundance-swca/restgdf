"""BL-46: ``FeatureLayer.where`` must memoize metadata across refinements.

Contract: calling ``.where(new_where)`` on a parent whose ``prep()`` has
already resolved metadata must return a refined child layer that reuses
the parent's cached metadata / fields / object_id_field state WITHOUT
issuing a second metadata GET (``?f=json``). A single feature-count POST
(``returnCountOnly=true``) scoped to the refined ``where_clause`` is
expected so ``refined.count`` is correct for the refined filter. The
new ``where_clause`` MUST still be threaded into the refined layer so
subsequent query calls use it.
"""

from __future__ import annotations

import re

import pytest
from aiohttp import ClientSession
from aioresponses import aioresponses

from restgdf.featurelayer.featurelayer import FeatureLayer


LAYER_URL = "https://svc.example/arcgis/rest/services/Demo/FeatureServer/0"
METADATA_URL_RE = re.compile(
    r"^https://svc\.example/arcgis/rest/services/Demo/FeatureServer/0(\?.*)?$",
)
# T8 (R-74): short count queries ride on GET and carry a query string.
QUERY_URL_RE = re.compile(
    r"^https://svc\.example/arcgis/rest/services/Demo/FeatureServer/0/query(\?.*)?$",
)


def _metadata_payload() -> dict:
    return {
        "name": "Demo Layer",
        "type": "Feature Layer",
        "fields": [
            {"name": "OBJECTID", "type": "esriFieldTypeOID"},
            {"name": "CITY", "type": "esriFieldTypeString"},
            {"name": "STATUS", "type": "esriFieldTypeString"},
        ],
        "maxRecordCount": 2000,
        "advancedQueryCapabilities": {"supportsPagination": True},
    }


def _count_metadata_and_count_calls(mocker: aioresponses) -> tuple[int, int]:
    """Return (metadata_call_count, count_call_count) observed so far."""
    metadata_calls = 0
    count_calls = 0
    for (method, url), calls in mocker.requests.items():
        url_str = str(url).split("?", 1)[0]
        if method == "GET" and url_str.rstrip("/").endswith("FeatureServer/0"):
            metadata_calls += len(calls)
        elif url_str.endswith("FeatureServer/0/query") and method in ("POST", "GET"):
            for call in calls:
                # T8 (R-74): count requests can ride on either verb. ``data``
                # carries the payload on POST; ``params`` carries it on GET.
                payload = call.kwargs.get("data") or call.kwargs.get("params") or {}
                if str(payload.get("returnCountOnly", "")).lower() == "true":
                    count_calls += 1
    return metadata_calls, count_calls


@pytest.mark.asyncio
async def test_where_reuses_parent_metadata_and_refreshes_count():
    """Refined layer from ``.where`` must skip the metadata GET but refresh count.

    This is BL-46's core contract: ``.where`` avoids the expensive
    metadata re-fetch while keeping ``refined.count`` correct for the
    refined filter. We assert zero extra metadata GETs and exactly one
    extra feature-count POST scoped to the refined ``where`` clause.
    """
    with aioresponses() as m:
        m.get(METADATA_URL_RE, payload=_metadata_payload(), repeat=True)
        m.post(
            f"{LAYER_URL}/query",
            payload={"count": 42},
            repeat=True,
        )
        # T8 (R-74): short count queries now route to GET.
        m.get(
            QUERY_URL_RE,
            payload={"count": 42},
            repeat=True,
        )

        async with ClientSession() as session:
            parent = await FeatureLayer.from_url(LAYER_URL, session=session)

            md_after_parent, cnt_after_parent = _count_metadata_and_count_calls(m)
            assert md_after_parent == 1
            assert cnt_after_parent == 1

            refined = await parent.where("STATUS = 'Open'")

            md_after_refined, cnt_after_refined = _count_metadata_and_count_calls(m)

    assert md_after_refined == md_after_parent, (
        "BL-46: .where must NOT trigger a second metadata GET; "
        f"saw {md_after_refined - md_after_parent} extra metadata call(s)."
    )
    assert cnt_after_refined == cnt_after_parent + 1, (
        "BL-46: .where must issue exactly one count POST scoped to the "
        f"refined where clause; saw {cnt_after_refined - cnt_after_parent} "
        "extra count call(s)."
    )

    refined_count_posts = [
        call
        for (method, url), calls in m.requests.items()
        if method in ("POST", "GET") and str(url).split("?", 1)[0].endswith("/query")
        for call in calls
        if str(
            (call.kwargs.get("data") or call.kwargs.get("params") or {}).get(
                "returnCountOnly",
                "",
            ),
        ).lower()
        == "true"
        and (call.kwargs.get("data") or call.kwargs.get("params") or {}).get("where")
        == "STATUS = 'Open'"
    ]
    assert (
        refined_count_posts
    ), "BL-46: refined count request must carry the refined `where` clause"

    assert refined.url == parent.url
    assert refined.session is parent.session
    assert refined.wherestr == "STATUS = 'Open'"
    assert refined.kwargs["data"]["where"] == "STATUS = 'Open'"
    assert refined.metadata is parent.metadata
    assert refined.fields == parent.fields
    assert refined.name == parent.name
    assert refined.object_id_field == parent.object_id_field


@pytest.mark.asyncio
async def test_where_combines_with_existing_where_and_refreshes_count():
    """Existing composition semantics (AND-joining) must be preserved."""
    with aioresponses() as m:
        m.get(METADATA_URL_RE, payload=_metadata_payload(), repeat=True)
        m.post(
            f"{LAYER_URL}/query",
            payload={"count": 7},
            repeat=True,
        )
        # T8 (R-74): short count queries now route to GET.
        m.get(
            QUERY_URL_RE,
            payload={"count": 7},
            repeat=True,
        )

        async with ClientSession() as session:
            parent = await FeatureLayer.from_url(
                LAYER_URL,
                session=session,
                where="CITY = 'DAYTONA'",
            )

            md_after_parent, cnt_after_parent = _count_metadata_and_count_calls(m)

            refined = await parent.where("STATUS = 'Open'")

            md_after_refined, cnt_after_refined = _count_metadata_and_count_calls(m)

    assert md_after_refined == md_after_parent
    assert cnt_after_refined == cnt_after_parent + 1
    assert refined.wherestr == "CITY = 'DAYTONA' AND STATUS = 'Open'"
    assert refined.kwargs["data"]["where"] == "CITY = 'DAYTONA' AND STATUS = 'Open'"
