import re
from contextlib import closing
from typing import Union, Optional

from pandas import DataFrame, concat
from requests import Session

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
    """
    Return data dict after adding default values
    Will not replace existing values
    """
    default_dict = default_dict or {
        "where": "1=1",
        "outFields": "*",
        "returnGeometry": True,
        "returnCountOnly": False,
        "f": "json",
    }

    return {**default_dict, **(data or {})}


def get_feature_count(url: str, session: Optional[Session] = None, **kwargs) -> int:
    """
    Return int number of features for a service
    Keyword arguments are passed on to post request
    """
    with closing(session or Session()) as s:
        data = kwargs.pop("data", {})
        data = {"where": "1=1", "returnCountOnly": True, "f": "json", **data}
        response = s.post(f"{url}/query", data=data, **kwargs)
    return response.json()["count"]


def get_jsondict(url: str, session: Optional[Session] = None, **kwargs) -> dict:
    """
    Return dict from a service's json
    Keyword arguments are passed on to post request
    """
    with closing(session or Session()) as s:
        data = kwargs.pop("data", {})
        response = s.post(url, data=default_data(data), **kwargs)
    return response.json()


def get_max_record_count(jsondict: dict) -> int:
    """
    Return int max record count for a service
    Keyword arguments are passed on to post request
    """
    key_pattern = re.compile(
        r"max(imum)?(\s|_)?record(\s|_)?count$",
        flags=re.IGNORECASE,
    )
    key_list = [key for key in jsondict.keys() if key_pattern.match(key)]
    if len(key_list) != 1:
        raise FIELDDOESNOTEXIST
    return jsondict[key_list[0]]


def get_offset_range(url: str, session: Optional[Session] = None, **kwargs) -> range:
    """
    Return offset range object using feature count and max record count
    Keyword arguments are passed on to post request
    """
    feature_count = get_feature_count(url, session, **kwargs)
    jsondict = get_jsondict(url, session, **kwargs)
    max_record_count = get_max_record_count(jsondict)
    return range(0, feature_count, max_record_count)


def get_name(jsondict: dict) -> str:
    """
    Return str name for a service
    """
    key_pattern = re.compile("name", flags=re.IGNORECASE)
    key_list = [key for key in jsondict.keys() if key_pattern.match(key)]
    if len(key_list) != 1:
        raise FIELDDOESNOTEXIST
    return jsondict[key_list[0]]


def getfields(jsondict: dict, types: bool = False):
    """
    Return list of field names or a name:type dict if types=True
    """
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
    sortby: Optional[str] = None,
    session: Optional[Session] = None,
    **kwargs,
) -> Union[list, DataFrame]:
    """
    Return list of unique values if fields is str or list of len 1
    Otherwise return pandas DataFrame of unique combinations, optionally sorted by field sortby
    """
    with closing(session or Session()) as s:
        data = kwargs.pop("data", {})
        data = {
            "where": "1=1",
            "f": "json",
            "returnGeometry": False,
            "returnDistinctValues": True,
            "outFields": fields if isinstance(fields, str) else ",".join(fields),
            **data,
        }
        response = s.post(f"{url}/query", data=data, **kwargs)
    jsondict = response.json()

    if isinstance(fields, str) or len(fields) == 1:
        field = fields if isinstance(fields, str) else fields[0]
        return [x["attributes"][field] for x in jsondict["features"]]
    else:
        res_df = concat(
            [DataFrame(x).T.reset_index(drop=True) for x in jsondict["features"]],
            ignore_index=True,
        )
        return res_df.sort_values(sortby).reset_index(drop=True) if sortby else res_df


def getvaluecounts(
    url: str,
    field: str,
    session: Optional[Session] = None,
    **kwargs,
) -> DataFrame:
    """
    Return DataFrame containing value counts (or dict if retdict=True)
    """
    with closing(session or Session()) as s:
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
        response = s.post(f"{url}/query", data=data, **kwargs)

    jsondict = response.json()
    features = jsondict["features"]
    cc = concat(
        [DataFrame(x["attributes"], index=[0]) for x in features],
        ignore_index=True,
    )
    return cc.sort_values(f"{field}_count", ascending=False).reset_index(drop=True)


def nestedcount(
    url: str,
    fields,
    session: Optional[Session] = None,
    **kwargs,
) -> DataFrame:
    """
    Return DataFrame containing count values for 2-field combinations
    """
    with closing(session or Session()) as s:
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
        response = s.post(f"{url}/query", data=data, **kwargs)

    jsondict = response.json()
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
