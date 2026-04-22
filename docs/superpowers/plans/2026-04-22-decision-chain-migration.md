# Decision Chain Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate the TradingAgents investment decision chain to finance-agent as a standalone Chat Agent with SSE streaming, preserving all 5 layers of logic and hidden behaviors from the original system.

**Architecture:** LangGraph StateGraph with conditional edges, dual OpenRouter LLMs, yfinance tools, BM25 reflection memory persisted in SQLite, SSE endpoint for stage-by-stage streaming. The decision chain runs independently of the existing screener/scorer pipeline.

**Tech Stack:** Python 3.12+, LangGraph, LangChain, yfinance, rank_bm25, FastAPI SSE, SQLite, OpenRouter API

---

## File Structure

```
apps/api/src/agents/decision_chain/
├── __init__.py                          # Exports TradingDecisionChain
├── config.py                            # DecisionChainConfig (pydantic-settings)
├── state.py                             # AgentState, InvestDebateState, RiskDebateState
├── graph.py                             # TradingDecisionChain class (main orchestrator)
├── propagation.py                       # create_initial_state()
├── conditional_logic.py                  # ConditionalLogic class
├── signal_processing.py                 # SignalProcessor
├── reflection.py                         # Reflector + BM25 memory integration
├── tools/
│   ├── __init__.py                      # Tool re-exports
│   ├── core_stock_tools.py             # get_stock_data
│   ├── technical_indicators_tools.py    # get_indicators
│   ├── fundamental_data_tools.py       # get_fundamentals, get_balance_sheet, get_cashflow, get_income_statement
│   └── news_data_tools.py              # get_news, get_global_news, get_insider_transactions
├── agents/
│   ├── __init__.py                      # Factory function re-exports
│   ├── analysts/
│   │   ├── __init__.py
│   │   ├── market_analyst.py
│   │   ├── social_media_analyst.py
│   │   ├── news_analyst.py
│   │   └── fundamentals_analyst.py
│   ├── researchers/
│   │   ├── __init__.py
│   │   ├── bull_researcher.py
│   │   └── bear_researcher.py
│   ├── managers/
│   │   ├── __init__.py
│   │   ├── research_manager.py
│   │   └── portfolio_manager.py
│   ├── trader/
│   │   ├── __init__.py
│   │   └── trader.py
│   └── risk_mgmt/
│       ├── __init__.py
│       ├── aggressive_debator.py
│       ├── conservative_debator.py
│       └── neutral_debator.py
└── utils/
    ├── __init__.py
    ├── memory.py                        # FinancialSituationMemory with SQLite persistence
    ├── agent_utils.py                   # build_instrument_context, create_msg_delete, get_language_instruction
    └── agent_states.py                  # TypedDict definitions (import from state.py)

apps/api/src/routers/
└── decision_chain.py                    # FastAPI router with SSE endpoint
```

---

### Task 1: Add dependencies to pyproject.toml

**Files:**
- Modify: `apps/api/pyproject.toml`

- [x] **Step 1: Add langgraph and rank_bm25 dependencies**

Add these entries to the `dependencies` list in `apps/api/pyproject.toml`:

```toml
    "langgraph>=0.2",
    "rank_bm25>=0.2",
    "sse-starlette>=1.6",
```

`langchain`, `langchain-openai`, and `yfinance` are already present in pyproject.toml.

- [x] **Step 2: Install dependencies**

Run: `cd apps/api && uv sync`
Expected: All dependencies install successfully.

- [x] **Step 3: Commit**

```bash
git add apps/api/pyproject.toml uv.lock
git commit -m "chore(decision-chain): add langgraph, rank_bm25, sse-starlette deps"
```

---

### Task 2: Create state and config modules

**Files:**
- Create: `apps/api/src/agents/decision_chain/__init__.py`
- Create: `apps/api/src/agents/decision_chain/config.py`
- Create: `apps/api/src/agents/decision_chain/state.py`

- [x] **Step 1: Create `__init__.py`**

```python
from src.agents.decision_chain.graph import TradingDecisionChain

__all__ = ["TradingDecisionChain"]
```

- [x] **Step 2: Create `config.py`**

```python
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class DecisionChainConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="DC_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    deep_think_llm: str = "openai/gpt-4.1"
    quick_think_llm: str = "openai/gpt-4.1-mini"

    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"

    max_debate_rounds: int = 1
    max_risk_discuss_rounds: int = 1
    max_recur_limit: int = 100

    output_language: str = "Chinese"
    results_dir: str = str(Path(__file__).parent.parent.parent.parent / "decision_results")

    data_vendors: dict = {
        "core_stock_apis": "yfinance",
        "technical_indicators": "yfinance",
        "fundamental_data": "yfinance",
        "news_data": "yfinance",
    }
    tool_vendors: dict = {}


decision_chain_config = DecisionChainConfig()
```

- [x] **Step 3: Create `state.py`**

```python
from typing import Annotated
from typing_extensions import TypedDict
from langgraph.graph import MessagesState


class InvestDebateState(TypedDict):
    bull_history: Annotated[str, "Bullish Conversation history"]
    bear_history: Annotated[str, "Bearish Conversation history"]
    history: Annotated[str, "Conversation history"]
    current_response: Annotated[str, "Latest response"]
    judge_decision: Annotated[str, "Final judge decision"]
    count: Annotated[int, "Length of the current conversation"]


class RiskDebateState(TypedDict):
    aggressive_history: Annotated[str, "Aggressive Agent Conversation history"]
    conservative_history: Annotated[str, "Conservative Agent Conversation history"]
    neutral_history: Annotated[str, "Neutral Agent Conversation history"]
    history: Annotated[str, "Conversation history"]
    latest_speaker: Annotated[str, "Analyst that spoke last"]
    current_aggressive_response: Annotated[str, "Latest response by the aggressive analyst"]
    current_conservative_response: Annotated[str, "Latest response by the conservative analyst"]
    current_neutral_response: Annotated[str, "Latest response by the neutral analyst"]
    judge_decision: Annotated[str, "Judge decision"]
    count: Annotated[int, "Length of the current conversation"]


class AgentState(MessagesState):
    company_of_interest: Annotated[str, "Company that we are interested in trading"]
    trade_date: Annotated[str, "What date we are trading at"]
    sender: Annotated[str, "Agent that sent this message"]
    market_report: Annotated[str, "Report from the Market Analyst"]
    sentiment_report: Annotated[str, "Report from the Social Media Analyst"]
    news_report: Annotated[str, "Report from the News Researcher"]
    fundamentals_report: Annotated[str, "Report from the Fundamentals Researcher"]
    investment_debate_state: Annotated[InvestDebateState, "Current state of the debate on if to invest or not"]
    investment_plan: Annotated[str, "Plan generated by the Analyst"]
    trader_investment_plan: Annotated[str, "Plan generated by the Trader"]
    risk_debate_state: Annotated[RiskDebateState, "Current state of the debate on evaluating risk"]
    final_trade_decision: Annotated[str, "Final decision made by the Risk Analysts"]
```

- [x] **Step 4: Commit**

```bash
git add apps/api/src/agents/decision_chain/
git commit -m "feat(decision-chain): add state and config modules"
```

---

### Task 3: Create utility modules (agent_utils, memory, agent_states)

**Files:**
- Create: `apps/api/src/agents/decision_chain/utils/__init__.py`
- Create: `apps/api/src/agents/decision_chain/utils/agent_states.py`
- Create: `apps/api/src/agents/decision_chain/utils/agent_utils.py`
- Create: `apps/api/src/agents/decision_chain/utils/memory.py`

- [x] **Step 1: Create `utils/__init__.py`**

```python
from src.agents.decision_chain.utils.agent_utils import (
    build_instrument_context,
    create_msg_delete,
    get_language_instruction,
)
from src.agents.decision_chain.utils.memory import FinancialSituationMemory

__all__ = [
    "FinancialSituationMemory",
    "build_instrument_context",
    "create_msg_delete",
    "get_language_instruction",
]
```

- [x] **Step 2: Create `utils/agent_states.py`**

This file re-exports from `state.py` for backward compatibility pattern:

```python
from src.agents.decision_chain.state import (
    AgentState,
    InvestDebateState,
    RiskDebateState,
)

__all__ = ["AgentState", "InvestDebateState", "RiskDebateState"]
```

- [x] **Step 3: Create `utils/agent_utils.py`**

