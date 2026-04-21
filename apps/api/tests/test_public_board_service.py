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
from src.services.public_board import _build_metric


def test_build_metric_marks_missing_vix_unavailable() -> None:
    result = _build_metric(
        name="VIX",
        symbol="^VIX",
        value=None,
        change_pct=None,
    )

    assert result.status == "unavailable"
    assert result.value is None
    assert result.name == "VIX"
    assert result.symbol == "^VIX"


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

    for valid_group in ("macro", "assets"):
        MarketGroupSnapshot(
            group=valid_group,
            status="ok",
            as_of=datetime(2026, 4, 20, 10, 30, tzinfo=UTC),
            last_success_at=datetime(2026, 4, 20, 10, 31, tzinfo=UTC),
            source="akshare",
            items=[],
        )

    for valid_group in ("crypto", "extended", "equity"):
        MarketGroupSnapshot(
            group=valid_group,
            status="ok",
            as_of=datetime(2026, 4, 20, 10, 30, tzinfo=UTC),
            last_success_at=datetime(2026, 4, 20, 10, 31, tzinfo=UTC),
            source="akshare",
            items=[],
        )

    with pytest.raises(ValidationError):
        MarketGroupSnapshot(
            group="custom",
            status="ok",
            as_of=datetime(2026, 4, 20, 10, 30, tzinfo=UTC),
            last_success_at=datetime(2026, 4, 20, 10, 31, tzinfo=UTC),
            source="akshare",
            items=[],
        )


