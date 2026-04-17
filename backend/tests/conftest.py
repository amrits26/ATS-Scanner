"""
Shared test fixtures for IntelliResume AI backend tests.

Usage:
    pytest backend/tests/ -v --cov=backend
"""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db_models import User, UserTier
from backend.main import app


# ---------------------------------------------------------------------------
# Mock JWT
# ---------------------------------------------------------------------------
MOCK_JWT_TOKEN = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIn0."
    "dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"
)


# ---------------------------------------------------------------------------
# Database fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def mock_db():
    """Async-compatible mock database session."""
    db = MagicMock(spec=AsyncSession)
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.execute = AsyncMock()
    db.rollback = AsyncMock()
    return db


# ---------------------------------------------------------------------------
# User fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def free_user():
    """A FREE-tier user with zero scans used."""
    user = MagicMock(spec=User)
    user.id = uuid.UUID("00000000-0000-0000-0000-000000000001")
    user.supabase_user_id = "sup-free-001"
    user.email = "free@test.com"
    user.full_name = "Free Tester"
    user.tier = UserTier.free
    user.scans_this_month = 0
    user.scan_limit = 3
    return user


@pytest.fixture
def pro_user():
    """A PRO-tier user with unlimited scans."""
    user = MagicMock(spec=User)
    user.id = uuid.UUID("00000000-0000-0000-0000-000000000002")
    user.supabase_user_id = "sup-pro-002"
    user.email = "pro@test.com"
    user.full_name = "Pro Tester"
    user.tier = UserTier.pro
    user.scans_this_month = 10
    user.scan_limit = 999
    return user


@pytest.fixture
def maxed_free_user():
    """A FREE-tier user who has hit the 3-scan monthly quota."""
    user = MagicMock(spec=User)
    user.id = uuid.UUID("00000000-0000-0000-0000-000000000003")
    user.supabase_user_id = "sup-maxed-003"
    user.email = "maxed@test.com"
    user.full_name = "Maxed Tester"
    user.tier = UserTier.free
    user.scans_this_month = 3
    user.scan_limit = 3
    return user


# ---------------------------------------------------------------------------
# HTTP client fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def auth_headers():
    """Authorization headers with mock JWT."""
    return {"Authorization": f"Bearer {MOCK_JWT_TOKEN}"}


@pytest.fixture
async def async_client():
    """Async HTTP client bound to the FastAPI app."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
