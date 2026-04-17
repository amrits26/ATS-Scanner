"""
Tests for the Redis analysis cache service.

Covers:
  - Cache key generation (deterministic SHA256)
  - Cache hit / miss behavior
  - TTL enforcement
  - Graceful degradation when Redis is unavailable

Run with:
    pytest backend/tests/test_analysis_cache.py -v
"""

import json
from unittest.mock import AsyncMock, patch

import pytest

from backend.services.analysis_cache import AnalysisCache


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_RESUME = "Senior Software Engineer. Python, AWS, Docker, 5 years experience."
SAMPLE_JD = "Looking for a Senior Backend Engineer with Python and AWS."
SAMPLE_RESULT = {
    "ats_score": {"final_ats_score": 82.3, "missing_keywords": ["Terraform"]},
    "keyword_heatmap": {"keywords": ["Python", "AWS"], "frequencies": [5, 3]},
    "optimized_resume": "Optimized resume text here...",
}


@pytest.fixture
def cache():
    """Create a fresh AnalysisCache instance (not connected)."""
    return AnalysisCache(redis_url="redis://localhost:6379/0")


# ---------------------------------------------------------------------------
# Key Generation
# ---------------------------------------------------------------------------

class TestKeyGeneration:
    """Cache keys must be deterministic and content-based."""

    def test_same_input_same_key(self, cache):
        key1 = cache._make_key(SAMPLE_RESUME, SAMPLE_JD)
        key2 = cache._make_key(SAMPLE_RESUME, SAMPLE_JD)
        assert key1 == key2

    def test_different_input_different_key(self, cache):
        key1 = cache._make_key(SAMPLE_RESUME, SAMPLE_JD)
        key2 = cache._make_key(SAMPLE_RESUME, "Different JD text")
        assert key1 != key2

    def test_key_has_correct_prefix(self, cache):
        key = cache._make_key(SAMPLE_RESUME, SAMPLE_JD)
        assert key.startswith("cache:analysis:")

    def test_key_length_is_consistent(self, cache):
        """SHA256 hex = 64 chars + prefix."""
        key = cache._make_key(SAMPLE_RESUME, SAMPLE_JD)
        prefix = "cache:analysis:"
        assert len(key) == len(prefix) + 64


# ---------------------------------------------------------------------------
# Cache Hit / Miss
# ---------------------------------------------------------------------------

class TestCacheOperations:
    """Verify get/set with mocked Redis client."""

    @pytest.mark.asyncio
    async def test_get_returns_none_when_not_connected(self, cache):
        """If Redis is down, get() returns None (graceful degradation)."""
        # _client is None by default (no connect called)
        result = await cache.get(SAMPLE_RESUME, SAMPLE_JD)
        assert result is None

    @pytest.mark.asyncio
    async def test_set_is_noop_when_not_connected(self, cache):
        """If Redis is down, set() silently returns (no crash)."""
        # Should not raise
        await cache.set(SAMPLE_RESUME, SAMPLE_JD, SAMPLE_RESULT)

    @pytest.mark.asyncio
    async def test_cache_hit_returns_stored_data(self, cache):
        """After set(), get() with same inputs returns the stored dict."""
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=json.dumps(SAMPLE_RESULT))
        cache._client = mock_redis

        result = await cache.get(SAMPLE_RESUME, SAMPLE_JD)

        assert result is not None
        assert result["ats_score"]["final_ats_score"] == 82.3
        assert "Python" in result["keyword_heatmap"]["keywords"]

    @pytest.mark.asyncio
    async def test_cache_miss_returns_none(self, cache):
        """get() on a key that doesn't exist returns None."""
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)
        cache._client = mock_redis

        result = await cache.get(SAMPLE_RESUME, SAMPLE_JD)
        assert result is None

    @pytest.mark.asyncio
    async def test_set_calls_redis_setex_with_ttl(self, cache):
        """set() stores data with the correct TTL (604800s = 7 days)."""
        mock_redis = AsyncMock()
        mock_redis.setex = AsyncMock()
        cache._client = mock_redis

        await cache.set(SAMPLE_RESUME, SAMPLE_JD, SAMPLE_RESULT, ttl=604800)

        mock_redis.setex.assert_awaited_once()
        call_args = mock_redis.setex.call_args
        assert call_args[0][1] == 604800  # TTL
        stored_data = json.loads(call_args[0][2])
        assert stored_data["ats_score"]["final_ats_score"] == 82.3

    @pytest.mark.asyncio
    async def test_set_with_custom_ttl(self, cache):
        """set() respects custom TTL values."""
        mock_redis = AsyncMock()
        mock_redis.setex = AsyncMock()
        cache._client = mock_redis

        await cache.set(SAMPLE_RESUME, SAMPLE_JD, SAMPLE_RESULT, ttl=3600)

        call_args = mock_redis.setex.call_args
        assert call_args[0][1] == 3600  # 1 hour


# ---------------------------------------------------------------------------
# Graceful Degradation
# ---------------------------------------------------------------------------

class TestGracefulDegradation:
    """Redis errors must not crash the application."""

    @pytest.mark.asyncio
    async def test_get_handles_redis_error(self, cache):
        """Redis exception during get() → returns None, no crash."""
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(side_effect=ConnectionError("Redis down"))
        cache._client = mock_redis

        result = await cache.get(SAMPLE_RESUME, SAMPLE_JD)
        assert result is None

    @pytest.mark.asyncio
    async def test_set_handles_redis_error(self, cache):
        """Redis exception during set() → silent, no crash."""
        mock_redis = AsyncMock()
        mock_redis.setex = AsyncMock(side_effect=ConnectionError("Redis down"))
        cache._client = mock_redis

        # Should not raise
        await cache.set(SAMPLE_RESUME, SAMPLE_JD, SAMPLE_RESULT)

    @pytest.mark.asyncio
    async def test_invalidate_handles_redis_error(self, cache):
        """Redis exception during invalidate() → silent, no crash."""
        mock_redis = AsyncMock()
        mock_redis.delete = AsyncMock(side_effect=ConnectionError("Redis down"))
        cache._client = mock_redis

        # Should not raise
        await cache.invalidate(SAMPLE_RESUME, SAMPLE_JD)

    @pytest.mark.asyncio
    async def test_connect_handles_redis_down(self, cache):
        """connect() with unreachable Redis → sets _client to None."""
        with patch("backend.services.analysis_cache.Redis") as MockRedis:
            mock_instance = AsyncMock()
            mock_instance.ping = AsyncMock(side_effect=ConnectionError("Connection refused"))
            MockRedis.from_url.return_value = mock_instance

            await cache.connect()

        assert cache._client is None
        assert not cache.is_available


# ---------------------------------------------------------------------------
# Invalidation
# ---------------------------------------------------------------------------

class TestCacheInvalidation:
    """Verify explicit cache invalidation."""

    @pytest.mark.asyncio
    async def test_invalidate_deletes_key(self, cache):
        """invalidate() calls Redis DELETE on the correct key."""
        mock_redis = AsyncMock()
        mock_redis.delete = AsyncMock()
        cache._client = mock_redis

        await cache.invalidate(SAMPLE_RESUME, SAMPLE_JD)

        mock_redis.delete.assert_awaited_once()
        key_arg = mock_redis.delete.call_args[0][0]
        assert key_arg.startswith("cache:analysis:")
