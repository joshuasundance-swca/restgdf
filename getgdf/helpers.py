"""getgdf/helpers.py: collect supporting data from service

these functions query and parse json responses from services

Joshua Sundance Bailey, SWCA Environmental Consultants
Joshua.Bailey@SWCA.com
05/16/2021
"""


import re

from requests import Session


def get_feature_count(url: str, session: Session = Session(), **kwargs) -> int:
    """Return int number of features for a service
    Keyword arguments are passed on to post request
    """
    data = {"where": "1=1", "returnCountOnly": True, "f": "json"}
    if "data" in kwargs.keys():
        data["where"] = kwargs["data"].get("where", "1=1")
        if "token" in kwargs["data"].keys():
            data["token"] = kwargs["data"]["token"]
    xkwargs = {k: v for k, v in kwargs.items() if k != "data"}
    response = session.post(
        f"{url}/query",
        data=data,
        **xkwargs,
        # the line above provides keyword arguments other than data dict
        # because data dict is manipulated for this function
        # (this allows the use of token authentication, for example)
    )
    return response.json()["count"]


def get_json_dict(url: str, session: Session = Session(), **kwargs) -> dict:
    """Return dict from a service's json
    Keyword arguments are passed on to post request
    """
    response = session.post(url, **kwargs)
    return response.json()


# def get_name(json_dict: dict) -> int:
#     """Return str name for a service"""
#     key_pattern = re.compile('name', flags=re.IGNORECASE)
#     key_list = [key for key in json_dict if re.match(key_pattern, key)]
#     assert len(key_list) == 1
#     return json_dict[key_list[0]]


def get_max_record_count(url: str, session: Session = Session(), **kwargs) -> int:
    """Return int max record count for a service
    Keyword arguments are passed on to post request
    """
    # TODO: why is there inconsistency in maxRecordCount key
    json_dict = get_json_dict(url, session, **kwargs)
    key_pattern = re.compile(
        r"max(imum)?(\s|_)?record(\s|_)?count$", flags=re.IGNORECASE
    )
    key_list = [key for key in json_dict if re.match(key_pattern, key)]
    assert len(key_list) == 1
    return json_dict[key_list[0]]


def get_offset_range(url: str, session: Session = Session(), **kwargs) -> range:
    """Return offset range object using feature count and max record count
    Keyword arguments are passed on to post request
    """
    feature_count = get_feature_count(url, session, **kwargs)
    max_record_count = get_max_record_count(url, session, **kwargs)
    return range(0, feature_count, max_record_count)
