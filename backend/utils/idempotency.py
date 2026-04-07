"""
Phase 3: Idempotency Key Generation & Tracking
Prevents duplicate free scans and share operations
"""

import hashlib
from datetime import datetime
from typing import Optional, Tuple
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class IdempotencyError(Exception):
    """Raised when idempotency check fails"""
    pass


def generate_free_scan_idempotency_key(
    email: str,
    resume_hash: str,
    scan_date: Optional[datetime] = None
) -> str:
    """
    Generate idempotency key for free scan (email + resume_hash + date)
    
    This ensures the same resume by same user on same day is counted once.
    
    Args:
        email: User email
        resume_hash: SHA256 hash of resume content
        scan_date: Date of scan (defaults to today)
    
    Returns:
        Deterministic idempotency key
    """
    if scan_date is None:
        scan_date = datetime.utcnow().date()
    
    # Format: email:resume_hash:YYYY-MM-DD
    key_material = f"{email.lower()}:{resume_hash}:{scan_date.isoformat()}"
    
    # Return hex digest (deterministic, 64 chars)
    return hashlib.sha256(key_material.encode()).hexdigest()


def generate_share_idempotency_key(
    user_id: str,
    scan_id: str,
    timestamp: Optional[datetime] = None
) -> str:
    """
    Generate idempotency key for share operation (user_id + scan_id + timestamp)
    
    Prevents duplicate share tokens for same scan by same user.
    
    Args:
        user_id: User UUID
        scan_id: Analysis scan UUID
        timestamp: Creation time (ISO format)
    
    Returns:
        Share token (32 char URL-safe)
    """
    if timestamp is None:
        timestamp = datetime.utcnow().isoformat()
    
    # Format: user_id:scan_id:timestamp
    key_material = f"{user_id}:{scan_id}:{timestamp}"
    
    # Return first 32 chars of hash (URL-safe)
    hash_digest = hashlib.sha256(key_material.encode()).hexdigest()
    return hash_digest[:32].lower()


async def check_free_scan_idempotency(
    db: AsyncSession,
    email: str,
    resume_hash: str
) -> Tuple[bool, int]:
    """
    Check if user already scanned this resume today
    
    Args:
        db: Database session
        email: User email
        resume_hash: Resume content hash
    
    Returns:
        Tuple of (is_duplicate: bool, scans_remaining: int)
    
    Raises:
        IdempotencyError if quota exceeded
    """
    # Count scans by this email TODAY
    stmt = text("""
        SELECT COUNT(*) as scan_count
        FROM free_scan_usage
        WHERE email = :email
        AND scan_date = CURRENT_DATE
    """)
    
    result = await db.execute(stmt, {"email": email.lower()})
    scan_count = result.scalar() or 0
    
    # Free tier: 3 scans per month (roughly 1 per 10 days, max 1 per day)
    MAX_SCANS_PER_DAY = 1
    DAILY_QUOTA = 3
    
    if scan_count >= MAX_SCANS_PER_DAY:
        scans_remaining = max(0, DAILY_QUOTA - scan_count)
        return True, scans_remaining
    
    # Check if this exact resume was scanned already today (idempotency)
    stmt_exact = text("""
        SELECT 1
        FROM free_scan_usage
        WHERE email = :email
        AND resume_hash = :resume_hash
        AND scan_date = CURRENT_DATE
        LIMIT 1
    """)
    
    exact_result = await db.execute(
        stmt_exact,
        {"email": email.lower(), "resume_hash": resume_hash}
    )
    is_duplicate = exact_result.scalar() is not None
    
    scans_remaining = max(0, MAX_SCANS_PER_DAY - scan_count - 1)
    
    return is_duplicate, scans_remaining


async def record_free_scan(
    db: AsyncSession,
    user_id: Optional[str],
    email: str,
    resume_hash: str
) -> bool:
    """
    Record free scan usage (idempotency: unique per email + hash + date)
    
    Args:
        db: Database session
        user_id: Optional user ID (NULL for anonymous)
        email: User email
        resume_hash: Resume hash
    
    Returns:
        True if recorded, False if already exists (duplicate)
    """
    stmt = text("""
        INSERT INTO free_scan_usage (user_id, email, resume_hash, scan_date)
        VALUES (:user_id, :email, :resume_hash, CURRENT_DATE)
        ON CONFLICT (email, resume_hash, scan_date) DO NOTHING
    """)
    
    result = await db.execute(
        stmt,
        {
            "user_id": user_id,
            "email": email.lower(),
            "resume_hash": resume_hash
        }
    )
    
    # rowcount == 0 means duplicate (conflict handled by DB)
    return result.rowcount > 0


async def check_share_rate_limit(
    db: AsyncSession,
    user_id: str,
    email: str,
    rate_limit_per_minute: int = 5
) -> Tuple[bool, int]:
    """
    Check share endpoint rate limit (5 per minute)
    
    Args:
        db: Database session
        user_id: User UUID
        email: User email
        rate_limit_per_minute: Max requests per minute
    
    Returns:
        Tuple of (is_rate_limited: bool, requests_remaining: int)
    """
    # Count requests in last 60 seconds
    stmt = text("""
        SELECT COUNT(*) as request_count
        FROM share_rate_limits
        WHERE (user_id = :user_id OR email = :email)
        AND request_at > NOW() - INTERVAL '1 minute'
    """)
    
    result = await db.execute(
        stmt,
        {"user_id": user_id, "email": email.lower()}
    )
    
    request_count = result.scalar() or 0
    is_limited = request_count >= rate_limit_per_minute
    remaining = max(0, rate_limit_per_minute - request_count)
    
    return is_limited, remaining


async def record_share_request(
    db: AsyncSession,
    user_id: str,
    email: str
) -> None:
    """Record share endpoint request for rate limiting"""
    stmt = text("""
        INSERT INTO share_rate_limits (user_id, email)
        VALUES (:user_id, :email)
    """)
    
    await db.execute(
        stmt,
        {"user_id": user_id, "email": email.lower()}
    )
    await db.commit()
