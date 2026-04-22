from datetime import datetime
from typing import Annotated

import pandas as pd
import yfinance as yf
from dateutil.relativedelta import relativedelta
from langchain_core.tools import tool


@tool
def get_indicators(
    symbol: Annotated[str, "ticker symbol of the company"],
    indicator: Annotated[str, "technical indicator name, e.g. 'rsi', 'macd'"],
    curr_date: Annotated[str, "The current trading date, YYYY-mm-dd"],
    look_back_days: Annotated[int, "how many days to look back"] = 30,
) -> str:
    """Retrieve a single technical indicator for a given ticker symbol. Comma-separated indicator names are supported."""
    indicators = [i.strip().lower() for i in indicator.split(",") if i.strip()]
    results = []
    for ind in indicators:
        try:
            results.append(_get_single_indicator(symbol, ind, curr_date, look_back_days))
        except Exception as e:
            results.append(f"Error getting {ind}: {str(e)}")
    return "\n\n".join(results)


def _get_single_indicator(symbol: str, indicator: str, curr_date: str, look_back_days: int) -> str:
    from stockstats import wrap

    best_ind_params = {
        "close_50_sma": "50 SMA: A medium-term trend indicator.",
        "close_200_sma": "200 SMA: A long-term trend benchmark.",
        "close_10_ema": "10 EMA: A responsive short-term average.",
        "macd": "MACD: Computes momentum via differences of EMAs.",
        "macds": "MACD Signal: An EMA smoothing of the MACD line.",
        "macdh": "MACD Histogram: Shows gap between MACD line and signal.",
        "rsi": "RSI: Measures momentum, overbought/oversold.",
        "boll": "Bollinger Middle: 20 SMA basis for Bollinger Bands.",
        "boll_ub": "Bollinger Upper Band.",
        "boll_lb": "Bollinger Lower Band.",
        "atr": "ATR: Averages true range for volatility.",
        "vwma": "VWMA: Volume-weighted moving average.",
    }

    if indicator not in best_ind_params:
        raise ValueError(f"Indicator {indicator} not supported. Choose from: {list(best_ind_params.keys())}")

    curr_date_dt = datetime.strptime(curr_date, "%Y-%m-%d")
    before = curr_date_dt - relativedelta(days=look_back_days)
    end_date = curr_date_dt + relativedelta(days=1)
    start_date = before.strftime("%Y-%m-%d")

    ticker = yf.Ticker(symbol.upper())
    data = ticker.history(start=start_date, end=end_date.strftime("%Y-%m-%d"))
    if data.empty:
        return f"No data for {symbol} to compute {indicator}"

    data.index = data.index.tz_localize(None)
    df = wrap(data.copy())
    df["Date"] = df.index.strftime("%Y-%m-%d")

    try:
        df[indicator]
    except Exception:
        pass

    ind_values = {}
    for idx, row in df.iterrows():
        date_str = row.get("Date", str(idx))
        val = row.get(indicator)
        if pd.isna(val) if isinstance(val, float) else False:
            ind_values[str(date_str)] = "N/A"
        else:
            ind_values[str(date_str)] = str(val)

    current_dt = curr_date_dt
    ind_string = ""
    while current_dt >= before:
        ds = current_dt.strftime("%Y-%m-%d")
        ind_string += f"{ds}: {ind_values.get(ds, 'N/A: Not a trading day')}\n"
        current_dt -= relativedelta(days=1)

    result_str = (
        f"## {indicator} values from {before.strftime('%Y-%m-%d')} to {curr_date}:\n\n"
        + ind_string
        + "\n\n"
        + best_ind_params.get(indicator, "No description available.")
    )
    return result_str