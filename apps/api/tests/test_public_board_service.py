import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.schemas.public_board import PublicMarketBoardResponse
from src.services import public_board
from src.services.public_board import QuoteSnapshot
from src.services.public_board import _yield_change_bps
from src.services.public_board import classify_market_state
from src.services.public_board import normalize_metric


def test_classify_market_state_risk_off() -> None:
    assert classify_market_state(
        vix=27.3,
        us10y_change_bps=8.0,
        spx_change_pct=-1.2,
    ) == "Risk-Off 偏避险"


def test_normalize_metric_marks_missing_vix_unavailable() -> None:
    result = normalize_metric(
        name="VIX",
        symbol="^VIX",
        value=None,
        change_pct=None,
    )

    assert result["status"] == "unavailable"
    assert result["value"] is None
    assert result["name"] == "VIX"
    assert result["symbol"] == "^VIX"


def test_yield_change_bps_converts_tnx_tenths_percent_to_basis_points() -> None:
    quote = QuoteSnapshot(value=45.3, previous_value=44.8, change_pct=1.12)

    assert _yield_change_bps(quote) == 5.0


def test_classify_market_state_returns_data_incomplete_when_core_inputs_missing() -> None:
    assert classify_market_state(
        vix=None,
        us10y_change_bps=8.0,
        spx_change_pct=-1.2,
    ) == "Data Incomplete 数据不足"


def test_get_public_market_board_builds_response_with_partial_missing_metrics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    quotes: dict[str, QuoteSnapshot | None] = {
        public_board.YFINANCE_SYMBOLS["VIX"]: None,
        public_board.YFINANCE_SYMBOLS["US10Y"]: QuoteSnapshot(
            value=45.3,
            previous_value=44.8,
            change_pct=1.12,
        ),
        public_board.YFINANCE_SYMBOLS["DXY"]: QuoteSnapshot(
            value=103.25,
            previous_value=103.0,
            change_pct=0.24,
        ),
        public_board.YFINANCE_SYMBOLS["SPX"]: QuoteSnapshot(
            value=5300.0,
            previous_value=5260.0,
            change_pct=0.76,
        ),
        public_board.YFINANCE_SYMBOLS["NASDAQ"]: QuoteSnapshot(
            value=16750.0,
            previous_value=16600.0,
            change_pct=0.9,
        ),
        public_board.YFINANCE_SYMBOLS["GOLD"]: None,
        public_board.YFINANCE_SYMBOLS["WTI"]: QuoteSnapshot(
            value=81.25,
            previous_value=80.0,
            change_pct=1.56,
        ),
        public_board.YFINANCE_SYMBOLS["BTC"]: QuoteSnapshot(
            value=70000.0,
            previous_value=69500.0,
            change_pct=0.72,
        ),
        public_board.YFINANCE_SYMBOLS["CSI300"]: QuoteSnapshot(
            value=3600.0,
            previous_value=3580.0,
            change_pct=0.56,
        ),
        public_board.YFINANCE_SYMBOLS["USDCNY"]: QuoteSnapshot(
            value=7.24,
            previous_value=7.23,
            change_pct=0.14,
        ),
        public_board.US2Y_SYMBOL: QuoteSnapshot(
            value=42.0,
            previous_value=41.8,
            change_pct=0.48,
        ),
    }

    async def fake_safe_fetch_quote(symbol: str) -> QuoteSnapshot | None:
        return quotes[symbol]

    monkeypatch.setattr(public_board, "_safe_fetch_quote", fake_safe_fetch_quote)
    monkeypatch.setattr(public_board, "_CACHE_PAYLOAD", None)
    monkeypatch.setattr(public_board, "_CACHE_EXPIRES_AT", None)

    response = asyncio.run(public_board.get_public_market_board())

    assert isinstance(response, PublicMarketBoardResponse)
    assert response.source == public_board.SOURCE_NAME
    assert len(response.macro) == 4
    assert len(response.assets) == 5
    assert len(response.custom) == 2
    assert response.market_state.label == "Data Incomplete 数据不足"
    assert response.macro[0].status == "unavailable"
    assert response.assets[2].status == "unavailable"


def test_safe_fetch_quote_returns_none_when_fetch_times_out(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_to_thread(*args: object, **kwargs: object) -> QuoteSnapshot:
        await asyncio.sleep(0.05)
        return QuoteSnapshot(value=1.0, previous_value=0.9, change_pct=11.11)

    monkeypatch.setattr(public_board.asyncio, "to_thread", fake_to_thread)
    monkeypatch.setattr(public_board, "YFINANCE_FETCH_TIMEOUT_SECONDS", 0.01, raising=False)

    result = asyncio.run(public_board._safe_fetch_quote("TEST"))

    assert result is None
