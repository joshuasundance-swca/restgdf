"""Pure metadata parsers for ArcGIS REST responses.

Private submodule; all public names are re-exported by
``restgdf.utils.getinfo`` to preserve import paths.
"""

from __future__ import annotations

from collections.abc import Mapping
from re import IGNORECASE, compile
from typing import TYPE_CHECKING, Any, Union

from pydantic import BaseModel

from restgdf._models.responses import LayerMetadata
from restgdf.errors import FieldDoesNotExistError
from restgdf.utils._deprecations import deprecated_alias
from restgdf.utils._optional import require_pandas_dataframe

if TYPE_CHECKING:
    from pandas import DataFrame

LayerMetadataLike = Union[LayerMetadata, Mapping[str, Any]]


def normalize_spatial_reference(
    sr: int | str | dict[str, Any] | None,
) -> tuple[int | None, dict[str, Any] | None]:
    """Extract EPSG int from a spatial reference value (BL-23).

    Returns ``(epsg_int, raw_dict)``:
    - dict → ``latestWkid`` preferred, then ``wkid``; raw dict preserved
    - int → passed through; raw is ``None``
    - str → coerced to int if possible; raw is ``None``
    - None → ``(None, None)``
    """
    if sr is None:
        return None, None
    if isinstance(sr, int):
        return sr, None
    if isinstance(sr, str):
        try:
            return int(sr), None
        except (ValueError, TypeError):
            return None, None
    if isinstance(sr, Mapping):
        raw = dict(sr)
        epsg = sr.get("latestWkid") or sr.get("wkid")
        if isinstance(epsg, int):
            return epsg, raw
        return None, raw
    return None, None


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


def supports_pagination_explicitly(metadata: LayerMetadataLike) -> bool:
    """Return whether pagination support is explicitly advertised."""
    metadata = _as_dict(metadata)
    advanced_query_capabilities = metadata.get("advancedQueryCapabilities") or {}
    if "supportsPagination" in advanced_query_capabilities:
        return advanced_query_capabilities["supportsPagination"] is True
    return metadata.get("supportsPagination") is True


def get_object_id_field(metadata: LayerMetadataLike) -> str:
    """Get the object id field name for a layer."""
    metadata = _as_dict(metadata)
    fields = metadata.get("fields") or []
    field_names = [
        field["name"] for field in fields if isinstance(field.get("name"), str)
    ]
    field_name_lookup = {name.lower(): name for name in field_names}

    oid_fields = [
        field["name"] for field in fields if field.get("type") == "esriFieldTypeOID"
    ]
    if len(oid_fields) == 1:
        return oid_fields[0]
    if len(oid_fields) > 1:
        raise FieldDoesNotExistError(
            context="get_object_id_field",
            message=f"Ambiguous OID fields: {oid_fields!r}",
        )

    for key, value in metadata.items():
        if key.lower() not in {"objectidfield", "objectidfieldname"}:
            continue
        if isinstance(value, str):
            return field_name_lookup.get(value.lower(), value)

    unique_id_info = metadata.get("uniqueIdInfo") or {}
    unique_id_name = unique_id_info.get("name")
    if isinstance(unique_id_name, str):
        return field_name_lookup.get(unique_id_name.lower(), unique_id_name)

    raise FieldDoesNotExistError(context="get_object_id_field")


def get_max_record_count(metadata: LayerMetadataLike) -> int:
    """Get the maximum record count for a layer."""
    metadata = _as_dict(metadata)
    key_pattern = compile(
        r"max(imum)?(\s|_)?record(\s|_)?count$",
        flags=IGNORECASE,
    )
    key_list = [key for key in metadata.keys() if key_pattern.match(key)]
    if len(key_list) != 1:
        raise FieldDoesNotExistError(context="get_max_record_count")
    return metadata[key_list[0]]


def get_name(metadata: LayerMetadataLike) -> str:
    """Get the name of a layer."""
    metadata = _as_dict(metadata)
    key_pattern = compile("name", flags=IGNORECASE)
    key_list = [key for key in metadata.keys() if key_pattern.match(key)]
    if len(key_list) != 1:
        raise FieldDoesNotExistError(context="get_name")
    return metadata[key_list[0]]


def get_fields(layer_metadata: LayerMetadataLike, types: bool = False):
    """Get the fields of a layer.

    W5-4 (ADAPTERS-01): a permissive-tier ``FieldSpec`` allows ``name``
    and ``type`` to be missing or ``None`` -- real ArcGIS servers do
    occasionally emit such entries. A field whose ``name`` cannot be
    resolved to a ``str`` has no addressable identity and is silently
    dropped from the result (mirroring ``get_object_id_field``'s
    ``isinstance(field.get("name"), str)`` guard); this is an
    intentional, contract-aligned skip, not silent data loss of a
    resolvable field. ``types=True`` routes through :func:`_field_rows`
    so the dict/list/DataFrame views agree on the surviving field set.
    """
    layer_metadata = _as_dict(layer_metadata)
    fields = layer_metadata.get("fields") or []
    if types:
        return dict(_field_rows(layer_metadata))
    return [f["name"] for f in fields if isinstance(f.get("name"), str)]


def _field_rows(layer_metadata: LayerMetadataLike) -> list[tuple[str, str]]:
    """Return ``(name, type)`` rows for the layer fields.

    W5-4 (ADAPTERS-01): entries with a missing/non-``str`` ``name`` are
    dropped (see :func:`get_fields`); a missing or explicit-``None``
    ``type`` defaults to ``""`` rather than raising ``AttributeError``
    on ``None.replace(...)``.
    """
    layer_metadata = _as_dict(layer_metadata)
    fields: list[dict[str, Any]] = layer_metadata.get("fields") or []
    return [
        (f["name"], (f.get("type") or "").replace("esriFieldType", ""))
        for f in fields
        if isinstance(f.get("name"), str)
    ]


def get_fields_frame(layer_metadata: LayerMetadataLike) -> DataFrame:
    """Get the fields of a layer as a DataFrame.

    Routes through :func:`_field_rows`, so a field with no resolvable
    ``name`` is dropped (W5-4/ADAPTERS-01) -- see that function's
    docstring for the full skip-behavior contract.
    """
    DataFrame = require_pandas_dataframe("get_fields_frame()")
    return DataFrame(
        _field_rows(layer_metadata),
        columns=["name", "type"],
    )


# Deprecated legacy aliases (Phase 6). Emit DeprecationWarning when called;
# delegate to the canonical snake_case functions.
getfields = deprecated_alias(get_fields, "getfields", "get_fields")
getfields_df = deprecated_alias(get_fields_frame, "getfields_df", "get_fields_frame")
