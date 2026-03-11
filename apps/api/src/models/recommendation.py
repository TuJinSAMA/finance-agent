import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base


class Recommendation(Base):
    __tablename__ = "recommendations"
    __table_args__ = (
        UniqueConstraint("rec_date", "stock_id"),
        Index("idx_recommendations_date", "rec_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    rec_date: Mapped[date] = mapped_column(Date, nullable=False)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"), nullable=False)
    quant_score: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    catalyst_score: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    final_score: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    rank: Mapped[int | None] = mapped_column(Integer)
    reason_short: Mapped[str | None] = mapped_column(Text)
    reason_detail: Mapped[str | None] = mapped_column(Text)

    price_at_rec: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    price_t1: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    price_t5: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    return_t1: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    return_t5: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    stock: Mapped["Stock"] = relationship()  # noqa: F821
    user_recommendations: Mapped[list["UserRecommendation"]] = relationship(
        back_populates="recommendation"
    )


class UserRecommendation(Base):
    __tablename__ = "user_recommendations"
    __table_args__ = (
        UniqueConstraint("user_id", "recommendation_id"),
        Index("idx_user_rec_user_date", "user_id", "rec_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    recommendation_id: Mapped[int] = mapped_column(
        ForeignKey("recommendations.id"), nullable=False
    )
    rec_date: Mapped[date] = mapped_column(Date, nullable=False)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    is_favorited: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    user_feedback: Mapped[str | None] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    recommendation: Mapped["Recommendation"] = relationship(
        back_populates="user_recommendations"
    )
