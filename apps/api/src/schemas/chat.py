import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from src.schemas.base import BaseSchema, BaseReadSchema


class ChatSessionCreate(BaseSchema):
    title: str = Field(default="New Chat", max_length=255)


class ChatSessionUpdate(BaseSchema):
    title: str = Field(max_length=255)


class ChatSessionRead(BaseReadSchema):
    user_id: uuid.UUID
    title: str
    message_count: int = 0


class ChatSessionListRead(BaseSchema):
    id: uuid.UUID
    title: str
    updated_at: datetime
    message_count: int = 0

    model_config = {"from_attributes": True}


class ChatMessageCreate(BaseSchema):
    content: str = Field(min_length=1, max_length=10000)


class ChatMessageRead(BaseReadSchema):
    session_id: uuid.UUID
    role: str
    content: str
    stage_data: dict | None = None
    token_count: int | None = None


class ChatMessageListRead(BaseSchema):
    id: uuid.UUID
    role: str
    content: str
    stage_data: dict | None = None
    token_count: int | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ContextUsageRead(BaseSchema):
    used_tokens: int
    max_tokens: int = 128000


class SSEEvent(BaseModel):
    type: str
    data: dict | str | None = None