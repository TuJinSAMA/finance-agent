import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from threading import Lock
from typing import Any, Callable

import pandas as pd

from src.schemas.public_board import (
    MarketGroupSnapshot,
    MarketMetric,
    SnapshotGroup,
)

logger = logging.getLogger(__name__)

SOURCE_NAME = "akshare"
YFINANCE_FETCH_TIMEOUT_SECONDS = 5.0
YFINANCE_CONCURRENT_LIMIT = 3  # Max concurrent requests to avoid rate limiting
YFINANCE_REQUEST_DELAY = 0.2  # Delay between requests in seconds
YFINANCE_RETRY_ATTEMPTS = 3
YFINANCE_RETRY_BACKOFF = [1, 2, 4]  # Exponential backoff delays

YFINANCE_SYMBOLS: dict[str, str] = {
    "VIX": "^VIX",
    "US10Y": "^TNX",
    "DXY": "DX-Y.NYB",
    "SPX": "^GSPC",
    "NASDAQ": "^IXIC",
    "GOLD": "GC=F",
    "WTI": "CL=F",
    "BTC": "BTC-USD",
}
US2Y_SYMBOL = "^UST2Y"

_YFINANCE_SEMAPHORE = asyncio.Semaphore(YFINANCE_CONCURRENT_LIMIT)

AKSHARE_INDEX_CODE_MAP: dict[str, list[str]] = {
    YFINANCE_SYMBOLS["SPX"]: ["SPX"],
    YFINANCE_SYMBOLS["NASDAQ"]: ["NDX"],
    YFINANCE_SYMBOLS["DXY"]: ["UDI"],  # 美元指数
}

AKSHARE_INDEX_NAME_MAP: dict[str, list[str]] = {
    YFINANCE_SYMBOLS["VIX"]: ["VIX", "恐慌"],
    YFINANCE_SYMBOLS["SPX"]: ["标普", "S&P"],
    YFINANCE_SYMBOLS["NASDAQ"]: ["纳斯达克"],
    YFINANCE_SYMBOLS["DXY"]: ["美元指数"],
}

AKSHARE_CACHE_TTL_SECONDS = 30

_AKSHARE_CACHE_LOCK = Lock()
_AKSHARE_GLOBAL_INDEX_CACHE: pd.DataFrame | None = None
_AKSHARE_GLOBAL_INDEX_CACHE_AT: datetime | None = None
_AKSHARE_CRYPTO_CACHE: pd.DataFrame | None = None
_AKSHARE_CRYPTO_CACHE_AT: datetime | None = None


@dataclass(slots=True)
class QuoteSnapshot:
    value: float
    previous_value: float | None
    change_pct: float | None


def normalize_metric(
    name: str,
    symbol: str,
    value: float | None,
    change_pct: float | None,
    display: str | None = None,
    status: str | None = None,
) -> dict[str, Any]:
    if value is None:
        return {
            "name": name,
            "symbol": symbol,
            "value": None,
            "display": None,
            "change_pct": None if change_pct is None else round(change_pct, 2),
            "status": status or "unavailable",
        }

    rounded_value = round(value, 4)
    return {
        "name": name,
        "symbol": symbol,
        "value": rounded_value,
        "display": display or f"{rounded_value:.2f}",
        "change_pct": None if change_pct is None else round(change_pct, 2),
        "status": status or "ok",
    }


async def build_macro_snapshot(as_of: datetime) -> MarketGroupSnapshot:
    quotes = await asyncio.gather(
        _safe_fetch_quote(YFINANCE_SYMBOLS["VIX"]),
        _safe_fetch_quote(YFINANCE_SYMBOLS["US10Y"]),
        _safe_fetch_quote(YFINANCE_SYMBOLS["DXY"]),
        _safe_fetch_quote(US2Y_SYMBOL),
    )
    vix_quote, us10y_quote, dxy_quote, us2y_quote = quotes

    return _build_macro_snapshot_from_quotes(
        as_of=as_of,
        vix_quote=vix_quote,
        us10y_quote=us10y_quote,
        dxy_quote=dxy_quote,
        us2y_quote=us2y_quote,
    )


