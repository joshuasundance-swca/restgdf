"""Red tests for BL-52 service-root token-bucket registry (commit 3)."""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from restgdf._config import ResilienceConfig


class TestServiceRootDerivation:
    """_service_root() parsing."""

    def test_feature_server_url(self) -> None:
        from restgdf.resilience._limiter import _service_root

        url = "https://example.com/arcgis/rest/services/MyMap/FeatureServer/0/query"
        assert _service_root(url) == "https://example.com/arcgis/rest/services/MyMap/FeatureServer"

    def test_map_server_url(self) -> None:
        from restgdf.resilience._limiter import _service_root

        url = "https://example.com/arcgis/rest/services/MyMap/MapServer/0/query"
        assert _service_root(url) == "https://example.com/arcgis/rest/services/MyMap/MapServer"

    def test_no_server_suffix_returns_host(self) -> None:
        from restgdf.resilience._limiter import _service_root

        url = "https://example.com/some/other/api/endpoint"
        result = _service_root(url)
        assert result == "https://example.com"


class TestLimiterRegistry:
    """Per-session limiter registry."""

    def test_get_limiter_returns_same_for_same_service_root(self) -> None:
        from restgdf.resilience._limiter import LimiterRegistry

        registry = LimiterRegistry(rate_per_second=5.0)
        a = registry.get("https://example.com/arcgis/rest/services/MyMap/FeatureServer")
        b = registry.get("https://example.com/arcgis/rest/services/MyMap/FeatureServer")
        assert a is b

    def test_get_limiter_different_for_different_service_roots(self) -> None:
        from restgdf.resilience._limiter import LimiterRegistry

        registry = LimiterRegistry(rate_per_second=5.0)
        a = registry.get("https://example.com/arcgis/rest/services/A/FeatureServer")
        b = registry.get("https://example.com/arcgis/rest/services/B/FeatureServer")
        assert a is not b

    def test_reset_clears_all(self) -> None:
        from restgdf.resilience._limiter import LimiterRegistry

        registry = LimiterRegistry(rate_per_second=5.0)
        registry.get("https://example.com/arcgis/rest/services/MyMap/FeatureServer")
        registry.reset()
        assert len(registry._limiters) == 0


class TestCooldownRegistry:
    """Per-session 429 cooldown registry (separate from AsyncLimiter tokens)."""

    @pytest.mark.asyncio
    async def test_cooldown_blocks_until_deadline(self) -> None:
        from restgdf.resilience._limiter import CooldownRegistry

        registry = CooldownRegistry()
        key = "https://example.com/arcgis/rest/services/MyMap/FeatureServer"
        registry.set_cooldown(key, 0.05)  # 50ms
        t0 = time.monotonic()
        await registry.wait_if_cooling(key)
        elapsed = time.monotonic() - t0
        assert elapsed >= 0.04  # tolerate timer jitter

    @pytest.mark.asyncio
    async def test_no_cooldown_returns_immediately(self) -> None:
        from restgdf.resilience._limiter import CooldownRegistry

        registry = CooldownRegistry()
        key = "https://example.com/arcgis/rest/services/X/FeatureServer"
        t0 = time.monotonic()
        await registry.wait_if_cooling(key)
        elapsed = time.monotonic() - t0
        assert elapsed < 0.01

    @pytest.mark.asyncio
    async def test_cooldown_expires_naturally(self) -> None:
        from restgdf.resilience._limiter import CooldownRegistry

        registry = CooldownRegistry()
        key = "https://example.com/arcgis/rest/services/MyMap/FeatureServer"
        registry.set_cooldown(key, 0.01)  # 10ms
        await asyncio.sleep(0.02)
        t0 = time.monotonic()
        await registry.wait_if_cooling(key)
        elapsed = time.monotonic() - t0
        assert elapsed < 0.01  # already expired
