from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel


class StockBrief(BaseModel):
    model_config = {"from_attributes": True}

    code: str
    name: str
    industry: str | None = None


class RecommendationRead(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    rec_date: date
    stock_id: int
    stock: StockBrief | None = None
    quant_score: Decimal | None = None
    catalyst_score: Decimal | None = None
    final_score: Decimal | None = None
    rank: int | None = None
    reason_short: str | None = None
    reason_detail: str | None = None
    price_at_rec: Decimal | None = None
    price_t1: Decimal | None = None
    price_t5: Decimal | None = None
    return_t1: Decimal | None = None
    return_t5: Decimal | None = None
    created_at: datetime


class RecommendationListResponse(BaseModel):
    rec_date: date
    count: int
    recommendations: list[RecommendationRead]


class PipelineTriggerResponse(BaseModel):
    status: str
    picks: int
    users: int
