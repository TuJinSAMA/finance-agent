import asyncio
import logging
from contextlib import asynccontextmanager
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


@asynccontextmanager
async def _scheduler_redis(redis: Redis | None = None):
    if redis is not None:
        yield redis
        return

    cache = Redis.from_url(
        settings.REDIS_URL,
        decode_responses=True,
    )
    try:
        await cache.ping()
        yield cache
    finally:
        await cache.aclose()


async def refresh_market_macro_snapshot(redis: Redis | None = None) -> None:
    async with _scheduler_redis(redis) as cache:
        snapshot = await build_macro_snapshot(datetime.now(UTC))
        await write_market_snapshot(cache, snapshot)
    logger.info("Refreshed public market macro snapshot")


async def refresh_market_assets_snapshot(redis: Redis | None = None) -> None:
    async with _scheduler_redis(redis) as cache:
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


def register_data_agent_jobs():
    """Register Data Agent scheduled jobs (idempotent)."""
    # NOTE: Jobs temporarily disabled
    # if not scheduler.get_job("daily_quotes"):
    #     scheduler.add_job(
    #         daily_quotes_job,
    #         "cron",
    #         hour=15,
    #         minute=30,
    #         day_of_week="mon-fri",
    #         id="daily_quotes",
    #         replace_existing=True,
    #     )
    #     logger.info("Registered daily_quotes job (weekdays 15:30)")
    logger.info("daily_quotes job is DISABLED")

    # if not scheduler.get_job("technical_indicators"):
    #     scheduler.add_job(
    #         technical_indicators_job,
    #         "cron",
    #         hour=16,
    #         minute=30,
    #         day_of_week="mon-fri",
    #         id="technical_indicators",
    #         replace_existing=True,
    #     )
    #     logger.info("Registered technical_indicators job (weekdays 16:30)")
    logger.info("technical_indicators job is DISABLED")

    # if not scheduler.get_job("weekly_stock_sync"):
    #     scheduler.add_job(
    #         weekly_sync_job,
    #         "cron",
    #         hour=17,
    #         minute=0,
    #         day_of_week="mon",
    #         id="weekly_stock_sync",
    #         replace_existing=True,
    #     )
    #     logger.info("Registered weekly_stock_sync job (Monday 17:00)")
    logger.info("weekly_stock_sync job is DISABLED")


def register_orchestrator_jobs():
    """Register Orchestrator scheduled jobs (idempotent)."""
    # NOTE: Jobs temporarily disabled
    # if not scheduler.get_job("daily_screening"):
    #     scheduler.add_job(
    #         daily_screening_job,
    #         "cron",
    #         hour=16,
    #         minute=0,
    #         day_of_week="mon-fri",
    #         id="daily_screening",
    #         replace_existing=True,
    #     )
    #     logger.info("Registered daily_screening job (weekdays 16:00)")
    logger.info("daily_screening job is DISABLED")


def register_event_agent_jobs():
    """Register Event Agent scheduled jobs (idempotent)."""
    # NOTE: Jobs temporarily disabled
    # if not scheduler.get_job("morning_event_scan"):
    #     scheduler.add_job(
    #         morning_event_scan_job,
    #         "cron",
    #         hour=6,
    #         minute=30,
    #         day_of_week="mon-fri",
    #         id="morning_event_scan",
    #         replace_existing=True,
    #     )
    #     logger.info("Registered morning_event_scan job (weekdays 06:30)")
    logger.info("morning_event_scan job is DISABLED")


def register_recommendation_jobs():
    """Register recommendation pipeline + performance tracking jobs (idempotent)."""
    # NOTE: Jobs temporarily disabled
    # if not scheduler.get_job("daily_recommendation"):
    #     scheduler.add_job(
    #         daily_recommendation_job,
    #         "cron",
    #         hour=7,
    #         minute=30,
    #         day_of_week="mon-fri",
    #         id="daily_recommendation",
    #         replace_existing=True,
    #     )
    #     logger.info("Registered daily_recommendation job (weekdays 07:30)")
    logger.info("daily_recommendation job is DISABLED")

    # if not scheduler.get_job("rec_performance_tracking"):
    #     scheduler.add_job(
    #         rec_performance_tracking_job,
    #         "cron",
    #         hour=15,
    #         minute=45,
    #         day_of_week="mon-fri",
    #         id="rec_performance_tracking",
    #         replace_existing=True,
    #     )
    #     logger.info("Registered rec_performance_tracking job (weekdays 15:45)")
    logger.info("rec_performance_tracking job is DISABLED")
