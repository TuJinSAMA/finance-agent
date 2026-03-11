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


class Portfolio(Base):
    __tablename__ = "portfolios"
    __table_args__ = (UniqueConstraint("user_id", "name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(100), default="默认组合", server_default="默认组合")
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    holdings: Mapped[list["PortfolioHolding"]] = relationship(
        back_populates="portfolio", cascade="all, delete-orphan"
    )


class PortfolioHolding(Base):
    __tablename__ = "portfolio_holdings"
    __table_args__ = (UniqueConstraint("portfolio_id", "stock_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    portfolio_id: Mapped[int] = mapped_column(
        ForeignKey("portfolios.id", ondelete="CASCADE"), nullable=False
    )
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    avg_cost: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    added_date: Mapped[date] = mapped_column(Date, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    portfolio: Mapped["Portfolio"] = relationship(back_populates="holdings")
    stock: Mapped["Stock"] = relationship()  # noqa: F821


class PortfolioAlert(Base):
    __tablename__ = "portfolio_alerts"
    __table_args__ = (
        Index("idx_portfolio_alerts_user_date", "user_id", "alert_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"), nullable=False)
    event_id: Mapped[int | None] = mapped_column(
        ForeignKey("stock_events.id"), nullable=True
    )
    alert_type: Mapped[str] = mapped_column(String(30), nullable=False)
    alert_date: Mapped[date] = mapped_column(Date, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str | None] = mapped_column(Text)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    stock: Mapped["Stock"] = relationship()  # noqa: F821
