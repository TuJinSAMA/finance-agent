from datetime import date
from decimal import Decimal

from sqlalchemy import (
    Date,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base


class Watchlist(Base):
    __tablename__ = "watchlist"
    __table_args__ = (
        UniqueConstraint("stock_id", "added_date"),
        Index("idx_watchlist_status", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"), nullable=False)
    added_date: Mapped[date] = mapped_column(Date, nullable=False)
    quant_score: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    factor_scores: Mapped[dict | None] = mapped_column(JSONB)

    catalyst_summary: Mapped[dict | None] = mapped_column(JSONB)
    catalyst_date: Mapped[date | None] = mapped_column(Date)

    recommended_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    last_recommended: Mapped[date | None] = mapped_column(Date)

    status: Mapped[str] = mapped_column(String(10), default="active", server_default="active")
    removed_date: Mapped[date | None] = mapped_column(Date)
    removed_reason: Mapped[str | None] = mapped_column(String(200))

    stock: Mapped["Stock"] = relationship()  # noqa: F821


class WatchlistSnapshot(Base):
    __tablename__ = "watchlist_snapshots"
    __table_args__ = (
        UniqueConstraint("snapshot_date", "stock_id"),
        Index("idx_watchlist_snapshots_date", "snapshot_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"), nullable=False)
    quant_score: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    rank_in_list: Mapped[int | None] = mapped_column(Integer)
