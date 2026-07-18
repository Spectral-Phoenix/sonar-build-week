"""Async engine / session factory / schema bootstrap."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


_SQLITE_FILE_PREFIX = "sqlite+aiosqlite:///"


def ensure_sqlite_dir(database_url: str) -> None:
    """Create the parent directory for a file-backed SQLite database if needed."""
    if not database_url.startswith(_SQLITE_FILE_PREFIX):
        return
    remainder = database_url[len(_SQLITE_FILE_PREFIX) :]
    if not remainder or remainder.startswith(":memory:"):
        return
    Path(remainder).parent.mkdir(parents=True, exist_ok=True)


def create_engine(database_url: str) -> AsyncEngine:
    """Create an async engine. Works for both SQLite (dev) and Postgres (prod)."""
    ensure_sqlite_dir(database_url)
    return create_async_engine(database_url, pool_pre_ping=True, future=True)


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Session factory with ``expire_on_commit=False`` so results survive commit."""
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def init_db(engine: AsyncEngine) -> None:
    """Create tables if they do not exist (dev convenience; use Alembic in production)."""
    # Import models for side-effect registration on Base.metadata.
    from charwatch.db import models  # noqa: F401, PLC0415 - lazy to avoid a circular import

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
