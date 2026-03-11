"""
首次运行脚本，回填历史数据。
预计耗时：30-60 分钟（5000只股票 × 180天数据）

用法：cd apps/api && uv run python -m scripts.backfill_history --days 180
      cd apps/api && uv run python -m scripts.backfill_history --days 180 --skip-fundamentals
      cd apps/api && uv run python -m scripts.backfill_history --step indicators  # 只跑技术指标
"""

import argparse
import asyncio
import logging
import sys
import time
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.exc import DBAPIError, OperationalError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("backfill")

BATCH_SIZE = 50
MAX_RETRIES = 3


async def _get_stock_id_codes(async_session) -> list[tuple[int, str]]:
    """Fetch all (stock_id, code) pairs using a short-lived session."""
    from src.models.stock import Stock

    async with async_session() as session:
        result = await session.execute(select(Stock.id, Stock.code).order_by(Stock.id))
        return [(row.id, row.code) for row in result.all()]


async def run_backfill(days: int, skip_fundamentals: bool, step: str | None):
    from src.agents.data_agent.fetcher import DataAgent
    from src.agents.data_agent.fundamentals import fetch_fundamentals_full
    from src.agents.data_agent.indicators import compute_and_store_indicators
    from src.agents.screener_config import screener_config
    from src.core.database import async_session
    from src.models.stock import StockDailyQuote

    t0 = time.time()

    # ── Step 1: Sync stock list ──
    if step is None or step == "stocks":
        logger.info("=" * 60)
        logger.info("Step 1: Syncing stock list...")
        async with async_session() as session:
            agent = DataAgent(session)
            count = await agent.sync_stock_list()
            logger.info("Stock list synced: %d stocks", count)

        logger.info("Syncing industry mapping (this may take a few minutes)...")
        async with async_session() as session:
            agent = DataAgent(session)
            updated = await agent.sync_industry_mapping()
            logger.info("Industry mapping done: %d updates", updated)

        logger.info("Syncing list dates from exchange APIs...")
        async with async_session() as session:
            agent = DataAgent(session)
            ld_count = await agent.sync_list_dates()
            logger.info("List dates synced: %d stocks", ld_count)

        if step == "stocks":
            return

    # ── Step 2: Backfill historical daily quotes ──
    if step is None or step == "quotes":
        logger.info("=" * 60)
        logger.info("Step 2: Backfilling %d days of daily quotes...", days)

        stocks = await _get_stock_id_codes(async_session)
        total = len(stocks)

        for batch_start in range(0, total, BATCH_SIZE):
            batch = stocks[batch_start : batch_start + BATCH_SIZE]
            async with async_session() as session:
                agent = DataAgent(session)
                for j, (stock_id, code) in enumerate(batch):
                    i = batch_start + j
                    raw_code = code.split(".")[0]

                    for attempt in range(MAX_RETRIES):
                        try:
                            existing_count = await session.execute(
                                select(func.count())
                                .select_from(StockDailyQuote)
                                .where(StockDailyQuote.stock_id == stock_id)
                            )
                            cnt = existing_count.scalar() or 0
                            if cnt >= days * 0.6:
                                if (i + 1) % 500 == 0:
                                    logger.info("Progress: %d/%d (skipped %s — already has %d rows)",
                                                i + 1, total, code, cnt)
                                break

                            rows = await agent.fetch_daily_quotes_history(raw_code, stock_id, days=days)

                            if (i + 1) % 100 == 0:
                                logger.info("Progress: %d/%d stocks (latest: %s, %d rows)",
                                            i + 1, total, code, rows)
                            break
                        except (DBAPIError, OperationalError, OSError) as e:
                            logger.warning("Connection error at %s (attempt %d/%d): %s",
                                           code, attempt + 1, MAX_RETRIES, e)
                            try:
                                await session.rollback()
                            except Exception:
                                pass
                            if attempt < MAX_RETRIES - 1:
                                await asyncio.sleep(2 ** attempt)
                            else:
                                logger.error("Skipping %s after %d retries", code, MAX_RETRIES)

                    await asyncio.sleep(screener_config.akshare_rate_limit)

        logger.info("Daily quotes backfill complete.")
        if step == "quotes":
            return

    # ── Step 3: Compute technical indicators ──
    if step is None or step == "indicators":
        logger.info("=" * 60)
        logger.info("Step 3: Computing technical indicators...")

        stocks = await _get_stock_id_codes(async_session)
        total = len(stocks)
        success = 0

        for batch_start in range(0, total, BATCH_SIZE):
            batch = stocks[batch_start : batch_start + BATCH_SIZE]
            async with async_session() as session:
                for j, (stock_id, _code) in enumerate(batch):
                    i = batch_start + j
                    ok = await compute_and_store_indicators(session, stock_id, date.today())
                    if ok:
                        success += 1

                    if (i + 1) % 500 == 0:
                        await session.commit()
                        logger.info("Indicators progress: %d/%d (%d computed)", i + 1, total, success)

                await session.commit()

        logger.info("Technical indicators complete: %d/%d stocks", success, total)
        if step == "indicators":
            return

    # ── Step 4: Fetch fundamentals ──
    if not skip_fundamentals and (step is None or step == "fundamentals"):
        logger.info("=" * 60)
        logger.info("Step 4: Fetching fundamental data...")
        async with async_session() as session:
            processed = await fetch_fundamentals_full(session)
            logger.info("Fundamentals complete: %d stocks processed", processed)

    elapsed = time.time() - t0
    logger.info("=" * 60)
    logger.info("Backfill finished in %.1f minutes", elapsed / 60)


def main():
    parser = argparse.ArgumentParser(description="Backfill historical stock data")
    from src.agents.screener_config import screener_config
    parser.add_argument("--days", type=int, default=screener_config.default_backfill_days,
                        help=f"Number of days to backfill (default: {screener_config.default_backfill_days})")
    parser.add_argument("--skip-fundamentals", action="store_true", help="Skip fundamental data fetch")
    parser.add_argument("--step", choices=["stocks", "quotes", "indicators", "fundamentals"],
                        help="Run only a specific step")
    args = parser.parse_args()

    logger.info("Starting backfill: days=%d, skip_fundamentals=%s, step=%s",
                args.days, args.skip_fundamentals, args.step)

    try:
        asyncio.run(run_backfill(args.days, args.skip_fundamentals, args.step))
    except KeyboardInterrupt:
        logger.info("Backfill interrupted by user. You can resume by running the script again.")
        sys.exit(1)


if __name__ == "__main__":
    main()
