from fastapi import APIRouter, Query

from src.dependencies import CurrentUser, DBSession
from src.schemas.notification import (
    NotificationListResponse,
    UnreadCountResponse,
)
from src.services.notification import NotificationService

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=NotificationListResponse)
async def get_notifications(
    db: DBSession,
    user: CurrentUser,
    unread_only: bool = Query(default=False),
    limit: int = Query(default=50, le=100),
):
    """获取当前用户的通知列表（推荐 + 持仓异动合并）。"""
    service = NotificationService(db)
    items = await service.get_notifications(user.id, unread_only, limit)
    return NotificationListResponse(count=len(items), notifications=items)


@router.get("/unread-count", response_model=UnreadCountResponse)
async def get_unread_count(
    db: DBSession,
    user: CurrentUser,
):
    """获取未读通知数量（供铃铛 badge 轮询）。"""
    service = NotificationService(db)
    count = await service.get_unread_count(user.id)
    return UnreadCountResponse(count=count)


@router.post("/{notification_id}/read")
async def mark_notification_read(
    notification_id: str,
    db: DBSession,
    user: CurrentUser,
):
    """标记单条通知为已读。"""
    service = NotificationService(db)
    ok = await service.mark_read(user.id, notification_id)
    return {"ok": ok}


@router.post("/mark-all-read")
async def mark_all_read(
    db: DBSession,
    user: CurrentUser,
):
    """标记所有通知为已读。"""
    service = NotificationService(db)
    count = await service.mark_all_read(user.id)
    return {"ok": True, "marked": count}
