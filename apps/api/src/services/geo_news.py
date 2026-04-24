import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.geo_event import GeoEvent, RawGeoArticle
from src.models.geo_news_config import geo_news_config

logger = logging.getLogger(__name__)


class GeoNewsService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_active_events(
        self,
        impact_level: int | None = None,
        category: str | None = None,
        region: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[GeoEvent], int, int, int, datetime | None]:
        now = datetime.now(UTC)
        query = select(GeoEvent).where(
            GeoEvent.is_active.is_(True),
            (GeoEvent.expires_at.is_(None)) | (GeoEvent.expires_at > now),
        )

        if impact_level is not None:
            query = query.where(GeoEvent.impact_level == impact_level)

        if category is not None:
            query = query.where(GeoEvent.categories.contains(category))

        if region is not None:
            query = query.where(GeoEvent.region == region)

        total_query = select(func.count()).select_from(query.subquery())
        total_result = await self.db.execute(total_query)
        total = total_result.scalar() or 0

        level3_query = select(func.count()).select_from(
            query.where(GeoEvent.impact_level == 3).subquery()
        )
        level3_result = await self.db.execute(level3_query)
        level3_count = level3_result.scalar() or 0

        level2_query = select(func.count()).select_from(
            query.where(GeoEvent.impact_level == 2).subquery()
        )
        level2_result = await self.db.execute(level2_query)
        level2_count = level2_result.scalar() or 0

        last_updated_query = select(func.max(GeoEvent.created_at)).where(
            GeoEvent.is_active.is_(True)
        )
        last_updated_result = await self.db.execute(last_updated_query)
        last_updated = last_updated_result.scalar()

        query = query.order_by(
            GeoEvent.impact_level.desc(),
            GeoEvent.event_date.desc(),
        ).offset(offset).limit(min(limit, 50))

        result = await self.db.execute(query)
        events = list(result.scalars().all())

        return events, total, level3_count, level2_count, last_updated

    async def upsert_raw_article(
        self,
        pipeline: str,
        source_name: str,
        url: str,
        title: str,
        content: str | None,
        published_at: datetime | None,
    ) -> bool:
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        fetched_at = datetime.now(UTC)
        stmt = pg_insert(RawGeoArticle).values(
            pipeline=pipeline,
            source_name=source_name,
            url=url,
            title=title,
            content=content,
            published_at=published_at,
            fetched_at=fetched_at,
        )
        stmt = stmt.on_conflict_do_nothing(constraint="raw_geo_articles_pipeline_url_key")
        result = await self.db.execute(stmt)
        await self.db.flush()
        return result.rowcount > 0

    async def get_unprocessed_articles(self, limit: int = 50) -> list[RawGeoArticle]:
        query = (
            select(RawGeoArticle)
            .where(RawGeoArticle.is_processed.is_(False))
            .order_by(RawGeoArticle.fetched_at.asc())
            .limit(limit)
        )
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def mark_articles_processed(self, article_ids: list[int]) -> None:
        if not article_ids:
            return
        await self.db.execute(
            update(RawGeoArticle)
            .where(RawGeoArticle.id.in_(article_ids))
            .values(is_processed=True)
        )
        await self.db.flush()

    async def create_geo_event(self, event_data: dict) -> GeoEvent | None:
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        stmt = pg_insert(GeoEvent).values(**event_data)
        stmt = stmt.on_conflict_do_nothing(constraint="geo_events_source_url_key")
        result = await self.db.execute(stmt)
        await self.db.flush()
        if result.rowcount > 0:
            sel = select(GeoEvent).where(GeoEvent.source_url == event_data["source_url"])
            res = await self.db.execute(sel)
            return res.scalar_one_or_none()
        return None

    async def deactivate_expired_events(self) -> int:
        now = datetime.now(UTC)
        result = await self.db.execute(
            update(GeoEvent)
            .where(GeoEvent.is_active.is_(True), GeoEvent.expires_at.is_not(None), GeoEvent.expires_at < now)
            .values(is_active=False)
        )
        await self.db.flush()
        return result.rowcount

    async def cleanup_processed_articles(self) -> int:
        cutoff = datetime.now(UTC) - timedelta(hours=geo_news_config.raw_article_ttl_hours)
        result = await self.db.execute(
            delete(RawGeoArticle).where(
                RawGeoArticle.is_processed.is_(True),
                RawGeoArticle.created_at < cutoff,
            )
        )
        await self.db.flush()
        return result.rowcount