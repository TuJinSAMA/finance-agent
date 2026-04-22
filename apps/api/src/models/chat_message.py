import uuid
import enum
from sqlalchemy import Text, ForeignKey, Integer, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import JSONB

from src.models.base import Base, TimestampMixin, UUIDMixin


class MessageRole(str, enum.Enum):
    user = "user"
    assistant = "assistant"
    system = "system"


class ChatMessage(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "chat_messages"

    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[str] = mapped_column(
        SQLEnum(MessageRole, name="message_role"),
        nullable=False,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    stage_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    token_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    session: Mapped["ChatSession"] = relationship(  # noqa: F821
        "ChatSession", back_populates="messages"
    )