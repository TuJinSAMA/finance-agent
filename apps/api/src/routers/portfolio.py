from fastapi import APIRouter, Query

from src.dependencies import CurrentUser, PortfolioServiceDep
from src.schemas.portfolio import (
    AlertRead,
    HoldingCreate,
    HoldingUpdate,
    PortfolioDetailRead,
)

router = APIRouter(prefix="/portfolio", tags=["portfolio"])


@router.get("", response_model=PortfolioDetailRead)
async def get_portfolio(
    current_user: CurrentUser,
    service: PortfolioServiceDep,
):
    """获取用户的持仓列表（含当前市值、盈亏）。"""
    return await service.get_portfolio_detail(current_user.id)


@router.post("/holdings", status_code=201)
async def add_holding(
    payload: HoldingCreate,
    current_user: CurrentUser,
    service: PortfolioServiceDep,
):
    """添加持仓。"""
    holding = await service.add_holding(current_user.id, payload)
    return {"id": holding.id, "stock_id": holding.stock_id}


@router.put("/holdings/{holding_id}")
async def update_holding(
    holding_id: int,
    payload: HoldingUpdate,
    current_user: CurrentUser,
    service: PortfolioServiceDep,
):
    """更新持仓（加仓/减仓/修改成本价）。"""
    holding = await service.update_holding(current_user.id, holding_id, payload)
    return {"id": holding.id, "quantity": holding.quantity, "avg_cost": holding.avg_cost}


@router.delete("/holdings/{holding_id}", status_code=204)
async def remove_holding(
    holding_id: int,
    current_user: CurrentUser,
    service: PortfolioServiceDep,
):
    """清仓。"""
    await service.remove_holding(current_user.id, holding_id)


@router.get("/alerts", response_model=list[AlertRead])
async def get_alerts(
    current_user: CurrentUser,
    service: PortfolioServiceDep,
    unread_only: bool = Query(default=False, description="只看未读"),
    limit: int = Query(default=50, le=200),
):
    """获取持仓相关的异动提醒。"""
    return await service.get_alerts(current_user.id, unread_only=unread_only, limit=limit)


@router.patch("/alerts/{alert_id}/read")
async def mark_alert_read(
    alert_id: int,
    current_user: CurrentUser,
    service: PortfolioServiceDep,
):
    """标记提醒已读。"""
    alert = await service.mark_alert_read(current_user.id, alert_id)
    return {"id": alert.id, "is_read": alert.is_read}