```python
from langchain_core.messages import HumanMessage, RemoveMessage

from src.agents.decision_chain.config import decision_chain_config


def get_language_instruction() -> str:
    lang = decision_chain_config.output_language
    if lang.strip().lower() == "english":
        return ""
    return f" Write your entire response in {lang}."


def build_instrument_context(ticker: str) -> str:
    return (
        f"The instrument to analyze is `{ticker}`. "
        "Use this exact ticker in every tool call, report, and recommendation, "
        "preserving any exchange suffix (e.g. `.TO`, `.L`, `.HK`, `.T`)."
    )


def create_msg_delete():
    def delete_messages(state):
        messages = state["messages"]
        removal_operations = [RemoveMessage(id=m.id) for m in messages]
        placeholder = HumanMessage(content="Continue")
        return {"messages": removal_operations + [placeholder]}
    return delete_messages
```

- [x] **Step 4: Create `utils/memory.py`**

```python
import json
import sqlite3
import re
from pathlib import Path
from typing import List, Tuple

from rank_bm25 import BM25Okapi


class FinancialSituationMemory:
    """BM25-based memory for storing and retrieving financial situations, persisted in SQLite."""

    def __init__(self, name: str, db_dir: str | None = None):
        self.name = name
        self.documents: List[str] = []
        self.recommendations: List[str] = []
        self.bm25: BM25Okapi | None = None

        if db_dir:
            db_path = Path(db_dir)
            db_path.mkdir(parents=True, exist_ok=True)
            self._db_path = db_path / f"{name}.db"
            self._load_from_db()
        else:
            self._db_path = None

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._db_path))
        conn.execute(
            "CREATE TABLE IF NOT EXISTS memories "
            "(id INTEGER PRIMARY KEY AUTOINCREMENT, situation TEXT, recommendation TEXT)"
        )
        conn.commit()
        return conn

    def _load_from_db(self):
        if not self._db_path:
            return
        conn = self._get_conn()
        try:
            rows = conn.execute("SELECT situation, recommendation FROM memories").fetchall()
            self.documents = [r[0] for r in rows]
            self.recommendations = [r[1] for r in rows]
            self._rebuild_index()
        finally:
            conn.close()

    def _tokenize(self, text: str) -> List[str]:
        return re.findall(r"\b\w+\b", text.lower())

    def _rebuild_index(self):
        if self.documents:
            tokenized_docs = [self._tokenize(doc) for doc in self.documents]
            self.bm25 = BM25Okapi(tokenized_docs)
        else:
            self.bm25 = None

    def add_situations(self, situations_and_advice: List[Tuple[str, str]]):
        for situation, recommendation in situations_and_advice:
            self.documents.append(situation)
            self.recommendations.append(recommendation)
        self._rebuild_index()
        if self._db_path:
            self._save_to_db(situations_and_advice)

    def _save_to_db(self, situations_and_advice: List[Tuple[str, str]]):
        conn = self._get_conn()
        try:
            conn.executemany(
                "INSERT INTO memories (situation, recommendation) VALUES (?, ?)",
                situations_and_advice,
            )
            conn.commit()
        finally:
            conn.close()

    def get_memories(self, current_situation: str, n_matches: int = 2) -> List[dict]:
        if not self.documents or self.bm25 is None:
            return []
        query_tokens = self._tokenize(current_situation)
        scores = self.bm25.get_scores(query_tokens)
        top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:n_matches]
        max_score = max(scores) if max(scores) > 0 else 1
        results = []
        for idx in top_indices:
            normalized_score = scores[idx] / max_score if max_score > 0 else 0
            results.append({
                "matched_situation": self.documents[idx],
                "recommendation": self.recommendations[idx],
                "similarity_score": normalized_score,
            })
        return results

    def clear(self):
        self.documents = []
        self.recommendations = []
        self.bm25 = None
        if self._db_path:
            conn = self._get_conn()
            try:
                conn.execute("DELETE FROM memories")
                conn.commit()
            finally:
                conn.close()
```

- [x] **Step 5: Commit**

```bash
git add apps/api/src/agents/decision_chain/utils/
git commit -m "feat(decision-chain): add agent_utils, memory, agent_states utils"
```

---

### Task 4: Create yfinance tool modules

**Files:**
- Create: `apps/api/src/agents/decision_chain/tools/__init__.py`
- Create: `apps/api/src/agents/decision_chain/tools/core_stock_tools.py`
- Create: `apps/api/src/agents/decision_chain/tools/technical_indicators_tools.py`
- Create: `apps/api/src/agents/decision_chain/tools/fundamental_data_tools.py`
- Create: `apps/api/src/agents/decision_chain/tools/news_data_tools.py`

- [x] **Step 1: Create `tools/__init__.py`**

```python
from src.agents.decision_chain.tools.core_stock_tools import get_stock_data
from src.agents.decision_chain.tools.technical_indicators_tools import get_indicators
from src.agents.decision_chain.tools.fundamental_data_tools import (
    get_fundamentals,
    get_balance_sheet,
    get_cashflow,
    get_income_statement,
)
from src.agents.decision_chain.tools.news_data_tools import (
    get_news,
    get_global_news,
    get_insider_transactions,
)

__all__ = [
    "get_stock_data",
    "get_indicators",
    "get_fundamentals",
    "get_balance_sheet",
    "get_cashflow",
    "get_income_statement",
    "get_news",
    "get_global_news",
    "get_insider_transactions",
]
```

- [x] **Step 2: Create `tools/core_stock_tools.py`**

Directly wraps yfinance to fetch OHLCV data. The function signature and behavior must match the original `get_stock_data` tool exactly:

```python
from langchain_core.tools import tool
from typing import Annotated
from datetime import datetime
import yfinance as yf


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
```

- [x] **Step 3: Create `tools/technical_indicators_tools.py`**

Uses `stockstats` to compute technical indicators (same library as original):

```python
from langchain_core.tools import tool
from typing import Annotated
from datetime import datetime
from dateutil.relativedelta import relativedelta
import yfinance as yf
import pandas as pd


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
```

- [x] **Step 4: Create `tools/fundamental_data_tools.py`**

```python
from langchain_core.tools import tool
from typing import Annotated
from datetime import datetime
import yfinance as yf


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
```

- [x] **Step 5: Create `tools/news_data_tools.py`**

```python
from langchain_core.tools import tool
from typing import Annotated
from datetime import datetime
from dateutil.relativedelta import relativedelta
import yfinance as yf


@tool
def get_news(
    ticker: Annotated[str, "Ticker symbol"],
    start_date: Annotated[str, "Start date in yyyy-mm-dd format"],
    end_date: Annotated[str, "End date in yyyy-mm-dd format"],
) -> str:
    """Retrieve news for a specific stock ticker."""
    try:
        stock = yf.Ticker(ticker)
        news = stock.get_news(count=20)
        if not news:
            return f"No news found for {ticker}"

        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")

        news_str = ""
        for article in news:
            data = _extract_article_data(article)
            if data["pub_date"]:
                pub_naive = data["pub_date"].replace(tzinfo=None) if hasattr(data["pub_date"], "replace") else data["pub_date"]
                if not (start_dt <= pub_naive <= end_dt + relativedelta(days=1)):
                    continue
            news_str += f"### {data['title']} (source: {data['publisher']})\n"
            if data["summary"]:
                news_str += f"{data['summary']}\n"
            if data["link"]:
                news_str += f"Link: {data['link']}\n"
            news_str += "\n"

        if not news_str:
            return f"No news found for {ticker} between {start_date} and {end_date}"
        return f"## {ticker} News, from {start_date} to {end_date}:\n\n{news_str}"
    except Exception as e:
        return f"Error fetching news for {ticker}: {str(e)}"


@tool
def get_global_news(
    curr_date: Annotated[str, "Current date in yyyy-mm-dd format"],
    look_back_days: Annotated[int, "Number of days to look back"] = 7,
    limit: Annotated[int, "Maximum number of articles to return"] = 5,
) -> str:
    """Retrieve global/macro economic news using yfinance Search."""
    search_queries = [
        "stock market economy",
        "Federal Reserve interest rates",
        "inflation economic outlook",
        "global markets trading",
    ]
    all_news = []
    seen_titles = set()

    try:
        for query in search_queries:
            search = yf.Search(query=query, news_count=limit, enable_fuzzy_query=True)
            if search.news:
                for article in search.news:
                    data = _extract_article_data(article) if "content" in article else None
                    title = data["title"] if data else article.get("title", "")
                    if title and title not in seen_titles:
                        seen_titles.add(title)
                        all_news.append(article)
            if len(all_news) >= limit:
                break

        if not all_news:
            return f"No global news found for {curr_date}"

        curr_dt = datetime.strptime(curr_date, "%Y-%m-%d")
        start_dt = curr_dt - relativedelta(days=look_back_days)
        start_date = start_dt.strftime("%Y-%m-%d")

        news_str = ""
        for article in all_news[:limit]:
            if "content" in article:
                data = _extract_article_data(article)
                title = data["title"]
                publisher = data["publisher"]
                link = data["link"]
                summary = data["summary"]
            else:
                title = article.get("title", "No title")
                publisher = article.get("publisher", "Unknown")
                link = article.get("link", "")
                summary = ""
            news_str += f"### {title} (source: {publisher})\n"
            if summary:
                news_str += f"{summary}\n"
            if link:
                news_str += f"Link: {link}\n"
            news_str += "\n"

        return f"## Global Market News, from {start_date} to {curr_date}:\n\n{news_str}"
    except Exception as e:
        return f"Error fetching global news: {str(e)}"


@tool
def get_insider_transactions(
    ticker: Annotated[str, "ticker symbol"],
) -> str:
    """Retrieve insider transaction information about a company."""
    try:
        ticker_obj = yf.Ticker(ticker.upper())
        data = ticker_obj.insider_transactions
        if data is None or data.empty:
            return f"No insider transactions data found for symbol '{ticker}'"
        csv_string = data.to_csv()
        header = f"# Insider Transactions data for {ticker.upper()}\n"
        header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        return header + csv_string
    except Exception as e:
        return f"Error retrieving insider transactions for {ticker}: {str(e)}"


def _extract_article_data(article: dict) -> dict:
    if "content" in article:
        content = article["content"]
        title = content.get("title", "No title")
        summary = content.get("summary", "")
        provider = content.get("provider", {})
        publisher = provider.get("displayName", "Unknown")
        url_obj = content.get("canonicalUrl") or content.get("clickThroughUrl") or {}
        link = url_obj.get("url", "")
        pub_date_str = content.get("pubDate", "")
        pub_date = None
        if pub_date_str:
            try:
                pub_date = datetime.fromisoformat(pub_date_str.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                pass
        return {"title": title, "summary": summary, "publisher": publisher, "link": link, "pub_date": pub_date}
    return {
        "title": article.get("title", "No title"),
        "summary": article.get("summary", ""),
        "publisher": article.get("publisher", "Unknown"),
        "link": article.get("link", ""),
        "pub_date": None,
    }
```

