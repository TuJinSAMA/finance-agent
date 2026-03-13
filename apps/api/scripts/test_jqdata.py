"""
JQData 接口连通性测试脚本。
逐一测试 jqdata_provider 中使用的所有接口，每个接口打印结果摘要。

用法：
    cd apps/api && uv run python -m scripts.test_jqdata
"""

import asyncio
import logging
import sys
from datetime import date

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("test_jqdata")

PASS = "\033[92m[PASS]\033[0m"
FAIL = "\033[91m[FAIL]\033[0m"
SKIP = "\033[93m[SKIP]\033[0m"


def _auth():
    """登录 JQData，返回 jqdatasdk 模块。"""
    from src.core.config import settings
    import jqdatasdk as jq

    logger.info("Authenticating with JQData (user=%s)...", settings.JQDATA_USERNAME)
    jq.auth(settings.JQDATA_USERNAME, settings.JQDATA_PASSWORD)
    logger.info("Auth success.")
    return jq


def test_get_all_securities(jq) -> list[str]:
    """get_all_securities — 全市场股票列表"""
    logger.info("─" * 50)
    logger.info("TEST: get_all_securities(types=['stock'])")
    try:
        df = jq.get_all_securities(types=["stock"])
        logger.info("  rows=%d  columns=%s", len(df), list(df.columns))
        logger.info("  sample:\n%s", df.head(3).to_string())
        print(PASS, "get_all_securities")
        codes = list(df.index[:20])  # 取前 20 只用于后续测试
        return codes
    except Exception as e:
        logger.exception("  FAILED: %s", e)
        print(FAIL, "get_all_securities")
        return []


def test_get_price_single(jq):
    """get_price — 单只股票"""
    logger.info("─" * 50)
    logger.info("TEST: get_price (single stock: 600519.XSHG)")
    try:
        today = date.today().isoformat()
        df = jq.get_price(
            "600519.XSHG",
            end_date=today,
            count=3,
            frequency="daily",
            fields=["open", "close", "high", "low", "volume", "money", "paused"],
            skip_paused=False,
            fq="pre",
            panel=False,
        )
        logger.info("  rows=%d  columns=%s", len(df), list(df.columns))
        logger.info("  data:\n%s", df.to_string())
        print(PASS, "get_price (single)")
    except Exception as e:
        logger.exception("  FAILED: %s", e)
        print(FAIL, "get_price (single)")


def test_get_price_batch(jq, codes: list[str]):
    """get_price — 批量（模拟 fetch_a_share_spot 的调用方式）"""
    logger.info("─" * 50)
    batch = codes[:10] if codes else ["600519.XSHG", "000001.XSHE"]
    logger.info("TEST: get_price (batch, %d stocks)", len(batch))
    try:
        today = date.today().isoformat()
        df = jq.get_price(
            batch,
            end_date=today,
            count=1,
            frequency="daily",
            fields=["open", "close", "high", "low", "volume", "money", "paused"],
            skip_paused=False,
            fq="pre",
            panel=False,
        )
        logger.info("  type=%s", type(df))
        if df is not None:
            df = df.reset_index()
            logger.info("  rows=%d  columns=%s", len(df), list(df.columns))
            logger.info("  sample:\n%s", df.head(3).to_string())
        print(PASS, "get_price (batch)")
    except Exception as e:
        logger.exception("  FAILED: %s", e)
        print(FAIL, "get_price (batch)")


def test_get_valuation(jq, codes: list[str]):
    """get_valuation — 批量估值"""
    logger.info("─" * 50)
    batch = codes[:10] if codes else ["600519.XSHG", "000001.XSHE"]
    logger.info("TEST: get_valuation (batch, %d stocks)", len(batch))
    try:
        today = date.today().isoformat()
        df = jq.get_valuation(
            batch,
            end_date=today,
            count=1,
            fields=["pe_ratio", "pb_ratio", "market_cap", "circulating_market_cap", "turnover_ratio"],
        )
        logger.info("  rows=%d  columns=%s", len(df), list(df.columns))
        logger.info("  sample:\n%s", df.head(3).to_string())
        print(PASS, "get_valuation")
    except Exception as e:
        logger.exception("  FAILED: %s", e)
        print(FAIL, "get_valuation")


