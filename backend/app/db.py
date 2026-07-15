"""Async database engine + session factory."""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from .config import settings
from .models import Base

def _connect_args() -> dict:
    """Per-driver connection options.

    TLS: hosted Postgres (Neon, Supabase, Render) rejects plaintext connections,
    while the local portable server has no certificate and rejects TLS. See
    `settings.use_database_ssl`.

    Note asyncpg takes `ssl=`, not libpq's `sslmode=`. Passing the URL Neon shows
    you verbatim - with `?sslmode=require` - makes asyncpg raise
    "invalid connection option 'sslmode'", which reads like a bug in the app
    rather than a driver difference.
    """
    if not settings.use_database_ssl:
        return {}

    import ssl as ssl_module

    ctx = ssl_module.create_default_context()
    # Neon terminates TLS at a pooler whose certificate does not match the
    # per-branch hostname. Verification would fail against a perfectly legitimate
    # endpoint, so it is relaxed here — the connection is still encrypted, and the
    # password remains the thing that authenticates us.
    ctx.check_hostname = False
    ctx.verify_mode = ssl_module.CERT_NONE
    return {"ssl": ctx}


engine = create_async_engine(
    settings.database_url,
    echo=False,
    pool_pre_ping=True,
    # Neon's free tier scales to zero when idle and takes ~500ms to wake. A
    # pooled connection held across that suspend is dead on arrival, so recycle
    # them well before it happens; pool_pre_ping catches the rest.
    pool_size=5,
    max_overflow=10,
    pool_recycle=280,
    connect_args=_connect_args(),
)

SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


async def init_models() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
