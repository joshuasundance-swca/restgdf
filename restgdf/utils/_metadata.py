"""Pure metadata parsers for ArcGIS REST responses.

Private submodule; all public names are re-exported by
``restgdf.utils.getinfo`` to preserve import paths.
"""

from __future__ import annotations

from collections.abc import Mapping
from re import IGNORECASE, compile
from typing import TYPE_CHECKING, Any, Union

from pydantic import BaseModel

from restgdf._models.responses import FieldSpec, LayerMetadata
from restgdf.utils._deprecations import deprecated_alias
from restgdf.utils._optional import require_pandas_dataframe

if TYPE_CHECKING:
    from pandas import DataFrame

FIELDDOESNOTEXIST: IndexError = IndexError("Field does not exist")

LayerMetadataLike = Union[LayerMetadata, Mapping[str, Any]]


def _as_dict(metadata: LayerMetadataLike) -> dict:
    """Normalize a ``LayerMetadata`` model or raw mapping to a plain dict.

    Extras from permissive-tier parsing are preserved so that case-insensitive
    regex lookups on keys like ``Name`` or ``MaxRecordCount`` keep working
    even when the input has already been validated into a pydantic model.
    """
    if isinstance(metadata, BaseModel):
        return metadata.model_dump(by_alias=True, exclude_none=True)
    return dict(metadata)


def supports_pagination(metadata: LayerMetadataLike) -> bool:
    """Return whether the layer supports resultOffset/resultRecordCount pagination."""
    metadata = _as_dict(metadata)
    advanced_query_capabilities = metadata.get("advancedQueryCapabilities") or {}
    if "supportsPagination" in advanced_query_capabilities:
        return advanced_query_capabilities["supportsPagination"]
    if "supportsPagination" in metadata:
        return metadata["supportsPagination"]
    return True


def get_object_id_field(metadata: LayerMetadataLike) -> str:
    """Get the object id field name for a layer."""
    metadata = _as_dict(metadata)
    oid_fields = [
        field["name"]
        for field in metadata.get("fields", [])
        if field.get("type") == "esriFieldTypeOID"
    ]
    if len(oid_fields) != 1:
        raise FIELDDOESNOTEXIST
    return oid_fields[0]


def get_max_record_count(metadata: LayerMetadataLike) -> int:
    """Get the maximum record count for a layer."""
    metadata = _as_dict(metadata)
    key_pattern = compile(
        r"max(imum)?(\s|_)?record(\s|_)?count$",
        flags=IGNORECASE,
    )
    key_list = [key for key in metadata.keys() if key_pattern.match(key)]
    if len(key_list) != 1:
        raise FIELDDOESNOTEXIST
    return metadata[key_list[0]]


def get_name(metadata: LayerMetadataLike) -> str:
    """Get the name of a layer."""
    metadata = _as_dict(metadata)
    key_pattern = compile("name", flags=IGNORECASE)
    key_list = [key for key in metadata.keys() if key_pattern.match(key)]
    if len(key_list) != 1:
        raise FIELDDOESNOTEXIST
    return metadata[key_list[0]]


def get_fields(layer_metadata: LayerMetadataLike, types: bool = False):
    """Get the fields of a layer."""
    layer_metadata = _as_dict(layer_metadata)
    fields = layer_metadata.get("fields") or []
    if types:
        return {f["name"]: f["type"].replace("esriFieldType", "") for f in fields}
    return [f["name"] for f in fields]


def _field_rows(layer_metadata: LayerMetadataLike) -> list[tuple[str, str]]:
    """Return ``(name, type)`` rows for the layer fields."""
    layer_metadata = _as_dict(layer_metadata)
    fields: list[FieldSpec] = layer_metadata.get("fields") or []
    return [(f["name"], f["type"].replace("esriFieldType", "")) for f in fields]


def get_fields_frame(layer_metadata: LayerMetadataLike) -> DataFrame:
    """Get the fields of a layer as a DataFrame."""
    DataFrame = require_pandas_dataframe("get_fields_frame()")
    return DataFrame(
        _field_rows(layer_metadata),
        columns=["name", "type"],
    )


# Deprecated legacy aliases (Phase 6). Emit DeprecationWarning when called;
# delegate to the canonical snake_case functions.
getfields = deprecated_alias(get_fields, "getfields", "get_fields")
getfields_df = deprecated_alias(get_fields_frame, "getfields_df", "get_fields_frame")