async def build_assets_snapshot(as_of: datetime) -> MarketGroupSnapshot:
    quotes = await asyncio.gather(
        _safe_fetch_quote(YFINANCE_SYMBOLS["SPX"]),
        _safe_fetch_quote(YFINANCE_SYMBOLS["NASDAQ"]),
        _safe_fetch_quote(YFINANCE_SYMBOLS["GOLD"]),
        _safe_fetch_quote(YFINANCE_SYMBOLS["WTI"]),
        _safe_fetch_quote(YFINANCE_SYMBOLS["BTC"]),
    )
    spx_quote, nasdaq_quote, gold_quote, wti_quote, btc_quote = quotes

    return _build_assets_snapshot_from_quotes(
        as_of=as_of,
        spx_quote=spx_quote,
        nasdaq_quote=nasdaq_quote,
        gold_quote=gold_quote,
        wti_quote=wti_quote,
        btc_quote=btc_quote,
    )


def _build_macro_metrics(
    vix_quote: QuoteSnapshot | None,
    us10y_quote: QuoteSnapshot | None,
    dxy_quote: QuoteSnapshot | None,
    us2y_quote: QuoteSnapshot | None,
) -> list[MarketMetric]:
    return [
        _metric_from_quote("VIX", YFINANCE_SYMBOLS["VIX"], vix_quote, _format_number),
        _metric_from_quote(
            "US 10Y",
            YFINANCE_SYMBOLS["US10Y"],
            us10y_quote,
            _format_percent,
            transform=_tnx_to_percent,
        ),
        _metric_from_quote(
            "DXY",
            YFINANCE_SYMBOLS["DXY"],
            dxy_quote,
            _format_number,
        ),
        _build_spread_metric(us2y_quote, us10y_quote),
    ]


def _build_macro_snapshot_from_quotes(
    as_of: datetime,
    vix_quote: QuoteSnapshot | None,
    us10y_quote: QuoteSnapshot | None,
    dxy_quote: QuoteSnapshot | None,
    us2y_quote: QuoteSnapshot | None,
) -> MarketGroupSnapshot:
    return _build_group_snapshot(
        group="macro",
        as_of=as_of,
        items=_build_macro_metrics(vix_quote, us10y_quote, dxy_quote, us2y_quote),
    )


def _build_assets_metrics(
    spx_quote: QuoteSnapshot | None,
    nasdaq_quote: QuoteSnapshot | None,
    gold_quote: QuoteSnapshot | None,
    wti_quote: QuoteSnapshot | None,
    btc_quote: QuoteSnapshot | None,
) -> list[MarketMetric]:
    return [
        _metric_from_quote(
            "S&P 500",
            YFINANCE_SYMBOLS["SPX"],
            spx_quote,
            _format_number,
        ),
        _metric_from_quote(
            "NASDAQ",
            YFINANCE_SYMBOLS["NASDAQ"],
            nasdaq_quote,
            _format_number,
        ),
        _metric_from_quote(
            "Gold",
            YFINANCE_SYMBOLS["GOLD"],
            gold_quote,
            _format_number,
        ),
        _metric_from_quote(
            "WTI",
            YFINANCE_SYMBOLS["WTI"],
            wti_quote,
            _format_number,
        ),
        _metric_from_quote(
            "BTC",
            YFINANCE_SYMBOLS["BTC"],
            btc_quote,
            _format_number,
        ),
    ]


def _build_assets_snapshot_from_quotes(
    as_of: datetime,
    spx_quote: QuoteSnapshot | None,
    nasdaq_quote: QuoteSnapshot | None,
    gold_quote: QuoteSnapshot | None,
    wti_quote: QuoteSnapshot | None,
    btc_quote: QuoteSnapshot | None,
) -> MarketGroupSnapshot:
    return _build_group_snapshot(
        group="assets",
        as_of=as_of,
        items=_build_assets_metrics(
            spx_quote,
            nasdaq_quote,
            gold_quote,
            wti_quote,
            btc_quote,
        ),
    )


def _build_group_snapshot(
    group: SnapshotGroup,
    as_of: datetime,
    items: list[MarketMetric],
) -> MarketGroupSnapshot:
    return MarketGroupSnapshot(
        group=group,
        status="ok",
        as_of=as_of,
        last_success_at=as_of,
        source=SOURCE_NAME,
        items=items,
    )


