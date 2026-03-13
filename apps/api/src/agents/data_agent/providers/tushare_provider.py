"""
Tushare 数据提供器 — 使用 Tushare Pro SDK 获取 A 股市场数据。

实现与 akshare_provider.py 相同的接口，可直接替换：
    from src.agents.data_agent.providers import tushare_provider as provider

认证：TUSHARE_TOKEN 环境变量（通过 settings.TUSHARE_TOKEN 读取）。
懒初始化：首次调用时创建 pro API 实例，使用 threading.Lock() 保证线程安全。
"""

import asyncio
import logging
import threading
from datetime import date, datetime, timedelta

import pandas as pd

logger = logging.getLogger(__name__)

_pro = None
_lock = threading.Lock()


def _ensure_auth():
    """懒初始化 Tushare pro API 实例（线程安全）。"""
    global _pro
    if _pro is not None:
        return _pro

    with _lock:
        if _pro is not None:
            return _pro

        try:
            import tushare as ts
            from src.core.config import settings

            token = settings.TUSHARE_TOKEN
            if not token:
                raise RuntimeError(
                    "TUSHARE_TOKEN is not set. "
                    "Please configure it in .env or environment variables."
                )
            _pro = ts.pro_api(token)
            logger.info("Tushare Pro API initialized successfully")
        except ImportError:
            raise RuntimeError(
                "tushare package is not installed. Run: uv add tushare"
            )

    return _pro


def _ts_code_to_plain(ts_code: str) -> str:
    """将 Tushare ts_code '600519.SH' → 纯代码 '600519'。"""
    return ts_code.split(".")[0] if "." in ts_code else ts_code


def _plain_to_ts_code(symbol: str) -> str:
    """将纯代码 '600519' → Tushare ts_code '600519.SH'/'000001.SZ'。"""
    if "." in symbol:
        return symbol  # 已经是 ts_code 格式
    if symbol.startswith("6") or symbol.startswith("9"):
        return f"{symbol}.SH"
    if symbol.startswith(("0", "3")):
        return f"{symbol}.SZ"
    if symbol.startswith(("4", "8")):
        return f"{symbol}.BJ"
    return f"{symbol}.SH"


async def _call_with_retry(func, *args, max_retries: int = 3, **kwargs):
    """在 asyncio.to_thread 中执行同步 Tushare 调用，带指数退避重试。"""
    for attempt in range(max_retries):
        try:
            return await asyncio.to_thread(func, *args, **kwargs)
        except Exception as e:
            if attempt < max_retries - 1:
                wait = 2 ** attempt
                logger.warning(
                    "Tushare call failed (attempt %d/%d): %s. Retrying in %ds...",
                    attempt + 1, max_retries, e, wait,
                )
                await asyncio.sleep(wait)
            else:
                logger.error("Tushare call failed after %d attempts: %s", max_retries, e)
                raise


