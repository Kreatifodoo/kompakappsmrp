"""Async SQLAlchemy engine + session factories.

Two engines:
- write_engine: primary DB for writes
- read_engine: replica for read-heavy queries (reports)

After a write, route subsequent reads to primary for ~5s (read-your-writes).
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import settings


class Base(DeclarativeBase):
    """Base class for all ORM models."""


write_engine: AsyncEngine = create_async_engine(
    settings.DB_PRIMARY_URL,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_pre_ping=True,
    echo=settings.APP_DEBUG,
)

read_engine: AsyncEngine = create_async_engine(
    settings.db_replica_url,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_pre_ping=True,
    echo=settings.APP_DEBUG,
)

WriteSession = async_sessionmaker(write_engine, expire_on_commit=False, class_=AsyncSession)
ReadSession = async_sessionmaker(read_engine, expire_on_commit=False, class_=AsyncSession)


async def get_write_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency for write operations."""
    async with WriteSession() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_read_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency for read-only operations (uses replica)."""
    async with ReadSession() as session:
        yield session


@asynccontextmanager
async def transaction() -> AsyncGenerator[AsyncSession, None]:
    """Standalone async context manager for non-request transactions."""
    async with WriteSession() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def dispose_engines() -> None:
    """Close all engine pools (call on shutdown)."""
    await write_engine.dispose()
    await read_engine.dispose()


async def set_tenant_context(session: AsyncSession, tenant_id: str) -> None:
    """Set Postgres session variable for RLS policies."""
    from sqlalchemy import text

    await session.execute(text("SET LOCAL app.current_tenant = :tid"), {"tid": tenant_id})
