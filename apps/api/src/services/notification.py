import uuid

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from src.models.portfolio import PortfolioAlert
from src.models.recommendation import Recommendation, UserRecommendation
from src.schemas.notification import NotificationRead


class NotificationService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_notifications(
        self,
        user_id: uuid.UUID,
        unread_only: bool = False,
        limit: int = 50,
    ) -> list[NotificationRead]:
        rec_notifications = await self._get_recommendation_notifications(
            user_id, unread_only, limit
        )
        alert_notifications = await self._get_alert_notifications(
            user_id, unread_only, limit
        )

        merged = rec_notifications + alert_notifications
        merged.sort(key=lambda n: n.created_at, reverse=True)
        return merged[:limit]

    async def get_unread_count(self, user_id: uuid.UUID) -> int:
        rec_count = await self.db.scalar(
            select(func.count())
            .select_from(UserRecommendation)
            .where(
                UserRecommendation.user_id == user_id,
                UserRecommendation.is_read.is_(False),
            )
        ) or 0

        alert_count = await self.db.scalar(
            select(func.count())
            .select_from(PortfolioAlert)
            .where(
                PortfolioAlert.user_id == user_id,
                PortfolioAlert.is_read.is_(False),
            )
        ) or 0

        return rec_count + alert_count

    async def mark_read(self, user_id: uuid.UUID, notification_id: str) -> bool:
        ntype, raw_id = self._parse_notification_id(notification_id)
        if ntype == "rec":
            result = await self.db.execute(
                update(UserRecommendation)
                .where(
                    UserRecommendation.id == int(raw_id),
                    UserRecommendation.user_id == user_id,
                )
                .values(is_read=True)
            )
        elif ntype == "alert":
            result = await self.db.execute(
                update(PortfolioAlert)
                .where(
                    PortfolioAlert.id == int(raw_id),
                    PortfolioAlert.user_id == user_id,
                )
                .values(is_read=True)
            )
        else:
            return False
        await self.db.flush()
        return result.rowcount > 0

    async def mark_all_read(self, user_id: uuid.UUID) -> int:
        r1 = await self.db.execute(
            update(UserRecommendation)
            .where(
                UserRecommendation.user_id == user_id,
                UserRecommendation.is_read.is_(False),
            )
            .values(is_read=True)
        )
        r2 = await self.db.execute(
            update(PortfolioAlert)
            .where(
                PortfolioAlert.user_id == user_id,
                PortfolioAlert.is_read.is_(False),
            )
            .values(is_read=True)
        )
        await self.db.flush()
        return (r1.rowcount or 0) + (r2.rowcount or 0)

    async def _get_recommendation_notifications(
        self,
        user_id: uuid.UUID,
        unread_only: bool,
        limit: int,
    ) -> list[NotificationRead]:
        stmt = (
            select(UserRecommendation)
            .options(
                joinedload(UserRecommendation.recommendation).joinedload(
                    Recommendation.stock
                )
            )
            .where(UserRecommendation.user_id == user_id)
            .order_by(UserRecommendation.created_at.desc())
            .limit(limit)
        )
        if unread_only:
            stmt = stmt.where(UserRecommendation.is_read.is_(False))

        result = await self.db.execute(stmt)
        user_recs = result.scalars().unique().all()

        notifications: list[NotificationRead] = []
        for ur in user_recs:
            rec = ur.recommendation
            stock_name = rec.stock.name if rec and rec.stock else "未知"
            stock_code = rec.stock.code if rec and rec.stock else ""
            reason = rec.reason_short if rec else None

            notifications.append(
                NotificationRead(
                    id=f"rec_{ur.id}",
                    type="recommendation",
                    title=f"新推荐 — {stock_name}（{stock_code}）",
                    description=reason,
                    action_url="/dashboard",
                    is_read=ur.is_read,
                    created_at=ur.created_at,
                )
            )
        return notifications

    async def _get_alert_notifications(
        self,
        user_id: uuid.UUID,
        unread_only: bool,
        limit: int,
    ) -> list[NotificationRead]:
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

        notifications: list[NotificationRead] = []
        for a in alerts:
            notifications.append(
                NotificationRead(
                    id=f"alert_{a.id}",
                    type="alert",
                    title=a.title,
                    description=a.content,
                    action_url="/dashboard/portfolio",
                    is_read=a.is_read,
                    created_at=a.created_at,
                )
            )
        return notifications

    @staticmethod
    def _parse_notification_id(notification_id: str) -> tuple[str, str]:
        if notification_id.startswith("rec_"):
            return "rec", notification_id[4:]
        if notification_id.startswith("alert_"):
            return "alert", notification_id[6:]
        return "unknown", notification_id
