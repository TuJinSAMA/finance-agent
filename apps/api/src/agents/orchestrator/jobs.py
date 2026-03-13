"""
APScheduler job wrappers for Orchestrator.
Synchronous entry points that bridge to async methods via asyncio.run().
"""

import asyncio
import logging
from datetime import date

from src.agents.data_agent.trading_calendar import trading_calendar
from src.core.job_logger import JobLogger

logger = logging.getLogger(__name__)


# ── 16:00 量化筛选 ───────────────────────────────────


def daily_screening_job():
    """每个交易日 16:00 执行量化筛选，更新关注池。"""
    if not trading_calendar.is_trading_day():
        logger.info("daily_screening_job: not a trading day, skipping")
        JobLogger.skip("daily_screening", "量化筛选 → 关注池")
        return
    log_id = JobLogger.start("daily_screening", "量化筛选 → 关注池")
    try:
        asyncio.run(_daily_screening_async(log_id))
    except Exception as exc:
        JobLogger.fail(log_id, str(exc))
        raise


async def _daily_screening_async(log_id: int | None):
    from src.agents.orchestrator.screener import StockScreener
    from src.core.database import async_session

    async with async_session() as session:
        try:
            screener = StockScreener()
            result = await screener.run_daily_screening(session, date.today())
            await session.commit()
            logger.info("daily_screening_job completed: %s", result)
            JobLogger.finish(log_id, meta=result if isinstance(result, dict) else {"result": str(result)})
        except Exception as exc:
            logger.exception("daily_screening_job failed")
            JobLogger.fail(log_id, str(exc))
            raise


# ── 07:30 推荐生成流水线 ─────────────────────────────


def daily_recommendation_job():
    """每个交易日 07:30 执行推荐生成流水线。"""
    if not trading_calendar.is_trading_day():
        logger.info("daily_recommendation_job: not a trading day, skipping")
        JobLogger.skip("daily_recommendation", "推荐生成流水线")
        return
    log_id = JobLogger.start("daily_recommendation", "推荐生成流水线")
    try:
        asyncio.run(_daily_recommendation_async(log_id))
    except Exception as exc:
        JobLogger.fail(log_id, str(exc))
        raise


async def _daily_recommendation_async(log_id: int | None):
    from src.agents.orchestrator.pipeline import daily_recommendation_pipeline
    from src.core.database import async_session

    async with async_session() as session:
        try:
            result = await daily_recommendation_pipeline(session, date.today())
            await session.commit()
            logger.info("daily_recommendation_job completed: %s", result)
            meta = result if isinstance(result, dict) else {"result": str(result)}
            records = meta.get("recommendations_count") or meta.get("candidates")
            JobLogger.finish(log_id, records_affected=records, meta=meta)
        except Exception as exc:
            logger.exception("daily_recommendation_job failed")
            JobLogger.fail(log_id, str(exc))
            raise


# ── 15:45 事后表现追踪 ───────────────────────────────


def rec_performance_tracking_job():
    """每个交易日 15:45 更新历史推荐的事后表现。"""
    if not trading_calendar.is_trading_day():
        logger.info("rec_performance_tracking_job: not a trading day, skipping")
        JobLogger.skip("rec_performance_tracking", "推荐表现追踪")
        return
    log_id = JobLogger.start("rec_performance_tracking", "推荐表现追踪")
    try:
        asyncio.run(_rec_performance_async(log_id))
    except Exception as exc:
        JobLogger.fail(log_id, str(exc))
        raise


async def _rec_performance_async(log_id: int | None):
    from src.agents.orchestrator.pipeline import update_recommendation_performance
    from src.core.database import async_session

    async with async_session() as session:
        try:
            result = await update_recommendation_performance(session, date.today())
            await session.commit()
            logger.info("rec_performance_tracking_job completed: %s", result)
            meta = result if isinstance(result, dict) else {"result": str(result)}
            records = meta.get("t1_updated") or meta.get("t5_updated")
            JobLogger.finish(log_id, records_affected=records, meta=meta)
        except Exception as exc:
            logger.exception("rec_performance_tracking_job failed")
            JobLogger.fail(log_id, str(exc))
            raise
