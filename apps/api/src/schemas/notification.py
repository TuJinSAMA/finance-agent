from datetime import datetime

from pydantic import BaseModel


class NotificationRead(BaseModel):
    id: str
    type: str  # "recommendation" | "alert"
    title: str
    description: str | None = None
    action_url: str | None = None
    is_read: bool = False
    created_at: datetime


class NotificationListResponse(BaseModel):
    count: int
    notifications: list[NotificationRead]


class UnreadCountResponse(BaseModel):
    count: int
