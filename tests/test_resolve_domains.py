"""T6 (R-75): ``FeatureLayer.get_df(resolve_domains=True)``.

Verifies the new post-processing hook that swaps ArcGIS coded-value
domain codes for their human-readable names and validates range-domain
values against the declared ``[min, max]`` bounds.

Guardrails:

* The default ``resolve_domains=False`` path must remain byte-for-byte
  identical to prior behavior (no accidental regression).
* No additional HTTP traffic — resolution reads from
  :attr:`FeatureLayer.metadata.fields`, which is already fetched during
  :meth:`FeatureLayer.prep`.
* Unknown codes and out-of-range values are preserved unchanged so the
  DataFrame remains a faithful projection of what the server sent.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from restgdf.featurelayer.featurelayer import FeatureLayer


pd = pytest.importorskip("pandas")


SAMPLE_METADATA_WITH_DOMAINS = {
    "name": "Test Layer",
    "type": "Feature Layer",
    "fields": [
        {"name": "OBJECTID", "type": "esriFieldTypeOID"},
        {
            "name": "STATUS",
            "type": "esriFieldTypeSmallInteger",
            "domain": {
                "type": "codedValue",
                "name": "StatusDomain",
                "codedValues": [
                    {"name": "Active", "code": 1},
                    {"name": "Inactive", "code": 2},
                    {"name": "Pending", "code": 3},
                ],
            },
        },
        {
            "name": "SCORE",
            "type": "esriFieldTypeInteger",
            "domain": {
                "type": "range",
                "name": "ScoreRange",
                "range": [0, 100],
            },
        },
        {"name": "NAME", "type": "esriFieldTypeString"},
    ],
    "maxRecordCount": 10,
    "advancedQueryCapabilities": {"supportsPagination": False},
}

SAMPLE_METADATA_NO_DOMAINS = {
    "name": "Test Layer",
    "type": "Feature Layer",
    "fields": [
        {"name": "OBJECTID", "type": "esriFieldTypeOID"},
        {"name": "NAME", "type": "esriFieldTypeString"},
    ],
    "maxRecordCount": 10,
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


async def _build_layer(
    metadata: dict,
    features_pages: list[list[dict]],
) -> tuple[FeatureLayer, QuerySession]:
    responses: list[dict] = []
    for page in features_pages:
        responses.append({"features": page})
    session = QuerySession(responses)
    layer = FeatureLayer(
        "https://example.com/arcgis/rest/services/Test/FeatureServer/0",
        session=session,
    )
    from restgdf._models.responses import LayerMetadata
    from restgdf.utils.getinfo import get_fields, get_name

    layer.metadata = LayerMetadata.model_validate(metadata)
    layer.name = get_name(layer.metadata)
    layer.fields = get_fields(layer.metadata)
    layer.count = sum(len(p) for p in features_pages)
    return layer, session


@pytest.mark.asyncio
async def test_get_df_default_preserves_codes() -> None:
    """Default ``resolve_domains=False`` leaves domain fields untouched."""
    page = [
        {"attributes": {"OBJECTID": 1, "STATUS": 1, "SCORE": 50, "NAME": "A"}},
        {"attributes": {"OBJECTID": 2, "STATUS": 2, "SCORE": 75, "NAME": "B"}},
    ]
    # Two calls → two pages worth of stubbed responses.
    layer, _session = await _build_layer(SAMPLE_METADATA_WITH_DOMAINS, [page, page])

    with patch(
        "restgdf.utils.getgdf.get_query_data_batches",
        new=AsyncMock(return_value=[{"where": "1=1"}]),
    ):
        df_default = await layer.get_df()
        df_explicit = await layer.get_df(resolve_domains=False)

    assert df_default["STATUS"].tolist() == [1, 2]
    assert df_default["SCORE"].tolist() == [50, 75]
    # Byte-for-byte identical when kwarg is omitted vs. explicitly False.
    pd.testing.assert_frame_equal(df_default, df_explicit)


@pytest.mark.asyncio
async def test_get_df_resolves_coded_value_domain() -> None:
    """``resolve_domains=True`` swaps coded values to their names."""
    layer, _session = await _build_layer(
        SAMPLE_METADATA_WITH_DOMAINS,
        [
            [
                {"attributes": {"OBJECTID": 1, "STATUS": 1, "SCORE": 50, "NAME": "A"}},
                {"attributes": {"OBJECTID": 2, "STATUS": 2, "SCORE": 75, "NAME": "B"}},
                {"attributes": {"OBJECTID": 3, "STATUS": 3, "SCORE": 10, "NAME": "C"}},
            ],
        ],
    )

    with patch(
        "restgdf.utils.getgdf.get_query_data_batches",
        new=AsyncMock(return_value=[{"where": "1=1"}]),
    ):
        df = await layer.get_df(resolve_domains=True)

    assert df["STATUS"].tolist() == ["Active", "Inactive", "Pending"]
    # Range-domain values within bounds pass through untouched.
    assert df["SCORE"].tolist() == [50, 75, 10]
    # Non-domain fields unchanged.
    assert df["NAME"].tolist() == ["A", "B", "C"]


@pytest.mark.asyncio
async def test_get_df_resolve_domains_unknown_code_passes_through() -> None:
    """Codes absent from the codedValues table stay as the raw code."""
    layer, _session = await _build_layer(
        SAMPLE_METADATA_WITH_DOMAINS,
        [
            [
                {"attributes": {"OBJECTID": 1, "STATUS": 99, "SCORE": 50, "NAME": "A"}},
                {"attributes": {"OBJECTID": 2, "STATUS": 1, "SCORE": 200, "NAME": "B"}},
            ],
        ],
    )

    with patch(
        "restgdf.utils.getgdf.get_query_data_batches",
        new=AsyncMock(return_value=[{"where": "1=1"}]),
    ):
        df = await layer.get_df(resolve_domains=True)

    # 99 is not in the coded-values map → unchanged.
    # 1 resolves → "Active".
    assert df["STATUS"].tolist() == [99, "Active"]
    # Out-of-range value is left as-is (no warning, no coercion).
    assert df["SCORE"].tolist() == [50, 200]


@pytest.mark.asyncio
async def test_get_df_resolve_domains_noop_when_no_domains() -> None:
    """Layer without any domain fields: ``resolve_domains=True`` is a no-op."""
    page = [
        {"attributes": {"OBJECTID": 1, "NAME": "A"}},
        {"attributes": {"OBJECTID": 2, "NAME": "B"}},
    ]
    layer, _session = await _build_layer(SAMPLE_METADATA_NO_DOMAINS, [page, page])

    with patch(
        "restgdf.utils.getgdf.get_query_data_batches",
        new=AsyncMock(return_value=[{"where": "1=1"}]),
    ):
        df_resolved = await layer.get_df(resolve_domains=True)
        df_raw = await layer.get_df(resolve_domains=False)

    pd.testing.assert_frame_equal(df_resolved, df_raw)


@pytest.mark.asyncio
async def test_get_df_resolve_domains_no_extra_http_calls() -> None:
    """Resolution is pure post-processing; no extra POSTs are issued."""
    layer, session = await _build_layer(
        SAMPLE_METADATA_WITH_DOMAINS,
        [
            [
                {"attributes": {"OBJECTID": 1, "STATUS": 1, "SCORE": 50, "NAME": "A"}},
            ],
        ],
    )

    with patch(
        "restgdf.utils.getgdf.get_query_data_batches",
        new=AsyncMock(return_value=[{"where": "1=1"}]),
    ):
        pre_call_count = len(session.post_calls)
        await layer.get_df(resolve_domains=True)
        post_call_count = len(session.post_calls)

    # Resolution must not issue any additional HTTP requests over and above
    # the baseline streaming query.
    assert post_call_count == pre_call_count + 1


def test_resolve_domains_helper_is_exposed() -> None:
    """The adapter helper is publicly importable for reuse."""
    from restgdf.adapters.pandas import resolve_domains  # noqa: F401


def test_resolve_domains_helper_handles_empty_fields() -> None:
    """Empty / ``None`` fields metadata produces an identical DataFrame."""
    from restgdf.adapters.pandas import resolve_domains

    df = pd.DataFrame({"STATUS": [1, 2, 3]})
    out = resolve_domains(df, None)
    pd.testing.assert_frame_equal(out, df)

    out2 = resolve_domains(df, [])
    pd.testing.assert_frame_equal(out2, df)


def test_resolve_domains_helper_with_dict_fields() -> None:
    """Helper accepts raw dict field specs (not just ``FieldSpec``)."""
    from restgdf.adapters.pandas import resolve_domains

    df = pd.DataFrame({"STATUS": [1, 2, 99], "NAME": ["a", "b", "c"]})
    fields = [
        {"name": "NAME", "type": "esriFieldTypeString"},
        {
            "name": "STATUS",
            "type": "esriFieldTypeSmallInteger",
            "domain": {
                "type": "codedValue",
                "codedValues": [
                    {"name": "Active", "code": 1},
                    {"name": "Inactive", "code": 2},
                ],
            },
        },
    ]
    out = resolve_domains(df, fields)
    assert out["STATUS"].tolist() == ["Active", "Inactive", 99]
    assert out["NAME"].tolist() == ["a", "b", "c"]
    # Helper must not mutate the input frame.
    assert df["STATUS"].tolist() == [1, 2, 99]
