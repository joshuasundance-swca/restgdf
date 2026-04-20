from __future__ import annotations

import asyncio
from typing import Any

import aiohttp
from pydantic import BaseModel

from restgdf._models.crawl import CrawlError, CrawlReport, CrawlServiceEntry
from restgdf._models.responses import LayerMetadata
from restgdf.utils.getinfo import service_metadata, get_metadata
from restgdf.utils.token import ArcGISTokenSession


def _to_plain_dict(value: Any) -> dict:
    """Normalize a pydantic model or mapping to a mutable ``dict``."""
    if isinstance(value, BaseModel):
        return value.model_dump(by_alias=True)
    return dict(value)


async def fetch_all_data(
    session: aiohttp.ClientSession | ArcGISTokenSession,
    base_url: str,
    token: str | None = None,
    return_feature_count: bool = False,
) -> dict:
    """Fetch all services and their layers in a highly concurrent manner."""
    # Retrieve the initial list of folders and services
    try:
        base_metadata = _to_plain_dict(await get_metadata(base_url, session, token))
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
            folder_metadata = _to_plain_dict(
                await get_metadata(folder_url, session, token),
            )
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
    return CrawlError(stage=stage, url=url, message=str(exc), exception=exc)


def _as_layer_metadata(raw: Any) -> LayerMetadata:
    if isinstance(raw, LayerMetadata):
        return raw
    return LayerMetadata.model_validate(raw)


async def safe_crawl(
    session: aiohttp.ClientSession | ArcGISTokenSession,
    base_url: str,
    token: str | None = None,
    return_feature_count: bool = False,
) -> CrawlReport:
    """Crawl an ArcGIS REST directory and aggregate results + errors.

    Unlike :func:`fetch_all_data`, this function never short-circuits on
    the first failure. Every recoverable error is captured as a typed
    :class:`~restgdf._models.crawl.CrawlError` entry in
    :attr:`CrawlReport.errors` and successful services are always
    present in :attr:`CrawlReport.services`.

    The three failure stages are ``"base_metadata"`` (root
    ``get_metadata`` call), ``"folder_metadata"`` (per-folder
    ``get_metadata`` call), and ``"service_metadata"`` (per-service
    ``service_metadata`` call). When a folder's metadata fails, services
    discovered in earlier folders (and the base) are still returned.
    """
    errors: list[CrawlError] = []
    services_raw: list[dict[str, Any]] = []

    try:
        base_metadata: dict[str, Any] = _to_plain_dict(
            await get_metadata(base_url, session, token),
        )
    except Exception as exc:
        errors.append(_make_error("base_metadata", base_url, exc))
        return CrawlReport(services=[], errors=errors, metadata=None)

    base_metadata["url"] = base_url

    for service in base_metadata.get("services") or []:
        services_raw.append(
            {
                "name": service["name"],
                "type": service.get("type"),
                "url": f"{base_url}/{service['name']}/{service['type']}",
            },
        )

    for folder in base_metadata.get("folders") or []:
        folder_url = f"{base_url}/{folder}"
        try:
            folder_metadata = _to_plain_dict(
                await get_metadata(folder_url, session, token),
            )
        except Exception as exc:
            errors.append(_make_error("folder_metadata", folder_url, exc))
            continue

        folder_metadata["url"] = folder_url
        for service in folder_metadata.get("services") or []:
            services_raw.append(
                {
                    "name": service["name"],
                    "type": service.get("type"),
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

    results = await asyncio.gather(*(_svc(svc["url"]) for svc in services_raw))
    service_entries: list[CrawlServiceEntry] = []
    for entry, result in zip(services_raw, results):
        service_entries.append(
            CrawlServiceEntry(
                name=entry["name"],
                url=entry["url"],
                type=entry.get("type"),
                metadata=_as_layer_metadata(result) if result is not None else None,
            ),
        )

    return CrawlReport(
        services=service_entries,
        errors=errors,
        metadata=_as_layer_metadata(base_metadata),
    )
