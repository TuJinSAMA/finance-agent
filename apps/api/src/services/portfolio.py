import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from src.core.exceptions import AlreadyExistsException, NotFoundException
from src.models.portfolio import Portfolio, PortfolioAlert, PortfolioHolding
from src.models.stock import Stock, StockDailyQuote
from src.schemas.portfolio import (
    AlertRead,
    HoldingCreate,
    HoldingRead,
    HoldingUpdate,
    PortfolioDetailRead,
    PortfolioRead,
    PortfolioSummary,
)
from src.schemas.recommendation import StockBrief


class PortfolioService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ── Portfolio CRUD ───────────────────────────────────────

    async def get_or_create_default(self, user_id: uuid.UUID) -> Portfolio:
        result = await self.db.execute(
            select(Portfolio).where(
                Portfolio.user_id == user_id, Portfolio.name == "默认组合"
            )
        )
        portfolio = result.scalar_one_or_none()
        if portfolio:
            return portfolio

        portfolio = Portfolio(user_id=user_id, name="默认组合")
        self.db.add(portfolio)
        try:
            await self.db.flush()
        except IntegrityError:
            await self.db.rollback()
            raise AlreadyExistsException("Portfolio", "默认组合")
        await self.db.refresh(portfolio)
        return portfolio

    # ── Portfolio Detail (with P&L) ──────────────────────────

    async def get_portfolio_detail(
        self, user_id: uuid.UUID
    ) -> PortfolioDetailRead:
        portfolio = await self.get_or_create_default(user_id)

        result = await self.db.execute(
            select(PortfolioHolding)
            .options(joinedload(PortfolioHolding.stock))
            .where(PortfolioHolding.portfolio_id == portfolio.id)
            .order_by(PortfolioHolding.added_date.desc())
        )
        holdings = list(result.scalars().unique().all())

        stock_ids = [h.stock_id for h in holdings]
        latest_prices = await self._get_latest_prices(stock_ids) if stock_ids else {}

        total_market_value = Decimal("0")
        total_cost = Decimal("0")
        holding_reads: list[HoldingRead] = []

        for h in holdings:
            stock_brief = None
            if h.stock:
                stock_brief = StockBrief(
                    code=h.stock.code,
                    name=h.stock.name,
                    industry=h.stock.industry,
                )

            current_price = latest_prices.get(h.stock_id)
            market_value = None
            profit_loss = None
            profit_pct = None

            if current_price is not None:
                market_value = current_price * h.quantity
                cost_total = h.avg_cost * h.quantity
                profit_loss = market_value - cost_total
                if h.avg_cost > 0:
                    profit_pct = (current_price - h.avg_cost) / h.avg_cost
                total_market_value += market_value
                total_cost += cost_total
            else:
                total_cost += h.avg_cost * h.quantity

            holding_reads.append(HoldingRead(
                id=h.id,
                stock=stock_brief,
                quantity=h.quantity,
                avg_cost=h.avg_cost,
                added_date=h.added_date,
                notes=h.notes,
                current_price=current_price,
                market_value=market_value,
                profit_loss=profit_loss,
                profit_pct=profit_pct,
            ))

        total_profit = total_market_value - total_cost
        total_profit_pct = (
            (total_profit / total_cost) if total_cost > 0 else None
        )

        return PortfolioDetailRead(
            portfolio=PortfolioRead(
                id=portfolio.id,
                name=portfolio.name,
                description=portfolio.description,
                created_at=portfolio.created_at,
                holdings_count=len(holding_reads),
            ),
            holdings=holding_reads,
            summary=PortfolioSummary(
                total_market_value=total_market_value,
                total_cost=total_cost,
                total_profit=total_profit,
                total_profit_pct=total_profit_pct,
            ),
        )

    # ── Holding CRUD ─────────────────────────────────────────

    async def add_holding(
        self, user_id: uuid.UUID, payload: HoldingCreate
    ) -> PortfolioHolding:
        portfolio = await self.get_or_create_default(user_id)

        stock = await self._resolve_stock(payload.stock_code)

        holding = PortfolioHolding(
            portfolio_id=portfolio.id,
            stock_id=stock.id,
            quantity=payload.quantity,
            avg_cost=payload.avg_cost,
            added_date=date.today(),
            notes=payload.notes,
        )
        self.db.add(holding)
        try:
            await self.db.flush()
        except IntegrityError:
            await self.db.rollback()
            raise AlreadyExistsException("Holding", payload.stock_code)
        await self.db.refresh(holding)
        return holding

    async def update_holding(
        self,
        user_id: uuid.UUID,
        holding_id: int,
        payload: HoldingUpdate,
    ) -> PortfolioHolding:
        holding = await self._get_holding_with_ownership(user_id, holding_id)
        update_data = payload.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(holding, field, value)
        await self.db.flush()
        await self.db.refresh(holding)
        return holding

    async def remove_holding(
        self, user_id: uuid.UUID, holding_id: int
    ) -> None:
        holding = await self._get_holding_with_ownership(user_id, holding_id)
        await self.db.delete(holding)
        await self.db.flush()

    # ── Alerts ───────────────────────────────────────────────

    async def get_alerts(
        self,
        user_id: uuid.UUID,
        unread_only: bool = False,
        limit: int = 50,
    ) -> list[AlertRead]:
        stmt = (
            select(PortfolioAlert)
            .options(joinedload(PortfolioAlert.stock))
            .where(PortfolioAlert.user_id == user_id)
            .order_by(PortfolioAlert.created_at.desc())
            .limit(limit)
        )
        if unread_only:
            stmt = stmt.where(PortfolioAlert.is_read.is_(False))

        result = await self.db.execute(stmt)
        alerts = result.scalars().unique().all()

        return [
            AlertRead(
                id=a.id,
                stock=StockBrief(
                    code=a.stock.code,
                    name=a.stock.name,
                    industry=a.stock.industry,
                ) if a.stock else None,
                alert_type=a.alert_type,
                alert_date=a.alert_date,
                title=a.title,
                content=a.content,
                is_read=a.is_read,
                created_at=a.created_at,
            )
            for a in alerts
        ]

    async def mark_alert_read(
        self, user_id: uuid.UUID, alert_id: int
    ) -> PortfolioAlert:
        result = await self.db.execute(
            select(PortfolioAlert).where(
                PortfolioAlert.id == alert_id,
                PortfolioAlert.user_id == user_id,
            )
        )
        alert = result.scalar_one_or_none()
        if not alert:
            raise NotFoundException("Alert", str(alert_id))
        alert.is_read = True
        await self.db.flush()
        await self.db.refresh(alert)
        return alert

    # ── Private helpers ──────────────────────────────────────

    async def _resolve_stock(self, stock_code: str) -> Stock:
        result = await self.db.execute(
            select(Stock).where(Stock.code == stock_code)
        )
        stock = result.scalar_one_or_none()
        if not stock:
            raise NotFoundException("Stock", stock_code)
        return stock

    async def _get_holding_with_ownership(
        self, user_id: uuid.UUID, holding_id: int
    ) -> PortfolioHolding:
        result = await self.db.execute(
            select(PortfolioHolding)
            .join(Portfolio)
            .where(
                PortfolioHolding.id == holding_id,
                Portfolio.user_id == user_id,
            )
        )
        holding = result.scalar_one_or_none()
        if not holding:
            raise NotFoundException("Holding", str(holding_id))
        return holding

    async def _get_latest_prices(
        self, stock_ids: list[int]
    ) -> dict[int, Decimal]:
        """Get the latest closing price for each stock from daily quotes."""
        # Subquery: max trade_date per stock
        latest_date_sq = (
            select(
                StockDailyQuote.stock_id,
                func.max(StockDailyQuote.trade_date).label("max_date"),
            )
            .where(StockDailyQuote.stock_id.in_(stock_ids))
            .group_by(StockDailyQuote.stock_id)
            .subquery()
        )

        result = await self.db.execute(
            select(StockDailyQuote.stock_id, StockDailyQuote.close)
            .join(
                latest_date_sq,
                (StockDailyQuote.stock_id == latest_date_sq.c.stock_id)
                & (StockDailyQuote.trade_date == latest_date_sq.c.max_date),
            )
        )

        return {
            row.stock_id: row.close
            for row in result.all()
            if row.close is not None
        }
