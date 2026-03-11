"""
Portfolio Monitor — 持仓事件联动。

在 morning_event_scan 完成后内联调用，将重大事件（impact_score >= 6）
与用户持仓关联，自动生成 PortfolioAlert。
"""

import logging
from datetime import date
from decimal import Decimal

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from src.models.event import StockEvent
from src.models.portfolio import Portfolio, PortfolioAlert, PortfolioHolding

logger = logging.getLogger(__name__)

MIN_IMPACT_SCORE = Decimal("6")


class PortfolioMonitor:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def check_holdings_against_events(
        self, target_date: date | None = None
    ) -> int:
        """
        Check today's significant events against all user holdings.
        Creates alerts for users who hold stocks with major events.

        Returns the number of alerts created.
        """
        target = target_date or date.today()

        significant_events = await self._get_significant_events(target)
        if not significant_events:
            logger.info("No significant events on %s for portfolio alerting", target)
            return 0

        event_stock_ids = {e.stock_id for e in significant_events}

        users_by_stock = await self._get_users_holding_stocks(event_stock_ids)
        if not users_by_stock:
            logger.info("No users hold stocks with significant events on %s", target)
            return 0

        existing_pairs = await self._get_existing_alert_pairs(target)

        alerts_created = 0
        for event in significant_events:
            user_ids = users_by_stock.get(event.stock_id, [])
            stock_name = event.stock.name if event.stock else f"stock#{event.stock_id}"

            for user_id in user_ids:
                pair_key = (user_id, event.id)
                if pair_key in existing_pairs:
                    continue

                alert = PortfolioAlert(
                    user_id=user_id,
                    stock_id=event.stock_id,
                    event_id=event.id,
                    alert_type="catalyst",
                    alert_date=target,
                    title=f"您持仓的{stock_name}有重大消息",
                    content=event.analysis or event.key_point or event.title,
                )
                self.db.add(alert)
                alerts_created += 1

        if alerts_created:
            await self.db.flush()

        logger.info(
            "Portfolio alerts created: %d (events=%d, date=%s)",
            alerts_created, len(significant_events), target,
        )
        return alerts_created

    async def _get_significant_events(self, target: date) -> list[StockEvent]:
        result = await self.db.execute(
            select(StockEvent)
            .options(joinedload(StockEvent.stock))
            .where(
                StockEvent.event_date == target,
                StockEvent.is_analyzed.is_(True),
                StockEvent.impact_score >= MIN_IMPACT_SCORE,
            )
        )
        return list(result.scalars().unique().all())

    async def _get_users_holding_stocks(
        self, stock_ids: set[int]
    ) -> dict[int, list]:
        """Return {stock_id: [user_id, ...]} for active holdings."""
        result = await self.db.execute(
            select(PortfolioHolding.stock_id, Portfolio.user_id)
            .join(Portfolio, PortfolioHolding.portfolio_id == Portfolio.id)
            .where(PortfolioHolding.stock_id.in_(stock_ids))
        )
        mapping: dict[int, list] = {}
        for row in result.all():
            mapping.setdefault(row.stock_id, []).append(row.user_id)
        return mapping

    async def _get_existing_alert_pairs(self, target: date) -> set[tuple]:
        """Get (user_id, event_id) pairs already alerted today to avoid dupes."""
        result = await self.db.execute(
            select(PortfolioAlert.user_id, PortfolioAlert.event_id).where(
                and_(
                    PortfolioAlert.alert_date == target,
                    PortfolioAlert.alert_type == "catalyst",
                    PortfolioAlert.event_id.is_not(None),
                )
            )
        )
        return {(row.user_id, row.event_id) for row in result.all()}
