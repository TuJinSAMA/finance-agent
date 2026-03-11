from datetime import date, timedelta

from fastapi import APIRouter, Query

from src.dependencies import DBSession
from src.models.recommendation import Recommendation
from src.schemas.recommendation import (
    PipelineTriggerResponse,
    RecommendationListResponse,
    RecommendationRead,
    StockBrief,
)

from sqlalchemy import select
from sqlalchemy.orm import joinedload

router = APIRouter(prefix="/recommendations", tags=["recommendations"])


@router.post("/trigger-pipeline", response_model=PipelineTriggerResponse)
async def trigger_pipeline(
    db: DBSession,
    trade_date: date = Query(default=None, description="推荐日期，默认今天"),
):
    """
    手动触发推荐流水线（开发调试用）。
    生产环境由 scheduler 在每个交易日 07:30 自动触发。
    """
    from src.agents.orchestrator.pipeline import daily_recommendation_pipeline

    target_date = trade_date or date.today()
    result = await daily_recommendation_pipeline(db, target_date)
    return PipelineTriggerResponse(
        status="ok",
        picks=result["picks"],
        users=result["users"],
    )


@router.get("/today", response_model=RecommendationListResponse)
async def get_today_recommendations(
    db: DBSession,
    rec_date: date = Query(default=None, description="查询日期，默认今天"),
):
    """获取指定日期的推荐列表（默认今天）。"""
    target_date = rec_date or date.today()

    result = await db.execute(
        select(Recommendation)
        .options(joinedload(Recommendation.stock))
        .where(Recommendation.rec_date == target_date)
        .order_by(Recommendation.rank.asc())
    )
    recs = result.scalars().unique().all()

    items = []
    for rec in recs:
        stock_brief = None
        if rec.stock:
            stock_brief = StockBrief(
                code=rec.stock.code,
                name=rec.stock.name,
                industry=rec.stock.industry,
            )
        items.append(RecommendationRead(
            id=rec.id,
            rec_date=rec.rec_date,
            stock_id=rec.stock_id,
            stock=stock_brief,
            quant_score=rec.quant_score,
            catalyst_score=rec.catalyst_score,
            final_score=rec.final_score,
            rank=rec.rank,
            reason_short=rec.reason_short,
            reason_detail=rec.reason_detail,
            price_at_rec=rec.price_at_rec,
            price_t1=rec.price_t1,
            price_t5=rec.price_t5,
            return_t1=rec.return_t1,
            return_t5=rec.return_t5,
            created_at=rec.created_at,
        ))

    return RecommendationListResponse(
        rec_date=target_date,
        count=len(items),
        recommendations=items,
    )


@router.get("/history", response_model=list[RecommendationListResponse])
async def get_recommendation_history(
    db: DBSession,
    days: int = Query(default=7, le=30, description="查询最近 N 天"),
):
    """获取历史推荐记录（含事后表现）。"""
    start_date = date.today() - timedelta(days=days)

    result = await db.execute(
        select(Recommendation)
        .options(joinedload(Recommendation.stock))
        .where(Recommendation.rec_date >= start_date)
        .order_by(Recommendation.rec_date.desc(), Recommendation.rank.asc())
    )
    recs = result.scalars().unique().all()

    grouped: dict[date, list[RecommendationRead]] = {}
    for rec in recs:
        stock_brief = None
        if rec.stock:
            stock_brief = StockBrief(
                code=rec.stock.code,
                name=rec.stock.name,
                industry=rec.stock.industry,
            )
        item = RecommendationRead(
            id=rec.id,
            rec_date=rec.rec_date,
            stock_id=rec.stock_id,
            stock=stock_brief,
            quant_score=rec.quant_score,
            catalyst_score=rec.catalyst_score,
            final_score=rec.final_score,
            rank=rec.rank,
            reason_short=rec.reason_short,
            reason_detail=rec.reason_detail,
            price_at_rec=rec.price_at_rec,
            price_t1=rec.price_t1,
            price_t5=rec.price_t5,
            return_t1=rec.return_t1,
            return_t5=rec.return_t5,
            created_at=rec.created_at,
        )
        grouped.setdefault(rec.rec_date, []).append(item)

    return [
        RecommendationListResponse(
            rec_date=d,
            count=len(items),
            recommendations=items,
        )
        for d, items in sorted(grouped.items(), reverse=True)
    ]
