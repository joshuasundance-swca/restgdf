import re
from typing import Union, Optional

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
    data: Optional[dict] = None,
    default_dict: Optional[dict] = None,
) -> dict:
    default_dict = default_dict or DEFAULTDICT
    return {**default_dict, **(data or {})}


async def get_feature_count(
    url: str,
    session: ClientSession,
    **kwargs,
) -> int:
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
    response_json = await response.json()
    try:
        return response_json["count"]
    except KeyError as e:
        print(response)
        print(url, datadict, kwargs, xkwargs, sep="\n")
        print(response_json)
        raise e


async def get_jsondict(
    url: str,
    session: ClientSession,
    **kwargs,
) -> dict:
    data = kwargs.pop("data", {})
    response = await session.post(url, data=default_data(data), **kwargs)
    response_json = await response.json()
    return response_json


def get_max_record_count(jsondict: dict) -> int:
    key_pattern = re.compile(
        r"max(imum)?(\s|_)?record(\s|_)?count$",
        flags=re.IGNORECASE,
    )
    key_list = [key for key in jsondict.keys() if key_pattern.match(key)]
    if len(key_list) != 1:
        raise FIELDDOESNOTEXIST
    return jsondict[key_list[0]]


async def get_offset_range(
    url: str,
    session: ClientSession,
    **kwargs,
) -> range:
    feature_count = await get_feature_count(url, session, **kwargs)
    jsondict = await get_jsondict(url, session, **kwargs)
    max_record_count = get_max_record_count(jsondict)
    return range(0, feature_count, max_record_count)


def get_name(jsondict: dict) -> str:
    key_pattern = re.compile("name", flags=re.IGNORECASE)
    key_list = [key for key in jsondict.keys() if key_pattern.match(key)]
    if len(key_list) != 1:
        raise FIELDDOESNOTEXIST
    return jsondict[key_list[0]]


def getfields(jsondict: dict, types: bool = False):
    if types:
        return {
            f["name"]: f["type"].replace("esriFieldType", "") for f in jsondict["fields"]
        }
    else:
        return [f["name"] for f in jsondict["fields"]]


def getfields_df(jsondict: dict) -> DataFrame:
    return DataFrame(
        [
            (f["name"], f["type"].replace("esriFieldType", ""))
            for f in jsondict["fields"]
        ],
        columns=["name", "type"],
    )


async def getuniquevalues(
    url: str,
    fields: Union[tuple, str],
    session: ClientSession,
    sortby: Optional[str] = None,
    **kwargs,
) -> Union[list, DataFrame]:
    data = kwargs.pop("data", {})
    data = {
        "where": "1=1",
        "f": "json",
        "returnGeometry": False,
        "returnDistinctValues": True,
        "outFields": fields if isinstance(fields, str) else ",".join(fields),
        **data,
    }
    response = await session.post(f"{url}/query", data=data, **kwargs)
    jsondict = await response.json()

    if isinstance(fields, str) or len(fields) == 1:
        field = fields if isinstance(fields, str) else fields[0]
        return [x["attributes"][field] for x in jsondict["features"]]
    else:
        res_df = concat(
            [DataFrame(x).T.reset_index(drop=True) for x in jsondict["features"]],
            ignore_index=True,
        )
        return res_df.sort_values(sortby).reset_index(drop=True) if sortby else res_df


async def getvaluecounts(
    url: str,
    field: str,
    session: ClientSession,
    **kwargs,
) -> DataFrame:
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

    jsondict = await response.json()
    features = jsondict["features"]
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

    jsondict = await response.json()
    features = jsondict["features"]
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
