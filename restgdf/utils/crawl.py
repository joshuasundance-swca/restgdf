import asyncio
from typing import Optional

import aiohttp

from restgdf.utils.getinfo import service_metadata


async def fetch_all_data(
    session: aiohttp.ClientSession,
    base_url: str,
    token: Optional[str] = None,
) -> dict:
    """Fetch all services and their layers in a highly concurrent manner."""
    # Retrieve the initial list of folders and services
    params = {"f": "json"}
    if token:
        params["token"] = token

    async with session.get(base_url, params=params) as base_resp:
        base_metadata = await base_resp.json()

    # Prepare list of URLs to fetch layers from each service
    accumulated_services = {
        service["name"]: f"{base_url}/{service['name']}/{service['type']}"
        for service in base_metadata.get("services", [])
    }

    # Add nested folders' service URLs
    for folder in base_metadata.get("folders", []):
        async with session.get(f"{base_url}/{folder}", params=params) as folder_resp:
            folder_metadata = await folder_resp.json()

        accumulated_services.update(
            {
                service[
                    "name"
                ]: f"{base_url}/{folder}/{service['name']}/{service['type']}"
                for service in folder_metadata.get("services", [])
            },
        )

    # Fetch all layers concurrently
    service_metadata_tasks = [
        service_metadata(session, url, token)
        for name, url in accumulated_services.items()
    ]
    service_metadata_results = await asyncio.gather(*service_metadata_tasks)
    # Combine service_metadata_results into a single dictionary
    service_data = {
        _service_name: _service_metadata
        for _service_name, _service_metadata in zip(
            accumulated_services.keys(),
            service_metadata_results,
        )
    }
    return {
        "metadata": base_metadata,
        "services": service_data,
    }
