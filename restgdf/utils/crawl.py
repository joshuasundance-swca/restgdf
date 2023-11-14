import asyncio
from typing import Optional

import aiohttp

from restgdf.utils.getinfo import service_metadata, get_metadata


async def fetch_all_data(
    session: aiohttp.ClientSession,
    base_url: str,
    token: Optional[str] = None,
    return_feature_count: bool = False,
) -> dict:
    """Fetch all services and their layers in a highly concurrent manner."""
    # Retrieve the initial list of folders and services
    try:
        base_metadata = await get_metadata(base_url, session, token)
    except Exception as e:
        return {"error": e}

    base_metadata["url"] = base_url

    # Prepare list of service information to fetch layers
    services_list = [
        {
            "name": service["name"],
            "url": f"{base_url}/{service['name']}/{service['type']}",
        }
        for service in base_metadata.get("services") or []
    ]

    # Add nested folders' service information
    for folder in base_metadata.get("folders") or []:
        folder_url = f"{base_url}/{folder}"
        try:
            folder_metadata = await get_metadata(folder_url, session, token)
        except Exception as e:
            return {"error": e}
        folder_metadata["url"] = folder_url

        services_list.extend(
            [
                {
                    "name": service["name"],
                    "url": f"{base_url}/{service['name']}/{service['type']}",
                }
                for service in folder_metadata.get("services") or []
            ],
        )

    async def _service_metadata(*args, **kwargs):
        try:
            return await service_metadata(*args, **kwargs)
        except Exception as e:
            return {"error": e}

    # Fetch all layers concurrently
    service_metadata_tasks = [
        _service_metadata(
            session,
            service["url"],
            token,
            return_feature_count=return_feature_count,
        )
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
