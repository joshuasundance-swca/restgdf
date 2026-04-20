from __future__ import annotations

import asyncio
from typing import Any

import aiohttp

from restgdf._types import CrawlError, CrawlReport, CrawlServiceEntry, LayerMetadata
from restgdf.utils.getinfo import service_metadata, get_metadata
from restgdf.utils.token import ArcGISTokenSession


async def fetch_all_data(
    session: aiohttp.ClientSession | ArcGISTokenSession,
    base_url: str,
    token: str | None = None,
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


def _make_error(stage: str, url: str, exc: BaseException) -> CrawlError:
    return {
        "stage": stage,
        "url": url,
        "message": str(exc),
        "exception": exc,
    }


async def safe_crawl(
    session: aiohttp.ClientSession | ArcGISTokenSession,
    base_url: str,
    token: str | None = None,
    return_feature_count: bool = False,
) -> CrawlReport:
    """Crawl an ArcGIS REST directory and aggregate results + errors.

    Unlike :func:`fetch_all_data`, this function never short-circuits on
    the first failure. Every recoverable error is captured as a typed
    :class:`~restgdf._types.CrawlError` entry in ``report["errors"]`` and
    successful services are always present in ``report["services"]``.

    The three failure stages are ``"base_metadata"`` (root ``get_metadata``
    call), ``"folder_metadata"`` (per-folder ``get_metadata`` call), and
    ``"service_metadata"`` (per-service ``service_metadata`` call). When a
    folder's metadata fails, services discovered in earlier folders (and
    the base) are still returned.
    """
    errors: list[CrawlError] = []
    services_list: list[CrawlServiceEntry] = []

    try:
        base_metadata: LayerMetadata = await get_metadata(base_url, session, token)
    except Exception as exc:
        errors.append(_make_error("base_metadata", base_url, exc))
        return {"services": services_list, "errors": errors}

    base_metadata["url"] = base_url

    for service in base_metadata.get("services") or []:
        services_list.append(
            {
                "name": service["name"],
                "url": f"{base_url}/{service['name']}/{service['type']}",
            },
        )

    for folder in base_metadata.get("folders") or []:
        folder_url = f"{base_url}/{folder}"
        try:
            folder_metadata = await get_metadata(folder_url, session, token)
        except Exception as exc:
            errors.append(_make_error("folder_metadata", folder_url, exc))
            continue

        folder_metadata["url"] = folder_url
        for service in folder_metadata.get("services") or []:
            services_list.append(
                {
                    "name": service["name"],
                    "url": f"{base_url}/{service['name']}/{service['type']}",
                },
            )

    async def _svc(url: str) -> Any:
        try:
            return await service_metadata(
                session,
                url,
                token,
                return_feature_count=return_feature_count,
            )
        except Exception as exc:
            errors.append(_make_error("service_metadata", url, exc))
            return None

    results = await asyncio.gather(*(_svc(svc["url"]) for svc in services_list))
    for entry, result in zip(services_list, results):
        if result is not None:
            entry["metadata"] = result

    return {
        "metadata": base_metadata,
        "services": services_list,
        "errors": errors,
    }
