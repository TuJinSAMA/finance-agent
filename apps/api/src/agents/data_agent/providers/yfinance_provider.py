"""
yfinance 数据源适配层 — 作为 AkShare 的备用数据源。

支持功能：
  - fetch_stock_history: 单只股票历史日线（前复权）
  - fetch_a_share_spot: 批量股票实时行情（需传入股票列表）

不支持：
  - 估值数据（PE/PB）、财务指标、行业分类、新闻、交易日历

代码格式：
  - yfinance 使用 '600519.SS'（上交所）/ '000001.SZ'（深交所）
  - 内部格式为 '600519.SH' / '000001.SZ'
"""

import asyncio
import logging
from datetime import date, timedelta

import pandas as pd

logger = logging.getLogger(__name__)

RETRY_ATTEMPTS = 3
RETRY_BACKOFF = [1, 2, 4]


def _to_yf_code(code: str) -> str:
    """
    将内部格式转换为 yfinance 格式。
    '600519.SH' / '600519' → '600519.SS'
    '000001.SZ' / '000001' → '000001.SZ'
    '430047.BJ' / '430047' → '430047.BJ' (北交所 yfinance 支持有限)
    """
    if "." in code:
        prefix, suffix = code.rsplit(".", 1)
    else:
        prefix = code
        suffix = ""

    if not suffix:
        if prefix.startswith("6"):
            suffix = "SH"
        elif prefix.startswith(("0", "3")):
            suffix = "SZ"
        elif prefix.startswith(("4", "8")):
            suffix = "BJ"
        else:
            suffix = "SH"

    if suffix == "SH":
        return f"{prefix}.SS"
    if suffix in ("SZ", "BJ"):
        return f"{prefix}.{suffix}"
    return code


def _from_yf_code(yf_code: str) -> str:
    """
    将 yfinance 格式转换为内部格式。
    '600519.SS' → '600519.SH'
    '000001.SZ' → '000001.SZ'
    """
    if "." not in yf_code:
        return yf_code
    prefix, suffix = yf_code.rsplit(".", 1)
    if suffix == "SS":
        return f"{prefix}.SH"
    return f"{prefix}.{suffix}"


def _plain_code(code: str) -> str:
    """提取纯 6 位代码。"""
    return code.split(".")[0]


async def _call(func, *args, **kwargs):
    """Wrap synchronous yfinance calls with retry + asyncio.to_thread."""
    for attempt in range(RETRY_ATTEMPTS):
        try:
            return await asyncio.to_thread(func, *args, **kwargs)
        except Exception as e:
            if attempt == RETRY_ATTEMPTS - 1:
                raise
            wait = RETRY_BACKOFF[attempt]
            logger.warning(
                "yfinance call failed (attempt %d/%d): %s. Retrying in %ds...",
                attempt + 1,
                RETRY_ATTEMPTS,
                e,
                wait,
            )
            await asyncio.sleep(wait)


async def fetch_stock_history(
    symbol: str,
    start_date: str,
    end_date: str,
    period: str = "daily",
    adjust: str = "qfq",
) -> pd.DataFrame:
    """
    获取单只股票历史日线数据。
    symbol: 纯代码 '600519' 或内部格式 '600519.SH'
    start_date / end_date: YYYYMMDD 或 YYYY-MM-DD 格式
    adjust: 'qfq' 前复权 / 'hfq' 后复权 / None 不复权

    返回列：日期, 开盘, 最高, 最低, 收盘, 成交量, 成交额, 换手率, 涨跌幅
    """
    import yfinance as yf

    yf_code = _to_yf_code(symbol)

    start_str = _norm_date(start_date)
    end_str = _norm_date(end_date)

    auto_adjust = adjust == "qfq"

    try:
        ticker = yf.Ticker(yf_code)
        df = await _call(
            ticker.history,
            start=start_str,
            end=end_str,
            auto_adjust=auto_adjust,
        )
    except Exception as e:
        logger.error("yfinance fetch_stock_history failed for %s: %s", yf_code, e)
        return pd.DataFrame()

    if df is None or df.empty:
        return pd.DataFrame()

    df = df.reset_index()
    df["日期"] = pd.to_datetime(df["Date"]).dt.date

    df["涨跌幅"] = df["Close"].pct_change() * 100

    df["成交额"] = df["Close"] * df["Volume"]

    df["换手率"] = None

    df = df.rename(
        columns={
            "Open": "开盘",
            "High": "最高",
            "Low": "最低",
            "Close": "收盘",
            "Volume": "成交量",
        }
    )

    cols = [
        "日期",
        "开盘",
        "最高",
        "最低",
        "收盘",
        "成交量",
        "成交额",
        "换手率",
        "涨跌幅",
    ]
    return df[cols].reset_index(drop=True)