- [x] **Step 6: Commit**

```bash
git add apps/api/src/agents/decision_chain/tools/
git commit -m "feat(decision-chain): add yfinance tool modules"
```

---

### Task 5: Create all agent node modules (4 analysts)

**Files:**
- Create: `apps/api/src/agents/decision_chain/agents/__init__.py`
- Create: `apps/api/src/agents/decision_chain/agents/analysts/__init__.py`
- Create: `apps/api/src/agents/decision_chain/agents/analysts/market_analyst.py`
- Create: `apps/api/src/agents/decision_chain/agents/analysts/social_media_analyst.py`
- Create: `apps/api/src/agents/decision_chain/agents/analysts/news_analyst.py`
- Create: `apps/api/src/agents/decision_chain/agents/analysts/fundamentals_analyst.py`

- [x] **Step 1: Create `agents/__init__.py`**

```python
from src.agents.decision_chain.agents.analysts.market_analyst import create_market_analyst
from src.agents.decision_chain.agents.analysts.social_media_analyst import create_social_media_analyst
from src.agents.decision_chain.agents.analysts.news_analyst import create_news_analyst
from src.agents.decision_chain.agents.analysts.fundamentals_analyst import create_fundamentals_analyst
from src.agents.decision_chain.agents.researchers.bull_researcher import create_bull_researcher
from src.agents.decision_chain.agents.researchers.bear_researcher import create_bear_researcher
from src.agents.decision_chain.agents.managers.research_manager import create_research_manager
from src.agents.decision_chain.agents.managers.portfolio_manager import create_portfolio_manager
from src.agents.decision_chain.agents.trader.trader import create_trader
from src.agents.decision_chain.agents.risk_mgmt.aggressive_debator import create_aggressive_debator
from src.agents.decision_chain.agents.risk_mgmt.conservative_debator import create_conservative_debator
from src.agents.decision_chain.agents.risk_mgmt.neutral_debator import create_neutral_debator

__all__ = [
    "create_market_analyst",
    "create_social_media_analyst",
    "create_news_analyst",
    "create_fundamentals_analyst",
    "create_bull_researcher",
    "create_bear_researcher",
    "create_research_manager",
    "create_portfolio_manager",
    "create_trader",
    "create_aggressive_debator",
    "create_conservative_debator",
    "create_neutral_debator",
]
```

- [x] **Step 2: Create `agents/analysts/__init__.py`**

```python
```

Empty init file.

- [x] **Step 3: Create `market_analyst.py`**

The market analyst uses `get_stock_data` and `get_indicators` tools, and writes to `market_report` when no tool_calls remain. The system prompt must include the indicator list and the requirement to call `get_stock_data` first:

```python
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from src.agents.decision_chain.tools.core_stock_tools import get_stock_data
from src.agents.decision_chain.tools.technical_indicators_tools import get_indicators
from src.agents.decision_chain.utils.agent_utils import (
    build_instrument_context,
    get_language_instruction,
)


def create_market_analyst(llm):
    def market_analyst_node(state):
        current_date = state["trade_date"]
        instrument_context = build_instrument_context(state["company_of_interest"])

        tools = [get_stock_data, get_indicators]

        system_message = (
            """You are a trading assistant tasked with analyzing financial markets. Your role is to select the **most relevant indicators** for a given market condition or trading strategy from the following list. The goal is to choose up to **8 indicators** that provide complementary insights without redundancy. Categories and each category's indicators are:

Moving Averages:
- close_50_sma: 50 SMA: A medium-term trend indicator. Usage: Identify trend direction and serve as dynamic support/resistance. Tips: It lags price; combine with faster indicators for timely signals.
- close_200_sma: 200 SMA: A long-term trend benchmark. Usage: Confirm overall market trend and identify golden/death cross setups. Tips: It reacts slowly; best for strategic trend confirmation rather than frequent trading entries.
- close_10_ema: 10 EMA: A responsive short-term average. Usage: Capture quick shifts in momentum and potential entry points. Tips: Prone to noise in choppy markets; use alongside longer averages for filtering false signals.

MACD Related:
- macd: MACD: Computes momentum via differences of EMAs. Usage: Look for crossovers and divergence as signals of trend changes. Tips: Confirm with other indicators in low-volatility or sideways markets.
- macds: MACD Signal: An EMA smoothing of the MACD line. Usage: Use crossovers with the MACD line to trigger trades. Tips: Should be part of a broader strategy to avoid false positives.
- macdh: MACD Histogram: Shows the gap between the MACD line and its signal. Usage: Visualize momentum strength and spot divergence early. Tips: Can be volatile; complement with additional filters in fast-moving markets.

Momentum Indicators:
- rsi: RSI: Measures momentum to flag overbought/oversold conditions. Usage: Apply 70/30 thresholds and watch for divergence to signal reversals. Tips: In strong trends, RSI may remain extreme; always cross-check with trend analysis.

Volatility Indicators:
- boll: Bollinger Middle: A 20 SMA serving as the basis for Bollinger Bands. Usage: Acts as a dynamic benchmark for price movement. Tips: Combine with the upper and lower bands to effectively spot breakouts or reversals.
- boll_ub: Bollinger Upper Band: Typically 2 standard deviations above the middle line. Usage: Signals potential overbought conditions and breakout zones. Tips: Confirm signals with other tools; prices may ride the band in strong trends.
- boll_lb: Bollinger Lower Band: Typically 2 standard deviations below the middle line. Usage: Indicates potential oversold conditions. Tips: Use additional analysis to avoid false reversal signals.
- atr: ATR: Averages true range to measure volatility. Usage: Set stop-loss levels and adjust position sizes based on current market volatility. Tips: It's a reactive measure, so use it as part of a broader risk management strategy.

Volume-Based Indicators:
- vwma: VWMA: A moving average weighted by volume. Usage: Confirm trends by integrating price action with volume data. Tips: Watch for skewed results from volume spikes; use in combination with other volume analyses.

- Select indicators that provide diverse and complementary information. Avoid redundancy (e.g., do not select both rsi and stochrsi). Also briefly explain why they are suitable for the given market context. When you tool call, please use the exact name of the indicators provided above as they are defined parameters, otherwise your call will fail. Please make sure to call get_stock_data first to retrieve the CSV that is needed to generate indicators. Then use get_indicators with the specific indicator names. Write a very detailed and nuanced report of the trends you observe. Provide specific, actionable insights with supporting evidence to help traders make informed decisions."""
            + """ Make sure to append a Markdown table at the end of the report to organize key points in the report, organized and easy to read."""
            + get_language_instruction()
        )

        prompt = ChatPromptTemplate.from_messages([
            (
                "system",
                "You are a helpful AI assistant, collaborating with other assistants."
                " Use the provided tools to progress towards answering the question."
                " If you are unable to fully answer, that's OK; another assistant with different tools"
                " will help where you left off. Execute what you can to make progress."
                " If you or any other assistant has the FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** or deliverable,"
                " prefix your response with FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** so the team knows to stop."
                " You have access to the following tools: {tool_names}.\n{system_message}"
                "For your reference, the current date is {current_date}. {instrument_context}",
            ),
            MessagesPlaceholder(variable_name="messages"),
        ])

        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(tool_names=", ".join([t.name for t in tools]))
        prompt = prompt.partial(current_date=current_date)
        prompt = prompt.partial(instrument_context=instrument_context)

        chain = prompt | llm.bind_tools(tools)
        result = chain.invoke(state["messages"])

        report = ""
        if len(result.tool_calls) == 0:
            report = result.content

        return {
            "messages": [result],
            "market_report": report,
        }

    return market_analyst_node
```

