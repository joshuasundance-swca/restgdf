"""Red tests for BL-01 nested fan-out — shared semaphore across orchestrators.

These tests pin the ``_sem`` threading contract before the fix: a single
``BoundedSemaphore`` must be created once at the top-level orchestration call
(``fetch_all_data`` / ``safe_crawl``) and reused by every nested
``service_metadata`` fan-out so the cap is truly global per request.

Without threading the semaphore, each ``service_metadata`` invocation would
build its own local ``BoundedSemaphore`` and the effective cap would become
multiplicative (outer_cap * inner_cap) instead of a single shared ``cap``.
"""

from __future__ import annotations

import asyncio

import pytest

from restgdf._models._settings import reset_settings_cache


def _install_counting_metadata_fakes(monkeypatch):
    """Patch ``get_metadata`` / ``get_feature_count`` in both namespaces so we
    can observe real-world in-flight concurrency across the nested fan-out.

    Returns a ``lambda: peak`` observer closure.
    """
    inflight = 0
    peak = 0
    lock = asyncio.Lock()

    async def _enter() -> None:
        nonlocal inflight, peak
        async with lock:
            inflight += 1
            if inflight > peak:
                peak = inflight

    async def _exit() -> None:
        nonlocal inflight
        async with lock:
            inflight -= 1

    async def fake_get_metadata(url, session, token=None):
        await _enter()
        try:
            # Yield so peers can advance and reveal true overlap.
            await asyncio.sleep(0.005)
            # Leaf layer call: ends in a digit after FeatureServer/MapServer.
            last = url.rsplit("/", 1)[-1]
            if last.isdigit():
                return {"type": "Table", "id": int(last)}
            if url.endswith(("FeatureServer", "MapServer")):
                return {"layers": [{"id": 0}, {"id": 1}, {"id": 2}]}
            # Base URL: three services, no folders.
            return {
                "services": [
                    {"name": f"Svc{i}", "type": "FeatureServer"} for i in range(3)
                ],
                "folders": [],
            }
        finally:
            await _exit()

    async def fake_get_feature_count(url, session, **kwargs):
        await _enter()
        try:
            await asyncio.sleep(0.005)
            return 0
        finally:
            await _exit()

    import restgdf.utils.getinfo as getinfo_mod
    import restgdf.utils.crawl as crawl_mod

    monkeypatch.setattr(getinfo_mod, "get_metadata", fake_get_metadata)
    monkeypatch.setattr(crawl_mod, "get_metadata", fake_get_metadata)
    monkeypatch.setattr(getinfo_mod, "get_feature_count", fake_get_feature_count)

    return lambda: peak


@pytest.mark.asyncio
async def test_fetch_all_data_shares_semaphore_across_nested_fanout(monkeypatch):
    """``fetch_all_data`` must share ONE ``BoundedSemaphore`` with every
    nested ``service_metadata`` call. With cap=2 and 3 services × 3 layers
    each, the observed peak must be ≤ 2 — not ≤ 4 (2*2) as the pre-fix
    nested-unshared semaphore would allow."""
    monkeypatch.setenv("RESTGDF_CONCURRENCY_MAX_CONCURRENT_REQUESTS", "2")
    reset_settings_cache()
    try:
        peak_of = _install_counting_metadata_fakes(monkeypatch)

        from restgdf.utils.crawl import fetch_all_data

        result = await fetch_all_data(
            session=object(),
            base_url="https://example.com/ArcGIS/rest/services",
            return_feature_count=False,
        )

        assert "error" not in result, result
        peak = peak_of()
        assert peak > 0, "nested fan-out never observed in-flight calls"
        assert peak <= 2, (
            f"peak concurrency {peak} exceeded shared cap 2 — nested "
            f"semaphores not shared across fetch_all_data → service_metadata"
        )
    finally:
        reset_settings_cache()


@pytest.mark.asyncio
async def test_safe_crawl_shares_semaphore_across_nested_fanout(monkeypatch):
    """``safe_crawl`` must share ONE ``BoundedSemaphore`` with every nested
    ``service_metadata`` call (same contract as ``fetch_all_data``)."""
    monkeypatch.setenv("RESTGDF_CONCURRENCY_MAX_CONCURRENT_REQUESTS", "2")
    reset_settings_cache()
    try:
        peak_of = _install_counting_metadata_fakes(monkeypatch)

        from restgdf.utils.crawl import safe_crawl

        report = await safe_crawl(
            session=object(),
            base_url="https://example.com/ArcGIS/rest/services",
            return_feature_count=False,
        )

        assert report.errors == [], report.errors
        peak = peak_of()
        assert peak > 0, "nested fan-out never observed in-flight calls"
        assert peak <= 2, (
            f"peak concurrency {peak} exceeded shared cap 2 — nested "
            f"semaphores not shared across safe_crawl → service_metadata"
        )
    finally:
        reset_settings_cache()
