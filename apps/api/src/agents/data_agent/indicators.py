import logging
from datetime import date

import numpy as np
import pandas as pd
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.agents.screener_config import screener_config
from src.models.stock import StockDailyQuote, StockTechnicalIndicator

logger = logging.getLogger(__name__)


def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    计算全部技术指标，返回与输入等长的 DataFrame（前面若干行因窗口不足会是 NaN）。

    输入列要求: close, high, low, volume
    输出列: ma5, ma10, ma20, ma60, macd, macd_signal, macd_hist,
            rsi_14, boll_upper, boll_mid, boll_lower, atr_14,
            volume_ma5, volume_ma20
    """
    out = pd.DataFrame(index=df.index)

    close = df["close"].astype(float)
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    volume = df["volume"].astype(float)

    # ── Moving Averages ──
    out["ma5"] = close.rolling(5).mean()
    out["ma10"] = close.rolling(10).mean()
    out["ma20"] = close.rolling(20).mean()
    out["ma60"] = close.rolling(60).mean()

    # ── MACD (12, 26, 9) ──
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    out["macd"] = ema12 - ema26
    out["macd_signal"] = out["macd"].ewm(span=9, adjust=False).mean()
    out["macd_hist"] = out["macd"] - out["macd_signal"]

    # ── RSI-14 ──
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta).where(delta < 0, 0.0)
    avg_gain = gain.ewm(alpha=1 / 14, min_periods=14, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / 14, min_periods=14, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100.0 - 100.0 / (1.0 + rs)
    # avg_loss==0 → rs=NaN → rsi=NaN, but should be 100 (all gains, no losses)
    rsi = rsi.fillna(pd.Series(np.where(avg_gain > 0, 100.0, 50.0), index=rsi.index))
    out["rsi_14"] = rsi

    # ── Bollinger Bands (20, 2) ──
    out["boll_mid"] = close.rolling(20).mean()
    boll_std = close.rolling(20).std()
    out["boll_upper"] = out["boll_mid"] + 2 * boll_std
    out["boll_lower"] = out["boll_mid"] - 2 * boll_std

    # ── ATR-14 ──
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    out["atr_14"] = tr.ewm(span=14, adjust=False).mean()

    # ── Volume Moving Averages ──
    out["volume_ma5"] = volume.rolling(5).mean()
    out["volume_ma20"] = volume.rolling(20).mean()

    return out


async def compute_and_store_indicators(
    db: AsyncSession,
    stock_id: int,
    target_date: date | None = None,
) -> bool:
    """
    计算某只股票截至 target_date 的技术指标并写入数据库。
    需要至少 MIN_DAYS_FOR_INDICATORS 天的历史日线数据。
    返回是否成功写入。
    """
    if target_date is None:
        target_date = date.today()

    result = await db.execute(
        select(
            StockDailyQuote.trade_date,
            StockDailyQuote.close,
            StockDailyQuote.high,
            StockDailyQuote.low,
            StockDailyQuote.volume,
        )
        .where(StockDailyQuote.stock_id == stock_id)
        .where(StockDailyQuote.trade_date <= target_date)
        .order_by(StockDailyQuote.trade_date.asc())
        .limit(250)
    )
    rows = result.all()

    min_days = screener_config.min_days_for_indicators
    if len(rows) < min_days:
        logger.debug("Stock %d has only %d days of data, need %d. Skipping indicators.",
                      stock_id, len(rows), min_days)
        return False

    df = pd.DataFrame(rows, columns=["trade_date", "close", "high", "low", "volume"])
    indicators = compute_indicators(df)

    last_idx = indicators.index[-1]
    last_row = indicators.loc[last_idx]
    last_trade_date = df.loc[last_idx, "trade_date"]

    record = {
        "stock_id": stock_id,
        "trade_date": last_trade_date,
        "ma5": _nan_to_none(last_row.get("ma5")),
        "ma10": _nan_to_none(last_row.get("ma10")),
        "ma20": _nan_to_none(last_row.get("ma20")),
        "ma60": _nan_to_none(last_row.get("ma60")),
        "macd": _nan_to_none(last_row.get("macd")),
        "macd_signal": _nan_to_none(last_row.get("macd_signal")),
        "macd_hist": _nan_to_none(last_row.get("macd_hist")),
        "rsi_14": _nan_to_none(last_row.get("rsi_14")),
        "boll_upper": _nan_to_none(last_row.get("boll_upper")),
        "boll_mid": _nan_to_none(last_row.get("boll_mid")),
        "boll_lower": _nan_to_none(last_row.get("boll_lower")),
        "atr_14": _nan_to_none(last_row.get("atr_14")),
        "volume_ma5": _nan_to_none_int(last_row.get("volume_ma5")),
        "volume_ma20": _nan_to_none_int(last_row.get("volume_ma20")),
    }

    stmt = pg_insert(StockTechnicalIndicator).values([record])
    stmt = stmt.on_conflict_do_update(
        index_elements=["stock_id", "trade_date"],
        set_={k: getattr(stmt.excluded, k) for k in record if k not in ("stock_id", "trade_date")},
    )
    await db.execute(stmt)
    return True


def _nan_to_none(val) -> float | None:
    if val is None:
        return None
    try:
        v = float(val)
        return None if np.isnan(v) else round(v, 4)
    except (ValueError, TypeError):
        return None


def _nan_to_none_int(val) -> int | None:
    if val is None:
        return None
    try:
        v = float(val)
        return None if np.isnan(v) else int(round(v))
    except (ValueError, TypeError):
        return None