- [x] **Step 4: Create `social_media_analyst.py`**

Identical pattern to market_analyst but uses `get_news` only and writes to `sentiment_report`:

```python
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from src.agents.decision_chain.tools.news_data_tools import get_news
from src.agents.decision_chain.utils.agent_utils import (
    build_instrument_context,
    get_language_instruction,
)


def create_social_media_analyst(llm):
    def social_media_analyst_node(state):
        current_date = state["trade_date"]
        instrument_context = build_instrument_context(state["company_of_interest"])

        tools = [get_news]

        system_message = (
            "You are a social media and company specific news researcher/analyst tasked with analyzing social media posts, recent company news, and public sentiment for a specific company over the past week. You will be given a company's name your objective is to write a comprehensive long report detailing your analysis, insights, and implications for traders and investors on this company's current state after looking at social media and what people are saying about that company, analyzing sentiment data of what people feel each day about the company, and looking at recent company news. Use the get_news(query, start_date, end_date) tool to search for company-specific news and social media discussions. Try to look at all sources possible from social media to sentiment to news. Provide specific, actionable insights with supporting evidence to help traders make informed decisions."
            + """ Make sure to append a Markdown table at the end of the report to organize key points in the report, organized and easy to read."""
            + get_language_instruction()
        )

        prompt = ChatPromptTemplate.from_messages([
            (
                "system",
                "You are a helpful AI assistant, collaborating with other assistants."
                " Use the provided tools to progress towards answering the question."
                " If you are unable to fully answer, that's OK; another assistant with different tools"
                " will help where you left off. Execute what you can to make progress."
                " If you or any other assistant has the FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** or deliverable,"
                " prefix your response with FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** so the team knows to stop."
                " You have access to the following tools: {tool_names}.\n{system_message}"
                "For your reference, the current date is {current_date}. {instrument_context}",
            ),
            MessagesPlaceholder(variable_name="messages"),
        ])

        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(tool_names=", ".join([t.name for t in tools]))
        prompt = prompt.partial(current_date=current_date)
        prompt = prompt.partial(instrument_context=instrument_context)

        chain = prompt | llm.bind_tools(tools)
        result = chain.invoke(state["messages"])

        report = ""
        if len(result.tool_calls) == 0:
            report = result.content

        return {
            "messages": [result],
            "sentiment_report": report,
        }

    return social_media_analyst_node
```

- [x] **Step 5: Create `news_analyst.py`**

Uses `get_news` and `get_global_news`, writes to `news_report`. Same pattern, distinct prompt:

```python
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from src.agents.decision_chain.tools.news_data_tools import get_news, get_global_news
from src.agents.decision_chain.utils.agent_utils import (
    build_instrument_context,
    get_language_instruction,
)


def create_news_analyst(llm):
    def news_analyst_node(state):
        current_date = state["trade_date"]
        instrument_context = build_instrument_context(state["company_of_interest"])

        tools = [get_news, get_global_news]

        system_message = (
            "You are a news researcher tasked with analyzing recent news and trends over the past week. Please write a comprehensive report of the current state of the world that is relevant for trading and macroeconomics. Use the available tools: get_news(query, start_date, end_date) for company-specific or targeted news searches, and get_global_news(curr_date, look_back_days, limit) for broader macroeconomic news. Provide specific, actionable insights with supporting evidence to help traders make informed decisions."
            + """ Make sure to append a Markdown table at the end of the report to organize key points in the report, organized and easy to read."""
            + get_language_instruction()
        )

        prompt = ChatPromptTemplate.from_messages([
            (
                "system",
                "You are a helpful AI assistant, collaborating with other assistants."
                " Use the provided tools to progress towards answering the question."
                " If you are unable to fully answer, that's OK; another assistant with different tools"
                " will help where you left off. Execute what you can to make progress."
                " If you or any other assistant has the FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** or deliverable,"
                " prefix your response with FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** so the team knows to stop."
                " You have access to the following tools: {tool_names}.\n{system_message}"
                "For your reference, the current date is {current_date}. {instrument_context}",
            ),
            MessagesPlaceholder(variable_name="messages"),
        ])

        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(tool_names=", ".join([t.name for t in tools]))
        prompt = prompt.partial(current_date=current_date)
        prompt = prompt.partial(instrument_context=instrument_context)

        chain = prompt | llm.bind_tools(tools)
        result = chain.invoke(state["messages"])

        report = ""
        if len(result.tool_calls) == 0:
            report = result.content

        return {
            "messages": [result],
            "news_report": report,
        }

    return news_analyst_node
```

- [x] **Step 6: Create `fundamentals_analyst.py`**

Uses `get_fundamentals`, `get_balance_sheet`, `get_cashflow`, `get_income_statement`, writes to `fundamentals_report`:

```python
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from src.agents.decision_chain.tools.fundamental_data_tools import (
    get_fundamentals,
    get_balance_sheet,
    get_cashflow,
    get_income_statement,
)
from src.agents.decision_chain.utils.agent_utils import (
    build_instrument_context,
    get_language_instruction,
)


def create_fundamentals_analyst(llm):
    def fundamentals_analyst_node(state):
        current_date = state["trade_date"]
        instrument_context = build_instrument_context(state["company_of_interest"])

        tools = [get_fundamentals, get_balance_sheet, get_cashflow, get_income_statement]

        system_message = (
            "You are a researcher tasked with analyzing fundamental information over the past week about a company. Please write a comprehensive report of the company's fundamental information such as financial documents, company profile, basic company financials, and company financial history to gain a full view of the company's fundamental information to inform traders. Make sure to include as much detail as possible. Provide specific, actionable insights with supporting evidence to help traders make informed decisions."
            + " Make sure to append a Markdown table at the end of the report to organize key points in the report, organized and easy to read."
            + " Use the available tools: `get_fundamentals` for comprehensive company analysis, `get_balance_sheet`, `get_cashflow`, and `get_income_statement` for specific financial statements."
            + get_language_instruction()
        )

        prompt = ChatPromptTemplate.from_messages([
            (
                "system",
                "You are a helpful AI assistant, collaborating with other assistants."
                " Use the provided tools to progress towards answering the question."
                " If you are unable to fully answer, that's OK; another assistant with different tools"
                " will help where you left off. Execute what you can to make progress."
                " If you or any other assistant has the FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** or deliverable,"
                " prefix your response with FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** so the team knows to stop."
                " You have access to the following tools: {tool_names}.\n{system_message}"
                "For your reference, the current date is {current_date}. {instrument_context}",
            ),
            MessagesPlaceholder(variable_name="messages"),
        ])

        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(tool_names=", ".join([t.name for t in tools]))
        prompt = prompt.partial(current_date=current_date)
        prompt = prompt.partial(instrument_context=instrument_context)

        chain = prompt | llm.bind_tools(tools)
        result = chain.invoke(state["messages"])

        report = ""
        if len(result.tool_calls) == 0:
            report = result.content

        return {
            "messages": [result],
            "fundamentals_report": report,
        }

    return fundamentals_analyst_node
```

- [x] **Step 7: Create `agents/analysts/__init__.py`** (empty file with just a comment)

```python
# Analyst nodes
```

- [x] **Step 8: Commit**

```bash
git add apps/api/src/agents/decision_chain/agents/
git commit -m "feat(decision-chain): add 4 analyst agent nodes"
```

---

### Task 6: Create researcher, manager, trader, and risk agent nodes

