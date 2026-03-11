"""
APScheduler job wrapper functions for Data Agent.
These are synchronous functions that bridge to async DataAgent methods via asyncio.run().
Each job checks the trading calendar before executing.
"""

import asyncio
import logging
from datetime import date

from sqlalchemy import select

from src.agents.data_agent.trading_calendar import trading_calendar

logger = logging.getLogger(__name__)


def daily_quotes_job():
    """每个交易日 15:30 拉取当日收盘行情。"""
    if not trading_calendar.is_trading_day():
        logger.info("daily_quotes_job: not a trading day, skipping")
        return
    asyncio.run(_daily_quotes_async())


def technical_indicators_job():
    """每个交易日 16:30 计算全市场技术指标。"""
    if not trading_calendar.is_trading_day():
        logger.info("technical_indicators_job: not a trading day, skipping")
        return
    asyncio.run(_technical_indicators_async())


def weekly_sync_job():
    """每周一 17:00 同步股票列表 + 基本面数据。"""
    asyncio.run(_weekly_sync_async())


async def _daily_quotes_async():
    from src.agents.data_agent.fetcher import DataAgent
    from src.core.database import async_session

    async with async_session() as session:
        try:
            agent = DataAgent(session)
            count = await agent.fetch_daily_quotes(trade_date=date.today())
            logger.info("daily_quotes_job completed: %d rows written", count)
        except Exception:
            logger.exception("daily_quotes_job failed")


async def _technical_indicators_async():
    from src.agents.data_agent.indicators import compute_and_store_indicators
    from src.core.database import async_session
    from src.models.stock import Stock

    BATCH_SIZE = 200

    async with async_session() as session:
        result = await session.execute(select(Stock.id).order_by(Stock.id))
        stock_ids = [row[0] for row in result.all()]

    total = len(stock_ids)
    success = 0
    today = date.today()

    for batch_start in range(0, total, BATCH_SIZE):
        batch = stock_ids[batch_start: batch_start + BATCH_SIZE]
        async with async_session() as session:
            try:
                for stock_id in batch:
                    ok = await compute_and_store_indicators(session, stock_id, today)
                    if ok:
                        success += 1
                await session.commit()
            except Exception:
                logger.exception(
                    "technical_indicators_job batch failed at offset %d", batch_start
                )

        if (batch_start + BATCH_SIZE) % 1000 == 0 or batch_start + BATCH_SIZE >= total:
            logger.info(
                "technical_indicators_job progress: %d/%d (%d computed)",
                min(batch_start + BATCH_SIZE, total), total, success,
            )

    logger.info("technical_indicators_job completed: %d/%d stocks", success, total)


async def _weekly_sync_async():
    from src.agents.data_agent.fetcher import DataAgent
    from src.agents.data_agent.fundamentals import fetch_fundamentals_full
    from src.core.database import async_session

    async with async_session() as session:
        try:
            agent = DataAgent(session)
            await agent.sync_stock_list()
            await agent.sync_industry_mapping()
            await agent.sync_list_dates()
            logger.info("weekly_sync_job: stock list/industry/dates synced, starting fundamentals...")
        except Exception:
            logger.exception("weekly_sync_job failed during stock sync")
            return

    async with async_session() as session:
        try:
            await fetch_fundamentals_full(session)
            logger.info("weekly_sync_job completed (including full fundamentals)")
        except Exception:
            logger.exception("weekly_sync_job failed during fundamentals fetch")