async def fetch_a_share_spot() -> pd.DataFrame:
    """
    获取全市场 A 股实时行情快照（当日）。
    合并 daily（OHLCV）+ daily_basic（PE/PB/市值）+ stock_basic（名称/ST标记）。

    返回列：代码, 名称, 今开, 最高, 最低, 最新价, 成交量, 成交额,
             换手率, 涨跌幅, 市盈率-动态, 市净率, 总市值, 流通市值
    """
    pro = _ensure_auth()
    today = date.today().strftime("%Y%m%d")

    async def _fetch_daily():
        return await _call_with_retry(
            pro.daily, trade_date=today,
            fields="ts_code,open,high,low,close,vol,amount,pct_chg",
        )

    async def _fetch_basic():
        return await _call_with_retry(
            pro.daily_basic, ts_code="", trade_date=today,
            fields="ts_code,turnover_rate,pe_ttm,pb,total_mv,circ_mv",
        )

    async def _fetch_stock_basic():
        return await _call_with_retry(
            pro.stock_basic, list_status="L",
            fields="ts_code,name,is_hs",
        )

    daily_df, basic_df, stock_df = await asyncio.gather(
        _fetch_daily(), _fetch_basic(), _fetch_stock_basic()
    )

    if daily_df is None or daily_df.empty:
        logger.warning("fetch_a_share_spot: daily data is empty for %s", today)
        return pd.DataFrame()

    # 合并 daily + daily_basic
    if basic_df is not None and not basic_df.empty:
        df = daily_df.merge(basic_df, on="ts_code", how="left")
    else:
        df = daily_df.copy()
        df["turnover_rate"] = None
        df["pe_ttm"] = None
        df["pb"] = None
        df["total_mv"] = None
        df["circ_mv"] = None

    # 合并 stock_basic（名称）
    if stock_df is not None and not stock_df.empty:
        df = df.merge(stock_df[["ts_code", "name"]], on="ts_code", how="left")
    else:
        df["name"] = ""

    # 提取纯 6 位代码
    df["代码"] = df["ts_code"].apply(_ts_code_to_plain)

    # 重命名到 AKShare 兼容的列名
    df = df.rename(columns={
        "name": "名称",
        "open": "今开",
        "high": "最高",
        "low": "最低",
        "close": "最新价",
        "vol": "成交量",
        "amount": "成交额",
        "turnover_rate": "换手率",
        "pct_chg": "涨跌幅",
        "pe_ttm": "市盈率-动态",
        "pb": "市净率",
        "total_mv": "总市值",
        "circ_mv": "流通市值",
    })

    # Tushare 成交量单位是"手"，成交额单位是"千元"；转换为与 AKShare 一致的单位
    # AKShare: 成交量（手），成交额（元）→ tushare amount（千元）* 1000
    if "成交额" in df.columns:
        df["成交额"] = pd.to_numeric(df["成交额"], errors="coerce") * 1000

    # Tushare 总市值/流通市值单位是"万元"；转换为"元"
    for col in ("总市值", "流通市值"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce") * 10000

    cols = ["代码", "名称", "今开", "最高", "最低", "最新价",
            "成交量", "成交额", "换手率", "涨跌幅",
            "市盈率-动态", "市净率", "总市值", "流通市值"]
    existing = [c for c in cols if c in df.columns]
    return df[existing].reset_index(drop=True)


async def fetch_industry_board_list() -> pd.DataFrame:
    """
    获取申万一级行业分类列表。

    返回列：板块代码, 板块名称
    """
    pro = _ensure_auth()

    df = await _call_with_retry(
        pro.index_classify, level="L1", src="SW2021",
    )

    if df is None or df.empty:
        return pd.DataFrame()

    # index_classify 返回 index_code, industry_name
    result = df[["index_code", "industry_name"]].rename(columns={
        "index_code": "板块代码",
        "industry_name": "板块名称",
    })
    return result.reset_index(drop=True)


async def fetch_industry_constituents(industry_code: str) -> pd.DataFrame:
    """
    获取指定申万一级行业的成分股。
    industry_code: 来自 fetch_industry_board_list 的 板块代码（如 '801010.SI'）

    返回列：代码（纯 6 位）
    """
    pro = _ensure_auth()

    df = await _call_with_retry(
        pro.index_member_all, l1_code=industry_code, is_new="Y",
    )

    if df is None or df.empty:
        return pd.DataFrame()

    # ts_code → 纯代码
    df["代码"] = df["ts_code"].apply(_ts_code_to_plain)
    return df[["代码"]].drop_duplicates().reset_index(drop=True)


async def fetch_stock_history(
    symbol: str,
    start_date: str,
    end_date: str,
    adjust: str = "qfq",
    period: str = "daily",
) -> pd.DataFrame:
    """
    获取单只股票历史日线数据（前复权）。
    symbol: 纯 6 位代码，如 '600519'
    start_date / end_date: YYYYMMDD 格式

    返回列：日期, 开盘, 最高, 最低, 收盘, 成交量, 成交额, 换手率, 涨跌幅
    """
    pro = _ensure_auth()
    ts_code = _plain_to_ts_code(symbol)

    async def _fetch_raw():
        return await _call_with_retry(
            pro.daily, ts_code=ts_code, start_date=start_date, end_date=end_date,
        )

    async def _fetch_adj():
        return await _call_with_retry(
            pro.adj_factor, ts_code=ts_code, start_date=start_date, end_date=end_date,
        )

    daily_df, adj_df = await asyncio.gather(_fetch_raw(), _fetch_adj())

    if daily_df is None or daily_df.empty:
        return pd.DataFrame()

    # 应用前复权
    if adjust == "qfq" and adj_df is not None and not adj_df.empty:
        adj_df = adj_df.sort_values("trade_date")
        latest_factor = adj_df["adj_factor"].iloc[-1]  # 最新复权因子

        daily_df = daily_df.merge(adj_df[["trade_date", "adj_factor"]], on="trade_date", how="left")
        daily_df["adj_factor"].fillna(latest_factor, inplace=True)

        ratio = daily_df["adj_factor"] / latest_factor
        for col in ("open", "high", "low", "close"):
            daily_df[col] = (daily_df[col] * ratio).round(4)

    # 解析日期
    daily_df["日期"] = pd.to_datetime(daily_df["trade_date"], format="%Y%m%d")

    # Tushare amount 单位是"千元"→"元"
    if "amount" in daily_df.columns:
        daily_df["amount"] = pd.to_numeric(daily_df["amount"], errors="coerce") * 1000

    daily_df = daily_df.rename(columns={
        "open": "开盘",
        "high": "最高",
        "low": "最低",
        "close": "收盘",
        "vol": "成交量",
        "amount": "成交额",
        "pct_chg": "涨跌幅",
    })

    # 换手率从 daily_basic 补充（可选，若 daily 无此字段则留空）
    if "turnover_rate" in daily_df.columns:
        daily_df = daily_df.rename(columns={"turnover_rate": "换手率"})
    else:
        daily_df["换手率"] = None

    cols = ["日期", "开盘", "最高", "最低", "收盘", "成交量", "成交额", "换手率", "涨跌幅"]
    existing = [c for c in cols if c in daily_df.columns]
    return daily_df[existing].sort_values("日期").reset_index(drop=True)


async def fetch_valuation_all() -> pd.DataFrame:
    """
    批量获取全市场估值指标（PE TTM, PB, 总市值, 流通市值）。

    返回列：code（纯 6 位）, pe_ttm, pb, total_mv（万元）, float_mv（万元）
    """
    pro = _ensure_auth()
    today = date.today().strftime("%Y%m%d")

    df = await _call_with_retry(
        pro.daily_basic, ts_code="", trade_date=today,
        fields="ts_code,pe_ttm,pb,total_mv,circ_mv",
    )

    if df is None or df.empty:
        return pd.DataFrame()

    df["code"] = df["ts_code"].apply(_ts_code_to_plain)
    df = df.rename(columns={"circ_mv": "float_mv"})
    return df[["code", "pe_ttm", "pb", "total_mv", "float_mv"]].reset_index(drop=True)


async def fetch_financial_report_batch(date: str) -> pd.DataFrame:
    """
    批量获取全市场财务指标（ROE, 毛利率, 现金流比率, 营收同比, 净利润同比）。
    date: YYYYMMDD 格式的报告期，如 '20230930'

    注：Tushare fina_indicator 按 ts_code 查询，无法一次性批量取全市场。
    通过先获取股票列表再分批查询来实现。每次最多 100 条，使用 period 参数。
    实际上 fina_indicator 支持 period 参数，但需要高积分（5000+）才能批量。
    低积分账号将逐只股票查询，但这非常耗时，此处改用 ts_code 批量分页方案。

    返回列：股票代码, 净资产收益率, 销售毛利率, 经营现金流率,
             营业总收入-同比增长, 净利润-同比增长
    """
    pro = _ensure_auth()

    # 先获取全量股票代码
    stock_df = await _call_with_retry(
        pro.stock_basic, list_status="L", fields="ts_code",
    )
    if stock_df is None or stock_df.empty:
        return pd.DataFrame()

    ts_codes = stock_df["ts_code"].tolist()
    all_records = []

    # 分批查询，每批 50 只（避免 API 频率限制）
    batch_size = 50
    for i in range(0, len(ts_codes), batch_size):
        batch = ts_codes[i: i + batch_size]
        batch_str = ",".join(batch)
        try:
            df = await _call_with_retry(
                pro.fina_indicator,
                ts_code=batch_str,
                period=date,
                fields="ts_code,end_date,roe,grossprofit_margin,ocf_to_or,tr_yoy,netprofit_yoy",
            )
            if df is not None and not df.empty:
                # 每只股票只取该报告期最新的一条
                df = df[df["end_date"] == date].copy()
                all_records.append(df)
        except Exception as e:
            logger.warning("Failed to fetch fina_indicator batch %d: %s", i, e)
            continue

        # 避免频率过高
        await asyncio.sleep(0.3)

    if not all_records:
        return pd.DataFrame()

    result = pd.concat(all_records, ignore_index=True)
    result["股票代码"] = result["ts_code"].apply(_ts_code_to_plain)
    result = result.rename(columns={
        "roe": "净资产收益率",
        "grossprofit_margin": "销售毛利率",
        "ocf_to_or": "经营现金流率",
        "tr_yoy": "营业总收入-同比增长",
        "netprofit_yoy": "净利润-同比增长",
    })

    cols = ["股票代码", "净资产收益率", "销售毛利率", "经营现金流率",
            "营业总收入-同比增长", "净利润-同比增长"]
    existing = [c for c in cols if c in result.columns]
    return result[existing].drop_duplicates(subset=["股票代码"]).reset_index(drop=True)


async def fetch_sh_stock_info(indicator: str = "主板A股") -> pd.DataFrame:
    """
    获取上交所 A 股上市日期信息。
    indicator 参数保留兼容性，实际通过 exchange='SSE' 过滤。

    返回列：A_STOCK_CODE（纯 6 位）, LIST_DATE（YYYYMMDD 字符串）
    """
    pro = _ensure_auth()

    df = await _call_with_retry(
        pro.stock_basic,
        list_status="L",
        exchange="SSE",
        fields="ts_code,symbol,list_date",
    )

    if df is None or df.empty:
        return pd.DataFrame()

    result = df.rename(columns={
        "symbol": "A_STOCK_CODE",
        "list_date": "LIST_DATE",
    })
    return result[["A_STOCK_CODE", "LIST_DATE"]].reset_index(drop=True)


async def fetch_sz_stock_info(indicator: str = "A股列表") -> pd.DataFrame:
    """
    获取深交所 A 股上市日期信息。

    返回列：A股代码（纯 6 位）, A股上市日期（YYYYMMDD 字符串）
    """
    pro = _ensure_auth()

    df = await _call_with_retry(
        pro.stock_basic,
        list_status="L",
        exchange="SZSE",
        fields="ts_code,symbol,list_date",
    )

    if df is None or df.empty:
        return pd.DataFrame()

    result = df.rename(columns={
        "symbol": "A股代码",
        "list_date": "A股上市日期",
    })
    return result[["A股代码", "A股上市日期"]].reset_index(drop=True)


async def fetch_stock_news(symbol: str) -> pd.DataFrame:
    """
    获取个股相关公告。
    使用 anns_d（上市公司公告）接口，按 ts_code 过滤近 7 天公告。

    返回列：新闻标题, 新闻内容, 发布时间, 文章来源, 新闻链接
    """
    pro = _ensure_auth()
    ts_code = _plain_to_ts_code(symbol)

    end_date = date.today().strftime("%Y%m%d")
    start_date = (date.today() - timedelta(days=7)).strftime("%Y%m%d")

    try:
        df = await _call_with_retry(
            pro.anns_d,
            ts_code=ts_code,
            start_date=start_date,
            end_date=end_date,
        )
    except Exception as e:
        logger.warning("Failed to fetch announcements for %s: %s", symbol, e)
        return pd.DataFrame()

    if df is None or df.empty:
        return pd.DataFrame()

    # ann_date 格式 YYYYMMDD → datetime
    def _parse_ann_date(val):
        try:
            return datetime.strptime(str(val), "%Y%m%d")
        except Exception:
            return None

    df["发布时间"] = df["ann_date"].apply(_parse_ann_date)
    df["新闻标题"] = df["title"].fillna("")
    df["新闻内容"] = df["title"].fillna("")  # 公告接口无正文，使用标题填充
    df["文章来源"] = "上市公司公告"
    df["新闻链接"] = df["url"].fillna("") if "url" in df.columns else ""

    cols = ["新闻标题", "新闻内容", "发布时间", "文章来源", "新闻链接"]
    existing = [c for c in cols if c in df.columns]
    return df[existing].reset_index(drop=True)


async def fetch_trading_calendar() -> pd.DataFrame:
    """
    获取 A 股交易日历（上交所）。
    返回自 1990 年至当年年底的全量交易日。

    返回列：trade_date（date 对象）
    """
    pro = _ensure_auth()
    end_year = date.today().year + 1
    end_date = f"{end_year}1231"

    df = await _call_with_retry(
        pro.trade_cal,
        exchange="SSE",
        start_date="19901219",
        end_date=end_date,
        is_open="1",
    )

    if df is None or df.empty:
        return pd.DataFrame()

    # cal_date 格式 YYYYMMDD → date 对象
    df["trade_date"] = pd.to_datetime(df["cal_date"], format="%Y%m%d").dt.date
    return df[["trade_date"]].reset_index(drop=True)