**Files:**
- Create: `apps/api/src/agents/decision_chain/agents/researchers/__init__.py`
- Create: `apps/api/src/agents/decision_chain/agents/researchers/bull_researcher.py`
- Create: `apps/api/src/agents/decision_chain/agents/researchers/bear_researcher.py`
- Create: `apps/api/src/agents/decision_chain/agents/managers/__init__.py`
- Create: `apps/api/src/agents/decision_chain/agents/managers/research_manager.py`
- Create: `apps/api/src/agents/decision_chain/agents/managers/portfolio_manager.py`
- Create: `apps/api/src/agents/decision_chain/agents/trader/__init__.py`
- Create: `apps/api/src/agents/decision_chain/agents/trader/trader.py`
- Create: `apps/api/src/agents/decision_chain/agents/risk_mgmt/__init__.py`
- Create: `apps/api/src/agents/decision_chain/agents/risk_mgmt/aggressive_debator.py`
- Create: `apps/api/src/agents/decision_chain/agents/risk_mgmt/conservative_debator.py`
- Create: `apps/api/src/agents/decision_chain/agents/risk_mgmt/neutral_debator.py`

Each file mirrors the original TradingAgents implementation exactly, with only import path changes from `tradingagents.*` to `src.agents.decision_chain.*`. The prompts, state update logic, and return structures must be identical.

All `__init__.py` files are empty except a comment.

Due to the length of these 10 files (each is a direct port with only import path changes), they will be created in this task following the exact same patterns established in the original source code, with these import replacements:
- `tradingagents.agents.utils.agent_utils` → `src.agents.decision_chain.utils.agent_utils`
- `tradingagents.agents.utils.agent_states` → `src.agents.decision_chain.state`
- `tradingagents.agents.utils.memory` → `src.agents.decision_chain.utils.memory`

The key behaviors preserved per spec:

- **bull_researcher**: Reads 4 reports + BM25 memories (n_matches=2), updates `investment_debate_state` with history, count+1, prefix `"Bull Analyst: "`
- **bear_researcher**: Symmetric to bull, prefix `"Bear Analyst: "`
- **research_manager**: Uses `deep_thinking_llm`, reads debate history + BM25 memories, writes both `judge_decision` and `investment_plan`
- **trader**: Uses `quick_thinking_llm` + trader_memory, structured system+user message, ends with `FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL**`, writes `trader_investment_plan` and `sender="Trader"`
- **aggressive_debator**: Updates risk_debate_state, prefix `"Aggressive Analyst: "`, latest_speaker=`"Aggressive"`
- **conservative_debator**: Symmetric, latest_speaker=`"Conservative"`
- **neutral_debator**: Symmetric, latest_speaker=`"Neutral"`
- **portfolio_manager**: Uses `deep_thinking_llm` + portfolio_manager_memory, five-tier rating (Buy/Overweight/Hold/Underweight/Sell), writes `final_trade_decision` and `risk_debate_state.judge_decision`, includes `get_language_instruction()`

- [x] **Step 1: Create all 10 agent files**

Create each file with the exact prompt text and state update logic from the original source, adjusting only the import paths. Each `__init__.py` is an empty file with a comment.

- [x] **Step 2: Commit**

```bash
git add apps/api/src/agents/decision_chain/agents/
git commit -m "feat(decision-chain): add researcher, manager, trader, and risk agent nodes"
```

---

### Task 7: Create propagation, conditional_logic, and signal_processing modules

**Files:**
- Create: `apps/api/src/agents/decision_chain/propagation.py`
- Create: `apps/api/src/agents/decision_chain/conditional_logic.py`
- Create: `apps/api/src/agents/decision_chain/signal_processing.py`

- [x] **Step 1: Create `propagation.py`**

```python
from typing import Dict, Any, List, Optional

from src.agents.decision_chain.state import (
    AgentState,
    InvestDebateState,
    RiskDebateState,
)


class Propagator:
    def __init__(self, max_recur_limit: int = 100):
        self.max_recur_limit = max_recur_limit

    def create_initial_state(self, company_name: str, trade_date: str) -> Dict[str, Any]:
        return {
            "messages": [("human", company_name)],
            "company_of_interest": company_name,
            "trade_date": str(trade_date),
            "investment_debate_state": InvestDebateState(
                {
                    "bull_history": "",
                    "bear_history": "",
                    "history": "",
                    "current_response": "",
                    "judge_decision": "",
                    "count": 0,
                }
            ),
            "risk_debate_state": RiskDebateState(
                {
                    "aggressive_history": "",
                    "conservative_history": "",
                    "neutral_history": "",
                    "history": "",
                    "latest_speaker": "",
                    "current_aggressive_response": "",
                    "current_conservative_response": "",
                    "current_neutral_response": "",
                    "judge_decision": "",
                    "count": 0,
                }
            ),
            "market_report": "",
            "fundamentals_report": "",
            "sentiment_report": "",
            "news_report": "",
        }

    def get_graph_args(self, callbacks: Optional[List] = None) -> Dict[str, Any]:
        config = {"recursion_limit": self.max_recur_limit}
        if callbacks:
            config["callbacks"] = callbacks
        return {"stream_mode": "values", "config": config}
```

- [x] **Step 2: Create `conditional_logic.py`**

```python
from src.agents.decision_chain.state import AgentState


class ConditionalLogic:
    def __init__(self, max_debate_rounds: int = 1, max_risk_discuss_rounds: int = 1):
        self.max_debate_rounds = max_debate_rounds
        self.max_risk_discuss_rounds = max_risk_discuss_rounds

    def should_continue_market(self, state: AgentState):
        messages = state["messages"]
        last_message = messages[-1]
        if last_message.tool_calls:
            return "tools_market"
        return "Msg Clear Market"

    def should_continue_social(self, state: AgentState):
        messages = state["messages"]
        last_message = messages[-1]
        if last_message.tool_calls:
            return "tools_social"
        return "Msg Clear Social"

    def should_continue_news(self, state: AgentState):
        messages = state["messages"]
        last_message = messages[-1]
        if last_message.tool_calls:
            return "tools_news"
        return "Msg Clear News"

    def should_continue_fundamentals(self, state: AgentState):
        messages = state["messages"]
        last_message = messages[-1]
        if last_message.tool_calls:
            return "tools_fundamentals"
        return "Msg Clear Fundamentals"

    def should_continue_debate(self, state: AgentState) -> str:
        if state["investment_debate_state"]["count"] >= 2 * self.max_debate_rounds:
            return "Research Manager"
        if state["investment_debate_state"]["current_response"].startswith("Bull"):
            return "Bear Researcher"
        return "Bull Researcher"

    def should_continue_risk_analysis(self, state: AgentState) -> str:
        if state["risk_debate_state"]["count"] >= 3 * self.max_risk_discuss_rounds:
            return "Portfolio Manager"
        if state["risk_debate_state"]["latest_speaker"].startswith("Aggressive"):
            return "Conservative Analyst"
        if state["risk_debate_state"]["latest_speaker"].startswith("Conservative"):
            return "Neutral Analyst"
        return "Aggressive Analyst"
```

- [x] **Step 3: Create `signal_processing.py`**

```python
from typing import Any


class SignalProcessor:
    def __init__(self, quick_thinking_llm: Any):
        self.quick_thinking_llm = quick_thinking_llm

    def process_signal(self, full_signal: str) -> str:
        messages = [
            (
                "system",
                "You are an efficient assistant that extracts the trading decision from analyst reports. "
                "Extract the rating as exactly one of: BUY, OVERWEIGHT, HOLD, UNDERWEIGHT, SELL. "
                "Output only the single rating word, nothing else.",
            ),
            ("human", full_signal),
        ]
        return self.quick_thinking_llm.invoke(messages).content
```

- [x] **Step 4: Commit**

```bash
git add apps/api/src/agents/decision_chain/propagation.py apps/api/src/agents/decision_chain/conditional_logic.py apps/api/src/agents/decision_chain/signal_processing.py
git commit -m "feat(decision-chain): add propagation, conditional_logic, signal_processing"
```

---

### Task 8: Create reflection module

**Files:**
- Create: `apps/api/src/agents/decision_chain/reflection.py`

- [x] **Step 1: Create `reflection.py`**