def test_build_crypto_snapshot_returns_btc_metric(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    as_of = datetime(2026, 4, 20, 10, 30, tzinfo=UTC)
    btc_quote = QuoteSnapshot(value=70000.0, previous_value=69500.0, change_pct=0.72)

    async def fake_safe_fetch_quote(symbol: str) -> QuoteSnapshot | None:
        if symbol == public_board.YFINANCE_SYMBOLS["BTC"]:
            return btc_quote
        return None

    monkeypatch.setattr(public_board, "_safe_fetch_quote", fake_safe_fetch_quote)

    snapshot = asyncio.run(public_board.build_crypto_snapshot(as_of))

    assert snapshot.group == "crypto"
    assert snapshot.status == "ok"
    assert len(snapshot.items) == 1
    assert snapshot.items[0].name == "BTC"
    assert snapshot.items[0].value == 70000.0


def test_build_extended_snapshot_returns_six_metrics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    as_of = datetime(2026, 4, 20, 10, 30, tzinfo=UTC)
    quotes: dict[str, QuoteSnapshot | None] = {
        public_board.YFINANCE_SYMBOLS["VIX"]: QuoteSnapshot(value=18.4, previous_value=19.1, change_pct=-3.66),
        public_board.YFINANCE_SYMBOLS["US10Y"]: QuoteSnapshot(value=45.3, previous_value=44.8, change_pct=1.12),
        public_board.YFINANCE_SYMBOLS["DXY"]: QuoteSnapshot(value=104.5, previous_value=104.0, change_pct=0.48),
        public_board.US2Y_SYMBOL: QuoteSnapshot(value=42.0, previous_value=41.8, change_pct=0.48),
        public_board.YFINANCE_SYMBOLS["GOLD"]: QuoteSnapshot(value=2360.5, previous_value=2350.0, change_pct=0.45),
        public_board.YFINANCE_SYMBOLS["WTI"]: QuoteSnapshot(value=81.25, previous_value=80.0, change_pct=1.56),
    }

    async def fake_safe_fetch_quote(symbol: str) -> QuoteSnapshot | None:
        return quotes[symbol]

    monkeypatch.setattr(public_board, "_safe_fetch_quote", fake_safe_fetch_quote)

    snapshot = asyncio.run(public_board.build_extended_snapshot(as_of))

    assert snapshot.group == "extended"
    assert snapshot.status == "ok"
    assert len(snapshot.items) == 6
    names = [item.name for item in snapshot.items]
    assert "VIX" in names
    assert "US 10Y" in names
    assert "DXY" in names
    assert "2Y-10Y Spread" in names
    assert "Gold" in names
    assert "WTI" in names


def test_build_equity_snapshot_returns_two_metrics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    as_of = datetime(2026, 4, 20, 10, 30, tzinfo=UTC)
    quotes: dict[str, QuoteSnapshot | None] = {
        public_board.YFINANCE_SYMBOLS["SPX"]: QuoteSnapshot(value=5300.0, previous_value=5260.0, change_pct=0.76),
        public_board.YFINANCE_SYMBOLS["NASDAQ"]: QuoteSnapshot(value=16750.0, previous_value=16600.0, change_pct=0.9),
    }

    async def fake_safe_fetch_quote(symbol: str) -> QuoteSnapshot | None:
        return quotes[symbol]

    monkeypatch.setattr(public_board, "_safe_fetch_quote", fake_safe_fetch_quote)

    snapshot = asyncio.run(public_board.build_equity_snapshot(as_of))

    assert snapshot.group == "equity"
    assert snapshot.status == "ok"
    assert len(snapshot.items) == 2
    names = [item.name for item in snapshot.items]
    assert "S&P 500" in names
    assert "NASDAQ" in names


def test_build_macro_snapshot_composes_from_extended(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    as_of = datetime(2026, 4, 20, 10, 30, tzinfo=UTC)
    quotes: dict[str, QuoteSnapshot | None] = {
        public_board.YFINANCE_SYMBOLS["VIX"]: QuoteSnapshot(value=18.4, previous_value=19.1, change_pct=-3.66),
        public_board.YFINANCE_SYMBOLS["US10Y"]: QuoteSnapshot(value=4.53, previous_value=4.48, change_pct=1.12),
        public_board.YFINANCE_SYMBOLS["DXY"]: None,
        public_board.US2Y_SYMBOL: QuoteSnapshot(value=4.20, previous_value=4.18, change_pct=0.48),
        public_board.YFINANCE_SYMBOLS["GOLD"]: QuoteSnapshot(value=2360.5, previous_value=2350.0, change_pct=0.45),
        public_board.YFINANCE_SYMBOLS["WTI"]: QuoteSnapshot(value=81.25, previous_value=80.0, change_pct=1.56),
    }

    async def fake_safe_fetch_quote(symbol: str) -> QuoteSnapshot | None:
        return quotes[symbol]

    monkeypatch.setattr(public_board, "_safe_fetch_quote", fake_safe_fetch_quote)

    snapshot = asyncio.run(public_board.build_macro_snapshot(as_of))

    assert snapshot.group == "macro"
    assert snapshot.status == "ok"
    assert len(snapshot.items) == 4
    names = [item.name for item in snapshot.items]
    assert "VIX" in names
    assert "US 10Y" in names
    assert "DXY" in names
    assert "2Y-10Y Spread" in names
    assert "Gold" not in names
    assert "WTI" not in names


def test_build_assets_snapshot_composes_from_all_groups(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    as_of = datetime(2026, 4, 20, 10, 30, tzinfo=UTC)
    quotes: dict[str, QuoteSnapshot | None] = {
        public_board.YFINANCE_SYMBOLS["SPX"]: QuoteSnapshot(value=5300.0, previous_value=5260.0, change_pct=0.76),
        public_board.YFINANCE_SYMBOLS["NASDAQ"]: QuoteSnapshot(value=16750.0, previous_value=16600.0, change_pct=0.9),
        public_board.YFINANCE_SYMBOLS["GOLD"]: QuoteSnapshot(value=2360.5, previous_value=2350.0, change_pct=0.45),
        public_board.YFINANCE_SYMBOLS["WTI"]: QuoteSnapshot(value=81.25, previous_value=80.0, change_pct=1.56),
        public_board.YFINANCE_SYMBOLS["BTC"]: QuoteSnapshot(value=70000.0, previous_value=69500.0, change_pct=0.72),
        public_board.YFINANCE_SYMBOLS["VIX"]: QuoteSnapshot(value=18.4, previous_value=19.1, change_pct=-3.66),
        public_board.YFINANCE_SYMBOLS["US10Y"]: QuoteSnapshot(value=4.53, previous_value=4.48, change_pct=1.12),
        public_board.YFINANCE_SYMBOLS["DXY"]: QuoteSnapshot(value=104.5, previous_value=104.0, change_pct=0.48),
        public_board.US2Y_SYMBOL: QuoteSnapshot(value=4.20, previous_value=4.18, change_pct=0.48),
    }

    async def fake_safe_fetch_quote(symbol: str) -> QuoteSnapshot | None:
        return quotes[symbol]

    monkeypatch.setattr(public_board, "_safe_fetch_quote", fake_safe_fetch_quote)

    snapshot = asyncio.run(public_board.build_assets_snapshot(as_of))

    assert snapshot.group == "assets"
    assert snapshot.status == "ok"
    assert len(snapshot.items) == 5
    names = [item.name for item in snapshot.items]
    assert "Gold" in names
    assert "WTI" in names
    assert "BTC" in names
    assert "S&P 500" in names
    assert "NASDAQ" in names


def test_safe_fetch_quote_returns_none_when_fetch_times_out(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_to_thread(*args: object, **kwargs: object) -> QuoteSnapshot:
        await asyncio.sleep(0.05)
        return QuoteSnapshot(value=1.0, previous_value=0.9, change_pct=11.11)

    monkeypatch.setattr(public_board.asyncio, "to_thread", fake_to_thread)
    monkeypatch.setattr(public_board, "FETCH_OVERALL_TIMEOUT_SECONDS", 0.01, raising=False)

    result = asyncio.run(public_board._safe_fetch_quote("TEST"))

    assert result is None