def _build_spread_metric(
    us2y_quote: QuoteSnapshot | None,
    us10y_quote: QuoteSnapshot | None,
) -> MarketMetric:
    if us2y_quote is None or us10y_quote is None:
        return _build_metric(
            name="2Y-10Y Spread",
            symbol=f"{US2Y_SYMBOL}/{YFINANCE_SYMBOLS['US10Y']}",
            value=None,
            change_pct=None,
        )

    spread_bps = (
        _tnx_to_percent(us10y_quote.value) - _tnx_to_percent(us2y_quote.value)
    ) * 100
    return _build_metric(
        name="2Y-10Y Spread",
        symbol=f"{US2Y_SYMBOL}/{YFINANCE_SYMBOLS['US10Y']}",
        value=spread_bps,
        change_pct=None,
        display=f"{spread_bps:.1f} bps",
    )


def _metric_from_quote(
    name: str,
    symbol: str,
    quote: QuoteSnapshot | None,
    formatter: Callable[[float], str],
    transform: Callable[[float], float] | None = None,
) -> MarketMetric:
    if quote is None:
        return _build_metric(name=name, symbol=symbol, value=None, change_pct=None)

    value = quote.value if transform is None else transform(quote.value)
    return _build_metric(
        name=name,
        symbol=symbol,
        value=value,
        change_pct=quote.change_pct,
        display=formatter(value),
    )


def _build_metric(
    name: str,
    symbol: str,
    value: float | None,
    change_pct: float | None,
    display: str | None = None,
    status: str | None = None,
) -> MarketMetric:
    return MarketMetric(
        **normalize_metric(
            name=name,
            symbol=symbol,
            value=value,
            change_pct=change_pct,
            display=display,
            status=status,
        )
    )


async def _safe_fetch_quote(symbol: str) -> QuoteSnapshot | None:
    async with _YFINANCE_SEMAPHORE:
        for attempt in range(YFINANCE_RETRY_ATTEMPTS):
            try:
                result = await _fetch_quote(symbol)
                if result is not None:
                    return result
            except Exception as exc:
                logger.warning(
                    "Failed to fetch public board metric %s (attempt %d/%d): %s",
                    symbol,
                    attempt + 1,
                    YFINANCE_RETRY_ATTEMPTS,
                    exc,
                )
                if attempt < YFINANCE_RETRY_ATTEMPTS - 1:
                    wait = YFINANCE_RETRY_BACKOFF[attempt]
                    logger.info("Retrying %s in %d seconds...", symbol, wait)
                    await asyncio.sleep(wait)
        return None


async def _fetch_quote(symbol: str) -> QuoteSnapshot | None:
    result = await asyncio.wait_for(
        asyncio.to_thread(_load_quote_snapshot, symbol),
        timeout=YFINANCE_FETCH_TIMEOUT_SECONDS,
    )
    await asyncio.sleep(YFINANCE_REQUEST_DELAY)
    return result


def _load_quote_snapshot(symbol: str) -> QuoteSnapshot | None:
    import akshare as ak

    # 当前环境的 akshare 无 index_investing_global；使用可用的实时接口。
    # 部分指标（如美债、VIX、黄金、WTI）在该接口下可能缺失，返回 None 由上层标记 unavailable。
    if symbol in (YFINANCE_SYMBOLS["US10Y"], US2Y_SYMBOL, YFINANCE_SYMBOLS["GOLD"], YFINANCE_SYMBOLS["WTI"]):
        return None

    if symbol == YFINANCE_SYMBOLS["BTC"]:
        return _load_btc_quote(ak)

    return _load_global_index_quote(ak, symbol)


def _load_global_index_quote(ak: Any, symbol: str) -> QuoteSnapshot | None:
    try:
        df = _get_cached_global_index_df(ak)
    except Exception as exc:
        logger.debug("akshare index_global_spot_em failed for %s: %s", symbol, exc)
        return None

    if df is None or df.empty:
        return None

    match = _match_row_from_global_index(df, symbol)
    if match is None:
        return None
    return _quote_from_spot_row(match)


def _load_btc_quote(ak: Any) -> QuoteSnapshot | None:
    try:
        df = _get_cached_crypto_df(ak)
    except Exception as exc:
        logger.debug("akshare crypto_js_spot failed: %s", exc)
        return None

    if df is None or df.empty:
        return None

    # 优先 BTCUSD，其次任意 BTC 交易对
    exact = df[df["交易品种"].astype(str).str.upper() == "BTCUSD"]
    if not exact.empty:
        row = exact.iloc[0]
    else:
        btc_rows = df[df["交易品种"].astype(str).str.contains("BTC", case=False, na=False)]
        if btc_rows.empty:
            return None
        row = btc_rows.iloc[0]

    latest = _to_float(row.get("最近报价"))
    if latest is None:
        return None

    change_pct = _to_float(row.get("涨跌幅"))
    previous = None if change_pct in (None, -100.0) else latest / (1 + change_pct / 100)
    return QuoteSnapshot(value=latest, previous_value=previous, change_pct=change_pct)


