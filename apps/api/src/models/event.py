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
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base


class StockEvent(Base):
    __tablename__ = "stock_events"
    __table_args__ = (
        UniqueConstraint("stock_id", "title", "event_date", name="uq_stock_event"),
        Index("idx_events_stock_date", "stock_id", "event_date", postgresql_ops={"event_date": "DESC"}),
        Index("idx_events_date", "event_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"), nullable=False)
    event_date: Mapped[date] = mapped_column(Date, nullable=False)
    event_type: Mapped[str] = mapped_column(String(20), nullable=False)
    source: Mapped[str | None] = mapped_column(String(100))
    title: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str | None] = mapped_column(Text)
    url: Mapped[str | None] = mapped_column(String(500))

    sentiment: Mapped[str | None] = mapped_column(String(10))
    impact_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    catalyst_type: Mapped[str | None] = mapped_column(String(50))
    time_horizon: Mapped[str | None] = mapped_column(String(10))
    key_point: Mapped[str | None] = mapped_column(Text)
    risk_note: Mapped[str | None] = mapped_column(Text)
    analysis: Mapped[str | None] = mapped_column(Text)

    is_analyzed: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    stock: Mapped["Stock"] = relationship()  # noqa: F821
