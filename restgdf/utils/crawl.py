import asyncio
from typing import Optional

import aiohttp

from restgdf.utils.getinfo import service_metadata, get_metadata


async def fetch_all_data(
    session: aiohttp.ClientSession,
    base_url: str,
    token: Optional[str] = None,
) -> dict:
    """Fetch all services and their layers in a highly concurrent manner."""
    # Retrieve the initial list of folders and services
    base_metadata = await get_metadata(base_url, session, token)

    # Prepare list of service information to fetch layers
    services_list = [
        {
            "name": service["name"],
            "url": f"{base_url}/{service['name']}/{service['type']}",
        }
        for service in base_metadata.get("services", [])
    ]

    # Add nested folders' service information
    for folder in base_metadata.get("folders", []):
        folder_metadata = await get_metadata(f"{base_url}/{folder}", session, token)

        services_list.extend(
            [
                {
                    "name": service["name"],
                    "url": f"{base_url}/{service['name']}/{service['type']}",
                }
                for service in folder_metadata.get("services", [])
            ],
        )

    # Fetch all layers concurrently
    service_metadata_tasks = [
        service_metadata(session, service["url"], token, return_feature_count=False)
        for service in services_list
    ]
    service_metadata_results = await asyncio.gather(*service_metadata_tasks)

    # Combine service_metadata_results with service names
    for i, service_data in enumerate(service_metadata_results):
        services_list[i]["metadata"] = service_data

    return {
        "metadata": base_metadata,
        "services": services_list,
    }
