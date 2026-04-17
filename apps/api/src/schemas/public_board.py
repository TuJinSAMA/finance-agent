from datetime import date, datetime

from pydantic import BaseModel


class MarketMetric(BaseModel):
    name: str
    symbol: str
    value: float | None
    display: str | None = None
    change_pct: float | None = None
    status: str


class MarketState(BaseModel):
    date: date
    label: str
    summary: str


class PublicMarketBoardResponse(BaseModel):
    market_state: MarketState
    macro: list[MarketMetric]
    assets: list[MarketMetric]
    custom: list[MarketMetric]
    as_of: datetime
    source: str
