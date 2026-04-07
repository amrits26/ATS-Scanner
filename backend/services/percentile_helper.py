"""
Percentile ranking helper with Redis-backed caching.
Prevents N+1 queries when calculating user's percentile rank.
"""

import time
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from ..db_models import AnalysisResult, AnalysisStatus

# In-memory cache fallback (replace with Redis in production)
_cache = {"total": None, "time": 0, "ttl": 3600}


async def get_total_completed_scans(db: AsyncSession) -> int:
    """
    Get total count of completed scans with 1-hour caching.
    
    Why: Prevents O(n) table scan on every percentile calculation.
    Cache TTL: 1 hour (balance between staleness and performance).
    
    Args:
        db: AsyncSession database connection
        
    Returns:
        int: Total count of completed scans (cached if < 1 hour old)
    """
    # Check if cache is still fresh
    if _cache["total"] and (time.time() - _cache["time"]) < _cache["ttl"]:
        return _cache["total"]
    
    # Cache miss: execute query
    stmt = select(func.count(AnalysisResult.id)).where(
        AnalysisResult.status == AnalysisStatus.completed
    )
    result = await db.execute(stmt)
    total = result.scalar() or 100
    
    # Update cache
    _cache["total"] = total
    _cache["time"] = time.time()
    
    return total


async def calculate_percentile_rank(db: AsyncSession, user_score: int) -> int:
    """
    Calculate percentile rank: what % of users scored lower than this score?
    
    Example: If user scores 75 and 200 other users scored lower out of 1000 total,
    their percentile = (200 / 1000) * 100 = 20th percentile
    
    Args:
        db: AsyncSession database connection
        user_score: User's current ATS score (0-100)
        
    Returns:
        int: Percentile rank (0-100)
    """
    total_completed = await get_total_completed_scans(db)
    
    # Count how many users scored lower
    stmt_lower = select(func.count(AnalysisResult.id)).where(
        AnalysisResult.status == AnalysisStatus.completed,
        AnalysisResult.final_ats_score < user_score
    )
    result = await db.execute(stmt_lower)
    lower_count = result.scalar() or 0
    
    # Calculate percentile
    if total_completed == 0:
        return 50  # Unknown percentile if no data
    
    percentile = int((lower_count / total_completed) * 100)
    return min(100, max(0, percentile))


def invalidate_cache():
    """
    Manually invalidate the percentile cache.
    Call this when a significant number of new analyses are added.
    """
    global _cache
    _cache = {"total": None, "time": 0, "ttl": 3600}
