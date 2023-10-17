# This is a working rewrite of the original datapillager. It requires arcpy.
# https://github.com/gdherbert/DataPillager/blob/main/DataServicePillager.py
# it uses type hints and some other syntax upgrades
# it uses requests instead of urllib
# next it will be refactored to work without arcpy
# important functionality should be moved into restgdf


# import codecs
# import datetime
# import itertools
# import json
# import logging
# import os
# import re
# import sys
# import time
# import traceback
# import urllib.parse
# import warnings
# from typing import Any, Optional, Union
# from collections.abc import Iterable
#
# import arcpy
# import requests
#
# arcpy.env.overwriteOutput = True
#
#
# def trace() -> tuple[str, str]:
#     tb = sys.exc_info()[2]
#     tbinfo = traceback.format_tb(tb)[0]  # script name + line number  # noqa
#     line = tbinfo.split(", ")[1]
#     # Get Python syntax error
#     synerror = traceback.format_exc().splitlines()[-1]
#     return line, synerror
#
#
# def test_trace() -> None:
#     try:
#         1 / 0
#     except ZeroDivisionError:
#         line, synerror = trace()
#         print("error on line: %s" % line)
#         print("error: %s" % synerror)
#
#
# def output_msg(msg: str, severity: int = 0) -> None:
#     logging.log(severity, msg)
#     if severity == 0:
#         print(msg)
#     elif severity == 1:
#         warnings.warn(msg, UserWarning)
#     elif severity == 2:
#         raise RuntimeError(msg)
#
#
# def validate_url(
#     url_to_test: str,
#     session: Optional[requests.Session] = None,
# ) -> Union[str, None]:
#     session = session or requests.Session()
#     try:
#         response = session.get(url_to_test)
#         response.raise_for_status()
#         output_msg(f"Ho, a successful url test: {url_to_test}")
#         return url_to_test
#     except requests.exceptions.HTTPError as e:
#         if e.response.status_code == 404:
#             output_msg(f"Arr, 404 error: {url_to_test}")
#         else:
#             output_msg(f"Avast, HTTP error: {e.response.status_code}")
#     except requests.exceptions.RequestException:
#         output_msg(f"Avast, RequestException: {url_to_test}")
#     return None
#
#
# def test_validate_url() -> None:
#     valid_url = "https://maps1.vcgov.org/arcgis/rest/services/Beaches/MapServer/7"
#     assert validate_url(valid_url) == valid_url  # nosec
#     invalid_url = "https://maps1.vcgov.org/arcgis/rest/services/Beaches/MapServer/75310"
#     assert validate_url(invalid_url) is None  # nosec
#
#
# def get_adapter_name(url_string: str) -> str:
#     u = urllib.parse.urlparse(url_string)
#     if u.netloc.find("arcgis.com") > -1:
#         # is an esri domain
#         adapter_name = u.path.split("/")[2]  # third element
#     else:
#         adapter_name = u.path.split("/")[1]  # second element
#     return adapter_name
#
#
# def test_get_adapter_name() -> None:
#     valid_url = "https://maps1.vcgov.org/arcgis/rest/services/Beaches/MapServer/7"
#     assert get_adapter_name(valid_url) == "arcgis"  # nosec
#
#
# def get_referring_domain(url_string: str) -> str:
#     u = urllib.parse.urlparse(url_string)
#     if u.netloc.find("arcgis.com") > -1:
#         # is an esri domain
#         ref_domain = r"https://www.arcgis.com"
#     else:
#         # generate from service url and hope it works
#         if u.scheme == "http":
#             ref_domain = urllib.parse.urlunsplit(["https", u.netloc, "", "", ""])
#         else:
#             ref_domain = urllib.parse.urlunsplit([u.scheme, u.netloc, "", "", ""])
#     return ref_domain
#
#
# def test_get_referring_domain() -> None:
#     valid_url = "https://maps1.vcgov.org/arcgis/rest/services/Beaches/MapServer/7"
#     assert get_referring_domain(valid_url) == "https://maps1.vcgov.org"  # nosec
#
#
# def get_token(
#     username: str,
#     password: str,
#     referer: str,
#     adapter_name: str,
#     client_type: str = "requestip",
#     expiration: int = 240,
#     session: Optional[requests.Session] = None,
# ) -> str:
#     session = session or requests.Session()
#     query_dict = {
#         "username": username,
#         "password": password,
#         "expiration": str(expiration),
#         "client": client_type,
#         "referer": referer,
#         "f": "json",
#     }
#
#     # check for ArcGIS token generator url
#     token_url = None
#     token_url_array = [
#         referer + r"/sharing/rest/generateToken",
#         referer + r"/" + adapter_name + r"/tokens/generateToken",
#     ]
#     for url2test in token_url_array:
#         if validate_url(url2test, session=session):
#             token_url = url2test
#             break
#     if token_url:
#         token_response = session.post(token_url, data=query_dict)
#         token_json = token_response.json()
#     else:
#         token_json = {"error": "unable to get token"}
#
#     if "token" in token_json:
#         token = token_json["token"]
#         return token
#     else:
#         output_msg(
#             "Avast! The scurvy gatekeeper says 'Could not generate a token with the username and password provided'. Check yer login details are shipshape!",
#             severity=2,
#         )
#         if "error" in token_json:
#             output_msg(token_json["error"], severity=2)
#         elif "message" in token_json:
#             output_msg(token_json["message"], severity=2)
#         raise ValueError("Token Error")
#
#
# def get_all_the_layers(
#     service_endpoint: str,
#     tokenstring: str,
#     session: Optional[requests.Session] = None,
# ) -> list[str]:
#     session = session or requests.Session()
#     try:
#         service_call = session.get(service_endpoint + "?f=json" + tokenstring)
#         service_call.raise_for_status()
#     except requests.exceptions.HTTPError as e:
#         raise Exception(
#             f"Gaaar, 'service_call' failed to access {service_endpoint}",
#         ) from e
#
#     service_layer_info = service_call.json()
#     # service_layer_info = json.loads(service_call, strict=False)
#     if service_layer_info.get("error"):
#         raise Exception(
#             f"Gaaar, 'service_call' failed to access {service_endpoint}",
#         )
#
#     service_layer_info.get("currentVersion")
#
#     service_layers_to_walk = []
#     service_layers_to_get = []
#
#     # search any folders
#     if (
#         "folders" in service_layer_info.keys()
#         and len(service_layer_info.get("folders")) > 0
#     ):
#         catalog_folder = service_layer_info.get("folders")
#         folder_list = [f for f in catalog_folder if f.lower() not in "utilities"]
#         for folder_name in folder_list:
#             output_msg(
#                 f"Ahoy, I be searching {folder_name} for hidden treasure...",
#                 severity=0,
#             )
#             lyr_list = get_all_the_layers(
#                 service_endpoint + "/" + folder_name,
#                 tokenstring,
#             )
#             if lyr_list:
#                 service_layers_to_walk.extend(lyr_list)
#
#     # get list of service urls
#     if (
#         "services" in service_layer_info.keys()
#         and len(service_layer_info.get("services")) > 0
#     ):
#         catalog_services = service_layer_info.get("services")
#         for service in catalog_services:
#             servicetype = service["type"]
#             servicename = service["name"]
#             if servicetype in ["MapServer", "FeatureServer"]:
#                 service_url = service_endpoint + "/" + servicename + "/" + servicetype
#                 if servicename.find("/") > -1:
#                     folder, sname = servicename.split("/")
#                     if service_endpoint.endswith(folder):
#                         service_url = service_endpoint + "/" + sname + "/" + servicetype
#
#                 service_layers_to_walk.append(service_url)
#
#     if len(service_layers_to_walk) == 0:
#         # no services or folders
#         service_layers_to_walk.append(service_endpoint)
#
#     for url in service_layers_to_walk:
#         # go get the json and information and walk down until you get all the service urls
#         service_call = session.get(url + "?f=json" + tokenstring).json()
#         # for getting all the layers, start with a list of sublayers
#         service_layers = None
#         service_layer_type = None
#         if service_call.get("layers"):
#             service_layers = service_call.get("layers")
#             service_layer_type = "layers"
#         elif service_call.get("subLayers"):
#             service_layers = service_layer_info.get("subLayers")
#             service_layer_type = "sublayers"
#
#         # subLayers an array of objects, each has an id
#         if service_layers is not None:
#             # has sub layers, get em all
#             for lyr in service_layers:
#                 if not lyr.get("subLayerIds"):  # ignore group layers
#                     lyr_id = str(lyr.get("id"))
#                     if service_layer_type == "layers":
#                         sub_layer_url = url + "/" + lyr_id
#                         lyr_list = get_all_the_layers(
#                             sub_layer_url,
#                             tokenstring,
#                             session=session,
#                         )
#                         if lyr_list:
#                             service_layers_to_walk.extend(lyr_list)
#                         # add the full url
#                         else:
#                             service_layers_to_get.append(sub_layer_url)
#                     elif service_layer_type == "sublayers":
#                         # handled differently, drop the parent layer id and use sublayer id
#                         sub_endpoint = url.rsplit("/", 1)[0]
#                         sub_layer_url = sub_endpoint + "/" + lyr_id
#                         lyr_list = get_all_the_layers(
#                             sub_layer_url,
#                             tokenstring,
#                             session=session,
#                         )
#                         if lyr_list:
#                             service_layers_to_walk.extend(lyr_list)
#                         else:
#                             service_layers_to_get.append(sub_layer_url)
#         else:
#             # no sub layers
#             # check if group layer
#             if service_call.get("type"):
#                 if service_call.get("type") not in ("Group Layer", "Raster Layer"):
#                     service_layers_to_get.append(url)
#
#     return service_layers_to_get
#
#
# def get_data(
#     query: str,
#     max_tries: int = 3,
#     sleep_time: int = 2,
#     session: Optional[requests.Session] = None,
# ) -> Union[dict[str, str], None]:
#     session = session or requests.Session()
#     count_tries = 0
#
#     try:
#         response = session.get(query).content
#         if response:
#             try:
#                 response = response.decode("utf-8")  # convert to unicode
#             except UnicodeDecodeError:
#                 response = response.decode("unicode-escape")  # convert to unicode
#             # load to json and check for error
#             resp_json = json.loads(response)
#             if resp_json.get("error"):
#                 output_msg(resp_json["error"])
#             return resp_json
#         else:
#             return {"error": "no response received"}
#
#     except Exception as e:
#         output_msg(str(e), severity=1)
#         # sleep and try again
#         if hasattr(e, "errno") and e.errno == 10054:
#             # connection forcible closed, extra sleep pause
#             time.sleep(sleep_time)
#         time.sleep(sleep_time)
#         count_tries += 1
#         if count_tries > max_tries:
#             count_tries = 0
#             output_msg("Avast! Error: ACCESS_FAILED")
#             return None
#         else:
#             output_msg(f"Hold fast, attempt {count_tries} of {max_tries}")
#             return get_data(
#                 query=query,
#                 max_tries=max_tries,
#                 sleep_time=sleep_time,
#                 session=session,
#             )
#
#
# def combine_data(fc_list: list[str], output_fc: str) -> None:
#     count_fc = len(fc_list)
#     drop_spatial = False  # whether to drop the spatial index before loading
#     if (
#         count_fc > 50
#     ):  # and not workspace_type.startswith('esriDataSourcesGDB.SdeWorkspaceFactory'): # larger inputs and not if SDE
#         drop_spatial = True
#
#     if count_fc == 1:
#         # simple case
#         arcpy.Copy_management(fc_list[0], output_fc)
#         output_msg(f"Created {output_fc}")
#     else:
#         for fc in fc_list:
#             if fc_list.index(fc) == 0:
#                 # append to first dataset. much faster
#                 output_msg(f"Prepping yer first dataset {fc}")
#                 if arcpy.Exists(output_fc):
#                     output_msg(
#                         f"Avast! {output_fc} exists, deleting...",
#                         severity=1,
#                     )
#                     arcpy.Delete_management(output_fc)
#
#                 arcpy.Copy_management(fc, output_fc)  # create dataset to append to
#                 output_msg(f"Created {output_fc}")
#                 if drop_spatial:
#                     # delete the spatial index for better loading
#                     output_msg("Dropping spatial index for loading performance")
#                     arcpy.management.RemoveSpatialIndex(output_fc)
#
#                 fieldlist = []
#                 # fieldlist = ["SHAPE@"]
#                 fields = arcpy.ListFields(output_fc)
#                 for field in fields:
#                     if field.name.lower() == "shape":
#                         fieldlist.insert(0, "SHAPE@")  # add shape token to start
#                     else:
#                         fieldlist.append(field.name)
#
#                 insert_rows = arcpy.da.InsertCursor(output_fc, fieldlist)
#             else:
#                 search_rows = arcpy.da.SearchCursor(
#                     fc,
#                     fieldlist,
#                 )  # append to first dataset
#                 for row in search_rows:
#                     insert_rows.insertRow(row)
#                 del row, search_rows
#                 output_msg(f"Appended {fc}...")
#
#         if drop_spatial:
#             # recreate the spatial index
#             output_msg("Adding spatial index")
#             arcpy.management.AddSpatialIndex(output_fc)
#         del insert_rows
#
#
# def grouper(iterable: Iterable, n: int, fillvalue: Any = None) -> Iterable:
#     args = [iter(iterable)] * n
#     return itertools.zip_longest(*args, fillvalue=fillvalue)
#
#
# def make_service_name(
#     service_info: dict,
#     output_workspace: str,
#     output_folder_path_len: int,
#     output_type: str,
#     service_output_name_tracking_list: list[str],
# ) -> str:
#     # establish a unique name that isn't too long
#     # 160-character limit for filegeodatabase
#     max_path_length = 230  # sanity length for Windows systems
#     if output_type == "Workspace":
#         max_name_len = 150  # based on fgdb
#     else:
#         max_name_len = max_path_length - output_folder_path_len
#
#     parent_id = ""
#     service_name = service_info.get("name")
#     service_id = str(service_info.get("id"))
#
#     # clean up the service name (remove invalid characters)
#     service_name_cl = service_name.encode(
#         "ascii",
#         "ignore",
#     )  # strip any non-ascii characters that may cause an issue
#     # remove multiple underscores and any other problematic characters
#     service_name_cl = re.sub(
#         r"[_]+",
#         "_",
#         arcpy.ValidateTableName(service_name_cl, output_workspace),
#     )
#     service_name_cl = service_name_cl.rstrip("_")
#
#     if len(service_name_cl) > max_name_len:
#         service_name_cl = service_name_cl[:max_name_len]
#
#     service_name_len = len(service_name_cl)
#
#     if service_info.get("parentLayer"):
#         service_info.get("parentLayer").get("name")
#         parent_id = str(service_info.get("parentLayer").get("id"))
#
#     if (
#         output_folder_path_len + service_name_len > max_path_length
#     ):  # can be written to disc
#         # shorten the service name
#         max_len = max_path_length - output_folder_path_len
#         if max_len < service_name_len:
#             service_name_cl = service_name_cl[:max_len]
#
#     # check if name already exists
#     if service_name_cl not in service_output_name_tracking_list:
#         service_output_name_tracking_list.append(service_name_cl)
#     else:
#         if service_name_cl + "_" + service_id not in service_output_name_tracking_list:
#             service_name_cl += "_" + service_id
#             service_output_name_tracking_list.append(service_name_cl)
#         else:
#             service_name_cl += parent_id + "_" + service_id
#
#     return service_name_cl
#
#
# # -------------------------------------------------
# def main(
#     service_endpoint: str,
#     output_workspace: str,
#     max_tries: int = 3,
#     sleep_time: int = 2,
#     strict_mode: bool = True,
#     username: str = "",
#     password: str = "",
#     referring_domain: str = "",
#     existing_token: str = "",
#     query_str: str = "",
#     session: Optional[requests.Session] = None,
# ):
#     session = session or requests.Session()
#
#     start_time = datetime.datetime.today()
#
#     try:
#         sanity_max_record_count = 10000
#
#         # to query by geometry need [xmin,ymin,xmax,ymax], spatial reference, and geometryType (eg esriGeometryEnvelope
#
#         if service_endpoint == "":
#             output_msg("Avast! Can't plunder nothing from an empty url! Time to quit.")
#             sys.exit()
#
#         if query_str:
#             query_str = urllib.parse.quote(query_str)
#
#         if output_workspace == "":
#             output_workspace = os.getcwd()
#
#         output_desc = arcpy.Describe(output_workspace)
#         output_type = output_desc.dataType
#         if hasattr(output_desc, "wrkspaceFactoryProgID"):
#             pass
#
#         if output_type == "Folder":  # To Folder
#             output_folder = output_workspace
#         else:
#             output_folder = output_desc.path
#
#         adapter_name = get_adapter_name(service_endpoint)
#         token_client_type = "requestip"  # nosec
#         if referring_domain != "":
#             referring_domain = referring_domain.replace("http:", "https:")
#             token_client_type = "referer"  # nosec
#         else:
#             referring_domain = get_referring_domain(service_endpoint)
#             if referring_domain == r"https://www.arcgis.com":
#                 token_client_type = "referer"  # nosec
#
#         token = ""  # nosec
#         if username and not existing_token:
#             token = get_token(
#                 username=username,
#                 password=password,
#                 referer=referring_domain,
#                 adapter_name=adapter_name,
#                 client_type=token_client_type,
#                 session=session,
#             )
#         elif existing_token:
#             token = existing_token
#
#         tokenstring = ""
#         if len(token) > 0:
#             tokenstring = "&token=" + token
#
#         output_msg(f"Start the plunder! {service_endpoint}")
#         output_msg(f"We be stashing the booty in {output_workspace}")
#
#         service_layers_to_get = get_all_the_layers(
#             service_endpoint,
#             tokenstring,
#             session=session,
#         )
#         output_msg(
#             f"Blimey, {len(service_layers_to_get)} layers for the pillagin'",
#         )
#         for slyr in service_layers_to_get:
#             downloaded_fc_list = []  # for file merging.
#             response = None
#             current_iter = 0
#             max_record_count = 0
#             feature_count = 0
#             final_fc = ""
#
#             output_msg(f"Now pillagin' yer data from {slyr}")
#             service_info_call = session.get(slyr + "?f=json" + tokenstring)
#             if service_info_call:
#                 # service_info = json.loads(service_info_call, strict=False)
#                 service_info = service_info_call.json()
#             else:
#                 raise Exception(f"'service_info_call' failed to access {slyr}")
#
#             if not service_info.get("error"):
#                 # add url to info
#                 service_info["serviceURL"] = slyr
#
#                 # assume JSON supported
#                 supports_json = True
#                 if strict_mode:
#                     # check JSON supported
#                     supports_json = False
#                     if "supportedQueryFormats" in service_info:
#                         supported_formats = service_info.get(
#                             "supportedQueryFormats",
#                         ).split(",")
#                         for data_format in supported_formats:
#                             if data_format == "JSON":
#                                 supports_json = True
#                                 break
#                     else:
#                         output_msg("Strict mode scuttled, no supported formats")
#
#                 objectid_field = "OBJECTID"
#                 if "fields" in service_info:
#                     field_list = service_info.get("fields")
#                     if field_list:
#                         for field in field_list:
#                             ftype = field.get("type")
#                             if ftype == "esriFieldTypeOID":
#                                 objectid_field = field.get("name")
#                 else:
#                     output_msg(
#                         f"No field list - come about using {objectid_field}!",
#                     )
#
#                 # get count
#                 if query_str == "":
#                     feature_count_call = session.get(
#                         slyr
#                         + "/query?where=1%3D1&returnCountOnly=true&f=pjson"
#                         + tokenstring,
#                     )
#                 else:
#                     feature_count_call = session.get(
#                         slyr
#                         + "/query?where="
#                         + query_str
#                         + "&returnCountOnly=true&f=pjson"
#                         + tokenstring,
#                     )
#
#                 if feature_count_call:
#                     feature_count = feature_count_call.json()
#                     service_info["FeatureCount"] = feature_count.get("count")
#
#                 service_output_name_tracking_list = []
#
#                 service_name_cl = make_service_name(
#                     service_info=service_info,
#                     output_workspace=output_workspace,
#                     output_folder_path_len=len(output_folder),
#                     output_type=output_type,
#                     service_output_name_tracking_list=service_output_name_tracking_list,
#                 )
#
#                 info_filename = service_name_cl + "_info.txt"
#                 info_file = os.path.join(output_folder, info_filename)
#
#                 # write out the service info for reference
#                 with open(info_file, "w") as i_file:
#                     json.dump(
#                         service_info,
#                         i_file,
#                         sort_keys=True,
#                         indent=4,
#                         separators=(",", ": "),
#                     )
#                     output_msg(
#                         f"Yar! {service_name_cl} Service info stashed in '{info_file}'",
#                     )
#
#                 if supports_json:
#                     try:
#                         # to query using geometry,&geometry=   &geometryType= esriGeometryEnvelope &inSR= and probably spatial relationship and buffering
#                         feat_data_query = (
#                             r"/query?outFields=*&returnGeometry=true&returnIdsOnly=false&returnCountOnly=false&objectIds=&time=&geometry=&geometryType=esriGeometryEnvelope&inSR=&spatialRel=esriSpatialRelIntersects&distance=&units=esriSRUnit_Meter&maxAllowableOffset=&geometryPrecision=&outSR=&returnExtentOnly=false&orderByFields=&groupByFieldsForStatistics=&outStatistics=&resultOffset=&resultRecordCount=&returnZ=false&returnM=false&f=json"
#                             + tokenstring
#                         )
#                         if query_str == "":
#                             feat_OIDLIST_query = (
#                                 r"/query?where="
#                                 + objectid_field
#                                 + r"+%3E+0&returnGeometry=false&returnIdsOnly=true&returnCountOnly=false&returnExtentOnly=false&objectIds=&time=&geometry=&geometryType=esriGeometryEnvelope&inSR=&spatialRel=esriSpatialRelIntersects&distance=&units=esriSRUnit_Meter&outFields=&maxAllowableOffset=&geometryPrecision=&outSR=&orderByFields=&groupByFieldsForStatistics=&outStatistics=&resultOffset=&resultRecordCount=&returnZ=false&returnM=false&f=json"
#                                 + tokenstring
#                             )
#                         else:
#                             feat_OIDLIST_query = (
#                                 r"/query?where="
#                                 + query_str
#                                 + r"&returnGeometry=false&returnIdsOnly=true&returnCountOnly=false&returnExtentOnly=false&objectIds=&time=&geometry=&geometryType=esriGeometryEnvelope&inSR=&spatialRel=esriSpatialRelIntersects&distance=&units=esriSRUnit_Meter&outFields=&maxAllowableOffset=&geometryPrecision=&outSR=&orderByFields=&groupByFieldsForStatistics=&outStatistics=&resultOffset=&resultRecordCount=&returnZ=false&returnM=false&f=json"
#                                 + tokenstring
#                             )
#
#                         max_record_count = service_info.get(
#                             "maxRecordCount",
#                         )  # maximum number of records returned by service at once
#                         if max_record_count > sanity_max_record_count:
#                             output_msg(
#                                 f"{max_record_count} max records is a wee bit large, using {sanity_max_record_count} instead...",
#                             )
#                             max_record_count = sanity_max_record_count
#
#                         # extract using actual OID values is the safest way
#                         feature_OIDs = None
#                         feature_OID_query = session.get(
#                             slyr + feat_OIDLIST_query,
#                         ).json()
#                         if feature_OID_query and "objectIds" in feature_OID_query:
#                             feature_OIDs = feature_OID_query["objectIds"]
#                         else:
#                             output_msg(
#                                 f"Blast, no OID values: {feature_OID_query}",
#                             )
#
#                         if feature_OIDs:
#                             OID_count = len(feature_OIDs)
#                             sortie_count = OID_count // max_record_count + (
#                                 OID_count % max_record_count > 0
#                             )
#                             output_msg(
#                                 f"{OID_count} records, in chunks of {max_record_count}, err, that be {sortie_count} sorties. Ready lads!",
#                             )
#
#                             feature_OIDs.sort()
#                             # chunk them
#                             for group in grouper(feature_OIDs, max_record_count):
#                                 # reset count_tries
#                                 start_oid = group[0]
#                                 end_oid = group[max_record_count - 1]
#                                 if end_oid is None:  # reached the end of the iterables
#                                     # loop through and find last oid, need this due to fillvalue of None in grouper
#                                     for i in reversed(group):
#                                         if i is not None:
#                                             end_oid = i
#                                             break
#
#                                 # >= %3E%3D, <= %3C%3D
#                                 if query_str == "":
#                                     where_clause = f"&where={objectid_field}+%3E%3D+{start_oid}+AND+{objectid_field}+%3C%3D+{end_oid}"
#                                 else:
#                                     where_clause = f"&where={query_str}+AND+{objectid_field}+%3E%3D+{start_oid}+AND+{objectid_field}+%3C%3D+{end_oid}"
#                                 # response is a string of json with the attributes and geometry
#                                 query = slyr + feat_data_query + where_clause
#                                 response = get_data(
#                                     query,
#                                     max_tries=max_tries,
#                                     sleep_time=sleep_time,
#                                     session=session,
#                                 )  # expects json object
#                                 if not response.get("features"):
#                                     raise ValueError(
#                                         "Abandon ship! Data access failed! Check what ye manag'd to plunder before failure.",
#                                     )
#                                 else:
#                                     feature_dict = response[
#                                         "features"
#                                     ]  # load the features so we can check they are not empty
#
#                                     if len(feature_dict) != 0:
#                                         # convert response to json file on disk then to gdb/shapefile (is fast)
#                                         # can hit long filename issue!!!!
#                                         # look at an arcpy.FeatureSet() to hold the data
#                                         # some services produce JSON that errors a FeatureSet()
#                                         ##fs = arcpy.FeatureSet()
#                                         ##fs.load(response)
#
#                                         out_JSON_name = (
#                                             service_name_cl
#                                             + str(current_iter)
#                                             + ".json"
#                                         )
#                                         out_JSON_file = os.path.join(
#                                             output_folder,
#                                             out_JSON_name,
#                                         )
#                                         with codecs.open(
#                                             out_JSON_file,
#                                             "w",
#                                             "utf-8",
#                                         ) as out_file:
#                                             data = json.dumps(
#                                                 response,
#                                                 ensure_ascii=False,
#                                             )
#                                             out_file.write(data)
#
#                                         output_msg(
#                                             f"Nabbed some json data fer ye: '{out_JSON_name}', oids {start_oid} to {end_oid}",
#                                         )
#
#                                         if output_type == "Folder":
#                                             out_file_name = (
#                                                 service_name_cl
#                                                 + str(current_iter)
#                                                 + ".shp"
#                                             )
#                                         else:
#                                             out_file_name = service_name_cl + str(
#                                                 current_iter,
#                                             )
#                                         out_geofile = os.path.join(
#                                             output_workspace,
#                                             out_file_name,
#                                         )
#
#                                         output_msg(
#                                             f"Converting yer json to {out_geofile}",
#                                         )
#                                         # may not be needed if using a featureSet()
#                                         arcpy.JSONToFeatures_conversion(
#                                             out_JSON_file,
#                                             out_geofile,
#                                         )
#                                         ##arcpy.JSONToFeatures_conversion(fs, out_geofile)
#                                         downloaded_fc_list.append(out_geofile)
#                                         os.remove(
#                                             out_JSON_file,
#                                         )  # clean up the JSON file
#
#                                     current_iter += 1
#                         else:
#                             raise ValueError(
#                                 "Aaar, plunderin' failed, feature OIDs is None",
#                             )
#
#                         # download complete, create a final output
#                         if output_type == "Folder":
#                             final_fc = os.path.join(
#                                 output_workspace,
#                                 service_name_cl + ".shp",
#                             )
#                         else:
#                             final_fc = os.path.join(output_workspace, service_name_cl)
#
#                         output_msg(f"Stashin' all the booty in '{final_fc}'")
#
#                         # combine all the data
#                         combine_data(fc_list=downloaded_fc_list, output_fc=final_fc)
#
#                         # create_layer_file(service_info=service_info, service_name=service_name_cl, layer_source=final_fc, output_folder=output_folder)
#
#                         elapsed_time = datetime.datetime.today() - start_time
#                         output_msg(
#                             f"{final_fc} plundered in {str(elapsed_time)}",
#                         )
#
#                     except ValueError as e:
#                         output_msg(str(e), severity=2)
#
#                     except Exception:
#                         line, err = trace()
#                         output_msg(
#                             f"Script Error\n{err}\n on {line}",
#                             severity=2,
#                         )
#                         output_msg(arcpy.GetMessages())
#
#                     finally:
#                         if arcpy.Exists(final_fc):
#                             data_count = int(arcpy.GetCount_management(final_fc)[0])
#                             if data_count == OID_count:  # we got it all
#                                 output_msg("Scrubbing the decks...")
#                                 for fc in downloaded_fc_list:
#                                     arcpy.Delete_management(fc)
#                             else:
#                                 output_msg(
#                                     f"Splicin' the data failed - found {data_count} but expected {OID_count}. Check {final_fc} to see what went wrong.",
#                                 )
#                 else:
#                     # no JSON output
#                     output_msg(
#                         "Aaaar, ye service does not support JSON output. Can't do it.",
#                     )
#             else:
#                 # service info error
#                 e = service_info.get("error")
#                 output_msg(f"Error: {e}", severity=2)
#
#     except ValueError as e:
#         output_msg("ERROR: " + str(e), severity=2)
#
#     except Exception as e:
#         if hasattr(e, "errno") and e.errno == 10054:
#             output_msg("ERROR: " + str(e), severity=2)
#         else:
#             line, err = trace()
#             output_msg(f"Error\n{err}\n on {line}", severity=2)
#         output_msg(arcpy.GetMessages())
#
#     finally:
#         elapsed_time = datetime.datetime.today() - start_time
#         output_msg("Plunderin' done, in " + str(elapsed_time))
#
#
# # if __name__ == "__main__":
# #     # arcgis toolbox parameters
# #     service_endpoint = arcpy.GetParameterAsText(
# #         0,
# #     )  # String - URL of Service endpoint required
# #     output_workspace = arcpy.GetParameterAsText(
# #         1,
# #     )  # String - gdb/folder to put the results required
# #     max_tries = arcpy.GetParameter(
# #         2,
# #     )  # Int - max number of retries allowed required
# #     sleep_time = arcpy.GetParameter(
# #         3,
# #     )  # Int - max number of retries allowed required`
# #     strict_mode = arcpy.GetParameter(4)  # Bool - JSON check True/False required
# #     username = arcpy.GetParameterAsText(5)  # String - username optional
# #     password = arcpy.GetParameterAsText(6)  # String - password optional
# #     referring_domain = arcpy.GetParameterAsText(7)  # String - url of auth domain
# #     existing_token = arcpy.GetParameterAsText(8)  # String - valid token value
# #     query_str = arcpy.GetParameterAsText(9)  # String - valid SQL query string
# #
# #     session = requests.Session()
# #
# #     main(
# #         service_endpoint=service_endpoint,
# #         output_workspace=output_workspace,
# #         max_tries=max_tries,
# #         sleep_time=sleep_time,
# #         strict_mode=strict_mode,
# #         username=username,
# #         password=password,
# #         referring_domain=referring_domain,
# #         existing_token=existing_token,
# #         query_str=query_str,
# #         session=session,
# #     )
