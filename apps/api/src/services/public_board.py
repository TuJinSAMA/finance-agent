import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Callable

from src.schemas.public_board import MarketMetric, MarketState, PublicMarketBoardResponse

logger = logging.getLogger(__name__)

CACHE_TTL = timedelta(minutes=10)
SOURCE_NAME = "yfinance"
YFINANCE_FETCH_TIMEOUT_SECONDS = 5.0
YFINANCE_SYMBOLS: dict[str, str] = {
    "VIX": "^VIX",
    "US10Y": "^TNX",
    "DXY": "DX-Y.NYB",
    "SPX": "^GSPC",
    "NASDAQ": "^IXIC",
    "GOLD": "GC=F",
    "WTI": "CL=F",
    "BTC": "BTC-USD",
    "CSI300": "000300.SS",
    "USDCNY": "CNY=X",
}
US2Y_SYMBOL = "^UST2Y"

_CACHE_LOCK = asyncio.Lock()
_CACHE_PAYLOAD: PublicMarketBoardResponse | None = None
_CACHE_EXPIRES_AT: datetime | None = None


@dataclass(slots=True)
class QuoteSnapshot:
    value: float
    previous_value: float | None
    change_pct: float | None


def classify_market_state(
    vix: float | None,
    us10y_change_bps: float | None,
    spx_change_pct: float | None,
) -> str:
    if vix is None or us10y_change_bps is None or spx_change_pct is None:
        return "Data Incomplete 数据不足"
    if (
        (vix or 0) >= 25
        and (us10y_change_bps or 0) >= 5
        and (spx_change_pct or 0) <= -0.75
    ):
        return "Risk-Off 偏避险"
    if (vix or 99) <= 18 and (spx_change_pct or 0) >= 0.75:
        return "Risk-On 偏风险"
    return "Neutral 中性"


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


async def get_public_market_board() -> PublicMarketBoardResponse:
    now = datetime.now(UTC)
    cached_payload = _get_cached_payload(now)
    if cached_payload is not None:
        return cached_payload

    async with _CACHE_LOCK:
        now = datetime.now(UTC)
        cached_payload = _get_cached_payload(now)
        if cached_payload is not None:
            return cached_payload

        try:
            payload = await _build_public_market_board(now)
        except Exception:
            logger.exception("Failed to build public market board payload")
            stale_payload = _get_stale_cached_payload()
            if stale_payload is not None:
                return stale_payload
            raise

        global _CACHE_PAYLOAD, _CACHE_EXPIRES_AT
        _CACHE_PAYLOAD = payload
        _CACHE_EXPIRES_AT = now + CACHE_TTL
        return payload


def _get_cached_payload(now: datetime) -> PublicMarketBoardResponse | None:
    if _CACHE_PAYLOAD is None or _CACHE_EXPIRES_AT is None:
        return None
    if now >= _CACHE_EXPIRES_AT:
        return None
    return _CACHE_PAYLOAD


def _get_stale_cached_payload() -> PublicMarketBoardResponse | None:
    if _CACHE_PAYLOAD is None:
        return None
    return _mark_payload_stale(_CACHE_PAYLOAD)


def _mark_payload_stale(
    payload: PublicMarketBoardResponse,
) -> PublicMarketBoardResponse:
    return payload.model_copy(
        update={
            "macro": _mark_metric_group_stale(payload.macro),
            "assets": _mark_metric_group_stale(payload.assets),
            "custom": _mark_metric_group_stale(payload.custom),
            "source": f"{payload.source} (stale cache)",
        }
    )


def _mark_metric_group_stale(metrics: list[MarketMetric]) -> list[MarketMetric]:
    return [
        metric.model_copy(
            update={
                "status": "stale" if metric.value is not None else metric.status,
            }
        )
        for metric in metrics
    ]


