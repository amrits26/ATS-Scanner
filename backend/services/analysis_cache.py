"""
Redis-backed analysis result cache.

Eliminates redundant Gemini API calls and Matplotlib chart rendering for
identical (resume, JD) pairs.  Reduces repeat-scan response time from ~7 s
to <100 ms and cuts Gemini costs proportionally.

Cache key format:  cache:analysis:{SHA256(resume_text + "|" + jd_text)}
Default TTL:       7 days (604 800 seconds)

Usage:
    from backend.services.analysis_cache import analysis_cache

    # In lifespan startup:
    await analysis_cache.connect()

    # In endpoint:
    cached = await analysis_cache.get(resume_text, jd_text)
    if cached:
        return cached  # instant

    # After heavy processing:
    await analysis_cache.set(resume_text, jd_text, result_dict)
"""

import hashlib
import json
import logging
import os
from typing import Optional

from redis.asyncio import Redis

logger = logging.getLogger(__name__)

# 7 days in seconds
DEFAULT_TTL = 604_800


class AnalysisCache:
    """Async Redis cache for ComprehensiveAnalysisResult dicts."""

    def __init__(self, redis_url: Optional[str] = None):
        self._redis_url = redis_url or os.getenv(
            "REDIS_URL", "redis://127.0.0.1:6379/0"
        )
        self._client: Optional[Redis] = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """Open the Redis connection.  Gracefully degrades if Redis is down."""
        try:
            self._client = Redis.from_url(
                self._redis_url,
                decode_responses=True,
                socket_connect_timeout=3,
            )
            await self._client.ping()
            logger.info("[CACHE] Redis connected (%s)", self._redis_url)
        except Exception as exc:
            logger.warning("[CACHE] Redis unavailable – caching disabled: %s", exc)
            self._client = None

    async def disconnect(self) -> None:
        """Close cleanly on app shutdown."""
        if self._client:
            await self._client.aclose()
            self._client = None
            logger.info("[CACHE] Redis connection closed")

    @property
    def is_available(self) -> bool:
        return self._client is not None

    # ------------------------------------------------------------------
    # Key generation
    # ------------------------------------------------------------------

    @staticmethod
    def _make_key(resume_text: str, jd_text: str) -> str:
        content = f"{resume_text}|{jd_text}".encode("utf-8")
        digest = hashlib.sha256(content).hexdigest()
        return f"cache:analysis:{digest}"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def get(
        self, resume_text: str, jd_text: str
    ) -> Optional[dict]:
        """Return cached result dict, or ``None`` on miss / error."""
        if not self._client:
            return None
        key = self._make_key(resume_text, jd_text)
        try:
            raw = await self._client.get(key)
            if raw:
                logger.info("[CACHE] HIT  %s…", key[:40])
                return json.loads(raw)
            logger.debug("[CACHE] MISS %s…", key[:40])
            return None
        except Exception as exc:
            logger.warning("[CACHE] GET error: %s", exc)
            return None

    async def set(
        self,
        resume_text: str,
        jd_text: str,
        result: dict,
        ttl: int = DEFAULT_TTL,
    ) -> None:
        """Store *result* with a TTL (default 7 days)."""
        if not self._client:
            return
        key = self._make_key(resume_text, jd_text)
        try:
            await self._client.setex(key, ttl, json.dumps(result, default=str))
            logger.info("[CACHE] SET  %s… (ttl=%ds)", key[:40], ttl)
        except Exception as exc:
            logger.warning("[CACHE] SET error: %s", exc)

    async def invalidate(self, resume_text: str, jd_text: str) -> None:
        """Explicitly remove a cached entry (e.g. after model retrain)."""
        if not self._client:
            return
        key = self._make_key(resume_text, jd_text)
        try:
            await self._client.delete(key)
            logger.info("[CACHE] DEL  %s…", key[:40])
        except Exception as exc:
            logger.warning("[CACHE] DEL error: %s", exc)


# Module-level singleton – import this everywhere
analysis_cache = AnalysisCache()
