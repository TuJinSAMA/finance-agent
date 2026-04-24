import asyncio
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.background import BackgroundScheduler
from redis.asyncio import Redis

from src.agents.geo_news_agent.jobs import (
    extract_geo_events_job,
    ingest_gdelt_job,
    ingest_gnews_job,
    ingest_rss_job,
)
from src.core.config import settings
from src.models.geo_news_config import geo_news_config
from src.services.market_metric_store import MarketMetricService
from src.services.public_board import build_assets_snapshot
from src.services.public_board import build_crypto_snapshot
from src.services.public_board import build_equity_snapshot
from src.services.public_board import build_extended_snapshot
from src.services.public_board import build_macro_snapshot
from src.services.public_market_cache import write_market_snapshot

logger = logging.getLogger(__name__)

ET = ZoneInfo("America/New_York")

INTERVAL_MAP: dict[str, dict[str, int]] = {
    "crypto": {
        "us_regular": 2,
        "us_extended": 5,
        "overnight": 10,
        "weekend": 10,
    },
    "extended": {
        "us_regular": 3,
        "us_extended": 10,
        "overnight": 30,
        "weekend": 60,
    },
    "equity": {
        "us_regular": 3,
        "us_extended": 15,
        "overnight": 60,
        "weekend": 60,
    },
}

INITIAL_INTERVALS: dict[str, int] = {"crypto": 5, "extended": 10, "equity": 15}

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


class _ETDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        return datetime.now(tz or ET)


_et_datetime_override: type[datetime] | None = None


def _now_et() -> datetime:
    cls = _et_datetime_override or _ETDateTime
    return cls.now(ET)


def _current_session() -> str:
    now_et = _now_et()
    if now_et.weekday() >= 5:
        return "weekend"
    t = now_et.hour * 60 + now_et.minute
    if 9 * 60 + 30 <= t < 16 * 60:
        return "us_regular"
    if 4 * 60 <= t < 9 * 60 + 30 or 16 * 60 <= t < 20 * 60:
        return "us_extended"
    return "overnight"


async def _run_refresh(group: str) -> None:
    redis = Redis.from_url(settings.REDIS_URL, decode_responses=True)
    try:
        if group == "crypto":
            await refresh_crypto_snapshot(redis)
        elif group == "extended":
            await refresh_extended_snapshot(redis)
        elif group == "equity":
            await refresh_equity_snapshot(redis)
    finally:
        await redis.aclose()


async def refresh_crypto_snapshot(redis: Redis) -> None:
    snapshot = await build_crypto_snapshot(datetime.now(UTC))
    await write_market_snapshot(redis, snapshot)
    from src.core.database import job_async_session
    async with job_async_session() as db:
        service = MarketMetricService(db)
        await service.persist_group_metrics(snapshot)
    logger.info("Refreshed public market crypto snapshot")


async def refresh_extended_snapshot(redis: Redis) -> None:
    snapshot = await build_extended_snapshot(datetime.now(UTC))
    await write_market_snapshot(redis, snapshot)
    from src.core.database import job_async_session
    async with job_async_session() as db:
        service = MarketMetricService(db)
        await service.persist_group_metrics(snapshot)
    logger.info("Refreshed public market extended snapshot")


async def refresh_equity_snapshot(redis: Redis) -> None:
    snapshot = await build_equity_snapshot(datetime.now(UTC))
    await write_market_snapshot(redis, snapshot)
    from src.core.database import job_async_session
    async with job_async_session() as db:
        service = MarketMetricService(db)
        await service.persist_group_metrics(snapshot)
    logger.info("Refreshed public market equity snapshot")


async def refresh_market_macro_snapshot(redis: Redis) -> None:
    snapshot = await build_macro_snapshot(datetime.now(UTC))
    await write_market_snapshot(redis, snapshot)
    logger.info("Refreshed public market macro snapshot")


async def refresh_market_assets_snapshot(redis: Redis) -> None:
    snapshot = await build_assets_snapshot(datetime.now(UTC))
    await write_market_snapshot(redis, snapshot)
    logger.info("Refreshed public market assets snapshot")


def _self_adjusting_job(group: str) -> None:
    session = _current_session()

    if group == "equity" and session == "weekend":
        logger.debug("Skipping equity refresh — weekend")
        return

    asyncio.run(_run_refresh(group))

    next_minutes = INTERVAL_MAP[group][session]
    scheduler.reschedule_job(
        f"refresh_{group}",
        trigger="interval",
        minutes=next_minutes,
    )
    logger.info(
        "Refreshed %s snapshot, next run in %d min (session=%s)",
        group, next_minutes, session,
    )


def _make_self_adjusting_job(group: str) -> Callable[[], None]:
    def job() -> None:
        _self_adjusting_job(group)
    return job


def register_public_market_jobs() -> None:
    for group, minutes in INITIAL_INTERVALS.items():
        job_id = f"refresh_{group}"
        scheduler.add_job(
            _self_adjusting_job,
            "interval",
            minutes=minutes,
            id=job_id,
            replace_existing=True,
            args=[group],
        )
        logger.info("Registered %s job (initial interval: %d min)", job_id, minutes)


def register_geo_news_jobs() -> None:
    scheduler.add_job(
        ingest_rss_job,
        "interval",
        minutes=geo_news_config.rss_interval_minutes,
        id="ingest_geo_rss",
        replace_existing=True,
    )
    logger.info("Registered ingest_geo_rss job (interval: %d min)", geo_news_config.rss_interval_minutes)

    scheduler.add_job(
        ingest_gnews_job,
        "interval",
        hours=geo_news_config.gnews_interval_hours,
        id="ingest_geo_gnews",
        replace_existing=True,
    )
    logger.info("Registered ingest_geo_gnews job (interval: %d hours)", geo_news_config.gnews_interval_hours)

    scheduler.add_job(
        ingest_gdelt_job,
        "interval",
        hours=geo_news_config.gdelt_interval_hours,
        id="ingest_geo_gdelt",
        replace_existing=True,
    )
    logger.info("Registered ingest_geo_gdelt job (interval: %d hours)", geo_news_config.gdelt_interval_hours)

    scheduler.add_job(
        extract_geo_events_job,
        "interval",
        minutes=geo_news_config.extraction_interval_minutes,
        id="extract_geo_events",
        replace_existing=True,
    )
    logger.info("Registered extract_geo_events job (interval: %d min)", geo_news_config.extraction_interval_minutes)