from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from src.schemas.recommendation import StockBrief


# ── Portfolio ────────────────────────────────────────────────


class PortfolioCreate(BaseModel):
    name: str = Field(default="默认组合", max_length=100)
    description: str | None = None


class PortfolioRead(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    name: str
    description: str | None = None
    created_at: datetime
    holdings_count: int = 0


# ── Holding ──────────────────────────────────────────────────


class HoldingCreate(BaseModel):
    stock_code: str = Field(description="股票代码，如 600519")
    quantity: int = Field(gt=0, description="持仓数量（股）")
    avg_cost: Decimal = Field(gt=0, description="平均成本价")
    notes: str | None = None


class HoldingUpdate(BaseModel):
    quantity: int | None = Field(default=None, gt=0)
    avg_cost: Decimal | None = Field(default=None, gt=0)
    notes: str | None = None


class HoldingRead(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    stock: StockBrief | None = None
    quantity: int
    avg_cost: float
    added_date: date
    notes: str | None = None
    current_price: float | None = None
    market_value: float | None = None
    profit_loss: float | None = None
    profit_pct: float | None = None


# ── Alert ────────────────────────────────────────────────────


class AlertRead(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    stock: StockBrief | None = None
    alert_type: str
    alert_date: date
    title: str
    content: str | None = None
    is_read: bool
    created_at: datetime


# ── Portfolio Detail (aggregate response) ────────────────────


class PortfolioSummary(BaseModel):
    total_market_value: float = 0
    total_cost: float = 0
    total_profit: float = 0
    total_profit_pct: float | None = None


class PortfolioDetailRead(BaseModel):
    portfolio: PortfolioRead
    holdings: list[HoldingRead]
    summary: PortfolioSummary
