"""
JQData 数据源适配层。
所有对 jqdatasdk 库的直接调用都集中在这个文件里。
对外接口与 akshare_provider 保持语义一致，上层 fetcher / fundamentals /
trading_calendar 只需 import 本模块替换即可。

代码格式：聚宽使用 <code>.XSHG（上交所）/ <code>.XSHE（深交所）
本模块内部统一用 JQ 格式，出口时保持 JQ 格式（上层按需转换）。

登录：通过 settings.JQDATA_USERNAME / JQDATA_PASSWORD 在模块首次使用前完成，
      后续调用不重复 auth()。
"""

import asyncio
import logging
import threading
from datetime import date, timedelta
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

RETRY_ATTEMPTS = 3
RETRY_BACKOFF = [1, 2, 4]

# ── 登录状态管理 ─────────────────────────────────────────────

_auth_lock = threading.Lock()
_authed = False


def _ensure_auth() -> None:
    """首次调用时完成 jqdatasdk 认证（线程安全，只认证一次）。"""
    global _authed
    if _authed:
        return
    with _auth_lock:
        if _authed:
            return
        from src.core.config import settings
        import jqdatasdk as jq

        username = settings.JQDATA_USERNAME
        password = settings.JQDATA_PASSWORD
        if not username or not password:
            raise RuntimeError(
                "JQDATA_USERNAME / JQDATA_PASSWORD not configured. "
                "Set them in your .env file."
            )
        jq.auth(username, password)
        _authed = True
        logger.info("JQData auth success (user=%s)", username)


async def _call(func, *args, **kwargs) -> pd.DataFrame:
    """Wrap synchronous jqdatasdk calls with retry + asyncio.to_thread."""

    def _run():
        _ensure_auth()
        return func(*args, **kwargs)

    for attempt in range(RETRY_ATTEMPTS):
        try:
            return await asyncio.to_thread(_run)
        except Exception:
            if attempt == RETRY_ATTEMPTS - 1:
                raise
            wait = RETRY_BACKOFF[attempt]
            logger.warning(
                "JQData call %s failed (attempt %d/%d), retrying in %ds...",
                func.__name__, attempt + 1, RETRY_ATTEMPTS, wait,
            )
            await asyncio.sleep(wait)


# ── Code Format Helpers ──────────────────────────────────────

def to_jq_code(code: str) -> str:
    """
    将内部格式（'600519.SH' / '000001.SZ'）转换为聚宽格式（'600519.XSHG' / '000001.XSHE'）。
    如果已经是聚宽格式则直接返回。
    """
    if code.endswith(".XSHG") or code.endswith(".XSHE"):
        return code
    if "." not in code:
        # 纯数字代码，根据前缀推断
        if code.startswith("6"):
            return f"{code}.XSHG"
        return f"{code}.XSHE"
    prefix, suffix = code.rsplit(".", 1)
    if suffix == "SH":
        return f"{prefix}.XSHG"
    if suffix in ("SZ", "BJ"):
        return f"{prefix}.XSHE"
    return code


def from_jq_code(jq_code: str) -> str:
    """
    将聚宽格式（'600519.XSHG'）转换为内部格式（'600519.SH'）。
    北交所股票（聚宽也用 .XSHE）按代码前缀区分。
    """
    if jq_code.endswith(".XSHG"):
        return jq_code.replace(".XSHG", ".SH")
    if jq_code.endswith(".XSHE"):
        raw = jq_code.split(".")[0]
        if raw.startswith(("4", "8", "92")):
            return f"{raw}.BJ"
        return f"{raw}.SZ"
    return jq_code


# ── Stock List ───────────────────────────────────────────────


