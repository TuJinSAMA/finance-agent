from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from src.core.config import settings

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
    pool_recycle=1800,
)

async_session = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


@asynccontextmanager
async def job_async_session():
    """Create a per-job engine + session for use in scheduled jobs.

    BackgroundScheduler runs jobs in threads where ``asyncio.run()`` creates
    a new event loop each time. The shared ``engine`` pools asyncpg connections
    bound to whatever loop created them, so reusing it across loops raises
    ``RuntimeError: Future attached to a different loop``.

    Using ``NullPool`` avoids cross-loop pooling entirely — each call gets a
    fresh connection on the current loop, and the engine is disposed after use.
    """
    job_engine: AsyncEngine = create_async_engine(
        settings.DATABASE_URL,
        echo=settings.DEBUG,
        poolclass=NullPool,
    )
    job_session_factory = async_sessionmaker(
        job_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    try:
        async with job_session_factory() as session:
            yield session
    finally:
        await job_engine.dispose()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
