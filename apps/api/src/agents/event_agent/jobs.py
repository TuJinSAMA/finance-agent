"""
APScheduler job wrapper functions for Event Agent.
Synchronous entry points that bridge to async methods via asyncio.run().
"""

import asyncio
import logging
from datetime import date, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.agents.data_agent.trading_calendar import trading_calendar

logger = logging.getLogger(__name__)


def morning_event_scan_job():
    """每日 06:30 合并扫描（关注池 + 用户持仓）。"""
    if not trading_calendar.is_trading_day():
        logger.info("morning_event_scan_job: not a trading day, skipping")
        return
    asyncio.run(_morning_event_scan_async())


async def _morning_event_scan_async():
    from src.agents.event_agent.analyzer import CatalystAnalyzer
    from src.agents.event_agent.scanner import EventScanner
    from src.core.database import async_session
    from src.models.stock import Stock
    from src.models.watchlist import Watchlist

    async with async_session() as session:
        try:
            # 1. 获取关注池股票 ID
            watchlist_result = await session.execute(
                select(Watchlist.stock_id).where(Watchlist.status == "active")
            )
            watchlist_ids = {row[0] for row in watchlist_result.all()}

            # 2. 获取用户持仓股票 ID（Phase 5 实现前为空集）
            portfolio_ids = await _get_portfolio_stock_ids(session)

            # 3. 合并去重
            all_stock_ids = list(watchlist_ids | portfolio_ids)
            if not all_stock_ids:
                logger.info("No stocks to scan (watchlist and portfolio both empty)")
                return

            # 4. ID → code 映射
            code_result = await session.execute(
                select(Stock.code).where(Stock.id.in_(all_stock_ids))
            )
            stock_codes = [row[0] for row in code_result.all()]

            overlap = len(watchlist_ids & portfolio_ids)
            logger.info(
                "Morning scan: %d stocks (watchlist=%d, portfolio=%d, overlap=%d)",
                len(all_stock_ids), len(watchlist_ids), len(portfolio_ids), overlap,
            )

            # 5. 扫描新闻
            scanner = EventScanner(session)
            news_count = await scanner.scan_stock_news(stock_codes)
            await session.commit()

            # 6. LLM 分析未分析事件
            analyzer = CatalystAnalyzer(session)
            analyzed_count = await analyzer.analyze_unanalyzed_events(target_date=date.today())
            await session.commit()

            # 7. 更新关注池的 catalyst_summary
            updated = await _update_watchlist_catalysts(session, watchlist_ids)
            await session.commit()

            # 8. 持仓事件联动：为持仓股票的重大事件生成 alert
            from src.agents.portfolio_agent.monitor import PortfolioMonitor

            monitor = PortfolioMonitor(session)
            alerts_created = await monitor.check_holdings_against_events(
                target_date=date.today()
            )
            await session.commit()

            logger.info(
                "morning_event_scan completed: news=%d, analyzed=%d, "
                "watchlist_catalyst_updated=%d, portfolio_alerts=%d",
                news_count, analyzed_count, updated, alerts_created,
            )
        except Exception:
            logger.exception("morning_event_scan_job failed")


async def _get_portfolio_stock_ids(db: AsyncSession) -> set[int]:
    """获取所有用户持仓股票 ID（去重）。"""
    from src.models.portfolio import PortfolioHolding

    result = await db.execute(
        select(PortfolioHolding.stock_id).distinct()
    )
    return {row[0] for row in result.all()}


async def _update_watchlist_catalysts(
    db: AsyncSession,
    watchlist_stock_ids: set[int],
) -> int:
    """
    更新关注池的催化剂摘要。
    对每只关注池股票，取近期事件中 impact_score 最高的，
    写入 Watchlist.catalyst_summary 和 catalyst_date。
    """
    if not watchlist_stock_ids:
        return 0

    from src.agents.screener_config import screener_config as cfg
    from src.models.event import StockEvent
    from src.models.watchlist import Watchlist

    cutoff_date = date.today() - timedelta(days=cfg.event_lookback_days)

    # 取每只股票近期事件中 impact_score 最高的
    result = await db.execute(
        select(StockEvent)
        .where(StockEvent.stock_id.in_(watchlist_stock_ids))
        .where(StockEvent.is_analyzed.is_(True))
        .where(StockEvent.event_date >= cutoff_date)
        .where(StockEvent.impact_score.is_not(None))
        .order_by(StockEvent.stock_id, StockEvent.impact_score.desc())
    )
    events = result.scalars().all()

    best_by_stock: dict[int, StockEvent] = {}
    for event in events:
        if event.stock_id not in best_by_stock:
            best_by_stock[event.stock_id] = event

    updated = 0
    for stock_id, event in best_by_stock.items():
        catalyst_summary = {
            "top_sentiment": event.sentiment,
            "top_impact_score": float(event.impact_score) if event.impact_score else 0,
            "top_catalyst_type": event.catalyst_type,
            "top_key_point": event.key_point,
            "top_title": event.title,
            "event_count": sum(1 for e in events if e.stock_id == stock_id),
        }
        await db.execute(
            update(Watchlist)
            .where(Watchlist.stock_id == stock_id)
            .where(Watchlist.status == "active")
            .values(
                catalyst_summary=catalyst_summary,
                catalyst_date=event.event_date,
            )
        )
        updated += 1

    # 无近期事件的关注池股票，清空 catalyst
    no_event_ids = watchlist_stock_ids - set(best_by_stock.keys())
    if no_event_ids:
        await db.execute(
            update(Watchlist)
            .where(Watchlist.stock_id.in_(no_event_ids))
            .where(Watchlist.status == "active")
            .values(catalyst_summary=None, catalyst_date=None)
        )

    await db.flush()
    return updated
