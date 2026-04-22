"""Red tests for BL-01 — bounded_gather + ``Settings.max_concurrent_requests``.

These tests pin the new concurrency cap surface before the green commit
materializes ``restgdf.utils._concurrency`` and the Settings field.
"""

from __future__ import annotations

import asyncio

import pytest

from restgdf._models._settings import Settings, reset_settings_cache


@pytest.mark.asyncio
async def test_bounded_gather_respects_semaphore():
    """``bounded_gather`` must never allow more coroutines into their body
    than the semaphore permits."""
    from restgdf.utils._concurrency import bounded_gather

    sem = asyncio.BoundedSemaphore(3)
    inflight = 0
    peak = 0
    release = asyncio.Event()

    async def work(idx: int) -> int:
        nonlocal inflight, peak
        inflight += 1
        peak = max(peak, inflight)
        # Hold the slot briefly so others must queue.
        await asyncio.sleep(0)
        inflight -= 1
        return idx

    # Pre-fill a tiny yield so the scheduler interleaves tasks.
    release.set()

    coros = [work(i) for i in range(10)]
    results = await bounded_gather(*coros, semaphore=sem)

    assert results == list(range(10))
    assert peak <= 3, f"peak concurrency {peak} exceeded semaphore cap 3"


@pytest.mark.asyncio
async def test_bounded_gather_preserves_order_and_return_exceptions():
    """When ``return_exceptions=True`` the output order must match the
    input order even if some coroutines raise."""
    from restgdf.utils._concurrency import bounded_gather

    sem = asyncio.BoundedSemaphore(2)

    async def ok(value: int) -> int:
        await asyncio.sleep(0)
        return value

    async def boom(value: int) -> int:
        await asyncio.sleep(0)
        raise RuntimeError(f"boom-{value}")

    coros = [ok(0), boom(1), ok(2), boom(3), ok(4)]
    results = await bounded_gather(*coros, semaphore=sem, return_exceptions=True)

    assert results[0] == 0
    assert isinstance(results[1], RuntimeError) and "boom-1" in str(results[1])
    assert results[2] == 2
    assert isinstance(results[3], RuntimeError) and "boom-3" in str(results[3])
    assert results[4] == 4


@pytest.mark.asyncio
async def test_bounded_gather_cancellation_releases_slots():
    """Cancelling the outer task must cancel pending children and leave
    no dangling semaphore acquisitions."""
    from restgdf.utils._concurrency import bounded_gather

    sem = asyncio.BoundedSemaphore(2)
    started = asyncio.Event()

    async def slow() -> None:
        started.set()
        await asyncio.sleep(10)

    outer = asyncio.create_task(bounded_gather(*(slow() for _ in range(5)), semaphore=sem))
    await started.wait()
    outer.cancel()
    with pytest.raises(asyncio.CancelledError):
        await outer

    # All slots must be free afterwards — we should be able to acquire
    # ``sem._value`` times without blocking.
    for _ in range(2):
        await asyncio.wait_for(sem.acquire(), timeout=0.5)
    for _ in range(2):
        sem.release()


def test_settings_exposes_max_concurrent_requests_default_8():
    """The new Settings field materializes with the locked default of 8
    (R-44 + R-46)."""
    settings = Settings()
    assert settings.max_concurrent_requests == 8


def test_settings_max_concurrent_requests_env_override(monkeypatch):
    """``RESTGDF_MAX_CONCURRENT_REQUESTS`` coerces to int ≥ 1."""
    monkeypatch.setenv("RESTGDF_MAX_CONCURRENT_REQUESTS", "4")
    reset_settings_cache()
    try:
        settings = Settings.from_env()
        assert settings.max_concurrent_requests == 4
    finally:
        reset_settings_cache()


def test_settings_max_concurrent_requests_rejects_zero():
    """``ge=1`` must reject 0 and negative values."""
    with pytest.raises(Exception):
        Settings(max_concurrent_requests=0)
    with pytest.raises(Exception):
        Settings(max_concurrent_requests=-1)


@pytest.mark.asyncio
async def test_bounded_semaphore_caps_concurrency_at_fanout_sites(monkeypatch):
    """Per kickoff §10.3 red test: schedule N mock tasks through one of
    the three enumerated gather sites and assert the in-flight counter
    never exceeds ``max_concurrent_requests``."""
    from restgdf.utils import _concurrency

    inflight = 0
    peak = 0
    original_bounded_gather = _concurrency.bounded_gather

    async def counting_bounded_gather(*aws, semaphore, **kwargs):
        nonlocal inflight, peak

        async def _count(aw):
            nonlocal inflight, peak
            async with semaphore:
                inflight += 1
                peak = max(peak, inflight)
                try:
                    return await aw
                finally:
                    inflight -= 1

        wrapped = [_count(aw) for aw in aws]
        # Bypass the outer semaphore in the real helper to avoid double
        # counting — the inner counter already enforces the cap.
        unbounded_sem = asyncio.BoundedSemaphore(10_000)
        return await original_bounded_gather(
            *wrapped, semaphore=unbounded_sem, **kwargs
        )

    monkeypatch.setattr(_concurrency, "bounded_gather", counting_bounded_gather)
    # Also patch the re-export at the call sites.
    import restgdf.utils.getinfo as getinfo_mod
    import restgdf.utils.crawl as crawl_mod

    monkeypatch.setattr(getinfo_mod, "bounded_gather", counting_bounded_gather, raising=False)
    monkeypatch.setattr(crawl_mod, "bounded_gather", counting_bounded_gather, raising=False)

    monkeypatch.setenv("RESTGDF_MAX_CONCURRENT_REQUESTS", "4")
    reset_settings_cache()
    try:
        from restgdf.utils.getinfo import service_metadata

        N = 20
        layers = [{"id": i} for i in range(N)]

        async def fake_get_metadata(url, session, token=None):
            if "FeatureServer" in url and url.count("/") > 6:
                # Leaf layer call.
                await asyncio.sleep(0)
                return {"type": "Table"}
            # Top-level service call returns N layers.
            return {"layers": layers}

        monkeypatch.setattr(getinfo_mod, "get_metadata", fake_get_metadata)

        await service_metadata(
            session=object(),
            service_url="https://example.com/ArcGIS/rest/services/Demo/FeatureServer",
        )
        assert peak <= 4, f"peak concurrency {peak} exceeded cap 4"
        assert peak > 0, "fan-out site never exercised"
    finally:
        reset_settings_cache()
