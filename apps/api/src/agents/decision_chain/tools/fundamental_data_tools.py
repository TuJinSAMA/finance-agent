from datetime import datetime
from typing import Annotated

import yfinance as yf
from langchain_core.tools import tool


@tool
def get_fundamentals(
    ticker: Annotated[str, "ticker symbol"],
    curr_date: Annotated[str, "current date, yyyy-mm-dd"],
) -> str:
    """Retrieve comprehensive fundamental data for a given ticker symbol."""
    try:
        ticker_obj = yf.Ticker(ticker.upper())
        info = ticker_obj.info
        if not info:
            return f"No fundamentals data found for symbol '{ticker}'"
        fields = [
            ("Name", info.get("longName")),
            ("Sector", info.get("sector")),
            ("Industry", info.get("industry")),
            ("Market Cap", info.get("marketCap")),
            ("PE Ratio (TTM)", info.get("trailingPE")),
            ("Forward PE", info.get("forwardPE")),
            ("PEG Ratio", info.get("pegRatio")),
            ("Price to Book", info.get("priceToBook")),
            ("EPS (TTM)", info.get("trailingEps")),
            ("Forward EPS", info.get("forwardEps")),
            ("Dividend Yield", info.get("dividendYield")),
            ("Beta", info.get("beta")),
            ("52 Week High", info.get("fiftyTwoWeekHigh")),
            ("52 Week Low", info.get("fiftyTwoWeekLow")),
            ("50 Day Average", info.get("fiftyDayAverage")),
            ("200 Day Average", info.get("twoHundredDayAverage")),
            ("Revenue (TTM)", info.get("totalRevenue")),
            ("Gross Profit", info.get("grossProfits")),
            ("EBITDA", info.get("ebitda")),
            ("Net Income", info.get("netIncomeToCommon")),
            ("Profit Margin", info.get("profitMargins")),
            ("Operating Margin", info.get("operatingMargins")),
            ("Return on Equity", info.get("returnOnEquity")),
            ("Return on Assets", info.get("returnOnAssets")),
            ("Debt to Equity", info.get("debtToEquity")),
            ("Current Ratio", info.get("currentRatio")),
            ("Book Value", info.get("bookValue")),
            ("Free Cash Flow", info.get("freeCashflow")),
        ]
        lines = [f"{label}: {value}" for label, value in fields if value is not None]
        header = f"# Company Fundamentals for {ticker.upper()}\n"
        header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        return header + "\n".join(lines)
    except Exception as e:
        return f"Error retrieving fundamentals for {ticker}: {str(e)}"


@tool
def get_balance_sheet(
    ticker: Annotated[str, "ticker symbol"],
    freq: Annotated[str, "reporting frequency: annual/quarterly"] = "quarterly",
    curr_date: Annotated[str, "current date, yyyy-mm-dd"] = None,
) -> str:
    """Retrieve balance sheet data for a given ticker symbol."""
    try:
        ticker_obj = yf.Ticker(ticker.upper())
        data = ticker_obj.quarterly_balance_sheet if freq.lower() == "quarterly" else ticker_obj.balance_sheet
        if data.empty:
            return f"No balance sheet data found for symbol '{ticker}'"
        csv_string = data.to_csv()
        header = f"# Balance Sheet data for {ticker.upper()} ({freq})\n"
        header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        return header + csv_string
    except Exception as e:
        return f"Error retrieving balance sheet for {ticker}: {str(e)}"


@tool
def get_cashflow(
    ticker: Annotated[str, "ticker symbol"],
    freq: Annotated[str, "reporting frequency: annual/quarterly"] = "quarterly",
    curr_date: Annotated[str, "current date, yyyy-mm-dd"] = None,
) -> str:
    """Retrieve cash flow statement data for a given ticker symbol."""
    try:
        ticker_obj = yf.Ticker(ticker.upper())
        data = ticker_obj.quarterly_cashflow if freq.lower() == "quarterly" else ticker_obj.cashflow
        if data.empty:
            return f"No cash flow data found for symbol '{ticker}'"
        csv_string = data.to_csv()
        header = f"# Cash Flow data for {ticker.upper()} ({freq})\n"
        header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        return header + csv_string
    except Exception as e:
        return f"Error retrieving cash flow for {ticker}: {str(e)}"


@tool
def get_income_statement(
    ticker: Annotated[str, "ticker symbol"],
    freq: Annotated[str, "reporting frequency: annual/quarterly"] = "quarterly",
    curr_date: Annotated[str, "current date, yyyy-mm-dd"] = None,
) -> str:
    """Retrieve income statement data for a given ticker symbol."""
    try:
        ticker_obj = yf.Ticker(ticker.upper())
        data = ticker_obj.quarterly_income_stmt if freq.lower() == "quarterly" else ticker_obj.income_stmt
        if data.empty:
            return f"No income statement data found for symbol '{ticker}'"
        csv_string = data.to_csv()
        header = f"# Income Statement data for {ticker.upper()} ({freq})\n"
        header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        return header + csv_string
    except Exception as e:
        return f"Error retrieving income statement for {ticker}: {str(e)}"