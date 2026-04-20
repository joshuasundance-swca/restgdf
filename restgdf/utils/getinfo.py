"""A package for getting GeoDataFrames from ArcGIS FeatureLayers."""

from __future__ import annotations

import asyncio
from re import compile, IGNORECASE

from aiohttp import ClientSession
from pandas import DataFrame, concat

from restgdf._client.request import build_conservative_query_data
from restgdf.utils.token import ArcGISTokenSession

FIELDDOESNOTEXIST: IndexError = IndexError("Field does not exist")
DEFAULT_METADATA_HEADERS = {
    "Accept": "application/json,text/plain,*/*",
    "User-Agent": "Mozilla/5.0",
}

DEFAULTDICT: dict = {
    "where": "1=1",
    "outFields": "*",
    "returnGeometry": True,
    "returnCountOnly": False,
    "f": "json",
}


def default_headers(headers: dict | None = None) -> dict:
    """Return request headers merged with ArcGIS-compatible defaults."""
    return {**DEFAULT_METADATA_HEADERS, **(headers or {})}


def default_data(
    data: dict | None = None,
    default_dict: dict | None = None,
) -> dict:
    """Return a dict with default values for ArcGIS REST API requests."""
    default_dict = default_dict or DEFAULTDICT
    return {**default_dict, **(data or {})}


async def get_feature_count(
    url: str,
    session: ClientSession | ArcGISTokenSession,
    **kwargs,
) -> int:
    """Get the feature count for a layer."""
    datadict = build_conservative_query_data(
        {"where": "1=1", "returnCountOnly": True, "f": "json"},
        kwargs.get("data"),
    )
    xkwargs: dict = {k: v for k, v in kwargs.items() if k != "data"}
    response = await session.post(
        f"{url}/query",
        data=datadict,
        headers=default_headers(xkwargs.pop("headers", None)),
        **xkwargs,
    )
    # the line above provides keyword arguments other than data dict
    # because data dict is manipulated for this function
    # (this allows the use of token authentication, for example)
    response_json = await response.json(content_type=None)
    try:
        return response_json["count"]
    except KeyError as e:
        # print(response)
        # print(url, datadict, kwargs, xkwargs, sep="\n")
        # print(response_json)
        raise e


async def get_metadata(
    url: str,
    session: ClientSession | ArcGISTokenSession,
    token: str | None = None,
) -> dict:
    """Get the JSON dict for a layer."""
    data = {"f": "json"}
    if token is not None:
        data["token"] = token
    response = await session.get(url, params=data, headers=default_headers())
    return await response.json(content_type=None)


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


async def get_offset_range(
    url: str,
    session: ClientSession | ArcGISTokenSession,
    **kwargs,
) -> range:
    """Get the offset range for a layer."""
    feature_count = await get_feature_count(url, session, **kwargs)
    token = (kwargs.get("data") or {}).get("token")
    metadata = await get_metadata(url, session, token=token)
    max_record_count = get_max_record_count(metadata)
    return range(0, feature_count, max_record_count)


async def get_object_ids(
    url: str,
    session: ClientSession | ArcGISTokenSession,
    **kwargs,
) -> tuple[str, list[int]]:
    """Get the object id field name and matching object ids for a layer query."""
    datadict = build_conservative_query_data(
        {"where": "1=1", "returnIdsOnly": True, "f": "json"},
        kwargs.get("data"),
    )
    xkwargs: dict = {k: v for k, v in kwargs.items() if k != "data"}
    response = await session.post(
        f"{url}/query",
        data=datadict,
        headers=default_headers(xkwargs.pop("headers", None)),
        **xkwargs,
    )
    response_json = await response.json(content_type=None)
    return response_json["objectIdFieldName"], response_json["objectIds"]


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


