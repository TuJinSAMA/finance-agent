from datetime import date

from fastapi import APIRouter, Query

from src.dependencies import DBSession
from src.schemas.admin import (
    PipelineLogResponse,
    PipelineStatusResponse,
    RecommendationStatsResponse,
    RerunResponse,
)
from src.services.admin import AdminService

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/pipeline/status", response_model=PipelineStatusResponse)
async def get_pipeline_status(
    db: DBSession,
    target_date: date = Query(default=None, description="查询日期，默认今天"),
):
    """查看指定日期各步骤的执行状态。"""
    svc = AdminService(db)
    d = target_date or date.today()
    steps = await svc.get_pipeline_status(d)
    return PipelineStatusResponse(date=d, steps=steps)


@router.get("/pipeline/logs", response_model=PipelineLogResponse)
async def get_pipeline_logs(
    db: DBSession,
    target_date: date = Query(default=None, description="查询日期，默认今天"),
):
    """查看流水线日志。"""
    svc = AdminService(db)
    d = target_date or date.today()
    logs = await svc.get_pipeline_logs(d)
    return PipelineLogResponse(date=d, logs=logs)


@router.post("/pipeline/rerun/{step}", response_model=RerunResponse)
async def rerun_pipeline_step(
    step: str,
    db: DBSession,
    target_date: date = Query(default=None, description="目标日期，默认今天"),
):
    """重跑某个步骤（如 LLM 调用失败需要重试）。"""
    svc = AdminService(db)
    d = target_date or date.today()
    try:
        result = await svc.rerun_step(step, d)
        return RerunResponse(status="ok", step=step, result=result)
    except ValueError as e:
        return RerunResponse(status="error", step=step, error=str(e))
    except Exception as e:
        return RerunResponse(status="error", step=step, error=str(e))


@router.get("/stats/recommendations", response_model=RecommendationStatsResponse)
async def get_recommendation_stats(db: DBSession):
    """推荐系统整体表现统计。"""
    svc = AdminService(db)
    return await svc.get_recommendation_stats()
