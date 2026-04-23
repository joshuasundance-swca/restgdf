"""S-6: verify FeatureLayer exposes typed LayerMetadata / FieldSpec models."""

from __future__ import annotations

import json

import pytest

from restgdf._models.responses import FieldSpec, LayerMetadata
from restgdf.featurelayer.featurelayer import FeatureLayer


class _Resp:
    def __init__(self, payload):
        self.payload = payload

    def __await__(self):
        async def _r():
            return self

        return _r().__await__()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return None

    async def json(self, content_type=None):
        return self.payload

    async def text(self):
        return json.dumps(self.payload)

    def raise_for_status(self):
        return None


class _Session:
    def __init__(self, metadata, count):
        self.metadata = metadata
        self.count = count

    def get(self, url, **kwargs):
        params = kwargs.get("params") or {}
        # T8 (R-74): metadata endpoint and short /query bodies arrive as GET.
        if url.endswith("/query") and params.get("returnCountOnly"):
            return _Resp({"count": self.count})
        return _Resp(self.metadata)

    def post(self, url, **kwargs):
        data = kwargs.get("data") or {}
        if url.endswith("/query") and data.get("returnCountOnly"):
            return _Resp({"count": self.count})
        return _Resp(self.metadata)


@pytest.mark.asyncio
async def test_featurelayer_prep_exposes_layer_metadata_model(feature_layer_metadata):
    session = _Session(metadata=feature_layer_metadata, count=3)
    layer = FeatureLayer(
        "https://example.com/arcgis/rest/services/Secured/FeatureServer/0",
        session=session,
    )

    await layer.prep()

    assert isinstance(layer.metadata, LayerMetadata)
    assert layer.metadata.type == "Feature Layer"
    assert layer.metadata.max_record_count == feature_layer_metadata["maxRecordCount"]
    assert layer.metadata.fields is not None
    assert len(layer.metadata.fields) == len(feature_layer_metadata["fields"])
    assert all(isinstance(f, FieldSpec) for f in layer.metadata.fields)
    assert layer.metadata.fields[0].name == "OBJECTID"
