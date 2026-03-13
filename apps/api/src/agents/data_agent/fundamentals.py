import logging
from datetime import date

import pandas as pd
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.agents.data_agent.fetcher import _full_code
from src.agents.data_agent.providers import tushare_provider as provider
from src.agents.screener_config import screener_config
from src.models.stock import Stock, StockFundamental

logger = logging.getLogger(__name__)

REPORT_DATES = ["1231", "0930", "0630", "0331"]


def _latest_report_date_str() -> str:
    """推算最新可用的季报日期（YYYYMMDD 格式）。"""
    today = date.today()
    year = today.year
    # 年报一般 4 月底前披露完，三季报 10 月底前，中报 8 月底前，一季报 4 月底前
    # 保守取上一个已披露完毕的报告期
    if today.month >= 11:
        return f"{year}0930"
    if today.month >= 9:
        return f"{year}0630"
    if today.month >= 5:
        return f"{year}0331"
    return f"{year - 1}1231"


async def fetch_valuation_batch(db: AsyncSession) -> int:
    """
    批量获取全市场估值指标（PE动态, PB, 总市值, 流通市值）。
    数据来自 stock_zh_a_spot_em 的估值字段。
    返回写入/更新的行数。
    """
    logger.info("Fetching batch valuation data...")
    try:
        df = await provider.fetch_valuation_all()
    except Exception:
        logger.exception("Failed to fetch batch valuation data")
        return 0

    if df is None or df.empty:
        logger.error("fetch_valuation_all returned empty data")
        return 0

    stock_map = await _get_stock_code_map(db)
    today = date.today()
    records = []

    for _, row in df.iterrows():
        raw_code = str(row.get("code", "")).strip()
        if not raw_code:
            continue
        code = _full_code(raw_code)
        stock_id = stock_map.get(code)
        if stock_id is None:
            continue

        records.append({
            "stock_id": stock_id,
            "report_date": today,
            "pe_ttm": _safe_float(row.get("pe_ttm")),
            "pb": _safe_float(row.get("pb")),
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
                "market_cap": stmt.excluded.market_cap,
                "float_market_cap": stmt.excluded.float_market_cap,
            },
        )
        await db.execute(stmt)

    await db.commit()
    logger.info("Batch valuation data written: %d records", len(records))
    return len(records)


async def fetch_financial_batch(db: AsyncSession) -> int:
    """
    批量获取全市场财务指标（ROE, 毛利率, 每股经营现金流等）。
    使用东方财富业绩报表接口 stock_yjbb_em，一次返回全市场 ~5900 只股票。
    返回写入/更新的行数。
    """
    report_date_str = _latest_report_date_str()
    report_date = date(
        int(report_date_str[:4]), int(report_date_str[4:6]), int(report_date_str[6:8])
    )
    logger.info("Fetching batch financial data for report period %s...", report_date_str)

    try:
        df = await provider.fetch_financial_report_batch(date=report_date_str)
    except Exception:
        logger.exception("Failed to fetch batch financial data")
        return 0

    if df is None or df.empty:
        logger.error("fetch_financial_report_batch returned empty data")
        return 0

    stock_map = await _get_stock_code_map(db)

    records = []
    for _, row in df.iterrows():
        raw_code = str(row.get("股票代码", "")).strip()
        if not raw_code:
            continue
        code = _full_code(raw_code)
        stock_id = stock_map.get(code)
        if stock_id is None:
            continue

        # ocf_to_revenue 是经营现金流/营收比率（0~1），存入 operating_cf 字段
        records.append({
            "stock_id": stock_id,
            "report_date": report_date,
            "roe": _safe_float(row.get("净资产收益率")),
            "gross_margin": _safe_float(row.get("销售毛利率")),
            "revenue_yoy": _safe_float(row.get("营业总收入-同比增长")),
            "profit_yoy": _safe_float(row.get("净利润-同比增长")),
            "operating_cf": _safe_float(row.get("经营现金流率")),
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
                "roe": stmt.excluded.roe,
                "gross_margin": stmt.excluded.gross_margin,
                "revenue_yoy": stmt.excluded.revenue_yoy,
                "profit_yoy": stmt.excluded.profit_yoy,
                "operating_cf": stmt.excluded.operating_cf,
            },
        )
        await db.execute(stmt)

    await db.commit()
    logger.info("Batch financial data written: %d records (period=%s)", len(records), report_date_str)
    return len(records)


async def fetch_fundamentals_full(db: AsyncSession) -> int:
    """
    完整基本面数据拉取：批量估值 + 批量财务指标。
    两步都是批量接口，总耗时约 10-15 秒。
    返回处理的股票数量。
    """
    valuation_count = await fetch_valuation_batch(db)
    financial_count = await fetch_financial_batch(db)

    total = max(valuation_count, financial_count)
    logger.info(
        "Fundamentals fetch complete: valuation=%d, financial=%d",
        valuation_count, financial_count,
    )
    return total


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
