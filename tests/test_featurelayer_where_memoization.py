"""BL-46: ``FeatureLayer.where`` must memoize metadata/feature-count.

Contract: calling ``.where(new_where)`` on a parent whose ``prep()`` has
already resolved metadata + count must return a refined child layer that
reuses the parent's cached metadata / feature-count state WITHOUT issuing
a second metadata GET (``?f=json``) or feature-count POST
(``returnCountOnly=true``). The new ``where_clause`` MUST still be
threaded into the refined layer so subsequent query calls use it.
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
        elif method == "POST" and url_str.endswith("FeatureServer/0/query"):
            for call in calls:
                data = call.kwargs.get("data") or {}
                if str(data.get("returnCountOnly", "")).lower() == "true":
                    count_calls += 1
    return metadata_calls, count_calls


@pytest.mark.asyncio
async def test_where_reuses_parent_metadata_and_count_no_second_prep():
    """Refined layer from ``.where`` must skip the second metadata/count round-trip.

    This is BL-46's core contract: ``.where`` is a cheap builder, not a
    HTTP round-trip.
    """
    with aioresponses() as m:
        m.get(METADATA_URL_RE, payload=_metadata_payload(), repeat=True)
        m.post(
            f"{LAYER_URL}/query",
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
    assert cnt_after_refined == cnt_after_parent, (
        "BL-46: .where must NOT trigger a second feature-count POST; "
        f"saw {cnt_after_refined - cnt_after_parent} extra count call(s)."
    )

    assert refined.url == parent.url
    assert refined.session is parent.session
    assert refined.wherestr == "STATUS = 'Open'"
    assert refined.kwargs["data"]["where"] == "STATUS = 'Open'"
    assert refined.metadata is parent.metadata
    assert refined.fields == parent.fields
    assert refined.name == parent.name
    assert refined.object_id_field == parent.object_id_field
    assert refined.count == parent.count


@pytest.mark.asyncio
async def test_where_combines_with_existing_where_and_still_skips_prep():
    """Existing composition semantics (AND-joining) must be preserved."""
    with aioresponses() as m:
        m.get(METADATA_URL_RE, payload=_metadata_payload(), repeat=True)
        m.post(
            f"{LAYER_URL}/query",
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
    assert cnt_after_refined == cnt_after_parent
    assert refined.wherestr == "CITY = 'DAYTONA' AND STATUS = 'Open'"
    assert refined.kwargs["data"]["where"] == "CITY = 'DAYTONA' AND STATUS = 'Open'"