def test_get_industries(jq):
    """get_industries — 申万一级行业列表"""
    logger.info("─" * 50)
    logger.info("TEST: get_industries(name='sw_l1')")
    try:
        df = jq.get_industries(name="sw_l1")
        logger.info("  rows=%d  columns=%s", len(df), list(df.columns))
        logger.info("  sample:\n%s", df.head(5).to_string())
        print(PASS, "get_industries")
        return list(df.index[:1])
    except Exception as e:
        logger.exception("  FAILED: %s", e)
        print(FAIL, "get_industries")
        return []


def test_get_industry_stocks(jq, industry_codes: list[str]):
    """get_industry_stocks — 行业成分股"""
    logger.info("─" * 50)
    ind = industry_codes[0] if industry_codes else "801010"
    logger.info("TEST: get_industry_stocks(%s)", ind)
    try:
        stocks = jq.get_industry_stocks(ind)
        logger.info("  count=%d  sample=%s", len(stocks), stocks[:5])
        print(PASS, "get_industry_stocks")
    except Exception as e:
        logger.exception("  FAILED: %s", e)
        print(FAIL, "get_industry_stocks")


def test_get_history_fundamentals(jq, codes: list[str]):
    """get_history_fundamentals — 财务指标"""
    logger.info("─" * 50)
    batch = codes[:5] if codes else ["600519.XSHG", "000001.XSHE"]
    logger.info("TEST: get_history_fundamentals (batch=%d, stat_date='2024q3')", len(batch))
    try:
        from jqdatasdk import indicator
        df = jq.get_history_fundamentals(
            batch,
            fields=[
                indicator.roe,
                indicator.gross_profit_margin,
                indicator.operating_cash_flow_ps,
                indicator.inc_total_revenue_year_on_year,
                indicator.inc_net_profit_year_on_year,
            ],
            stat_date="2024q3",
            count=1,
        )
        logger.info("  rows=%d  columns=%s", len(df), list(df.columns))
        logger.info("  sample:\n%s", df.head(3).to_string())
        print(PASS, "get_history_fundamentals")
    except Exception as e:
        logger.exception("  FAILED: %s", e)
        print(FAIL, "get_history_fundamentals")


def test_get_trade_days(jq):
    """get_trade_days — 交易日历"""
    logger.info("─" * 50)
    logger.info("TEST: get_trade_days('2026-01-01', '2026-12-31')")
    try:
        days = jq.get_trade_days(start_date="2026-01-01", end_date="2026-12-31")
        logger.info("  count=%d  first=%s  last=%s", len(days), days[0], days[-1])
        print(PASS, "get_trade_days")
    except Exception as e:
        logger.exception("  FAILED: %s", e)
        print(FAIL, "get_trade_days")


def test_get_current_data(jq):
    """
    get_current_data — 实时行情快照（可选，部分账号权限不同）。
    若无权限会报错，不影响其他测试。
    """
    logger.info("─" * 50)
    logger.info("TEST: get_current_data(['600519.XSHG'])")
    try:
        data = jq.get_current_data(["600519.XSHG"])
        item = data.get("600519.XSHG")
        logger.info("  600519.XSHG: %s", item)
        print(PASS, "get_current_data")
    except Exception as e:
        logger.exception("  FAILED / NO PERMISSION: %s", e)
        print(SKIP, "get_current_data (may require extra permission)")


def main():
    jq = _auth()

    print()
    print("=" * 60)
    print("JQData API Connectivity Tests")
    print("=" * 60)

    codes = test_get_all_securities(jq)

    test_get_price_single(jq)
    test_get_price_batch(jq, codes)
    test_get_valuation(jq, codes)

    industry_codes = test_get_industries(jq)
    test_get_industry_stocks(jq, industry_codes)

    test_get_history_fundamentals(jq, codes)
    test_get_trade_days(jq)
    test_get_current_data(jq)

    print()
    print("=" * 60)
    print("All tests done.")
    print("=" * 60)


if __name__ == "__main__":
    main()
