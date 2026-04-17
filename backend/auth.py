"""
Supabase JWT Authentication & User Provisioning.

This module handles:
1. JWT token verification from the Authorization header
2. First-login user provisioning (auto-create FREE tier)
3. Permission checks (e.g., "is_pro()") for feature gating
"""

import os
from typing import Optional

import jwt
from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from .database import get_db
from .db_models import User, UserTier, RecruiterAccount


# =============================================================================
# Configuration
# =============================================================================

SUPABASE_JWT_SECRET = os.getenv("SUPABASE_JWT_SECRET", "")
if not SUPABASE_JWT_SECRET:
    raise RuntimeError(
        "SUPABASE_JWT_SECRET not set. This is required for JWT verification. "
        "Set it in your .env file from Supabase → Settings → API → JWT Settings."
    )

SUPABASE_URL = os.getenv("SUPABASE_URL", "")

JWT_ALGORITHMS = ["HS256"]

# Pro testing mode: emails that automatically get PRO tier
# No default — must be explicitly set in .env for production safety
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL")


# =============================================================================
# JWT Verification & User Provisioning
# =============================================================================

async def get_current_user(
    authorization: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
) -> Optional[User]:
    """
    FastAPI dependency that:
    1. Extracts the JWT from Authorization: Bearer <token>
    2. Verifies the token with Supabase's JWT secret
    3. Either returns an existing User or creates a new FREE-tier one
    4. Returns the User DB object

    Usage in a route:
        @app.get("/api/me")
        async def me(user: User = Depends(get_current_user)):
            return user

    Raises:
        401 if no header, invalid token, or verification fails
        500 if DB operation fails
    """
    # Extract token from Authorization header
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Authorization header format. Expected: Bearer <token>",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = parts[1]

    # Decode and verify JWT
    try:
        payload = jwt.decode(
            token,
            SUPABASE_JWT_SECRET,
            algorithms=JWT_ALGORITHMS,
            audience="authenticated",
            issuer=SUPABASE_URL or None,
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Extract supabase_user_id from JWT (Supabase places it in 'sub' claim)
    supabase_user_id = payload.get("sub")
    if not supabase_user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing 'sub' (user ID)",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Provisional user info from token (for first-login provisioning)
    email = payload.get("email", "")

    # Lookup user in DB
    from sqlalchemy import select
    stmt = select(User).where(User.supabase_user_id == supabase_user_id)
    result = await db.execute(stmt)
    user = result.scalars().first()

    # First login: auto-create FREE tier user
    if not user:
        # Check if email matches admin/founder email for PRO access
        tier = UserTier.pro if email == ADMIN_EMAIL else UserTier.free
        user = User(
            supabase_user_id=supabase_user_id,
            email=email,
            full_name=payload.get("user_metadata", {}).get("full_name") or "",
            tier=tier,
        )
        db.add(user)
        await db.flush()  # Flush to DB but don't commit yet; FastAPI dependency does that
        if tier == UserTier.pro:
            print(f"[AUTH] Founder/admin user created with PRO tier: {email}")
    else:
        # Upgrade to PRO if email matches admin list
        if email == ADMIN_EMAIL and user.tier != UserTier.pro:
            user.tier = UserTier.pro
            await db.commit()
            print(f"[AUTH] User upgraded to PRO tier: {email}")

    return user


async def require_auth(
    authorization: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Strongly-typed version of get_current_user that raises 401 if not available.
    Returns a User object that is guaranteed to exist.
    """
    user = await get_current_user(authorization, db)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or could not be provisioned",
        )
    return user


# =============================================================================
# Permission Helpers
# =============================================================================

def is_pro(user: User) -> bool:
    """Check if user has PRO tier."""
    return user.tier == UserTier.pro


def is_free(user: User) -> bool:
    """Check if user has FREE tier."""
    return user.tier == UserTier.free


def can_scan(user: User) -> bool:
    """
    Check if user has scans remaining this month.
    Built into User.can_scan() but included here for explicit checks in routes.
    """
    return user.can_scan()


async def require_pro(user: User = Depends(require_auth)) -> User:
    """FastAPI dependency that enforces PRO tier access."""
    if not is_pro(user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This feature requires a PRO subscription",
        )
    return user


async def check_scan_quota(user: User = Depends(require_auth)) -> User:
    """FastAPI dependency that checks if user has scans left this month."""
    if not user.can_scan():
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"You have reached your monthly scan limit ({user.scan_limit}). "
            "Upgrade to PRO for unlimited scans.",
        )
    return user


# =============================================================================
# Recruiter Authentication
# =============================================================================

async def get_current_recruiter(
    authorization: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
) -> RecruiterAccount:
    """
    Validate JWT and return the corresponding RecruiterAccount.
    Uses the same Supabase JWT infrastructure but looks up recruiter_accounts.
    """
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Authorization header format",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = jwt.decode(
            parts[1],
            SUPABASE_JWT_SECRET,
            algorithms=JWT_ALGORITHMS,
            audience="authenticated",
            issuer=SUPABASE_URL or None,
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {e}")

    supabase_user_id = payload.get("sub")
    email = payload.get("email", "")
    if not supabase_user_id:
        raise HTTPException(status_code=401, detail="Token missing 'sub'")

    from sqlalchemy import select

    stmt = select(RecruiterAccount).where(RecruiterAccount.supabase_user_id == supabase_user_id)
    result = await db.execute(stmt)
    recruiter = result.scalars().first()

    # Fallback: look up by email (for accounts created before Supabase link)
    if not recruiter:
        stmt = select(RecruiterAccount).where(RecruiterAccount.email == email)
        result = await db.execute(stmt)
        recruiter = result.scalars().first()
        if recruiter and not recruiter.supabase_user_id:
            recruiter.supabase_user_id = supabase_user_id
            await db.flush()

    if not recruiter:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No recruiter account found. Please sign up at /recruiter/signup.",
        )

    return recruiter
