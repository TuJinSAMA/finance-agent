import asyncio
import contextlib
import logging
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from threading import Lock
from typing import Any, Callable

import pandas as pd
import requests as _requests

from src.schemas.public_board import (
    MarketGroupSnapshot,
    MarketMetric,
    SnapshotGroup,
)

logger = logging.getLogger(__name__)

_PROXY_ENV_KEYS = (
    "HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy",
    "ALL_PROXY", "all_proxy",
)


@contextlib.contextmanager
def _no_proxy_env():
    saved: dict[str, str | None] = {}
    for key in _PROXY_ENV_KEYS:
        saved[key] = os.environ.get(key)
        os.environ.pop(key, None)
    try:
        yield
    finally:
        for key, val in saved.items():
            if val is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = val


_NO_PROXY_SESSION: _requests.Session | None = None


def _get_no_proxy_session() -> _requests.Session:
    global _NO_PROXY_SESSION
    if _NO_PROXY_SESSION is not None:
        return _NO_PROXY_SESSION
    s = _requests.Session()
    s.trust_env = False
    s.proxies = {"http": None, "https": None}
    _NO_PROXY_SESSION = s
    return s

SOURCE_NAME = "akshare"

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

YAHOO_FETCH_TIMEOUT_SECONDS = 10.0
YAHOO_BASE_URL = "https://query1.finance.yahoo.com/v8/finance/chart"

YAHOO_CHART_SYMBOLS: frozenset[str] = frozenset({
    YFINANCE_SYMBOLS["VIX"],
    YFINANCE_SYMBOLS["DXY"],
    YFINANCE_SYMBOLS["SPX"],
    YFINANCE_SYMBOLS["NASDAQ"],
    YFINANCE_SYMBOLS["GOLD"],
    YFINANCE_SYMBOLS["WTI"],
    YFINANCE_SYMBOLS["BTC"],
})

AKSHARE_TREASURY_SYMBOLS: dict[str, str] = {
    YFINANCE_SYMBOLS["US10Y"]: "美国10年期国债",
    US2Y_SYMBOL: "美国2年期国债",
}

FETCH_CONCURRENT_LIMIT = 3
FETCH_RETRY_ATTEMPTS = 3
FETCH_RETRY_BACKOFF = [1, 2, 4]
FETCH_REQUEST_DELAY = 0.2
FETCH_OVERALL_TIMEOUT_SECONDS = 15.0

_FETCH_SEMAPHORE = asyncio.Semaphore(FETCH_CONCURRENT_LIMIT)