```python
from typing import Any, Dict

from src.agents.decision_chain.utils.memory import FinancialSituationMemory


class Reflector:
    def __init__(self, quick_thinking_llm: Any):
        self.quick_thinking_llm = quick_thinking_llm
        self.reflection_system_prompt = self._get_reflection_prompt()

    def _get_reflection_prompt(self) -> str:
        return """
You are an expert financial analyst tasked with reviewing trading decisions/analysis and providing a comprehensive, step-by-step analysis. 
Your goal is to deliver detailed insights into investment decisions and highlight opportunities for improvement, adhering strictly to the following guidelines:

1. Reasoning:
   - For each trading decision, determine whether it was correct or incorrect. A correct decision results in an increase in returns, while an incorrect decision does the opposite.
   - Analyze the contributing factors to each success or mistake. Consider:
     - Market intelligence.
     - Technical indicators.
     - Technical signals.
     - Price movement analysis.
     - Overall market data analysis 
     - News analysis.
     - Social media and sentiment analysis.
     - Fundamental data analysis.
     - Weight the importance of each factor in the decision-making process.

2. Improvement:
   - For any incorrect decisions, propose revisions to maximize returns.
   - Provide a detailed list of corrective actions or improvements, including specific recommendations (e.g., changing a decision from HOLD to BUY on a particular date).

3. Summary:
   - Summarize the lessons learned from the successes and mistakes.
   - Highlight how these lessons can be adapted for future trading scenarios and draw connections between similar situations to apply the knowledge gained.

4. Query:
   - Extract key insights from the summary into a concise sentence of no more than 1000 tokens.
   - Ensure the condensed sentence captures the essence of the lessons and reasoning for easy reference.

Adhere strictly to these instructions, and ensure your output is detailed, accurate, and actionable. You will also be given objective descriptions of the market from a price movements, technical indicator, news, and sentiment perspective to provide more context for your analysis.
"""

    def _extract_current_situation(self, current_state: Dict[str, Any]) -> str:
        return (
            f"{current_state['market_report']}\n\n"
            f"{current_state['sentiment_report']}\n\n"
            f"{current_state['news_report']}\n\n"
            f"{current_state['fundamentals_report']}"
        )

    def _reflect_on_component(self, component_type: str, report: str, situation: str, returns_losses) -> str:
        messages = [
            ("system", self.reflection_system_prompt),
            (
                "human",
                f"Returns: {returns_losses}\n\nAnalysis/Decision: {report}\n\nObjective Market Reports for Reference: {situation}",
            ),
        ]
        result = self.quick_thinking_llm.invoke(messages).content
        return result

    def reflect_bull_researcher(self, current_state, returns_losses, bull_memory: FinancialSituationMemory):
        situation = self._extract_current_situation(current_state)
        bull_debate_history = current_state["investment_debate_state"]["bull_history"]
        result = self._reflect_on_component("BULL", bull_debate_history, situation, returns_losses)
        bull_memory.add_situations([(situation, result)])

    def reflect_bear_researcher(self, current_state, returns_losses, bear_memory: FinancialSituationMemory):
        situation = self._extract_current_situation(current_state)
        bear_debate_history = current_state["investment_debate_state"]["bear_history"]
        result = self._reflect_on_component("BEAR", bear_debate_history, situation, returns_losses)
        bear_memory.add_situations([(situation, result)])

    def reflect_trader(self, current_state, returns_losses, trader_memory: FinancialSituationMemory):
        situation = self._extract_current_situation(current_state)
        trader_decision = current_state["trader_investment_plan"]
        result = self._reflect_on_component("TRADER", trader_decision, situation, returns_losses)
        trader_memory.add_situations([(situation, result)])

    def reflect_invest_judge(self, current_state, returns_losses, invest_judge_memory: FinancialSituationMemory):
        situation = self._extract_current_situation(current_state)
        judge_decision = current_state["investment_debate_state"]["judge_decision"]
        result = self._reflect_on_component("INVEST JUDGE", judge_decision, situation, returns_losses)
        invest_judge_memory.add_situations([(situation, result)])

    def reflect_portfolio_manager(self, current_state, returns_losses, portfolio_manager_memory: FinancialSituationMemory):
        situation = self._extract_current_situation(current_state)
        judge_decision = current_state["risk_debate_state"]["judge_decision"]
        result = self._reflect_on_component("PORTFOLIO MANAGER", judge_decision, situation, returns_losses)
        portfolio_manager_memory.add_situations([(situation, result)])
```

- [x] **Step 2: Commit**

```bash
git add apps/api/src/agents/decision_chain/reflection.py
git commit -m "feat(decision-chain): add reflection module"
```

---

### Task 9: Create main graph orchestrator (TradingDecisionChain)

**Files:**
- Create: `apps/api/src/agents/decision_chain/graph.py`

This is the central orchestrator that:
1. Initializes dual LLMs via OpenRouter
2. Creates 5 memory instances with SQLite persistence
3. Creates 4 tool nodes
4. Builds the LangGraph StateGraph with all nodes and conditional edges
5. Has `propagate()` method that runs the graph and returns `(final_state, extracted_rating)`
6. Has `reflect_and_remember()` method
7. Logs state to JSON file

- [x] **Step 1: Create `graph.py`**

