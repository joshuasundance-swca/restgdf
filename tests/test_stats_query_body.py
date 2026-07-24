"""W5-2 (API-01) / W5-3 (API-04): stats query-body correctness.

W5-2: ``FeatureLayer.get_value_counts`` / ``get_nested_count`` must send a
conservative statistics body -- ``returnGeometry=False``, ``outFields=<field>``,
no ``returnCountOnly`` -- while PRESERVING the instance ``where`` clause. The
pre-fix code spread the caller ``data`` (the instance ``datadict``, which
carries ``returnGeometry=True`` / ``outFields="*"`` / ``returnCountOnly=False``)
LAST, clobbering the stats flags.

W5-3: ``nested_count`` requires EXACTLY two field names; a one-element tuple
must raise a clear ``ValueError`` at both the FeatureLayer method and the bare
helper, not an ``IndexError`` deep inside post-processing.
"""

from __future__ import annotations

from typing import Any

import pytest

from restgdf.featurelayer.featurelayer import FeatureLayer
from restgdf.utils.getinfo import nested_count


class _FakeResp:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload
        self.content_type = "application/json"
        self.status = 200

    async def json(self, content_type: str | None = None) -> dict[str, Any]:
        return self._payload


class _CapturingSession:
    """A duck-typed async HTTP session that records the outgoing body.

    A ``token`` in the body forces ``_arcgis_request`` down the POST path
    (AUTH-01), so the captured ``data`` kwarg is the raw, un-coerced body
    dict -- exactly what we want to assert against.
    """

    def __init__(self, features: list[dict[str, Any]]) -> None:
        self.captured: list[tuple[str, str, dict[str, Any]]] = []
        self._features = features

    async def post(self, url: str, **kwargs: Any) -> _FakeResp:
        self.captured.append(("post", url, kwargs))
        return _FakeResp({"features": self._features})

    async def get(self, url: str, **kwargs: Any) -> _FakeResp:
        self.captured.append(("get", url, kwargs))
        return _FakeResp({"features": self._features})

    def body_of(self, index: int = -1) -> dict[str, Any]:
        _, _, kwargs = self.captured[index]
        # POST path -> data=; GET path -> params=.
        return dict(kwargs.get("data") or kwargs.get("params") or {})


def _layer(session: _CapturingSession, *, where: str = "1=1") -> FeatureLayer:
    """Build an un-prepped FeatureLayer with a token (forces the POST path)."""
    fl = FeatureLayer(
        "https://example.test/MapServer/0",
        session=session,  # type: ignore[arg-type]
        where=where,
        token="tok-123",
    )
    fl.fields = ("City", "Status")
    return fl


# --- W5-2: conservative stats body -----------------------------------------


@pytest.mark.asyncio
async def test_get_value_counts_sends_conservative_body() -> None:
    session = _CapturingSession(
        [{"attributes": {"City": "A", "City_count": 3}}],
    )
    fl = _layer(session, where="CITY = 'DAYTONA'")
    await fl.get_value_counts("City")

    body = session.body_of()
    assert body["returnGeometry"] is False
    assert body["outFields"] == "City"
    assert "returnCountOnly" not in body
    assert body["outStatistics"]
    assert body["groupByFieldsForStatistics"] == "City"
    # W5-2 anti-rec: the instance WHERE must survive the conservative merge.
    assert body["where"] == "CITY = 'DAYTONA'"
    # token forwarded through build_conservative_query_data.
    assert body["token"] == "tok-123"


@pytest.mark.asyncio
async def test_get_nested_count_sends_conservative_body() -> None:
    session = _CapturingSession(
        [
            {
                "attributes": {
                    "City": "A",
                    "Status": "X",
                    "City_count": 2,
                    "Status_count": 2,
                },
            },
        ],
    )
    fl = _layer(session, where="STATUS = 'OPEN'")
    await fl.get_nested_count(("City", "Status"))

    body = session.body_of()
    assert body["returnGeometry"] is False
    assert body["outFields"] == "City,Status"
    assert "returnCountOnly" not in body
    assert body["groupByFieldsForStatistics"] == "City,Status"
    assert body["where"] == "STATUS = 'OPEN'"
    assert body["token"] == "tok-123"


# --- W5-3: nested_count arity ----------------------------------------------


@pytest.mark.asyncio
async def test_featurelayer_nested_count_rejects_single_field() -> None:
    session = _CapturingSession([])
    fl = _layer(session)
    with pytest.raises(ValueError, match="exactly two"):
        await fl.get_nested_count(("City",))
    # No request should have been issued.
    assert session.captured == []


@pytest.mark.asyncio
async def test_bare_nested_count_helper_rejects_single_field() -> None:
    session = _CapturingSession([])
    with pytest.raises(ValueError, match="exactly two"):
        await nested_count(
            "https://example.test/MapServer/0",
            ("City",),
            session,  # type: ignore[arg-type]
        )
    assert session.captured == []


@pytest.mark.asyncio
async def test_featurelayer_nested_count_rejects_three_fields() -> None:
    session = _CapturingSession([])
    fl = _layer(session)
    fl.fields = ("City", "Status", "Kind")
    with pytest.raises(ValueError, match="exactly two"):
        await fl.get_nested_count(("City", "Status", "Kind"))
    assert session.captured == []