async def fetch_a_share_spot() -> pd.DataFrame:
    """
    全市场 A 股快照（含股票基础信息 + 当日行情）。

    返回列（与 akshare_provider 保持兼容）：
        code, name, market, exchange, is_st, list_date,
        close, open, high, low, volume, amount, turnover_rate, pct_change,
        pe_ttm, pb, total_mv, float_mv
    """
    import jqdatasdk as jq

    # 1. 获取所有在市 A 股列表
    securities_df = await _call(jq.get_all_securities, types=["stock"], date=None)
    if securities_df is None or securities_df.empty:
        return pd.DataFrame()

    # 过滤掉已退市（end_date < 今天）的股票
    today_str = date.today().isoformat()
    active = securities_df[securities_df["end_date"].astype(str) >= today_str].copy()
    codes = list(active.index)  # index 是 JQ 格式的代码，如 '600519.XSHG'

    if not codes:
        return pd.DataFrame()

    # 2. 批量获取当日行情
    # get_price with panel=False + multiple securities returns a DataFrame with
    # MultiIndex (time, code); reset_index() gives columns: time, code, open, ...
    batch_size = 500
    price_parts = []
    for i in range(0, len(codes), batch_size):
        batch = codes[i: i + batch_size]
        try:
            df = await _call(
                jq.get_price,
                batch,
                end_date=today_str,
                count=1,
                frequency="daily",
                fields=["open", "close", "high", "low", "volume", "money", "paused"],
                skip_paused=False,
                fq="pre",
                panel=False,
            )
            if df is not None and not df.empty:
                df = df.reset_index()
                price_parts.append(df)
        except Exception:
            logger.warning("get_price batch %d failed, skipping", i // batch_size)

    if price_parts:
        price_df = pd.concat(price_parts, ignore_index=True)
        # 标准化 code 列名
        if "code" not in price_df.columns and "index" in price_df.columns:
            price_df = price_df.rename(columns={"index": "code"})
    else:
        price_df = pd.DataFrame()

    # 构建 code → price row 的快速查找字典
    price_map: dict[str, dict] = {}
    if not price_df.empty and "code" in price_df.columns:
        for _, prow in price_df.iterrows():
            price_map[prow["code"]] = prow.to_dict()

    # 3. 批量获取估值
    val_parts = []
    for i in range(0, len(codes), batch_size):
        batch = codes[i: i + batch_size]
        try:
            df = await _call(
                jq.get_valuation,
                batch,
                end_date=today_str,
                count=1,
                fields=["pe_ratio", "pb_ratio", "market_cap", "circulating_market_cap", "turnover_ratio"],
            )
            if df is not None and not df.empty:
                val_parts.append(df)
        except Exception:
            logger.warning("get_valuation batch %d failed, skipping", i // batch_size)

    val_df = pd.concat(val_parts, ignore_index=True) if val_parts else pd.DataFrame()
    val_map: dict[str, dict] = {}
    if not val_df.empty and "code" in val_df.columns:
        for _, vrow in val_df.iterrows():
            val_map[vrow["code"]] = vrow.to_dict()

    # 4. 拼合结果，统一列名
    records = []
    for jq_code in codes:
        raw_code = jq_code.split(".")[0]
        name = active.loc[jq_code, "display_name"] if jq_code in active.index else ""
        list_date_val = active.loc[jq_code, "start_date"] if jq_code in active.index else None

        row: dict = {
            "代码": raw_code,
            "名称": name,
            "jq_code": jq_code,
            "list_date": list_date_val,
        }

        # 行情
        p = price_map.get(jq_code)
        if p:
            row.update({
                "最新价": p.get("close"),
                "今开": p.get("open"),
                "最高": p.get("high"),
                "最低": p.get("low"),
                "成交量": p.get("volume"),
                "成交额": p.get("money"),
            })

        # 估值
        v = val_map.get(jq_code)
        if v:
            row.update({
                "市盈率-动态": v.get("pe_ratio"),
                "市净率": v.get("pb_ratio"),
                # get_valuation market_cap 单位是亿元，转成元
                "总市值": _to_yuan(v.get("market_cap")),
                "流通市值": _to_yuan(v.get("circulating_market_cap")),
                "换手率": v.get("turnover_ratio"),
            })

        records.append(row)

    return pd.DataFrame(records)


# ── Industry ─────────────────────────────────────────────────


def _jq_safe_date() -> str:
    """
    返回 JQData 账号有效期内的最近日期。
    JQData 免费账号数据截止约 1 年前，取今天与 1 年前两者中的较早者作为安全日期，
    确保行业分类查询不超出权限范围。
    """
    one_year_ago = date.today() - timedelta(days=365)
    return one_year_ago.isoformat()


async def fetch_industry_board_list() -> pd.DataFrame:
    """
    行业板块列表（申万一级行业）。
    返回列：板块名称, 板块代码
    """
    import jqdatasdk as jq

    safe_date = _jq_safe_date()
    df = await _call(jq.get_industries, name="sw_l1", date=safe_date)
    if df is None or df.empty:
        return pd.DataFrame()
    result = df[["name"]].reset_index()
    result.columns = ["板块代码", "板块名称"]
    return result


async def fetch_industry_constituents(industry_code: str) -> pd.DataFrame:
    """
    单个行业的成分股列表（按申万一级行业代码）。
    返回列：代码（内部格式 '600519.SH'）
    """
    import jqdatasdk as jq

    safe_date = _jq_safe_date()
    stocks = await _call(jq.get_industry_stocks, industry_code, date=safe_date)
    if not stocks:
        return pd.DataFrame()
    records = [{"代码": from_jq_code(c).split(".")[0], "jq_code": c} for c in stocks]
    return pd.DataFrame(records)


# ── Daily Quotes ─────────────────────────────────────────────


async def fetch_stock_history(
    symbol: str,
    start_date: str,
    end_date: str,
    period: str = "daily",
    adjust: str = "qfq",
) -> pd.DataFrame:
    """
    单只股票历史日线（前复权）。
    symbol: 纯数字如 '600519' 或内部格式 '600519.SH'。
    start_date / end_date: 'YYYYMMDD' 格式（兼容旧接口）或 'YYYY-MM-DD'。
    返回列：日期, 开盘, 最高, 最低, 收盘, 成交量, 成交额, 换手率, 涨跌幅
    """
    import jqdatasdk as jq

    # 代码格式转换
    jq_code = to_jq_code(symbol) if "." in symbol else (
        f"{symbol}.XSHG" if symbol.startswith("6") else f"{symbol}.XSHE"
    )

    # 日期格式标准化 YYYYMMDD → YYYY-MM-DD
    start_str = _norm_date(start_date)
    end_str = _norm_date(end_date)

    fq = "pre" if adjust in ("qfq", "pre") else ("post" if adjust in ("hfq", "post") else "none")

    df = await _call(
        jq.get_price,
        jq_code,
        start_date=start_str,
        end_date=end_str,
        frequency="daily",
        fields=["open", "close", "high", "low", "volume", "money", "paused"],
        skip_paused=True,
        fq=fq,
        panel=False,
    )

    if df is None or df.empty:
        return pd.DataFrame()

    # 重命名列以兼容上层（fetcher.py）期望的列名
    df = df.reset_index()
    df = df.rename(columns={
        "index": "日期",
        "time": "日期",
        "open": "开盘",
        "close": "收盘",
        "high": "最高",
        "low": "最低",
        "volume": "成交量",
        "money": "成交额",
    })
    if "日期" not in df.columns and df.index.name in ("time", None):
        df.insert(0, "日期", df.index)

    # 计算涨跌幅（get_price 不直接返回，需自行计算）
    if "收盘" in df.columns and "涨跌幅" not in df.columns:
        df["涨跌幅"] = df["收盘"].pct_change() * 100
    # 换手率（get_price 不含，填 None）
    if "换手率" not in df.columns:
        df["换手率"] = None

    return df


# ── Fundamentals ─────────────────────────────────────────────


async def fetch_valuation_all() -> pd.DataFrame:
    """
    全市场估值指标（PE TTM, PB, 总市值, 流通市值）。
    返回列：code（内部格式 '600519.SH'）, pe_ttm, pb, total_mv, float_mv
    """
    import jqdatasdk as jq

    today_str = date.today().isoformat()

    # 获取所有在市股票
    securities_df = await _call(jq.get_all_securities, types=["stock"], date=today_str)
    if securities_df is None or securities_df.empty:
        return pd.DataFrame()
    codes = list(securities_df.index)

    batch_size = 500
    parts = []
    for i in range(0, len(codes), batch_size):
        batch = codes[i: i + batch_size]
        try:
            df = await _call(
                jq.get_valuation,
                batch,
                end_date=today_str,
                count=1,
                fields=["pe_ratio", "pb_ratio", "market_cap", "circulating_market_cap"],
            )
            parts.append(df)
        except Exception:
            logger.warning("get_valuation batch %d failed", i // batch_size)
        await asyncio.sleep(0.2)

    if not parts:
        return pd.DataFrame()

    val_df = pd.concat(parts, ignore_index=True)
    val_df = val_df.rename(columns={
        "code": "code",
        "pe_ratio": "pe_ttm",
        "pb_ratio": "pb",
        "market_cap": "total_mv",
        "circulating_market_cap": "float_mv",
    })
    # 转换代码格式
    val_df["code"] = val_df["code"].apply(from_jq_code).str.split(".").str[0]
    # market_cap 单位亿元 → 元
    val_df["total_mv"] = val_df["total_mv"].apply(_to_yuan)
    val_df["float_mv"] = val_df["float_mv"].apply(_to_yuan)

    return val_df[["code", "pe_ttm", "pb", "total_mv", "float_mv"]]


async def fetch_financial_report_batch(date: str = "20240930") -> pd.DataFrame:
    """
    全市场财务指标（ROE, 毛利率, 每股经营现金流等）。
    date 格式: YYYYMMDD，须为季报日期（0331/0630/0930/1231）。
    返回列：股票代码（纯数字）, 净资产收益率, 销售毛利率, 每股经营现金流量,
            营业总收入-同比增长, 净利润-同比增长
    """
    import jqdatasdk as jq
    from jqdatasdk import indicator

    stat_date = _yyyymmdd_to_stat_date(date)

    today_str = _today_str()
    securities_df = await _call(jq.get_all_securities, types=["stock"], date=today_str)
    if securities_df is None or securities_df.empty:
        return pd.DataFrame()
    codes = list(securities_df.index)

    batch_size = 200
    parts = []
    for i in range(0, len(codes), batch_size):
        batch = codes[i: i + batch_size]
        try:
            df = await _call(
                jq.get_history_fundamentals,
                batch,
                fields=[
                    indicator.roe,
                    indicator.gross_profit_margin,
                    indicator.ocf_to_revenue,
                    indicator.inc_total_revenue_year_on_year,
                    indicator.inc_net_profit_year_on_year,
                ],
                stat_date=stat_date,
                count=1,
            )
            parts.append(df)
        except Exception:
            logger.warning(
                "get_history_fundamentals batch %d failed", i // batch_size, exc_info=True
            )
        await asyncio.sleep(0.2)

    if not parts:
        return pd.DataFrame()

    result = pd.concat(parts, ignore_index=True)
    # 转换列名以兼容 fundamentals.py 上层
    result = result.rename(columns={
        "code": "股票代码_jq",
        "roe": "净资产收益率",
        "gross_profit_margin": "销售毛利率",
        "ocf_to_revenue": "经营现金流率",
        "inc_total_revenue_year_on_year": "营业总收入-同比增长",
        "inc_net_profit_year_on_year": "净利润-同比增长",
    })
    # 纯数字代码（去掉 .XSHG/.XSHE）
    result["股票代码"] = result["股票代码_jq"].apply(lambda c: c.split(".")[0] if isinstance(c, str) else "")
    return result


# ── Stock Info (Listing Dates) ────────────────────────────────


async def fetch_sh_stock_info(indicator: str = "主板A股") -> pd.DataFrame:
    """
    上交所股票信息（含上市日期）。
    返回格式兼容 fetcher.py sync_list_dates，列：A_STOCK_CODE, LIST_DATE
    """
    import jqdatasdk as jq

    today_str = _today_str()
    df = await _call(jq.get_all_securities, types=["stock"], date=today_str)
    if df is None or df.empty:
        return pd.DataFrame()

    sh = df[df.index.str.endswith(".XSHG")].copy()
    sh = sh.reset_index()
    sh = sh.rename(columns={"index": "jq_code", "start_date": "LIST_DATE"})
    sh["A_STOCK_CODE"] = sh["jq_code"].str.split(".").str[0]
    return sh[["A_STOCK_CODE", "LIST_DATE"]]


async def fetch_sz_stock_info(indicator: str = "A股列表") -> pd.DataFrame:
    """
    深交所股票信息（含上市日期）。
    """
    import jqdatasdk as jq

    today_str = _today_str()
    df = await _call(jq.get_all_securities, types=["stock"], date=today_str)
    if df is None or df.empty:
        return pd.DataFrame()

    sz = df[df.index.str.endswith(".XSHE")].copy()
    sz = sz.reset_index()
    sz = sz.rename(columns={"index": "jq_code", "start_date": "LIST_DATE"})
    sz["A股代码"] = sz["jq_code"].str.split(".").str[0]
    sz = sz.rename(columns={"LIST_DATE": "A股上市日期"})
    return sz[["A股代码", "A股上市日期"]]


# ── News / Events ────────────────────────────────────────────

# 统一输出列名（scanner.py 依赖这些列名）
_NEWS_COLS = ["新闻标题", "新闻内容", "发布时间", "文章来源", "新闻链接"]


async def fetch_stock_news(symbol: str) -> pd.DataFrame:
    """
    个股新闻 + 公告，多源合并以提升覆盖率。

    数据源优先级：
      1. 东方财富个股新闻 (stock_news_em)      — 实时性最好
      2. 巨潮资讯个股公告 (stock_zh_a_disclosure_report_cninfo) — 公告权威性高
    JQData 舆情数据（jqdatasdk.get_news）目前仅限付费账号，
    待购买权限后可替换 _fetch_news_jq() 并接入。

    返回列：新闻标题, 新闻内容, 发布时间, 文章来源, 新闻链接
    按发布时间降序排列，已按标题去重。
    """
    raw_code = symbol.split(".")[0] if "." in symbol else symbol

    parts = await asyncio.gather(
        _fetch_news_em(raw_code),
        _fetch_notices_cninfo(raw_code),
        return_exceptions=True,
    )

    frames: list[pd.DataFrame] = []
    for result in parts:
        if isinstance(result, Exception):
            logger.warning("fetch_stock_news partial failure: %s", result)
            continue
        if isinstance(result, pd.DataFrame) and not result.empty:
            frames.append(result)

    if not frames:
        return pd.DataFrame(columns=_NEWS_COLS)

    merged = pd.concat(frames, ignore_index=True)
    # 按标题去重，保留首条
    merged = merged.drop_duplicates(subset=["新闻标题"], keep="first")
    # 按发布时间降序（字符串比较兼容 YYYY-MM-DD 格式）
    merged = merged.sort_values("发布时间", ascending=False, na_position="last")
    return merged.reset_index(drop=True)


async def _fetch_news_em(raw_code: str) -> pd.DataFrame:
    """东方财富个股新闻 (stock_news_em)。"""
    import akshare as ak

    try:
        df = await asyncio.to_thread(ak.stock_news_em, symbol=raw_code)
        if df is None or df.empty:
            return pd.DataFrame(columns=_NEWS_COLS)
        # stock_news_em 返回列：新闻标题, 新闻内容, 发布时间, 文章来源, 新闻链接
        # 列名已与 _NEWS_COLS 一致，直接补全缺失列
        return _normalize_cols(df, source_tag="东财新闻")
    except Exception:
        logger.warning("stock_news_em failed for %s", raw_code, exc_info=True)
        return pd.DataFrame(columns=_NEWS_COLS)


async def _fetch_notices_cninfo(raw_code: str) -> pd.DataFrame:
    """
    巨潮资讯个股公告 (stock_zh_a_disclosure_report_cninfo)。
    取最近 30 天，将公告映射为统一 _NEWS_COLS 格式。
    """
    import akshare as ak

    end_date = date.today()
    start_date = end_date - timedelta(days=30)

    try:
        df = await asyncio.to_thread(
            ak.stock_zh_a_disclosure_report_cninfo,
            symbol=raw_code,
            market="沪深京",
            start_date=start_date.strftime("%Y%m%d"),
            end_date=end_date.strftime("%Y%m%d"),
        )
        if df is None or df.empty:
            return pd.DataFrame(columns=_NEWS_COLS)

        # 巨潮返回列：代码, 简称, 公告标题, 公告类型, 公告时间, 公告链接
        result = pd.DataFrame()
        result["新闻标题"] = df.get("公告标题", pd.Series(dtype=str)).fillna("").astype(str)
        result["新闻内容"] = ""  # 巨潮接口不返回正文，仅有标题和链接
        # 公告时间可能是 datetime 或 date，统一转字符串
        pub_time = df.get("公告时间", pd.Series(dtype=str))
        result["发布时间"] = pd.to_datetime(pub_time, errors="coerce").dt.strftime("%Y-%m-%d").fillna("")
        result["文章来源"] = df.get("公告类型", pd.Series(dtype=str)).fillna("公告").astype(str)
        result["新闻链接"] = df.get("公告链接", pd.Series(dtype=str)).fillna("").astype(str)
        # 过滤空标题
        result = result[result["新闻标题"] != ""]
        return result.reset_index(drop=True)
    except Exception:
        logger.warning("stock_zh_a_disclosure_report_cninfo failed for %s", raw_code, exc_info=True)
        return pd.DataFrame(columns=_NEWS_COLS)


async def _fetch_news_jq(symbol: str) -> pd.DataFrame:
    """
    JQData 舆情数据接口（付费权限）。
    暂未启用，留作备用。
    """
    # import jqdatasdk as jq
    # jq_code = to_jq_code(symbol) if '.' in symbol else (
    #     f"{symbol}.XSHG" if symbol.startswith('6') else f"{symbol}.XSHE"
    # )
    # df = await _call(jq.get_news, code=jq_code, count=20)
    # return df
    return pd.DataFrame()


def _normalize_cols(df: pd.DataFrame, source_tag: str = "") -> pd.DataFrame:
    """将 DataFrame 补全为 _NEWS_COLS 格式，缺失列填空字符串。"""
    result = df.copy()
    for col in _NEWS_COLS:
        if col not in result.columns:
            result[col] = ""
    # 若 source_tag 不为空且 文章来源 全为空，填入 source_tag
    if source_tag and result["文章来源"].fillna("").eq("").all():
        result["文章来源"] = source_tag
    return result[_NEWS_COLS]


# ── Trading Calendar ──────────────────────────────────────────


async def fetch_trading_calendar() -> pd.DataFrame:
    """
    A 股交易日历（从 2005 至今年年底）。
    返回列：trade_date（datetime.date 对象）
    """
    import jqdatasdk as jq

    start = "2005-01-01"
    end = f"{date.today().year}-12-31"

    trade_days = await _call(jq.get_trade_days, start_date=start, end_date=end)
    if trade_days is None or len(trade_days) == 0:
        return pd.DataFrame(columns=["trade_date"])

    df = pd.DataFrame({"trade_date": trade_days})
    return df


# ── Private Helpers ───────────────────────────────────────────


def _norm_date(d: str) -> str:
    """YYYYMMDD → YYYY-MM-DD。已经是 YYYY-MM-DD 格式的直接返回。"""
    d = str(d).strip()
    if len(d) == 8 and d.isdigit():
        return f"{d[:4]}-{d[4:6]}-{d[6:8]}"
    return d


def _today_str() -> str:
    return date.today().isoformat()


def _to_yuan(val: Optional[float]) -> Optional[float]:
    """亿元 → 元（JQData 市值单位为亿元，系统内部用元）。"""
    if val is None:
        return None
    try:
        return float(val) * 1e8
    except (TypeError, ValueError):
        return None


def _yyyymmdd_to_stat_date(date_str: str) -> str:
    """
    将 YYYYMMDD 格式的季报日期转为 jqdatasdk get_history_fundamentals 的 stat_date 格式。
    '20240930' → '2024q3'
    '20241231' → '2024'（年报）
    """
    d = str(date_str).strip()
    year = d[:4]
    mmdd = d[4:]
    mapping = {"0331": f"{year}q1", "0630": f"{year}q2", "0930": f"{year}q3", "1231": year}
    return mapping.get(mmdd, f"{year}q3")
