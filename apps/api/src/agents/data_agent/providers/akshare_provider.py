"""
AKShare 数据源适配层。
所有对 AKShare 库的直接调用都集中在这个文件里。
后续接入美股（yfinance）、加密货币等数据源时，在 providers/ 下新增对应文件即可，
上层 fetcher / fundamentals / trading_calendar 无需改动。
"""

import asyncio
import logging

import akshare as ak
import pandas as pd

logger = logging.getLogger(__name__)

RETRY_ATTEMPTS = 3
RETRY_BACKOFF = [1, 2, 4]


async def _call(func, *args, **kwargs) -> pd.DataFrame:
    """Wrap synchronous AKShare calls with retry + asyncio.to_thread."""
    for attempt in range(RETRY_ATTEMPTS):
        try:
            return await asyncio.to_thread(func, *args, **kwargs)
        except Exception:
            if attempt == RETRY_ATTEMPTS - 1:
                raise
            wait = RETRY_BACKOFF[attempt]
            logger.warning(
                "AKShare call %s failed (attempt %d/%d), retrying in %ds...",
                func.__name__, attempt + 1, RETRY_ATTEMPTS, wait,
            )
            await asyncio.sleep(wait)


# ── Stock List ──────────────────────────────────────────────


async def fetch_a_share_spot() -> pd.DataFrame:
    """全市场 A 股实时行情快照（代码、名称、最新价、成交量等）。"""
    return await _call(ak.stock_zh_a_spot_em)


# ── Industry ────────────────────────────────────────────────


async def fetch_industry_board_list() -> pd.DataFrame:
    """行业板块列表。"""
    return await _call(ak.stock_board_industry_name_em)


async def fetch_industry_constituents(industry_name: str) -> pd.DataFrame:
    """单个行业的成分股列表。"""
    return await _call(ak.stock_board_industry_cons_em, symbol=industry_name)


# ── Daily Quotes ────────────────────────────────────────────


async def fetch_stock_history(
    symbol: str,
    start_date: str,
    end_date: str,
    period: str = "daily",
    adjust: str = "qfq",
) -> pd.DataFrame:
    """单只股票历史日线（前复权）。symbol 为纯数字如 '600519'。"""
    return await _call(
        ak.stock_zh_a_hist,
        symbol=symbol,
        period=period,
        start_date=start_date,
        end_date=end_date,
        adjust=adjust,
    )


# ── Fundamentals ────────────────────────────────────────────


async def fetch_valuation_all() -> pd.DataFrame:
    """
    全市场估值指标（PE动态, PB, 市值等），批量接口。
    原 stock_a_lg_indicator 数据源已停服，改用 stock_zh_a_spot_em 中的估值字段。
    """
    df = await _call(ak.stock_zh_a_spot_em)
    if df is None or df.empty:
        return df
    return df[["代码", "市盈率-动态", "市净率", "总市值", "流通市值"]].rename(columns={
        "代码": "code",
        "市盈率-动态": "pe_ttm",
        "市净率": "pb",
        "总市值": "total_mv",
        "流通市值": "float_mv",
    })


async def fetch_financial_report_batch(date: str = "20240930") -> pd.DataFrame:
    """
    全市场业绩报表（东方财富），批量接口，一次返回 ~5900 只股票。
    date 格式: YYYYMMDD，须为季报日期（0331/0630/0930/1231）。
    返回列: 股票代码, 净资产收益率, 销售毛利率, 每股经营现金流量, 所处行业 等。
    """
    return await _call(ak.stock_yjbb_em, date=date)


# ── Stock Info (Listing Dates) ─────────────────────────────


async def fetch_sh_stock_info(indicator: str = "主板A股") -> pd.DataFrame:
    """上交所股票信息（含上市日期）。indicator: '主板A股' | '科创板'。"""
    return await _call(ak.stock_info_sh_name_code, indicator=indicator)


async def fetch_sz_stock_info(indicator: str = "A股列表") -> pd.DataFrame:
    """深交所股票信息（含上市日期）。indicator: 'A股列表'。"""
    return await _call(ak.stock_info_sz_name_code, indicator=indicator)


# ── News / Events ──────────────────────────────────────────


async def fetch_stock_news(symbol: str) -> pd.DataFrame:
    """个股新闻（东方财富）。返回列: 新闻标题, 新闻内容, 发布时间, 文章来源, 新闻链接。"""
    return await _call(ak.stock_news_em, symbol=symbol)


# ── Trading Calendar ────────────────────────────────────────


async def fetch_trading_calendar() -> pd.DataFrame:
    """A 股交易日历（从 1990 至今年年底）。"""
    return await _call(ak.tool_trade_date_hist_sina)