async def _build_public_market_board(
    as_of: datetime,
) -> PublicMarketBoardResponse:
    quotes = await asyncio.gather(
        _safe_fetch_quote(YFINANCE_SYMBOLS["VIX"]),
        _safe_fetch_quote(YFINANCE_SYMBOLS["US10Y"]),
        _safe_fetch_quote(YFINANCE_SYMBOLS["DXY"]),
        _safe_fetch_quote(YFINANCE_SYMBOLS["SPX"]),
        _safe_fetch_quote(YFINANCE_SYMBOLS["NASDAQ"]),
        _safe_fetch_quote(YFINANCE_SYMBOLS["GOLD"]),
        _safe_fetch_quote(YFINANCE_SYMBOLS["WTI"]),
        _safe_fetch_quote(YFINANCE_SYMBOLS["BTC"]),
        _safe_fetch_quote(YFINANCE_SYMBOLS["CSI300"]),
        _safe_fetch_quote(YFINANCE_SYMBOLS["USDCNY"]),
        _safe_fetch_quote(US2Y_SYMBOL),
    )
    (
        vix_quote,
        us10y_quote,
        dxy_quote,
        spx_quote,
        nasdaq_quote,
        gold_quote,
        wti_quote,
        btc_quote,
        csi300_quote,
        usdcny_quote,
        us2y_quote,
    ) = quotes

    us10y_change_bps = _yield_change_bps(us10y_quote)
    spx_change_pct = None if spx_quote is None else spx_quote.change_pct
    market_label = classify_market_state(
        vix=None if vix_quote is None else vix_quote.value,
        us10y_change_bps=us10y_change_bps,
        spx_change_pct=spx_change_pct,
    )

    macro = [
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
    assets = [
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
    custom = [
        _metric_from_quote(
            "CSI 300",
            YFINANCE_SYMBOLS["CSI300"],
            csi300_quote,
            _format_number,
        ),
        _metric_from_quote(
            "USD/CNY",
            YFINANCE_SYMBOLS["USDCNY"],
            usdcny_quote,
            _format_fx,
        ),
    ]

    return PublicMarketBoardResponse(
        market_state=MarketState(
            date=as_of.date(),
            label=market_label,
            summary=_build_market_summary(market_label, macro, assets),
        ),
        macro=[MarketMetric(**metric) for metric in macro],
        assets=[MarketMetric(**metric) for metric in assets],
        custom=[MarketMetric(**metric) for metric in custom],
        as_of=as_of,
        source=SOURCE_NAME,
    )


def _build_market_summary(
    market_label: str,
    macro: list[dict[str, Any]],
    assets: list[dict[str, Any]],
) -> str:
    available_macro = sum(metric["status"] == "ok" for metric in macro)
    available_assets = sum(metric["status"] == "ok" for metric in assets)
    return (
        f"{market_label}; macro available {available_macro}/{len(macro)}, "
        f"assets available {available_assets}/{len(assets)}."
    )


def _build_spread_metric(
    us2y_quote: QuoteSnapshot | None,
    us10y_quote: QuoteSnapshot | None,
) -> dict[str, Any]:
    if us2y_quote is None or us10y_quote is None:
        return normalize_metric(
            name="2Y-10Y Spread",
            symbol=f"{US2Y_SYMBOL}/{YFINANCE_SYMBOLS['US10Y']}",
            value=None,
            change_pct=None,
        )

    spread_bps = (_tnx_to_percent(us10y_quote.value) - _tnx_to_percent(us2y_quote.value)) * 100
    return normalize_metric(
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
) -> dict[str, Any]:
    if quote is None:
        return normalize_metric(name=name, symbol=symbol, value=None, change_pct=None)

    value = quote.value if transform is None else transform(quote.value)
    return normalize_metric(
        name=name,
        symbol=symbol,
        value=value,
        change_pct=quote.change_pct,
        display=formatter(value),
    )


async def _safe_fetch_quote(symbol: str) -> QuoteSnapshot | None:
    try:
        return await _fetch_quote(symbol)
    except Exception as exc:
        logger.warning("Failed to fetch public board metric %s: %s", symbol, exc)
        return None


async def _fetch_quote(symbol: str) -> QuoteSnapshot | None:
    return await asyncio.wait_for(
        asyncio.to_thread(_load_quote_snapshot, symbol),
        timeout=YFINANCE_FETCH_TIMEOUT_SECONDS,
    )


def _load_quote_snapshot(symbol: str) -> QuoteSnapshot | None:
    import yfinance as yf

    history = yf.Ticker(symbol).history(period="5d", interval="1d", auto_adjust=False)
    if history is None or history.empty or "Close" not in history:
        return None

    closes = history["Close"].dropna()
    if closes.empty:
        return None

    latest = float(closes.iloc[-1])
    previous = float(closes.iloc[-2]) if len(closes) > 1 else None
    if previous in (None, 0):
        change_pct = None
    else:
        change_pct = ((latest - previous) / previous) * 100

    return QuoteSnapshot(value=latest, previous_value=previous, change_pct=change_pct)


def _yield_change_bps(quote: QuoteSnapshot | None) -> float | None:
    if quote is None or quote.previous_value is None:
        return None
    return round((quote.value - quote.previous_value) * 10, 2)


def _tnx_to_percent(value: float) -> float:
    return value / 10


def _format_number(value: float) -> str:
    return f"{value:,.2f}"


def _format_percent(value: float) -> str:
    return f"{value:.2f}%"


def _format_fx(value: float) -> str:
    return f"{value:.4f}"