async def getuniquevalues(
    url: str,
    fields: tuple | str,
    session: ClientSession | ArcGISTokenSession,
    sortby: str | None = None,
    **kwargs,
) -> list | DataFrame:
    """Get the unique values for a field."""
    datadict = build_conservative_query_data(
        {
            "where": "1=1",
            "f": "json",
            "returnGeometry": False,
            "returnDistinctValues": True,
            "outFields": fields if isinstance(fields, str) else ",".join(fields),
        },
        kwargs.get("data"),
    )

    xkwargs: dict = {k: v for k, v in kwargs.items() if k != "data"}

    response = await session.post(
        f"{url}/query",
        data=datadict,
        headers=default_headers(xkwargs.pop("headers", None)),
        **xkwargs,
    )
    metadata = await response.json(content_type=None)

    res_l: list | None = None
    res_df: DataFrame | None = None

    if isinstance(fields, str):
        res_l = [x["attributes"][fields] for x in metadata["features"]]
        if sortby and sortby == fields:
            res_l = sorted(res_l)
    elif len(fields) == 1:
        res_l = [x["attributes"][fields[0]] for x in metadata["features"]]
        if sortby and sortby == fields[0]:
            res_l = sorted(res_l)
    else:
        res_df = concat(
            [DataFrame(x).T.reset_index(drop=True) for x in metadata["features"]],
            ignore_index=True,
        )
        if sortby:
            res_df = res_df.sort_values(sortby).reset_index(drop=True)
    return res_l or res_df


async def getvaluecounts(
    url: str,
    field: str,
    session: ClientSession | ArcGISTokenSession,
    **kwargs,
) -> DataFrame:
    """Get the value counts for a field."""
    statstr = f'[{{"statisticType":"count","onStatisticField":"{field}","outStatisticFieldName":"{field}_count"}}]'
    data = kwargs.pop("data", None) or {}
    data = {
        "where": "1=1",
        "f": "json",
        "returnGeometry": False,
        "outFields": field,
        "outStatistics": statstr,
        "groupByFieldsForStatistics": field,
        **data,
    }
    response = await session.post(
        f"{url}/query",
        data=data,
        headers=default_headers(kwargs.pop("headers", None)),
        **kwargs,
    )
    metadata = await response.json(content_type=None)
    features = metadata["features"]
    cc = concat(
        [DataFrame(x["attributes"], index=[0]) for x in features],
        ignore_index=True,
    )
    return cc.sort_values(f"{field}_count", ascending=False).reset_index(drop=True)


async def nestedcount(
    url: str,
    fields,
    session: ClientSession | ArcGISTokenSession,
    **kwargs,
) -> DataFrame:
    """Get the nested value counts for a field."""
    statstr = "".join(
        (
            "[",
            ",".join(
                f'{{"statisticType":"count","onStatisticField":"{f}","outStatisticFieldName":"{f}_count"}}'
                for f in fields
            ),
            "]",
        ),
    )
    data = kwargs.pop("data", None) or {}
    data = {
        "where": "1=1",
        "f": "json",
        "returnGeometry": False,
        "outFields": ",".join(fields),
        "outStatistics": statstr,
        "groupByFieldsForStatistics": ",".join(fields),
        **data,
    }
    response = await session.post(
        f"{url}/query",
        data=data,
        headers=default_headers(kwargs.pop("headers", None)),
        **kwargs,
    )
    metadata = await response.json(content_type=None)
    features = metadata["features"]
    cc = concat(
        [DataFrame(x).T.reset_index(drop=True) for x in features],
        ignore_index=True,
    )
    dropcol = [c for c in cc.columns if c.startswith(f"{fields[0]}_count")][0]
    rencol = [c for c in cc.columns if c.startswith(f"{fields[1]}_count")][0]
    return (
        cc.drop(columns=dropcol)
        .rename(columns={rencol: "Count"})
        .sort_values([fields[0], "Count"], ascending=[True, False])
        .reset_index(drop=True)
    )


async def service_metadata(
    session: ClientSession | ArcGISTokenSession,
    service_url: str,
    token: str | None = None,
    return_feature_count: bool = False,
) -> dict:
    """Asynchronously retrieve layers for a single service."""
    _service_metadata = await get_metadata(service_url, session, token=token)

    async def _comprehensive_metadata(layer_url: str) -> dict:
        metadata = await get_metadata(layer_url, session, token=token)
        metadata["url"] = layer_url
        if return_feature_count and metadata["type"] == "Feature Layer":
            try:
                feature_count = await get_feature_count(
                    layer_url,
                    session,
                    **({"data": {"token": token}} if token is not None else {}),
                )
            except KeyError:
                feature_count = None
            metadata["feature_count"] = feature_count  # type: ignore
        return metadata

    tasks = [
        _comprehensive_metadata(f"{service_url}/{layer['id']}")
        for layer in _service_metadata.get("layers") or []
    ]
    results = await asyncio.gather(*tasks)
    _service_metadata["layers"] = results
    return _service_metadata