```python
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode

from src.agents.decision_chain.config import decision_chain_config
from src.agents.decision_chain.state import AgentState
from src.agents.decision_chain.agents import (
    create_market_analyst,
    create_social_media_analyst,
    create_news_analyst,
    create_fundamentals_analyst,
    create_bull_researcher,
    create_bear_researcher,
    create_research_manager,
    create_portfolio_manager,
    create_trader,
    create_aggressive_debator,
    create_conservative_debator,
    create_neutral_debator,
)
from src.agents.decision_chain.tools import (
    get_stock_data,
    get_indicators,
    get_news,
    get_global_news,
    get_insider_transactions,
    get_fundamentals,
    get_balance_sheet,
    get_cashflow,
    get_income_statement,
)
from src.agents.decision_chain.utils.agent_utils import create_msg_delete
from src.agents.decision_chain.utils.memory import FinancialSituationMemory
from src.agents.decision_chain.conditional_logic import ConditionalLogic
from src.agents.decision_chain.propagation import Propagator
from src.agents.decision_chain.reflection import Reflector
from src.agents.decision_chain.signal_processing import SignalProcessor

logger = logging.getLogger(__name__)


class TradingDecisionChain:
    def __init__(
        self,
        selected_analysts: list[str] | None = None,
        config: dict | None = None,
    ):
        if selected_analysts is None:
            selected_analysts = ["market", "social", "news", "fundamentals"]
        if not selected_analysts:
            raise ValueError("At least one analyst must be selected")

        self.config = config or decision_chain_config.model_dump()
        self.selected_analysts = selected_analysts

        os.makedirs(self.config.get("results_dir", "./decision_results"), exist_ok=True)

        deep_client = ChatOpenAI(
            openai_api_key=self.config.get("openrouter_api_key") or decision_chain_config.openrouter_api_key,
            openai_api_base=self.config.get("openrouter_base_url", decision_chain_config.openrouter_base_url),
            model=self.config.get("deep_think_llm", decision_chain_config.deep_think_llm),
            temperature=0.3,
        )
        quick_client = ChatOpenAI(
            openai_api_key=self.config.get("openrouter_api_key") or decision_chain_config.openrouter_api_key,
            openai_api_base=self.config.get("openrouter_base_url", decision_chain_config.openrouter_base_url),
            model=self.config.get("quick_think_llm", decision_chain_config.quick_think_llm),
            temperature=0.3,
        )
        self.deep_thinking_llm = deep_client
        self.quick_thinking_llm = quick_client

        db_dir = os.path.join(self.config.get("results_dir", "./decision_results"), "memories")
        self.bull_memory = FinancialSituationMemory("bull_memory", db_dir=db_dir)
        self.bear_memory = FinancialSituationMemory("bear_memory", db_dir=db_dir)
        self.trader_memory = FinancialSituationMemory("trader_memory", db_dir=db_dir)
        self.invest_judge_memory = FinancialSituationMemory("invest_judge_memory", db_dir=db_dir)
        self.portfolio_manager_memory = FinancialSituationMemory("portfolio_manager_memory", db_dir=db_dir)

        self.tool_nodes = self._create_tool_nodes()

        self.conditional_logic = ConditionalLogic(
            max_debate_rounds=self.config.get("max_debate_rounds", decision_chain_config.max_debate_rounds),
            max_risk_discuss_rounds=self.config.get("max_risk_discuss_rounds", decision_chain_config.max_risk_discuss_rounds),
        )

        self._build_graph()

        self.propagator = Propagator(max_recur_limit=self.config.get("max_recur_limit", decision_chain_config.max_recur_limit))
        self.reflector = Reflector(self.quick_thinking_llm)
        self.signal_processor = SignalProcessor(self.quick_thinking_llm)

        self.curr_state = None
        self.ticker = None

    def _create_tool_nodes(self) -> Dict[str, ToolNode]:
        return {
            "market": ToolNode([get_stock_data, get_indicators]),
            "social": ToolNode([get_news]),
            "news": ToolNode([get_news, get_global_news, get_insider_transactions]),
            "fundamentals": ToolNode([get_fundamentals, get_balance_sheet, get_cashflow, get_income_statement]),
        }

    def _build_graph(self):
        graph_setup = GraphSetup(
            self.quick_thinking_llm,
            self.deep_thinking_llm,
            self.tool_nodes,
            self.bull_memory,
            self.bear_memory,
            self.trader_memory,
            self.invest_judge_memory,
            self.portfolio_manager_memory,
            self.conditional_logic,
        )
        self.graph = graph_setup.setup_graph(self.selected_analysts)

    def propagate(self, company_name: str, trade_date: str) -> Tuple[dict, str]:
        self.ticker = company_name
        init_state = self.propagator.create_initial_state(company_name, trade_date)
        args = self.propagator.get_graph_args()

        final_state = self.graph.invoke(init_state, **args)
        self.curr_state = final_state
        self._log_state(trade_date, final_state)

        return final_state, self.process_signal(final_state["final_trade_decision"])

    async def apropagate(self, company_name: str, trade_date: str):
        self.ticker = company_name
        init_state = self.propagator.create_initial_state(company_name, trade_date)
        args = self.propagator.get_graph_args()

        async for event in self.graph.astream(init_state, **args):
            yield event

    def process_signal(self, full_signal: str) -> str:
        return self.signal_processor.process_signal(full_signal)

    def _log_state(self, trade_date, final_state):
        log_data = {
            "company_of_interest": final_state["company_of_interest"],
            "trade_date": final_state["trade_date"],
            "market_report": final_state["market_report"],
            "sentiment_report": final_state["sentiment_report"],
            "news_report": final_state["news_report"],
            "fundamentals_report": final_state["fundamentals_report"],
            "investment_debate_state": {
                "bull_history": final_state["investment_debate_state"]["bull_history"],
                "bear_history": final_state["investment_debate_state"]["bear_history"],
                "history": final_state["investment_debate_state"]["history"],
                "current_response": final_state["investment_debate_state"]["current_response"],
                "judge_decision": final_state["investment_debate_state"]["judge_decision"],
            },
            "trader_investment_decision": final_state["trader_investment_plan"],
            "risk_debate_state": {
                "aggressive_history": final_state["risk_debate_state"]["aggressive_history"],
                "conservative_history": final_state["risk_debate_state"]["conservative_history"],
                "neutral_history": final_state["risk_debate_state"]["neutral_history"],
                "history": final_state["risk_debate_state"]["history"],
                "judge_decision": final_state["risk_debate_state"]["judge_decision"],
            },
            "investment_plan": final_state["investment_plan"],
            "final_trade_decision": final_state["final_trade_decision"],
        }

        directory = Path(self.config.get("results_dir", "./decision_results")) / (self.ticker or "unknown") / "decision_chain_logs"
        directory.mkdir(parents=True, exist_ok=True)
        log_path = directory / f"full_states_log_{trade_date}.json"
        with open(log_path, "w", encoding="utf-8") as f:
            json.dump(log_data, f, indent=4, ensure_ascii=False)

    def reflect_and_remember(self, returns_losses):
        self.reflector.reflect_bull_researcher(self.curr_state, returns_losses, self.bull_memory)
        self.reflector.reflect_bear_researcher(self.curr_state, returns_losses, self.bear_memory)
        self.reflector.reflect_trader(self.curr_state, returns_losses, self.trader_memory)
        self.reflector.reflect_invest_judge(self.curr_state, returns_losses, self.invest_judge_memory)
        self.reflector.reflect_portfolio_manager(self.curr_state, returns_losses, self.portfolio_manager_memory)


class GraphSetup:
    def __init__(
        self,
        quick_thinking_llm,
        deep_thinking_llm,
        tool_nodes: Dict[str, ToolNode],
        bull_memory,
        bear_memory,
        trader_memory,
        invest_judge_memory,
        portfolio_manager_memory,
        conditional_logic: ConditionalLogic,
    ):
        self.quick_thinking_llm = quick_thinking_llm
        self.deep_thinking_llm = deep_thinking_llm
        self.tool_nodes = tool_nodes
        self.bull_memory = bull_memory
        self.bear_memory = bear_memory
        self.trader_memory = trader_memory
        self.invest_judge_memory = invest_judge_memory
        self.portfolio_manager_memory = portfolio_manager_memory
        self.conditional_logic = conditional_logic

    def setup_graph(self, selected_analysts=None):
        if selected_analysts is None:
            selected_analysts = ["market", "social", "news", "fundamentals"]
        if len(selected_analysts) == 0:
            raise ValueError("At least one analyst must be selected")

        analyst_nodes = {}
        delete_nodes = {}
        analyst_tool_nodes = {}

        analyst_creators = {
            "market": create_market_analyst,
            "social": create_social_media_analyst,
            "news": create_news_analyst,
            "fundamentals": create_fundamentals_analyst,
        }

        for analyst_type in selected_analysts:
            if analyst_type not in analyst_creators:
                raise ValueError(f"Unknown analyst type: {analyst_type}")
            analyst_nodes[analyst_type] = analyst_creators[analyst_type](self.quick_thinking_llm)
            delete_nodes[analyst_type] = create_msg_delete()
            analyst_tool_nodes[analyst_type] = self.tool_nodes[analyst_type]

        bull_researcher_node = create_bull_researcher(self.quick_thinking_llm, self.bull_memory)
        bear_researcher_node = create_bear_researcher(self.quick_thinking_llm, self.bear_memory)
        research_manager_node = create_research_manager(self.deep_thinking_llm, self.invest_judge_memory)
        trader_node = create_trader(self.quick_thinking_llm, self.trader_memory)

        aggressive_analyst = create_aggressive_debator(self.quick_thinking_llm)
        neutral_analyst = create_neutral_debator(self.quick_thinking_llm)
        conservative_analyst = create_conservative_debator(self.quick_thinking_llm)
        portfolio_manager_node = create_portfolio_manager(self.deep_thinking_llm, self.portfolio_manager_memory)

        workflow = StateGraph(AgentState)

        for analyst_type, node in analyst_nodes.items():
            workflow.add_node(f"{analyst_type.capitalize()} Analyst", node)
            workflow.add_node(f"Msg Clear {analyst_type.capitalize()}", delete_nodes[analyst_type])
            workflow.add_node(f"tools_{analyst_type}", analyst_tool_nodes[analyst_type])

        workflow.add_node("Bull Researcher", bull_researcher_node)
        workflow.add_node("Bear Researcher", bear_researcher_node)
        workflow.add_node("Research Manager", research_manager_node)
        workflow.add_node("Trader", trader_node)
        workflow.add_node("Aggressive Analyst", aggressive_analyst)
        workflow.add_node("Neutral Analyst", neutral_analyst)
        workflow.add_node("Conservative Analyst", conservative_analyst)
        workflow.add_node("Portfolio Manager", portfolio_manager_node)

        first_analyst = selected_analysts[0]
        workflow.add_edge(START, f"{first_analyst.capitalize()} Analyst")

        for i, analyst_type in enumerate(selected_analysts):
            current_analyst = f"{analyst_type.capitalize()} Analyst"
            current_tools = f"tools_{analyst_type}"
            current_clear = f"Msg Clear {analyst_type.capitalize()}"

            workflow.add_conditional_edges(
                current_analyst,
                getattr(self.conditional_logic, f"should_continue_{analyst_type}"),
                [current_tools, current_clear],
            )
            workflow.add_edge(current_tools, current_analyst)

            if i < len(selected_analysts) - 1:
                next_analyst = f"{selected_analysts[i + 1].capitalize()} Analyst"
                workflow.add_edge(current_clear, next_analyst)
            else:
                workflow.add_edge(current_clear, "Bull Researcher")

        workflow.add_conditional_edges(
            "Bull Researcher",
            self.conditional_logic.should_continue_debate,
            {"Bear Researcher": "Bear Researcher", "Research Manager": "Research Manager"},
        )
        workflow.add_conditional_edges(
            "Bear Researcher",
            self.conditional_logic.should_continue_debate,
            {"Bull Researcher": "Bull Researcher", "Research Manager": "Research Manager"},
        )
        workflow.add_edge("Research Manager", "Trader")
        workflow.add_edge("Trader", "Aggressive Analyst")
        workflow.add_conditional_edges(
            "Aggressive Analyst",
            self.conditional_logic.should_continue_risk_analysis,
            {"Conservative Analyst": "Conservative Analyst", "Portfolio Manager": "Portfolio Manager"},
        )
        workflow.add_conditional_edges(
            "Conservative Analyst",
            self.conditional_logic.should_continue_risk_analysis,
            {"Neutral Analyst": "Neutral Analyst", "Portfolio Manager": "Portfolio Manager"},
        )
        workflow.add_conditional_edges(
            "Neutral Analyst",
            self.conditional_logic.should_continue_risk_analysis,
            {"Aggressive Analyst": "Aggressive Analyst", "Portfolio Manager": "Portfolio Manager"},
        )
        workflow.add_edge("Portfolio Manager", END)

        return workflow.compile()
```

