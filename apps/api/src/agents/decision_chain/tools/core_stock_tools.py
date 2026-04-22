from datetime import datetime
from typing import Annotated

import yfinance as yf
from langchain_core.tools import tool


@tool
def get_stock_data(
    symbol: Annotated[str, "ticker symbol of the company"],
    start_date: Annotated[str, "Start date in yyyy-mm-dd format"],
    end_date: Annotated[str, "End date in yyyy-mm-dd format"],
) -> str:
    """Retrieve stock price data (OHLCV) for a given ticker symbol."""
    datetime.strptime(start_date, "%Y-%m-%d")
    datetime.strptime(end_date, "%Y-%m-%d")
    ticker = yf.Ticker(symbol.upper())
    data = ticker.history(start=start_date, end=end_date)
    if data.empty:
        return f"No data found for symbol '{symbol}' between {start_date} and {end_date}"
    if data.index.tz is not None:
        data.index = data.index.tz_localize(None)
    numeric_columns = ["Open", "High", "Low", "Close", "Adj Close"]
    for col in numeric_columns:
        if col in data.columns:
            data[col] = data[col].round(2)
    csv_string = data.to_csv()
    header = f"# Stock data for {symbol.upper()} from {start_date} to {end_date}\n"
    header += f"# Total records: {len(data)}\n"
    header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    return header + csv_string