async def fetch_a_share_spot(codes: list[str] | None = None) -> pd.DataFrame:
    """
    批量获取股票实时行情快照。

    注意：yfinance 无法获取全市场股票列表，需要传入 codes 参数。
    如果 codes 为 None，返回空 DataFrame。

    codes: 纯代码列表 ['600519', '000001'] 或内部格式 ['600519.SH', '000001.SZ']

    返回列：代码, 名称, 今开, 最高, 最低, 最新价, 成交量, 成交额,
             换手率, 涨跌幅, 市盈率-动态, 市净率, 总市值, 流通市值
    """
    import yfinance as yf

    if not codes:
        logger.warning(
            "fetch_a_share_spot: codes is empty, yfinance requires a list of stock codes"
        )
        return pd.DataFrame()

    yf_codes = [_to_yf_code(c) for c in codes]

    end_date = date.today() + timedelta(days=1)
    start_date = date.today() - timedelta(days=7)

    try:
        df = await _call(
            yf.download,
            yf_codes,
            start=start_date,
            end=end_date,
            progress=False,
            group_by="ticker",
        )
    except Exception as e:
        logger.error("yfinance download failed: %s", e)
        return pd.DataFrame()

    if df is None or df.empty:
        return pd.DataFrame()

    records = []
    for code, yf_code in zip(codes, yf_codes):
        plain = _plain_code(code)

        try:
            if len(codes) == 1:
                stock_df = df
            else:
                stock_df = df[yf_code] if yf_code in df.columns.levels[0] else None

            if stock_df is None or stock_df.empty:
                continue

            latest = stock_df.iloc[-1]

            records.append(
                {
                    "代码": plain,
                    "名称": "",
                    "今开": latest.get("Open"),
                    "最高": latest.get("High"),
                    "最低": latest.get("Low"),
                    "最新价": latest.get("Close"),
                    "成交量": latest.get("Volume"),
                    "成交额": latest.get("Close", 0) * latest.get("Volume", 0),
                    "换手率": None,
                    "涨跌幅": None,
                    "市盈率-动态": None,
                    "市净率": None,
                    "总市值": None,
                    "流通市值": None,
                }
            )
        except Exception as e:
            logger.debug("Failed to parse data for %s: %s", code, e)
            continue

    return pd.DataFrame(records)


async def fetch_industry_board_list() -> pd.DataFrame:
    """yfinance 不支持行业分类。"""
    logger.warning("yfinance does not support industry board list")
    return pd.DataFrame()


async def fetch_industry_constituents(industry_name: str) -> pd.DataFrame:
    """yfinance 不支持行业成分股。"""
    logger.warning("yfinance does not support industry constituents")
    return pd.DataFrame()


async def fetch_valuation_all() -> pd.DataFrame:
    """yfinance 不支持估值数据。"""
    logger.warning("yfinance does not support valuation data")
    return pd.DataFrame()


async def fetch_financial_report_batch(date: str = "20240930") -> pd.DataFrame:
    """yfinance 不支持财务指标。"""
    logger.warning("yfinance does not support financial report batch")
    return pd.DataFrame()


async def fetch_sh_stock_info(indicator: str = "主板A股") -> pd.DataFrame:
    """yfinance 不支持上市日期。"""
    logger.warning("yfinance does not support stock listing dates")
    return pd.DataFrame()


async def fetch_sz_stock_info(indicator: str = "A股列表") -> pd.DataFrame:
    """yfinance 不支持上市日期。"""
    logger.warning("yfinance does not support stock listing dates")
    return pd.DataFrame()


async def fetch_stock_news(symbol: str) -> pd.DataFrame:
    """yfinance 新闻功能不适用于 A 股。"""
    logger.warning("yfinance does not support A-share news")
    return pd.DataFrame()


async def fetch_trading_calendar() -> pd.DataFrame:
    """yfinance 不支持 A 股交易日历。"""
    logger.warning("yfinance does not support A-share trading calendar")
    return pd.DataFrame()


def _norm_date(d: str) -> str:
    """YYYYMMDD → YYYY-MM-DD。已经是 YYYY-MM-DD 格式的直接返回。"""
    d = str(d).strip()
    if len(d) == 8 and d.isdigit():
        return f"{d[:4]}-{d[4:6]}-{d[6:8]}"
    return d
