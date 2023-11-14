"""A package for getting GeoDataFrames from ArcGIS FeatureLayers."""
from __future__ import annotations

import asyncio
from re import compile, IGNORECASE

from aiohttp import ClientSession
from pandas import DataFrame, concat

FIELDDOESNOTEXIST: IndexError = IndexError("Field does not exist")

DEFAULTDICT: dict = {
    "where": "1=1",
    "outFields": "*",
    "returnGeometry": True,
    "returnCountOnly": False,
    "f": "json",
}


def default_data(
    data: dict | None = None,
    default_dict: dict | None = None,
) -> dict:
    """Return a dict with default values for ArcGIS REST API requests."""
    default_dict = default_dict or DEFAULTDICT
    return {**default_dict, **(data or {})}


async def get_feature_count(
    url: str,
    session: ClientSession,
    **kwargs,
) -> int:
    """Get the feature count for a layer."""
    datadict: dict = {"where": "1=1", "returnCountOnly": True, "f": "json"}
    if "data" in kwargs:
        datadict["where"] = kwargs["data"].get("where", "1=1")
        if "token" in kwargs["data"]:
            datadict["token"] = kwargs["data"]["token"]
    xkwargs: dict = {k: v for k, v in kwargs.items() if k != "data"}
    response = await session.post(f"{url}/query", data=datadict, **xkwargs)
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
    session: ClientSession,
    token: str | None = None,
) -> dict:
    """Get the JSON dict for a layer."""
    data = {"f": "json"}
    if token:
        data["token"] = token
    response = await session.post(url, data=data)
    return await response.json(content_type=None)


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
    session: ClientSession,
    **kwargs,
) -> range:
    """Get the offset range for a layer."""
    feature_count = await get_feature_count(url, session, **kwargs)
    metadata = await get_metadata(url, session)
    max_record_count = get_max_record_count(metadata)
    return range(0, feature_count, max_record_count)


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
    session: ClientSession,
    sortby: str | None = None,
    **kwargs,
) -> list | DataFrame:
    """Get the unique values for a field."""
    datadict: dict = {
        "where": "1=1",
        "f": "json",
        "returnGeometry": False,
        "returnDistinctValues": True,
        "outFields": fields if isinstance(fields, str) else ",".join(fields),
    }
    if "data" in kwargs:
        datadict["where"] = kwargs["data"].get("where", "1=1")
        if "token" in kwargs["data"]:
            datadict["token"] = kwargs["data"]["token"]

    xkwargs: dict = {k: v for k, v in kwargs.items() if k != "data"}

    response = await session.post(f"{url}/query", data=datadict, **xkwargs)
    metadata = await response.json(content_type=None)

    res_l: list | None = None
    res_df: DataFrame | None = None

    if isinstance(fields, str):
        res_l = [x["attributes"][fields] for x in metadata["features"]]
    elif len(fields) == 1:
        res_l = [x["attributes"][fields[0]] for x in metadata["features"]]
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
    session: ClientSession,
    **kwargs,
) -> DataFrame:
    """Get the value counts for a field."""
    statstr = f'[{{"statisticType":"count","onStatisticField":"{field}","outStatisticFieldName":"{field}_count"}}]'
    data = kwargs.pop("data", {})
    data = {
        "where": "1=1",
        "f": "json",
        "returnGeometry": False,
        "outFields": field,
        "outStatistics": statstr,
        "groupByFieldsForStatistics": field,
        **data,
    }
    response = await session.post(f"{url}/query", data=data, **kwargs)
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
    session: ClientSession,
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
    data = kwargs.pop("data", {})
    data = {
        "where": "1=1",
        "f": "json",
        "returnGeometry": False,
        "outFields": ",".join(fields),
        "outStatistics": statstr,
        "groupByFieldsForStatistics": ",".join(fields),
        **data,
    }
    response = await session.post(f"{url}/query", data=data, **kwargs)
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
    session: ClientSession,
    service_url: str,
    token: str | None = None,
    return_feature_count: bool = False,
) -> dict:
    """Asynchronously retrieve layers for a single service."""
    _service_metadata = await get_metadata(service_url, session, token=token)

    async def _comprehensive_metadata(layer_url: str) -> dict:
        metadata = await get_metadata(layer_url, session)
        metadata["url"] = layer_url
        if return_feature_count and metadata["type"] == "Feature Layer":
            try:
                feature_count = await get_feature_count(layer_url, session)
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