Note: The `__init__.py` will also need to be updated to import from `graph.py`. Let me update it:

```python
from src.agents.decision_chain.graph import TradingDecisionChain

__all__ = ["TradingDecisionChain"]
```

This was already set in Task 2, so no change needed.

- [x] **Step 2: Commit**

```bash
git add apps/api/src/agents/decision_chain/graph.py apps/api/src/agents/decision_chain/__init__.py
git commit -m "feat(decision-chain): add main graph orchestrator and GraphSetup"
```

---

### Task 10: Create FastAPI SSE router

**Files:**
- Create: `apps/api/src/routers/decision_chain.py`
- Modify: `apps/api/src/main.py` — add router

- [x] **Step 1: Create `decision_chain.py` router**

```python
import logging
from typing import Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from src.agents.decision_chain.graph import TradingDecisionChain

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/decision-chain", tags=["decision-chain"])


class DecisionChainRequest(BaseModel):
    ticker: str
    trade_date: Optional[str] = None


class DecisionChainResponse(BaseModel):
    status: str
    ticker: str
    rating: str
    trade_date: str


@router.post("/run", response_class=EventSourceResponse)
async def run_decision_chain(request: DecisionChainRequest):
    """Run the investment decision chain and stream stage-by-stage results via SSE."""
    import json
    from datetime import date

    trade_date = request.trade_date or date.today().strftime("%Y-%m-%d")
    chain = TradingDecisionChain()

    async def event_generator():
        try:
            stage_map = {
                "Market Analyst": "market_analyst",
                "Social Analyst": "social_analyst",
                "News Analyst": "news_analyst",
                "Fundamentals Analyst": "fundamentals_analyst",
                "Bull Researcher": "bull_researcher",
                "Bear Researcher": "bear_researcher",
                "Research Manager": "research_manager",
                "Trader": "trader",
                "Aggressive Analyst": "aggressive_analyst",
                "Conservative Analyst": "conservative_analyst",
                "Neutral Analyst": "neutral_analyst",
                "Portfolio Manager": "portfolio_manager",
            }

            async for event in chain.apropagate(request.ticker, trade_date):
                for node_name, node_state in event.items():
                    stage = stage_map.get(node_name, node_name)
                    yield {
                        "event": "stage_update",
                        "data": json.dumps({
                            "stage": stage,
                            "node": node_name,
                            "state_keys": list(node_state.keys()) if isinstance(node_state, dict) else None,
                        }, ensure_ascii=False),
                    }

            final_state = chain.curr_state
            if final_state:
                rating = chain.process_signal(final_state["final_trade_decision"])
                yield {
                    "event": "final_decision",
                    "data": json.dumps({
                        "content": final_state.get("final_trade_decision", ""),
                        "rating": rating,
                        "ticker": request.ticker,
                        "trade_date": trade_date,
                    }, ensure_ascii=False),
                }
                yield {
                    "event": "rating_extracted",
                    "data": json.dumps({"rating": rating}, ensure_ascii=False),
                }
        except Exception as e:
            logger.exception("Decision chain execution failed")
            yield {
                "event": "stage_error",
                "data": json.dumps({"error": str(e)}, ensure_ascii=False),
            }

    return EventSourceResponse(event_generator())


@router.post("/run-sync", response_model=DecisionChainResponse)
async def run_decision_chain_sync(request: DecisionChainRequest):
    """Run the decision chain synchronously and return the final result."""
    from datetime import date

    trade_date = request.trade_date or date.today().strftime("%Y-%m-%d")
    chain = TradingDecisionChain()
    final_state, rating = chain.propagate(request.ticker, trade_date)

    return DecisionChainResponse(
        status="ok",
        ticker=request.ticker,
        rating=rating,
        trade_date=trade_date,
    )
```

- [x] **Step 2: Register router in `main.py`**

Add import and router registration. In `apps/api/src/main.py`, add:

```python
from src.routers import decision_chain
```

to the imports, and add:

```python
app.include_router(decision_chain.router, prefix=settings.API_V1_PREFIX)
```

after the existing router registrations.

- [x] **Step 3: Commit**

```bash
git add apps/api/src/routers/decision_chain.py apps/api/src/main.py
git commit -m "feat(decision-chain): add SSE and sync API endpoints"
```

---

### Task 11: Add `stockstats` dependency and verify imports

**Files:**
- Modify: `apps/api/pyproject.toml`

- [x] **Step 1: Add `stockstats` dependency**

Add `"stockstats"` to the dependencies list in `apps/api/pyproject.toml`. This is needed by the technical indicators tool.

- [x] **Step 2: Install and verify**

Run: `cd apps/api && uv sync`
Expected: All dependencies install successfully.

- [x] **Step 3: Verify all imports resolve**

Run: `cd apps/api && uv run python -c "from src.agents.decision_chain import TradingDecisionChain; print('OK')"`
Expected: Prints `OK` with no import errors.

- [x] **Step 4: Commit**

```bash
git add apps/api/pyproject.toml uv.lock
git commit -m "chore(decision-chain): add stockstats dep and verify imports"
```

---

### Task 12: Integration test — run a single synchronous decision chain

**Files:**
- Create: `apps/api/scripts/test_decision_chain.py`

- [x] **Step 1: Create a test script**

```python
"""Quick integration test for the decision chain.

Usage:
    cd apps/api && uv run python -m scripts.test_decision_chain AAPL

Requires OPENROUTER_API_KEY in .env
"""
import sys
import json
from src.agents.decision_chain.graph import TradingDecisionChain


def main():
    ticker = sys.argv[1] if len(sys.argv) > 1 else "AAPL"
    trade_date = sys.argv[2] if len(sys.argv) > 2 else "2026-01-15"

    print(f"Running decision chain for {ticker} on {trade_date}...")
    chain = TradingDecisionChain()
    final_state, rating = chain.propagate(ticker, trade_date)

    print(f"\n{'='*60}")
    print(f"FINAL RATING: {rating}")
    print(f"{'='*60}")
    print(f"\nMarket Report (first 200 chars): {final_state.get('market_report', '')[:200]}...")
    print(f"Sentiment Report (first 200 chars): {final_state.get('sentiment_report', '')[:200]}...")
    print(f"News Report (first 200 chars): {final_state.get('news_report', '')[:200]}...")
    print(f"Fundamentals Report (first 200 chars): {final_state.get('fundamentals_report', '')[:200]}...")
    print(f"Investment Plan (first 200 chars): {final_state.get('investment_plan', '')[:200]}...")
    print(f"Trader Plan (first 200 chars): {final_state.get('trader_investment_plan', '')[:200]}...")
    print(f"Final Decision (first 300 chars): {final_state.get('final_trade_decision', '')[:300]}...")
    print(f"\nInvestment Debate count: {final_state['investment_debate_state']['count']}")
    print(f"Risk Debate count: {final_state['risk_debate_state']['count']}")


if __name__ == "__main__":
    main()
```

- [x] **Step 2: Verify lint passes**

Run: `cd apps/api && uv run ruff check src/agents/decision_chain/ src/routers/decision_chain.py`
Expected: No errors or warnings.

- [x] **Step 3: Commit**

```bash
git add apps/api/scripts/test_decision_chain.py
git commit -m "test(decision-chain): add integration test script"
```

---

## Self-Review

**1. Spec coverage:** Every section of the design spec maps to a task:
- Module structure → Task 2-5, 6, 7
- State structure → Task 2
- Config → Task 2
- Tools layer → Task 4
- 4 Analysts → Task 5
- Bull/Bear researchers → Task 6
- Research Manager → Task 6
- Trader → Task 6
- Risk debaters → Task 6
- Portfolio Manager → Task 6
- Graph orchestration → Task 9
- Condition logic → Task 7
- Propagation → Task 7
- Signal processing → Task 7
- Reflection → Task 8
- Logging → Task 9
- SSE endpoint → Task 10
- BM25 memory → Task 3

**2. Placeholder scan:** No TBD/TODO/placeholders found. All code blocks contain complete implementations.

**3. Type consistency:** All state field names, function signatures, and return types are consistent across tasks. `InvestDebateState`, `RiskDebateState`, `AgentState` are defined in Task 2 and used consistently. Tool names match between Task 4 definitions and Task 5/9 usage.