"""Pure metadata parsers for ArcGIS REST responses.

Private submodule; all public names are re-exported by
``restgdf.utils.getinfo`` to preserve import paths.
"""

from __future__ import annotations

from re import IGNORECASE, compile

from pandas import DataFrame

FIELDDOESNOTEXIST: IndexError = IndexError("Field does not exist")


def supports_pagination(metadata: dict) -> bool:
    """Return whether the layer supports resultOffset/resultRecordCount pagination."""
    advanced_query_capabilities = metadata.get("advancedQueryCapabilities") or {}
    if "supportsPagination" in advanced_query_capabilities:
        return advanced_query_capabilities["supportsPagination"]
    if "supportsPagination" in metadata:
        return metadata["supportsPagination"]
    return True


def get_object_id_field(metadata: dict) -> str:
    """Get the object id field name for a layer."""
    oid_fields = [
        field["name"]
        for field in metadata.get("fields", [])
        if field.get("type") == "esriFieldTypeOID"
    ]
    if len(oid_fields) != 1:
        raise FIELDDOESNOTEXIST
    return oid_fields[0]


def get_max_record_count(metadata: dict) -> int:
    """Get the maximum record count for a layer."""
    key_pattern = compile(
        r"max(imum)?(\s|_)?record(\s|_)?count$",
        flags=IGNORECASE,
    )
    key_list = [key for key in metadata.keys() if key_pattern.match(key)]
    if len(key_list) != 1:
        raise FIELDDOESNOTEXIST
    return metadata[key_list[0]]


def get_name(metadata: dict) -> str:
    """Get the name of a layer."""
    key_pattern = compile("name", flags=IGNORECASE)
    key_list = [key for key in metadata.keys() if key_pattern.match(key)]
    if len(key_list) != 1:
        raise FIELDDOESNOTEXIST
    return metadata[key_list[0]]


def getfields(layer_metadata: dict, types: bool = False):
    """Get the fields of a layer."""
    if types:
        return {
            f["name"]: f["type"].replace("esriFieldType", "")
            for f in layer_metadata["fields"]
        }
    else:
        return [f["name"] for f in layer_metadata["fields"]]


def getfields_df(layer_metadata: dict) -> DataFrame:
    """Get the fields of a layer as a DataFrame."""
    return DataFrame(
        [
            (f["name"], f["type"].replace("esriFieldType", ""))
            for f in layer_metadata["fields"]
        ],
        columns=["name", "type"],
    )
