"""restgdf/_getinfo.py: collect supporting data from service

these functions query and parse json responses from services

Joshua Sundance Bailey
36394687+joshuasundance@users.noreply.github.com
"""

import re
from typing import Union, Optional

from pandas import DataFrame, concat
from requests import Session, Response

FIELDDOESNOTEXIST: IndexError = IndexError("Field does not exist")

DEFAULTDICT: dict = {
    "where": "1=1",
    "outFields": "*",
    "returnGeometry": True,
    "returnCountOnly": False,
    "f": "json",
}

DEFAULTDICTSTR: str = "\n".join([f"{k}: {v}" for k, v in DEFAULTDICT.items()])


def default_data(data: dict = None, default_dict: dict = None) -> dict:
    f"""Return data dict after adding default values
    Will not replace existing values
    Defaults:
    {DEFAULTDICTSTR}
    """
    data = data or {}
    default_dict = default_dict or DEFAULTDICT
    new_data: dict = {k: v for k, v in data.items()}
    for k, v in default_dict.items():
        new_data[k] = new_data.get(k, v)
    return new_data


def get_feature_count(url: str, session: Optional[Session] = None, **kwargs) -> int:
    """Return int number of features for a service
    Keyword arguments are passed on to post request
    """
    session = session or Session()
    datadict: dict = {"where": "1=1", "returnCountOnly": True, "f": "json"}
    if "data" in kwargs:
        datadict["where"] = kwargs["data"].get("where", "1=1")
        if "token" in kwargs["data"]:
            datadict["token"] = kwargs["data"]["token"]
    xkwargs: dict = {k: v for k, v in kwargs.items() if k != "data"}
    response: Response = session.post(
        f"{url}/query",
        data=datadict,
        **xkwargs,
        # the line above provides keyword arguments other than data dict
        # because data dict is manipulated for this function
        # (this allows the use of token authentication, for example)
    )
    return response.json()["count"]


def get_jsondict(url: str, session: Optional[Session] = None, **kwargs) -> dict:
    """Return dict from a service's json
    Keyword arguments are passed on to post request
    """
    session = session or Session()
    datadict: dict = default_data({}) if "data" not in kwargs else kwargs["data"]
    xkwargs: dict = {k: v for k, v in kwargs.items() if k != "data"}
    response: Response = session.post(url, data=datadict, **xkwargs)
    return response.json()


def get_max_record_count(jsondict: dict) -> int:
    """Return int max record count for a service
    Keyword arguments are passed on to post request
    """
    # TODO: why is there inconsistency in maxRecordCount key
    key_pattern: re.Pattern = re.compile(
        r"max(imum)?(\s|_)?record(\s|_)?count$", flags=re.IGNORECASE
    )
    key_list: list = [key for key in jsondict if re.match(key_pattern, key)]
    assert len(key_list) == 1
    return jsondict[key_list[0]]


def get_offset_range(url: str, session: Optional[Session] = None, **kwargs) -> range:
    """Return offset range object using feature count and max record count
    Keyword arguments are passed on to post request
    """
    session = session or Session()
    feature_count: int = get_feature_count(url, session, **kwargs)
    jsondict: dict = get_jsondict(url, session, **kwargs)
    max_record_count: int = get_max_record_count(jsondict)
    return range(0, feature_count, max_record_count)


# TODO: convert post requests to session requests
# TODO: add docstrings
# TODO: implement class(url, s:Session=Session(), auth=None, **kwargs)
def get_name(jsondict: dict) -> str:
    """Return str name for a service"""
    key_pattern: re.Pattern = re.compile("name", flags=re.IGNORECASE)
    key_list: list = [key for key in jsondict if re.match(key_pattern, key)]
    assert len(key_list) == 1
    return jsondict[key_list[0]]


def getfields(jsondict: dict, types: bool = False):
    """Return list of field names or a name:type dict if types=True"""
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


