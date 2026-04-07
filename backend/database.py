"""
Async SQLAlchemy 2.x engine, session factory, and ORM Base.

Usage (in FastAPI route):
    from .database import get_db
    from sqlalchemy.ext.asyncio import AsyncSession

    @app.get("/example")
    async def example(db: AsyncSession = Depends(get_db)):
        ...
"""

import os
from typing import AsyncGenerator
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

# Load .env files - backend/.env takes precedence over root .env
# This allows local overrides for development
root_env = Path(__file__).parent.parent / ".env"
if root_env.exists():
    load_dotenv(root_env, override=False)  # Load root .env first (no override)

backend_env = Path(__file__).parent / ".env"
if backend_env.exists():
    load_dotenv(backend_env, override=True)  # Override with backend/.env


def _build_database_url() -> str:
    """
    Normalize DATABASE_URL to the asyncpg dialect.
    Supabase provides   postgres://...
    SQLAlchemy expects  postgresql+asyncpg://...
    """
    url = os.getenv("DATABASE_URL", "")
    if not url:
        return ""
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+asyncpg://", 1)
    if url.startswith("postgresql://") and "+asyncpg" not in url:
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


_DATABASE_URL = _build_database_url()

if _DATABASE_URL:
    engine = create_async_engine(
        _DATABASE_URL,
        echo=False,          # Set True for SQL query logging in dev
        pool_size=5,
        max_overflow=10,
        pool_pre_ping=True,  # Recover stale connections automatically
    )
    AsyncSessionLocal: async_sessionmaker[AsyncSession] | None = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
else:
    engine = None  # type: ignore[assignment]
    AsyncSessionLocal = None


class Base(DeclarativeBase):
    """Shared ORM declarative base for all models."""
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency that yields an async DB session with
    automatic commit on success and rollback on error.
    """
    if AsyncSessionLocal is None:
        raise RuntimeError(
            "DATABASE_URL is not configured. "
            "Set it in your .env file or environment before starting the server."
        )
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
