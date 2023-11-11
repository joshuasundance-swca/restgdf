import asyncio
import re
from collections.abc import Iterable

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
) -> tuple[list[str], list[dict]]:
    """Asynchronously retrieve services and folders from the given ArcGIS server URL."""
    async with session.get(url, params={"f": "json"}) as resp:
        resp_dict = await resp.json()
        folders = resp_dict.get("folders", [])
        services = resp_dict.get("services", [])
        return folders, services


async def get_all_services_and_folders(
    session: aiohttp.ClientSession,
    base_url: str,
    current_folder: str = "",
) -> list[str]:
    """Recursively (asynchronously) find all folders and services starting from the base_url."""
    full_url = f"{base_url}/{current_folder}" if current_folder else base_url
    folders, services = await get_services_and_folders(session, full_url)
    # Store services with their full URLs
    all_services = [
        f"{base_url}/{service['name']}/{service['type']}" for service in services
    ]
    # Tasks for recursively exploring each sub-folder
    tasks = [
        get_all_services_and_folders(session, base_url, folder) for folder in folders
    ]
    subfolder_services = await asyncio.gather(*tasks)
    # Flatten the list of lists
    for sublist in subfolder_services:
        all_services.extend(sublist)
    return all_services
