import asyncio
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.schemas.public_board import MarketGroupSnapshot
from src.schemas.public_board import MarketMetric
from src.services import public_board
from src.services.public_board import QuoteSnapshot
from src.services.public_board import normalize_metric


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


def test_market_group_snapshot_serializes_macro_payload() -> None:
    payload = MarketGroupSnapshot(
        group="macro",
        status="ok",
        as_of=datetime(2026, 4, 20, 10, 30, tzinfo=UTC),
        last_success_at=datetime(2026, 4, 20, 10, 31, tzinfo=UTC),
        source="akshare",
        items=[
            MarketMetric(
                name="VIX",
                symbol="^VIX",
                value=18.42,
                display="18.42",
                change_pct=-1.13,
                status="ok",
            )
        ],
    )

    dumped = payload.model_dump()

    assert dumped["group"] == "macro"
    assert dumped["status"] == "ok"
    assert dumped["items"][0]["name"] == "VIX"

    with pytest.raises(ValidationError):
        MarketGroupSnapshot(
            group="custom",
            status="ok",
            as_of=datetime(2026, 4, 20, 10, 30, tzinfo=UTC),
            last_success_at=datetime(2026, 4, 20, 10, 31, tzinfo=UTC),
            source="akshare",
            items=[],
        )

def test_build_macro_snapshot_marks_partial_failures_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    as_of = datetime(2026, 4, 20, 10, 30, tzinfo=UTC)
    quotes: dict[str, QuoteSnapshot | None] = {
        public_board.YFINANCE_SYMBOLS["VIX"]: QuoteSnapshot(
            value=18.4,
            previous_value=19.1,
            change_pct=-3.66,
        ),
        public_board.YFINANCE_SYMBOLS["US10Y"]: QuoteSnapshot(
            value=45.3,
            previous_value=44.8,
            change_pct=1.12,
        ),
        public_board.YFINANCE_SYMBOLS["DXY"]: None,
        public_board.US2Y_SYMBOL: QuoteSnapshot(
            value=42.0,
            previous_value=41.8,
            change_pct=0.48,
        ),
    }

    async def fake_safe_fetch_quote(symbol: str) -> QuoteSnapshot | None:
        return quotes[symbol]

    monkeypatch.setattr(public_board, "_safe_fetch_quote", fake_safe_fetch_quote)

    snapshot = asyncio.run(public_board.build_macro_snapshot(as_of))

    assert snapshot.group == "macro"
    assert snapshot.status == "ok"
    assert snapshot.as_of == as_of
    assert snapshot.last_success_at == as_of
    assert snapshot.source == public_board.SOURCE_NAME
    assert len(snapshot.items) == 4
    dxy_metric = next(metric for metric in snapshot.items if metric.name == "DXY")
    spread_metric = next(
        metric for metric in snapshot.items if metric.name == "2Y-10Y Spread"
    )
    assert dxy_metric.status == "unavailable"
    assert spread_metric.display is not None
    assert spread_metric.display.endswith("bps")


def test_build_assets_snapshot_returns_five_metrics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    as_of = datetime(2026, 4, 20, 10, 30, tzinfo=UTC)
    quotes: dict[str, QuoteSnapshot | None] = {
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
        public_board.YFINANCE_SYMBOLS["GOLD"]: QuoteSnapshot(
            value=2360.5,
            previous_value=2350.0,
            change_pct=0.45,
        ),
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
    }

    async def fake_safe_fetch_quote(symbol: str) -> QuoteSnapshot | None:
        return quotes[symbol]

    monkeypatch.setattr(public_board, "_safe_fetch_quote", fake_safe_fetch_quote)

    snapshot = asyncio.run(public_board.build_assets_snapshot(as_of))

    assert snapshot.group == "assets"
    assert snapshot.status == "ok"
    assert snapshot.as_of == as_of
    assert snapshot.last_success_at == as_of
    assert snapshot.source == public_board.SOURCE_NAME
    assert len(snapshot.items) == 5
    spx_metric = next(metric for metric in snapshot.items if metric.name == "S&P 500")
    btc_metric = next(metric for metric in snapshot.items if metric.name == "BTC")
    assert spx_metric.symbol == public_board.YFINANCE_SYMBOLS["SPX"]
    assert spx_metric.display == "5,300.00"
    assert btc_metric.symbol == public_board.YFINANCE_SYMBOLS["BTC"]
    assert btc_metric.change_pct == 0.72


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
