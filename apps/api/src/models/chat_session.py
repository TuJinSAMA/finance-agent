import uuid
from sqlalchemy import String, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base, TimestampMixin, UUIDMixin


class ChatSession(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "chat_sessions"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(255), default="New Chat")
    updated_at = TimestampMixin.updated_at

    messages: Mapped[list["ChatMessage"]] = relationship(  # noqa: F821
        "ChatMessage",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="ChatMessage.created_at",
    )

    __table_args__ = (
        Index("ix_chat_sessions_user_updated", "user_id", "updated_at"),
    )