AKSHARE_INDEX_CODE_MAP: dict[str, list[str]] = {
    YFINANCE_SYMBOLS["SPX"]: ["SPX"],
    YFINANCE_SYMBOLS["NASDAQ"]: ["NDX"],
    YFINANCE_SYMBOLS["DXY"]: ["UDI"],
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
_AKSHARE_TREASURY_CACHE: dict[str, tuple[pd.DataFrame, datetime]] = {}


@dataclass(slots=True)
class QuoteSnapshot:
    value: float
    previous_value: float | None
    change_pct: float | None





async def build_crypto_snapshot(as_of: datetime) -> MarketGroupSnapshot:
    btc_quote = await _safe_fetch_quote(YFINANCE_SYMBOLS["BTC"])
    items = [_metric_from_quote("BTC", YFINANCE_SYMBOLS["BTC"], btc_quote, _format_number)]
    return _build_group_snapshot(group="crypto", as_of=as_of, items=items)


async def build_extended_snapshot(as_of: datetime) -> MarketGroupSnapshot:
    quotes = await asyncio.gather(
        _safe_fetch_quote(YFINANCE_SYMBOLS["VIX"]),
        _safe_fetch_quote(YFINANCE_SYMBOLS["US10Y"]),
        _safe_fetch_quote(YFINANCE_SYMBOLS["DXY"]),
        _safe_fetch_quote(US2Y_SYMBOL),
        _safe_fetch_quote(YFINANCE_SYMBOLS["GOLD"]),
        _safe_fetch_quote(YFINANCE_SYMBOLS["WTI"]),
    )
    vix_q, us10y_q, dxy_q, us2y_q, gold_q, wti_q = quotes
    items = [
        _metric_from_quote("VIX", YFINANCE_SYMBOLS["VIX"], vix_q, _format_number),
        _metric_from_quote("US 10Y", YFINANCE_SYMBOLS["US10Y"], us10y_q, _format_percent),
        _metric_from_quote("DXY", YFINANCE_SYMBOLS["DXY"], dxy_q, _format_number),
        _build_spread_metric(us2y_q, us10y_q),
        _metric_from_quote("Gold", YFINANCE_SYMBOLS["GOLD"], gold_q, _format_number),
        _metric_from_quote("WTI", YFINANCE_SYMBOLS["WTI"], wti_q, _format_number),
    ]
    return _build_group_snapshot(group="extended", as_of=as_of, items=items)


async def build_equity_snapshot(as_of: datetime) -> MarketGroupSnapshot:
    quotes = await asyncio.gather(
        _safe_fetch_quote(YFINANCE_SYMBOLS["SPX"]),
        _safe_fetch_quote(YFINANCE_SYMBOLS["NASDAQ"]),
    )
    spx_q, nasdaq_q = quotes
    items = [
        _metric_from_quote("S&P 500", YFINANCE_SYMBOLS["SPX"], spx_q, _format_number),
        _metric_from_quote("NASDAQ", YFINANCE_SYMBOLS["NASDAQ"], nasdaq_q, _format_number),
    ]
    return _build_group_snapshot(group="equity", as_of=as_of, items=items)


MACRO_ITEM_NAMES = {"VIX", "US 10Y", "DXY", "2Y-10Y Spread"}
ASSET_ITEM_NAMES_FROM_EXTENDED = {"Gold", "WTI"}


async def build_macro_snapshot(as_of: datetime) -> MarketGroupSnapshot:
    extended = await build_extended_snapshot(as_of)
    macro_items = [item for item in extended.items if item.name in MACRO_ITEM_NAMES]
    return extended.model_copy(update={"group": "macro", "items": macro_items})


async def build_assets_snapshot(as_of: datetime) -> MarketGroupSnapshot:
    crypto, equity, extended = await asyncio.gather(
        build_crypto_snapshot(as_of),
        build_equity_snapshot(as_of),
        build_extended_snapshot(as_of),
    )
    asset_items = [item for item in extended.items if item.name in ASSET_ITEM_NAMES_FROM_EXTENDED]
    asset_items += crypto.items + equity.items
    return MarketGroupSnapshot(
        group="assets",
        status="ok",
        as_of=as_of,
        last_success_at=as_of,
        source=SOURCE_NAME,
        items=asset_items,
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

    spread_bps = (us10y_quote.value - us2y_quote.value) * 100
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
    if value is None:
        return MarketMetric(
            name=name,
            symbol=symbol,
            value=None,
            display=None,
            change_pct=None if change_pct is None else round(change_pct, 2),
            status=status or "unavailable",
        )

    rounded_value = round(value, 4)
    return MarketMetric(
        name=name,
        symbol=symbol,
        value=rounded_value,
        display=display or f"{rounded_value:.2f}",
        change_pct=None if change_pct is None else round(change_pct, 2),
        status=status or "ok",
    )


async def _safe_fetch_quote(symbol: str) -> QuoteSnapshot | None:
    async with _FETCH_SEMAPHORE:
        for attempt in range(FETCH_RETRY_ATTEMPTS):
            try:
                result = await asyncio.wait_for(
                    asyncio.to_thread(_load_quote_snapshot, symbol),
                    timeout=FETCH_OVERALL_TIMEOUT_SECONDS,
                )
                if result is not None:
                    return result
            except Exception as exc:
                logger.warning(
                    "Failed to fetch public board metric %s (attempt %d/%d): %s",
                    symbol,
                    attempt + 1,
                    FETCH_RETRY_ATTEMPTS,
                    exc,
                )
                if attempt < FETCH_RETRY_ATTEMPTS - 1:
                    wait = FETCH_RETRY_BACKOFF[attempt]
                    logger.info("Retrying %s in %d seconds...", symbol, wait)
                    await asyncio.sleep(wait)
        return None


def _load_quote_snapshot(symbol: str) -> QuoteSnapshot | None:
    with _no_proxy_env():
        if symbol in AKSHARE_TREASURY_SYMBOLS:
            return _load_treasury_quote(symbol)

        if symbol == YFINANCE_SYMBOLS["BTC"]:
            import akshare as ak
            result = _load_btc_quote(ak)
            if result is not None:
                return result

        if symbol in YAHOO_CHART_SYMBOLS:
            return _load_yahoo_quote(symbol)

        return _load_global_index_quote_cached(symbol)


def _load_treasury_quote(symbol: str) -> QuoteSnapshot | None:
    import akshare as ak

    ak_name = AKSHARE_TREASURY_SYMBOLS.get(symbol)
    if ak_name is None:
        return None

    try:
        df = _get_cached_treasury_df(ak, symbol)
    except Exception as exc:
        logger.debug("akshare bond_gb_us_sina failed for %s: %s", symbol, exc)
        return None

    if df is None or df.empty:
        return None

    last_row = df.iloc[-1]
    close = _to_float(last_row.get("close"))
    if close is None:
        return None

    if len(df) >= 2:
        prev_close = _to_float(df.iloc[-2].get("close"))
        change_pct = ((close - prev_close) / prev_close * 100) if prev_close else None
    else:
        change_pct = None

    previous = None if change_pct in (None, -100.0) else close / (1 + change_pct / 100)
    return QuoteSnapshot(value=close, previous_value=previous, change_pct=change_pct)


def _get_cached_treasury_df(ak: Any, symbol: str) -> pd.DataFrame:
    global _AKSHARE_TREASURY_CACHE

    now = datetime.now(UTC)
    with _AKSHARE_CACHE_LOCK:
        cached = _AKSHARE_TREASURY_CACHE.get(symbol)
        if cached is not None:
            df, ts = cached
            if (now - ts).total_seconds() < AKSHARE_CACHE_TTL_SECONDS:
                return df

        try:
            df = ak.bond_gb_us_sina(symbol=AKSHARE_TREASURY_SYMBOLS[symbol])
            _AKSHARE_TREASURY_CACHE[symbol] = (df, now)
            return df
        except Exception:
            _AKSHARE_TREASURY_CACHE[symbol] = (pd.DataFrame(), now)
            raise


def _load_yahoo_quote(symbol: str) -> QuoteSnapshot | None:
    session = _get_no_proxy_session()
    url = f"{YAHOO_BASE_URL}/{_requests.utils.quote(symbol)}"
    params = {"range": "2d", "interval": "1d"}
    headers = {"User-Agent": "Mozilla/5.0"}

    try:
        resp = session.get(url, params=params, headers=headers, timeout=YAHOO_FETCH_TIMEOUT_SECONDS)
        if resp.status_code != 200:
            logger.debug("Yahoo Finance returned %d for %s", resp.status_code, symbol)
            return None
        data = resp.json()
    except Exception as exc:
        logger.debug("Yahoo Finance request failed for %s: %s", symbol, exc)
        return None

    try:
        result = data.get("chart", {}).get("result", [])
        if not result:
            return None
        meta = result[0].get("meta", {})
        price = meta.get("regularMarketPrice")
        prev = meta.get("chartPreviousClose")
        if price is None:
            return None
        change_pct = ((price - prev) / prev * 100) if prev else None
        previous = None if change_pct in (None, -100.0) else price / (1 + change_pct / 100)
        return QuoteSnapshot(value=float(price), previous_value=previous, change_pct=change_pct)
    except (KeyError, IndexError, TypeError) as exc:
        logger.debug("Yahoo Finance parse failed for %s: %s", symbol, exc)
        return None


def _load_global_index_quote_cached(symbol: str) -> QuoteSnapshot | None:
    import akshare as ak

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
    global _AKSHARE_GLOBAL_INDEX_CACHE, _AKSHARE_GLOBAL_INDEX_CACHE_AT

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
            _AKSHARE_GLOBAL_INDEX_CACHE = df
            _AKSHARE_GLOBAL_INDEX_CACHE_AT = now
            return df
        except Exception:
            _AKSHARE_GLOBAL_INDEX_CACHE = pd.DataFrame()
            _AKSHARE_GLOBAL_INDEX_CACHE_AT = now
            raise


def _get_cached_crypto_df(ak: Any) -> pd.DataFrame:
    global _AKSHARE_CRYPTO_CACHE, _AKSHARE_CRYPTO_CACHE_AT

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
            _AKSHARE_CRYPTO_CACHE = df
            _AKSHARE_CRYPTO_CACHE_AT = now
            return df
        except Exception:
            _AKSHARE_CRYPTO_CACHE = pd.DataFrame()
            _AKSHARE_CRYPTO_CACHE_AT = now
            raise


def _format_number(value: float) -> str:
    return f"{value:,.2f}"


def _format_percent(value: float) -> str:
    return f"{value:.2f}%"



