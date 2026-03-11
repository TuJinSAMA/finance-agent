import asyncio
import logging
from datetime import date

import pandas as pd
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.agents.data_agent.fetcher import _full_code
from src.agents.data_agent.providers import akshare_provider as provider
from src.agents.screener_config import screener_config
from src.models.stock import Stock, StockFundamental

logger = logging.getLogger(__name__)


async def fetch_valuation_batch(db: AsyncSession) -> int:
    """
    批量获取全市场估值指标（PE_TTM, PB, PS_TTM, 总市值, 流通市值）。
    使用 ak.stock_a_lg_indicator(stock="all") 一次性获取。
    返回写入/更新的行数。
    """
    logger.info("Fetching batch valuation data...")
    try:
        df = await provider.fetch_valuation_all()
    except Exception:
        logger.exception("Failed to fetch batch valuation data")
        return 0

    if df is None or df.empty:
        logger.error("stock_a_lg_indicator returned empty data")
        return 0

    stock_map = await _get_stock_code_map(db)
    today = date.today()
    records = []

    for _, row in df.iterrows():
        raw_code = str(row.get("stock_code", row.get("code", ""))).strip()
        if not raw_code:
            continue
        code = _full_code(raw_code)
        stock_id = stock_map.get(code)
        if stock_id is None:
            continue

        trade_date = row.get("trade_date")
        if trade_date is not None:
            try:
                report_date = pd.to_datetime(trade_date).date()
            except Exception:
                report_date = today
        else:
            report_date = today

        records.append({
            "stock_id": stock_id,
            "report_date": report_date,
            "pe_ttm": _safe_float(row.get("pe_ttm")),
            "pb": _safe_float(row.get("pb")),
            "ps_ttm": _safe_float(row.get("ps_ttm")),
            "market_cap": _safe_float(row.get("total_mv")),
            "float_market_cap": _safe_float(row.get("float_mv")),
        })

    if not records:
        return 0

    chunk_size = screener_config.db_batch_chunk_size
    for i in range(0, len(records), chunk_size):
        chunk = records[i : i + chunk_size]
        stmt = pg_insert(StockFundamental).values(chunk)
        stmt = stmt.on_conflict_do_update(
            index_elements=["stock_id", "report_date"],
            set_={
                "pe_ttm": stmt.excluded.pe_ttm,
                "pb": stmt.excluded.pb,
                "ps_ttm": stmt.excluded.ps_ttm,
                "market_cap": stmt.excluded.market_cap,
                "float_market_cap": stmt.excluded.float_market_cap,
            },
        )
        await db.execute(stmt)

    await db.commit()
    logger.info("Batch valuation data written: %d records", len(records))
    return len(records)


async def fetch_financial_single(
    db: AsyncSession,
    stock_code: str,
    stock_id: int,
) -> bool:
    """
    获取单只股票的财务指标（ROE, 毛利率, 净利率等），
    使用 ak.stock_financial_analysis_indicator()。
    返回是否成功。
    """
    try:
        df = await provider.fetch_financial_analysis(symbol=stock_code)
    except Exception:
        logger.debug("Failed to fetch financial indicators for %s", stock_code)
        return False

    if df is None or df.empty:
        return False

    latest = df.iloc[0]

    report_date_val = latest.get("日期")
    if report_date_val is not None:
        try:
            report_date = pd.to_datetime(report_date_val).date()
        except Exception:
            report_date = date.today()
    else:
        report_date = date.today()

    # 尝试从 total_shares 推算绝对经营现金流
    operating_cf = None
    cf_per_share = _safe_float(latest.get("每股经营现金流量(元)"))
    if cf_per_share is not None:
        stock_result = await db.execute(
            select(Stock.total_shares).where(Stock.id == stock_id)
        )
        total_shares = stock_result.scalar()
        if total_shares:
            operating_cf = round(cf_per_share * total_shares, 2)

    record = {
        "stock_id": stock_id,
        "report_date": report_date,
        "roe": _safe_float(latest.get("净资产收益率(%)")),
        "gross_margin": _safe_float(latest.get("销售毛利率(%)")),
        "net_margin": _safe_float(latest.get("销售净利率(%)")),
        "debt_ratio": _safe_float(latest.get("资产负债率(%)")),
        "revenue_yoy": _safe_float(latest.get("营业总收入同比增长率(%)")),
        "profit_yoy": _safe_float(latest.get("归属净利润同比增长率(%)")),
        "operating_cf": operating_cf,
    }

    stmt = pg_insert(StockFundamental).values([record])
    stmt = stmt.on_conflict_do_update(
        index_elements=["stock_id", "report_date"],
        set_={
            "roe": stmt.excluded.roe,
            "gross_margin": stmt.excluded.gross_margin,
            "net_margin": stmt.excluded.net_margin,
            "debt_ratio": stmt.excluded.debt_ratio,
            "revenue_yoy": stmt.excluded.revenue_yoy,
            "profit_yoy": stmt.excluded.profit_yoy,
            "operating_cf": stmt.excluded.operating_cf,
        },
    )
    await db.execute(stmt)
    return True


async def fetch_fundamentals_full(db: AsyncSession) -> int:
    """
    完整基本面数据拉取：先批量估值，再逐只财务指标。
    db 参数仅用于批量估值，逐只财务指标使用独立短周期 session 避免连接超时。
    返回处理的股票数量。
    """
    from src.core.database import async_session

    await fetch_valuation_batch(db)

    result = await db.execute(select(Stock.id, Stock.code).order_by(Stock.id))
    stocks = result.all()

    processed = 0
    session = None
    rotate_every = 50

    try:
        for i, (stock_id, code) in enumerate(stocks):
            if i % rotate_every == 0:
                if session is not None:
                    await session.commit()
                    await session.close()
                session = async_session()

            raw_code = code.split(".")[0]
            ok = await fetch_financial_single(session, raw_code, stock_id)
            if ok:
                processed += 1

            if (i + 1) % 100 == 0:
                await session.commit()
                logger.info("Financial indicators progress: %d/%d", i + 1, len(stocks))

            await asyncio.sleep(screener_config.akshare_rate_limit + 0.2)
    finally:
        if session is not None:
            await session.commit()
            await session.close()

    logger.info("Fundamentals fetch complete: %d/%d stocks processed", processed, len(stocks))
    return processed


async def _get_stock_code_map(db: AsyncSession) -> dict[str, int]:
    result = await db.execute(select(Stock.id, Stock.code))
    return {row.code: row.id for row in result.all()}


def _safe_float(val) -> float | None:
    if val is None:
        return None
    try:
        v = float(val)
        return None if pd.isna(v) else v
    except (ValueError, TypeError):
        return None
