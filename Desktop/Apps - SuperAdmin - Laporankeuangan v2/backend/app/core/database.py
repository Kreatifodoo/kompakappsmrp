"""Async SQLAlchemy engine + session factories.

Two engines:
- write_engine: primary DB for writes
- read_engine: replica for read-heavy queries (reports)

After a write, route subsequent reads to primary for ~5s (read-your-writes).
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import Request
from sqlalchemy import text
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


async def _apply_tenant_context(session: AsyncSession, request: Request) -> None:
    """Decode JWT inline and SET LOCAL the tenant + super-admin GUCs.

    These power the Postgres RLS policies on tenant-scoped tables. Done
    at session-start so every subsequent statement runs with the right
    context. Failures here are silent — the actual auth dependency
    (`get_current_user`) will reject the request with a proper 401.
    """
    auth = request.headers.get("Authorization", "") if request else ""
    if not auth.startswith("Bearer "):
        return
    # Local import to avoid a dependency cycle (security imports config; ok)
    from jose import JWTError

    from app.core.security import decode_access_token

    try:
        payload = decode_access_token(auth[7:])
    except JWTError:
        return

    tid = payload.get("tid")
    if tid:
        await session.execute(
            text("SELECT set_config('app.current_tenant', :tid, true)"),
            {"tid": str(tid)},
        )
    if payload.get("sa"):
        await session.execute(text("SELECT set_config('app.is_super_admin', 'true', true)"))

    # Populate audit contextvars so SQLAlchemy listener tags writes with
    # the acting user. Best-effort import so a missing audit module
    # doesn't break the request path.
    try:
        from uuid import UUID as _UUID

        from app.modules.audit.listener import current_request_id, current_user_id

        sub = payload.get("sub")
        if sub:
            current_user_id.set(_UUID(sub))
        rid = request.headers.get("x-request-id") if request else None
        if rid:
            current_request_id.set(rid)
    except ImportError:
        pass


async def get_write_session(request: Request = None) -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency for write operations."""
    async with WriteSession() as session:
        if request is not None:
            await _apply_tenant_context(session, request)
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_read_session(request: Request = None) -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency for read-only operations (uses replica)."""
    async with ReadSession() as session:
        if request is not None:
            await _apply_tenant_context(session, request)
        yield session


@asynccontextmanager
async def transaction() -> AsyncGenerator[AsyncSession, None]:
    """Standalone async context manager for non-request transactions.

    Bypasses tenant RLS — intended for admin scripts (seed, importer,
    cron jobs) that need cross-tenant access. NEVER use for request-
    handling paths; use `get_write_session` instead.
    """
    async with WriteSession() as session:
        await session.execute(text("SELECT set_config('app.is_super_admin', 'true', true)"))
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
