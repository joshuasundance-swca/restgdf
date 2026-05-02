"""Q-A7 red-first pin: safe_crawl feature_count is semaphore-bound.

When ``return_feature_count=True``, the per-service ``get_feature_count``
HTTP call must run inside the shared ``BoundedSemaphore`` created by
``safe_crawl``.  This test stubs a 20-layer directory and asserts the
observed high-water mark of in-flight calls never exceeds
``max_concurrent_requests``.
"""

from __future__ import annotations

import asyncio

import pytest

from restgdf._models._settings import reset_settings_cache


def _install_counting_fakes(monkeypatch, *, layer_count: int = 20):
    """Patch ``get_metadata`` and ``get_feature_count`` with in-flight probes.

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
            await asyncio.sleep(0.005)
            last = url.rsplit("/", 1)[-1]
            if last.isdigit():
                return {"type": "Feature Layer", "id": int(last)}
            if url.endswith(("FeatureServer", "MapServer")):
                return {
                    "layers": [{"id": i} for i in range(layer_count)],
                }
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
            await asyncio.sleep(0.01)  # longer sleep to amplify overlap
            return 42
        finally:
            await _exit()

    import restgdf.utils.getinfo as getinfo_mod
    import restgdf.utils.crawl as crawl_mod

    monkeypatch.setattr(getinfo_mod, "get_metadata", fake_get_metadata)
    monkeypatch.setattr(crawl_mod, "get_metadata", fake_get_metadata)
    monkeypatch.setattr(getinfo_mod, "get_feature_count", fake_get_feature_count)

    return lambda: peak


@pytest.mark.asyncio
async def test_feature_count_fanout_bounded_by_max_concurrent_requests(monkeypatch):
    """With ``return_feature_count=True``, the per-service
    ``get_feature_count`` calls must not exceed the shared semaphore cap.

    3 services × 20 layers = 60 ``get_feature_count`` calls. With
    ``max_concurrent_requests=4``, observed peak must be ≤ 4.
    """
    monkeypatch.setenv("RESTGDF_CONCURRENCY_MAX_CONCURRENT_REQUESTS", "4")
    reset_settings_cache()
    try:
        peak_of = _install_counting_fakes(monkeypatch, layer_count=20)

        from restgdf.utils.crawl import safe_crawl

        report = await safe_crawl(
            session=object(),
            base_url="https://example.com/ArcGIS/rest/services",
            return_feature_count=True,
        )

        assert report.errors == [], report.errors
        peak = peak_of()
        assert peak > 0, "fan-out never observed any in-flight calls"
        assert peak <= 4, (
            f"peak concurrency {peak} exceeded shared cap 4 — "
            f"feature_count calls are escaping the semaphore"
        )
    finally:
        reset_settings_cache()