def getuniquevalues(
    url: str,
    fields: Union[tuple, str],
    sortby: str = None,
    session: Optional[Session] = None,
    **kwargs,
) -> Union[list, DataFrame]:
    """Return list of unique values if fields is str or list of len 1
    Otherwise return pandas DataFrame of unique combinations, optionally sorted by field sortby
    """
    session = session or Session()

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
    response: Response = session.post(f"{url}/query", data=datadict, **xkwargs)
    jsondict: dict = response.json()

    res_l: Union[list, None] = None
    res_df: Union[DataFrame, None] = None

    if isinstance(fields, str):
        res_l = [x["attributes"][fields] for x in jsondict["features"]]
    elif len(fields) == 1:
        res_l = [x["attributes"][fields[0]] for x in jsondict["features"]]
    else:
        res_df = concat(
            [DataFrame(x).T.reset_index(drop=True) for x in jsondict["features"]],
            ignore_index=True,
        )
        if sortby:
            res_df = res_df.sort_values(sortby).reset_index(drop=True)
    return res_l or res_df


def getvaluecounts(
    url: str, field: str, session: Optional[Session] = None, **kwargs
) -> DataFrame:
    """Return DataFrame containing value counts (or dict if retdict=True)"""
    session = session or Session()
    statstr: str = (
        "[{"
        f'"statisticType":"count","onStatisticField":"{field}",'
        f'"outStatisticFieldName":"{field}_count"'
        "}]"
    )
    datadict: dict = {
        "where": "1=1",
        "f": "json",
        "returnGeometry": False,
        "outFields": field,
        "outStatistics": statstr,
        "groupByFieldsForStatistics": field,
    }
    if "data" in kwargs:
        datadict["where"] = kwargs["data"].get("where", "1=1")
        if "token" in kwargs["data"]:
            datadict["token"] = kwargs["data"]["token"]

    xkwargs: dict = {k: v for k, v in kwargs.items() if k != "data"}
    response: Response = session.post(f"{url}/query", data=datadict, **xkwargs)

    jsondict: dict = response.json()
    features: list = jsondict["features"]
    cc: DataFrame = concat(
        [DataFrame(x["attributes"], index=[0]) for x in features], ignore_index=True,
    )
    return cc.sort_values(f"{field}_count", ascending=False).reset_index(drop=True)


def nestedcount(
    url: str, fields, session: Optional[Session] = None, **kwargs
) -> DataFrame:
    """Return DataFrame containing count values for 2-field combinations"""
    session = session or Session()
    statstr: str = "".join(
        (
            "[",
            ",".join(
                f'{{"statisticType":"count","onStatisticField":"{f}","outStatisticFieldName":"{f}_count"}}'
                for f in fields
            ),
            "]",
        )
    )
    datadict: dict = {
        "where": "1=1",
        "f": "json",
        "returnGeometry": False,
        "outFields": ",".join(fields),
        "outStatistics": statstr,
        "groupByFieldsForStatistics": ",".join(fields),
    }
    if "data" in kwargs:
        datadict["where"] = kwargs["data"].get("where", "1=1")
        if "token" in kwargs["data"]:
            datadict["token"] = kwargs["data"]["token"]

    xkwargs: dict = {k: v for k, v in kwargs.items() if k != "data"}
    response: Response = session.post(f"{url}/query", data=datadict, **xkwargs)

    jsondict: dict = response.json()
    features: list = jsondict["features"]
    cc: DataFrame = concat(
        [DataFrame(x).T.reset_index(drop=True) for x in features], ignore_index=True,
    )
    dropcol: str = [c for c in cc.columns if c.startswith(f"{fields[0]}_count")][0]
    rencol: str = [c for c in cc.columns if c.startswith(f"{fields[1]}_count")][0]
    return (
        cc.drop(columns=dropcol)
        .rename(columns={rencol: "Count"})
        .sort_values([fields[0], "Count"], ascending=[True, False])
        .reset_index(drop=True)
    )
