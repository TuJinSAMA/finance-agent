from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base


class Stock(Base):
    __tablename__ = "stocks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(10), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    market: Mapped[str] = mapped_column(String(10), nullable=False, default="CN_A", server_default="CN_A")
    exchange: Mapped[str] = mapped_column(String(10), nullable=False)
    industry: Mapped[str | None] = mapped_column(String(50), nullable=True)
    list_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_st: Mapped[bool] = mapped_column(Boolean, default=False)
    is_delisting: Mapped[bool] = mapped_column(Boolean, default=False)
    total_shares: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    float_shares: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    daily_quotes: Mapped[list["StockDailyQuote"]] = relationship(back_populates="stock")
    technical_indicators: Mapped[list["StockTechnicalIndicator"]] = relationship(
        back_populates="stock"
    )
    fundamentals: Mapped[list["StockFundamental"]] = relationship(back_populates="stock")


class StockDailyQuote(Base):
    __tablename__ = "stock_daily_quotes"
    __table_args__ = (
        UniqueConstraint("stock_id", "trade_date"),
        Index("idx_daily_quotes_date", "trade_date"),
        Index("idx_daily_quotes_stock_date", "stock_id", "trade_date", postgresql_ops={"trade_date": "DESC"}),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"), nullable=False)
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)
    open: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    high: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    low: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    close: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    volume: Mapped[int | None] = mapped_column(BigInteger)
    amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    turnover_rate: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    pct_change: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))

    stock: Mapped["Stock"] = relationship(back_populates="daily_quotes")


class StockTechnicalIndicator(Base):
    __tablename__ = "stock_technical_indicators"
    __table_args__ = (UniqueConstraint("stock_id", "trade_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"), nullable=False)
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)
    ma5: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    ma10: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    ma20: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    ma60: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    macd: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    macd_signal: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    macd_hist: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    rsi_14: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    boll_upper: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    boll_mid: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    boll_lower: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    atr_14: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    volume_ma5: Mapped[int | None] = mapped_column(BigInteger)
    volume_ma20: Mapped[int | None] = mapped_column(BigInteger)

    stock: Mapped["Stock"] = relationship(back_populates="technical_indicators")


class StockFundamental(Base):
    __tablename__ = "stock_fundamentals"
    __table_args__ = (UniqueConstraint("stock_id", "report_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"), nullable=False)
    report_date: Mapped[date] = mapped_column(Date, nullable=False)
    pe_ttm: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    pb: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    ps_ttm: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    roe: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    gross_margin: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    net_margin: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    revenue_yoy: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    profit_yoy: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    operating_cf: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    debt_ratio: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    market_cap: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    float_market_cap: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    stock: Mapped["Stock"] = relationship(back_populates="fundamentals")
