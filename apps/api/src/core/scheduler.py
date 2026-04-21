import asyncio
import logging
from datetime import UTC, datetime

from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.background import BackgroundScheduler
from redis.asyncio import Redis

from src.core.config import settings
from src.services.public_board import build_assets_snapshot
from src.services.public_board import build_macro_snapshot
from src.services.public_market_cache import write_market_snapshot

logger = logging.getLogger(__name__)

jobstores = {
    "default": SQLAlchemyJobStore(
        url=settings.DATABASE_URL_SYNC,
        tablename="apscheduler_jobs",
    ),
}

executors = {
    "default": ThreadPoolExecutor(max_workers=10),
}

job_defaults = {
    "coalesce": True,
    "max_instances": 1,
    "misfire_grace_time": 60,
}

scheduler = BackgroundScheduler(
    jobstores=jobstores,
    executors=executors,
    job_defaults=job_defaults,
)

_scheduler_redis: Redis | None = None


async def get_scheduler_redis() -> Redis:
    global _scheduler_redis
    if _scheduler_redis is None:
        _scheduler_redis = Redis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
        )
        await _scheduler_redis.ping()
    return _scheduler_redis


async def close_scheduler_redis() -> None:
    global _scheduler_redis
    if _scheduler_redis is not None:
        await _scheduler_redis.aclose()
        _scheduler_redis = None


async def refresh_market_macro_snapshot(redis: Redis | None = None) -> None:
    cache = redis or await get_scheduler_redis()
    snapshot = await build_macro_snapshot(datetime.now(UTC))
    await write_market_snapshot(cache, snapshot)
    logger.info("Refreshed public market macro snapshot")


async def refresh_market_assets_snapshot(redis: Redis | None = None) -> None:
    cache = redis or await get_scheduler_redis()
    snapshot = await build_assets_snapshot(datetime.now(UTC))
    await write_market_snapshot(cache, snapshot)
    logger.info("Refreshed public market assets snapshot")


def refresh_public_market_macro() -> None:
    asyncio.run(refresh_market_macro_snapshot())


def refresh_public_market_assets() -> None:
    asyncio.run(refresh_market_assets_snapshot())


def register_public_market_jobs() -> None:
    """Register public market refresh jobs (idempotent)."""
    scheduler.add_job(
        refresh_public_market_macro,
        "interval",
        minutes=15,
        id="refresh_public_market_macro",
        replace_existing=True,
    )
    logger.info("Registered refresh_public_market_macro job (every 15 min)")

    scheduler.add_job(
        refresh_public_market_assets,
        "interval",
        minutes=15,
        id="refresh_public_market_assets",
        replace_existing=True,
    )
    logger.info("Registered refresh_public_market_assets job (every 15 min)")



