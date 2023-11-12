import asyncio
import re
from collections.abc import Iterable
from typing import Any, Optional

import aiohttp

ends_with_num_pat = re.compile(r"\d+$")


def ends_with_num(url: str) -> bool:
    """Return True if the given URL ends with a number."""
    return bool(ends_with_num_pat.search(url))


def where_var_in_list(var: str, vals: Iterable[str]) -> str:
    """Return a where clause for a variable in a list of values."""
    vals_str = ", ".join(f"'{val}'" for val in vals)
    return f"{var} In ({vals_str})"


async def get_services_and_folders(
    session: aiohttp.ClientSession,
    url: str,
    token: Optional[str] = None,
) -> tuple[list[str], list[dict]]:
    """Asynchronously retrieve services and folders from the given ArcGIS server URL."""
    params = {"f": "json"}
    if token:
        params["token"] = token
    async with session.get(url, params=params) as resp:
        resp_dict = await resp.json()
        folders = resp_dict.get("folders", [])
        services = resp_dict.get("services", [])
        return folders, services


async def get_layers_for_service(
    session: aiohttp.ClientSession,
    service_url: str,
    token: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Asynchronously retrieve layers for a single service."""
    params = {"f": "json"}
    if token:
        params["token"] = token
    async with session.get(service_url, params=params) as response:
        service_data = await response.json()
        return [
            layer | {"url": f"{service_url}/{layer['id']}"}
            for layer in service_data.get("layers", [])
        ]


async def fetch_all_data(
    session: aiohttp.ClientSession,
    base_url: str,
    token: Optional[str] = None,
) -> dict[str, list[dict[str, Any]]]:
    """Fetch all services and their layers in a highly concurrent manner."""
    # Retrieve the initial list of folders and services
    folders, services = await get_services_and_folders(session, base_url, token)
    # Prepare list of URLs to fetch layers from each service
    accumulated_services = {
        service["name"]: f"{base_url}/{service['name']}/{service['type']}"
        for service in services
    }
    # Add nested folders' service URLs
    for folder in folders:
        nested_folders, nested_services = await get_services_and_folders(
            session,
            f"{base_url}/{folder}",
            token,
        )
        accumulated_services.update(
            {
                service[
                    "name"
                ]: f"{base_url}/{folder}/{service['name']}/{service['type']}"
                for service in nested_services
            },
        )
    # Fetch all layers concurrently
    layer_tasks = [
        get_layers_for_service(session, url, token)
        for name, url in accumulated_services.items()
    ]
    results = await asyncio.gather(*layer_tasks)
    # Combine results into a single dictionary
    return {name: layer for name, layer in zip(accumulated_services.keys(), results)}
