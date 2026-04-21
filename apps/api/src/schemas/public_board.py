from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel


MetricStatus = Literal["ok", "unavailable", "stale"]
GroupStatus = Literal["ok", "stale", "empty"]
SnapshotGroup = Literal["macro", "assets", "crypto", "extended", "equity"]


class MarketMetric(BaseModel):
    name: str
    symbol: str
    value: float | None
    display: str | None = None
    change_pct: float | None = None
    status: MetricStatus


class MarketGroupSnapshot(BaseModel):
    group: SnapshotGroup
    status: GroupStatus
    as_of: datetime
    last_success_at: datetime
    source: str
    items: list[MarketMetric]


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