def _match_row_from_global_index(df: pd.DataFrame, symbol: str) -> pd.Series | None:
    code_matches = AKSHARE_INDEX_CODE_MAP.get(symbol, [])
    if code_matches:
        for code in code_matches:
            matched = df[df["代码"].astype(str).str.upper() == code.upper()]
            if not matched.empty:
                return matched.iloc[0]

    name_keywords = AKSHARE_INDEX_NAME_MAP.get(symbol, [])
    if name_keywords:
        for keyword in name_keywords:
            matched = df[df["名称"].astype(str).str.contains(keyword, case=False, na=False)]
            if not matched.empty:
                return matched.iloc[0]

    return None


def _quote_from_spot_row(row: pd.Series) -> QuoteSnapshot | None:
    latest = _to_float(row.get("最新价"))
    if latest is None:
        return None

    change_pct = _to_float(row.get("涨跌幅"))
    previous = None if change_pct in (None, -100.0) else latest / (1 + change_pct / 100)
    return QuoteSnapshot(value=latest, previous_value=previous, change_pct=change_pct)


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        if isinstance(value, str):
            value = value.replace(",", "").replace("%", "").strip()
            if value in ("", "-", "--", "None", "nan", "NaN"):
                return None
        result = float(value)
        if pd.isna(result):
            return None
        return result
    except (TypeError, ValueError):
        return None


def _get_cached_global_index_df(ak: Any) -> pd.DataFrame:
    global _AKSHARE_GLOBAL_INDEX_CACHE
    global _AKSHARE_GLOBAL_INDEX_CACHE_AT

    now = datetime.now(UTC)
    with _AKSHARE_CACHE_LOCK:
        if (
            _AKSHARE_GLOBAL_INDEX_CACHE is not None
            and _AKSHARE_GLOBAL_INDEX_CACHE_AT is not None
            and (now - _AKSHARE_GLOBAL_INDEX_CACHE_AT).total_seconds()
            < AKSHARE_CACHE_TTL_SECONDS
        ):
            return _AKSHARE_GLOBAL_INDEX_CACHE

    try:
        df = ak.index_global_spot_em()
    except Exception:
        # 缓存失败结果，避免同一轮快照内重复触发上游请求风暴
        with _AKSHARE_CACHE_LOCK:
            _AKSHARE_GLOBAL_INDEX_CACHE = pd.DataFrame()
            _AKSHARE_GLOBAL_INDEX_CACHE_AT = now
        raise

    with _AKSHARE_CACHE_LOCK:
        _AKSHARE_GLOBAL_INDEX_CACHE = df
        _AKSHARE_GLOBAL_INDEX_CACHE_AT = now
    return df


def _get_cached_crypto_df(ak: Any) -> pd.DataFrame:
    global _AKSHARE_CRYPTO_CACHE
    global _AKSHARE_CRYPTO_CACHE_AT

    now = datetime.now(UTC)
    with _AKSHARE_CACHE_LOCK:
        if (
            _AKSHARE_CRYPTO_CACHE is not None
            and _AKSHARE_CRYPTO_CACHE_AT is not None
            and (now - _AKSHARE_CRYPTO_CACHE_AT).total_seconds()
            < AKSHARE_CACHE_TTL_SECONDS
        ):
            return _AKSHARE_CRYPTO_CACHE

    try:
        df = ak.crypto_js_spot()
    except Exception:
        with _AKSHARE_CACHE_LOCK:
            _AKSHARE_CRYPTO_CACHE = pd.DataFrame()
            _AKSHARE_CRYPTO_CACHE_AT = now
        raise

    with _AKSHARE_CACHE_LOCK:
        _AKSHARE_CRYPTO_CACHE = df
        _AKSHARE_CRYPTO_CACHE_AT = now
    return df


def _tnx_to_percent(value: float) -> float:
    return value / 10


def _format_number(value: float) -> str:
    return f"{value:,.2f}"


def _format_percent(value: float) -> str:
    return f"{value:.2f}%"


def _format_fx(value: float) -> str:
    return f"{value:.4f}"
