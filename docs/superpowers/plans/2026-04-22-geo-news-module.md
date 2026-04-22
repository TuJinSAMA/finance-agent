# Geo News Module Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a geopolitical news module to the public board that surfaces investor-relevant events from 20+ global news sources, processed by LLM into structured impact-rated events.

**Architecture:** Three ingestion pipelines (RSS, GNews, GDELT) write raw articles to a temporary table, a unified LLM extraction pipeline processes them into structured events with impact levels (2=medium, 3=high; level 1 is discarded), and a public API serves them to the frontend board page. The frontend renders events between Macro and Assets sections with expandable cards, level-based visual hierarchy, and source links.

**Tech Stack:** Python 3.12+ / FastAPI / SQLAlchemy 2.0 async / Pydantic v2 / feedparser / httpx / APScheduler / Alembic / Next.js 16 / React 19 / TypeScript / Tailwind CSS v4

---

## File Structure

### Backend (apps/api/src/)

**New files:**
- `models/geo_event.py` — GeoEvent and RawGeoArticle SQLAlchemy models
- `models/geo_event_config.py` — GeoNewsConfig dataclass (will become `models/geo_news_config.py` — see note below)
- `schemas/geo_news.py` — Pydantic schemas for request/response
- `services/geo_news.py` — GeoNewsService (CRUD + query for geo_events)
- `agents/geo_news_agent/ingestion/rss_collector.py` — RSS pipeline
- `agents/geo_news_agent/ingestion/gnews_collector.py` — GNews pipeline
- `agents/geo_news_agent/ingestion/gdelt_collector.py` — GDELT pipeline
- `agents/geo_news_agent/extractor.py` — LLM event extraction pipeline
- `agents/geo_news_agent/dedup.py` — Jaccard similarity dedup utility
- `agents/geo_news_agent/__init__.py` — Package init
- `agents/geo_news_agent/jobs.py` — APScheduler job wrappers
- `routers/geo_news.py` — Public + admin API endpoints

**Modified files:**
- `models/__init__.py` — Add GeoEvent, RawGeoArticle exports
- `schemas/__init__.py` — Add exports if needed
- `dependencies.py` — Add GeoNewsServiceDep
- `main.py` — Mount geo_news router
- `core/config.py` — Add GNEWS_API_KEY and geo news config fields
- `core/scheduler.py` — Register 4 new scheduler jobs

**Migration:**
- `alembic/versions/<auto>_add_geo_events_and_raw_geo_articles.py`

### Frontend (apps/web/src/)

**New files:**
- `components/geo-news/GeoNewsSection.tsx` — Main section component
- `components/geo-news/GeoEventCard.tsx` — Expandable event card
- `components/geo-news/GeoNewsFilter.tsx` — Level filter toggle
- `types/geo-news.ts` — TypeScript types for API response

**Modified files:**
- `app/[locale]/board/page.tsx` — Add GeoNewsSection between Macro and Assets
- `types/api.ts` — Re-export geo-news types
- `messages/en.json` — Add board.geoNews keys
- `messages/zh.json` — Add board.geoNews keys

---

### Task 1: Database Models & Migration

**Files:**
- Create: `apps/api/src/models/geo_event.py`
- Create: `apps/api/src/models/geo_news_config.py`
- Modify: `apps/api/src/models/__init__.py`
- Create: `apps/api/alembic/versions/<auto>_add_geo_events_and_raw_articles.py`

- [ ] **Step 1: Write the GeoEvent model**

Create `apps/api/src/models/geo_event.py`:

```python
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base


class GeoEvent(Base):
    __tablename__ = "geo_events"
    __table_args__ = (
        Index(
            "idx_geo_events_active_level_date",
            "is_active",
            "impact_level",
            "event_date",
            postgresql_ops={"impact_level": "DESC", "event_date": "DESC"},
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    source_name: Mapped[str] = mapped_column(String(100), nullable=False)
    source_url: Mapped[str] = mapped_column(String(500), nullable=False, unique=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    impact_level: Mapped[int] = mapped_column(Integer, nullable=False)
    categories: Mapped[str | None] = mapped_column(String(500))
    region: Mapped[str | None] = mapped_column(String(50))
    event_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class RawGeoArticle(Base):
    __tablename__ = "raw_geo_articles"
    __table_args__ = (
        Index("idx_raw_geo_processed", "is_processed"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pipeline: Mapped[str] = mapped_column(String(20), nullable=False)
    source_name: Mapped[str] = mapped_column(String(100), nullable=False)
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str | None] = mapped_column(Text)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_processed: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
```

- [ ] **Step 2: Write the GeoNewsConfig dataclass**

Create `apps/api/src/models/geo_news_config.py`:

```python
from dataclasses import dataclass, field


RSS_FEEDS_EN = [
    "https://feeds.bbci.co.uk/news/world/middle_east/rss.xml",
    "https://feeds.bbci.co.uk/news/world/rss.xml",
    "https://www.aljazeera.com/xml/rss/all.xml",
    "https://www.theguardian.com/world/rss",
    "https://search.cnbc.com/rss/news/world/",
    "https://www.timesofisrael.com/feed/",
    "https://feeds.npr.org/1004/rss.xml",
    "https://www.france24.com/en/middle-east/rss",
    "https://rss.dw.com/rss/rss-en-world",
    "https://feeds.skynews.com/feeds/rss/world.xml",
    "https://oilprice.com/rss/main",
    "https://www.scmp.com/rss/91/feed",
]

RSS_FEEDS_CN = [
    "https://rsshub.app/cls-telegraph",
    "https://rsshub.app/wallstreetcn/news/global",
    "https://rsshub.app/jin10",
    "https://rsshub.app/sina/finance",
    "https://rsshub.app/xueqiu/hotstock",
]

RSS_FEEDS_GLOBAL = [
    "https://www.investing.com/rss/news_301.rss",
    "https://finviz.com/rss.ashx",
]

GNEWS_QUERIES = [
    "iran war military strike",
    "hormuz strait oil tanker",
    "iran us sanctions nuclear",
    "iran israel military",
    "gulf oil supply disruption",
]

GDELT_KEYWORDS = ["iran", "oil", "military"]

GEO_CATEGORIES = [
    "military",
    "sanctions",
    "energy",
    "trade_policy",
    "geopolitics",
    "macro_economy",
    "supply_disruption",
    "regulation",
]

GEO_REGIONS = [
    "middle_east",
    "east_asia",
    "europe",
    "americas",
    "africa",
    "global",
]


@dataclass(frozen=True)
class GeoNewsConfig:
    rss_feeds: list[str] = field(default_factory=lambda: RSS_FEEDS_EN + RSS_FEEDS_CN + RSS_FEEDS_GLOBAL)
    gnews_api_key: str = ""
    gnews_base_url: str = "https://newsapi.org/v2"
    gnews_queries: list[str] = field(default_factory=lambda: list(GNEWS_QUERIES))
    gnews_max_articles_per_query: int = 10

    gdelt_base_url: str = "https://api.gdeltproject.org/api/v2/doc/doc"
    gdelt_keywords: list[str] = field(default_factory=lambda: list(GDELT_KEYWORDS))
    gdelt_max_articles: int = 50

    llm_model: str = "google/gemini-3.1-flash-lite-preview"
    batch_size: int = 10
    dedup_threshold: float = 0.7

    raw_article_ttl_hours: int = 48

    sensitivity_hours_ttl: int = 24
    sensitivity_days_ttl: int = 7
    sensitivity_weeks_ttl: int = 30

    rss_interval_minutes: int = 15
    gnews_interval_hours: int = 2
    gdelt_interval_hours: int = 6
    extraction_interval_minutes: int = 10


geo_news_config = GeoNewsConfig()
```

- [ ] **Step 3: Update models/__init__.py**

Add imports and exports for `GeoEvent` and `RawGeoArticle`:

```python
from src.models.geo_event import GeoEvent, RawGeoArticle
```

Add to `__all__`:

```python
"GeoEvent",
"RawGeoArticle",
```

- [ ] **Step 4: Add config to settings**

Modify `apps/api/src/core/config.py` to add `GNEWS_API_KEY`:

```python
GNEWS_API_KEY: str = ""
```

- [ ] **Step 5: Generate migration**

Run:
```bash
cd apps/api && uv run alembic revision --autogenerate -m "add geo_events and raw_geo_articles tables"
```

Then edit the generated migration to verify it creates both tables with the correct columns, unique constraints, and indexes.

- [ ] **Step 6: Run migration**

```bash
cd apps/api && uv run alembic upgrade head
```

- [ ] **Step 7: Commit**

```bash
git add apps/api/src/models/geo_event.py apps/api/src/models/geo_news_config.py apps/api/src/models/__init__.py apps/api/src/core/config.py apps/api/alembic/versions/
git commit -m "feat(geo-news): add GeoEvent and RawGeoArticle models, config, and migration"
```

---

### Task 2: Pydantic Schemas

**Files:**
- Create: `apps/api/src/schemas/geo_news.py`

- [ ] **Step 1: Write the Pydantic schemas**

Create `apps/api/src/schemas/geo_news.py`:

```python
from datetime import datetime

from pydantic import BaseModel


class GeoEventRead(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    source_name: str
    source_url: str
    title: str
    summary: str
    impact_level: int
    categories: str | None
    region: str | None
    event_date: datetime
    is_active: bool


class GeoEventListResponse(BaseModel):
    events: list[GeoEventRead]
    total: int
    level3_count: int
    level2_count: int
    last_updated: datetime | None


class GeoEventQueryParams(BaseModel):
    impact_level: int | None = None
    category: str | None = None
    region: str | None = None
    limit: int = 20
    offset: int = 0
```

- [ ] **Step 2: Commit**

```bash
git add apps/api/src/schemas/geo_news.py
git commit -m "feat(geo-news): add Pydantic schemas for geo news API"
```

---

### Task 3: GeoNewsService (CRUD + Query)

**Files:**
- Create: `apps/api/src/services/geo_news.py`
- Modify: `apps/api/src/dependencies.py`

- [ ] **Step 1: Write GeoNewsService**

Create `apps/api/src/services/geo_news.py`:

```python
import json
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
```

- [ ] **Step 2: Add dependency to dependencies.py**

Add to `apps/api/src/dependencies.py`:

```python
from src.services.geo_news import GeoNewsService

def get_geo_news_service(db: DBSession) -> GeoNewsService:
    return GeoNewsService(db)

GeoNewsServiceDep = Annotated[GeoNewsService, Depends(get_geo_news_service)]
```

- [ ] **Step 3: Commit**

```bash
git add apps/api/src/services/geo_news.py apps/api/src/dependencies.py
git commit -m "feat(geo-news): add GeoNewsService with CRUD, query, and cleanup"
```

---

### Task 4: RSS Pipeline Collector

**Files:**
- Create: `apps/api/src/agents/geo_news_agent/__init__.py`
- Create: `apps/api/src/agents/geo_news_agent/ingestion/rss_collector.py`

- [ ] **Step 1: Create package init**

Create `apps/api/src/agents/geo_news_agent/__init__.py`:

```python
```

- [ ] **Step 2: Create ingestion package init**

Create `apps/api/src/agents/geo_news_agent/ingestion/__init__.py`:

```python
```

- [ ] **Step 3: Write RSS collector**

Create `apps/api/src/agents/geo_news_agent/ingestion/rss_collector.py`:

```python
import asyncio
import logging
from datetime import UTC, datetime

import feedparser
import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.geo_news_config import geo_news_config
from src.services.geo_news import GeoNewsService

logger = logging.getLogger(__name__)

FETCH_TIMEOUT = 30
FETCH_DELAY = 1.0


async def collect_rss(db: AsyncSession) -> int:
    service = GeoNewsService(db)
    total_inserted = 0

    async with httpx.AsyncClient(timeout=FETCH_TIMEOUT, follow_redirects=True) as client:
        for feed_url in geo_news_config.rss_feeds:
            try:
                inserted = await _process_feed(client, feed_url, service)
                total_inserted += inserted
            except Exception:
                logger.warning("Failed to process RSS feed: %s", feed_url, exc_info=True)
            await asyncio.sleep(FETCH_DELAY)

    await db.commit()
    logger.info("RSS collection completed: %d new articles", total_inserted)
    return total_inserted


async def _process_feed(
    client: httpx.AsyncClient,
    feed_url: str,
    service: GeoNewsService,
) -> int:
    try:
        response = await client.get(feed_url)
        response.raise_for_status()
    except httpx.HTTPError:
        logger.warning("HTTP error fetching %s", feed_url, exc_info=True)
        return 0

    feed = feedparser.parse(response.text)
    source_name = feed.feed.get("title", feed_url)

    inserted = 0
    for entry in feed.entries[:20]:
        title = entry.get("title", "").strip()
        url = entry.get("link", "").strip()
        if not title or not url:
            continue

        content = entry.get("summary", "") or entry.get("description", "") or ""
        if isinstance(content, dict):
            content = content.get("value", "")
        content = str(content)[:2000]

        published_at = _parse_published(entry)

        added = await service.upsert_raw_article(
            pipeline="rss",
            source_name=source_name[:100],
            url=url,
            title=title,
            content=content or None,
            published_at=published_at,
        )
        if added:
            inserted += 1

    return inserted


def _parse_published(entry) -> datetime | None:
    for attr in ("published_parsed", "updated_parsed", "created_parsed"):
        parsed = getattr(entry, attr, None)
        if parsed:
            try:
                import time
                return datetime(*parsed[:6], tzinfo=UTC)
            except Exception:
                continue

    for attr in ("published", "updated"):
        val = entry.get(attr, "")
        if val:
            try:
                from dateutil.parser import parse as parse_dt
                return parse_dt(val)
            except Exception:
                continue

    return None
```

- [ ] **Step 4: Add feedparser dependency**

Add `feedparser` to `apps/api/pyproject.toml` dependencies:

```bash
cd apps/api && uv add feedparser python-dateutil
```

- [ ] **Step 5: Commit**

```bash
git add apps/api/src/agents/geo_news_agent/ apps/api/pyproject.toml apps/api/uv.lock
git commit -m "feat(geo-news): add RSS pipeline collector"
```

---

### Task 5: GNews Pipeline Collector

**Files:**
- Create: `apps/api/src/agents/geo_news_agent/ingestion/gnews_collector.py`

- [ ] **Step 1: Write GNews collector**

Create `apps/api/src/agents/geo_news_agent/ingestion/gnews_collector.py`:

```python
import asyncio
import logging
from datetime import UTC, datetime

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.geo_news_config import geo_news_config
from src.services.geo_news import GeoNewsService

logger = logging.getLogger(__name__)

GNEWS_API_URL = "https://newsapi.org/v2/everything"
FETCH_TIMEOUT = 30
QUERY_DELAY = 2.0


async def collect_gnews(db: AsyncSession) -> int:
    if not geo_news_config.gnews_api_key:
        logger.warning("GNEWS_API_KEY not configured, skipping GNews collection")
        return 0

    service = GeoNewsService(db)
    total_inserted = 0

    async with httpx.AsyncClient(timeout=FETCH_TIMEOUT, follow_redirects=True) as client:
        for query in geo_news_config.gnews_queries:
            try:
                inserted = await _search_query(client, query, service)
                total_inserted += inserted
            except Exception:
                logger.warning("Failed to fetch GNews for query: %s", query, exc_info=True)
            await asyncio.sleep(QUERY_DELAY)

    await db.commit()
    logger.info("GNews collection completed: %d new articles", total_inserted)
    return total_inserted


async def _search_query(
    client: httpx.AsyncClient,
    query: str,
    service: GeoNewsService,
) -> int:
    params = {
        "q": query,
        "apiKey": geo_news_config.gnews_api_key,
        "language": "en",
        "sortBy": "publishedAt",
        "pageSize": geo_news_config.gnews_max_articles_per_query,
    }

    try:
        response = await client.get(GNEWS_API_URL, params=params)
        response.raise_for_status()
        data = response.json()
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 429:
            logger.error("GNews API rate limit hit for query: %s", query)
        raise

    articles = data.get("articles", [])
    inserted = 0

    for article in articles:
        title = (article.get("title") or "").strip()
        url = (article.get("url") or "").strip()
        if not title or not url:
            continue

        source_info = article.get("source", {})
        source_name = source_info.get("name", "GNews")[:100]
        content = (article.get("description") or "")[:2000]

        published_at = _parse_gnews_date(article.get("publishedAt"))

        added = await service.upsert_raw_article(
            pipeline="gnews",
            source_name=source_name,
            url=url,
            title=title,
            content=content or None,
            published_at=published_at,
        )
        if added:
            inserted += 1

    return inserted


def _parse_gnews_date(date_str: str | None) -> datetime | None:
    if not date_str:
        return None
    try:
        from dateutil.parser import parse as parse_dt
        dt = parse_dt(date_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt
    except Exception:
        return None
```

- [ ] **Step 2: Commit**

```bash
git add apps/api/src/agents/geo_news_agent/ingestion/gnews_collector.py
git commit -m "feat(geo-news): add GNews pipeline collector"
```

---

### Task 6: GDELT Pipeline Collector

**Files:**
- Create: `apps/api/src/agents/geo_news_agent/ingestion/gdelt_collector.py`

- [ ] **Step 1: Write GDELT collector**

Create `apps/api/src/agents/geo_news_agent/ingestion/gdelt_collector.py`:

```python
import asyncio
import logging
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.geo_news_config import geo_news_config
from src.services.geo_news import GeoNewsService

logger = logging.getLogger(__name__)

GDELT_API_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
FETCH_TIMEOUT = 30
MAX_RETRIES = 3
RETRY_BASE_DELAY = 2.0


async def collect_gdelt(db: AsyncSession) -> int:
    service = GeoNewsService(db)
    total_inserted = 0

    async with httpx.AsyncClient(timeout=FETCH_TIMEOUT, follow_redirects=True) as client:
        for keyword in geo_news_config.gdelt_keywords:
            try:
                inserted = await _fetch_keyword(client, keyword, service)
                total_inserted += inserted
            except Exception:
                logger.warning("Failed to fetch GDELT for keyword: %s", keyword, exc_info=True)
            await asyncio.sleep(RETRY_BASE_DELAY)

    await db.commit()
    logger.info("GDELT collection completed: %d new articles", total_inserted)
    return total_inserted


async def _fetch_keyword(
    client: httpx.AsyncClient,
    keyword: str,
    service: GeoNewsService,
) -> int:
    query = f'{keyword} (sourcelang:english OR sourcelang:chinese)'
    params = {
        "query": query,
        "mode": "ArtList",
        "maxRecords": geo_news_config.gdelt_max_articles,
        "format": "json",
        "timespan": "7d",
    }

    for attempt in range(MAX_RETRIES):
        try:
            response = await client.get(GDELT_API_URL, params=params)
            response.raise_for_status()
            data = response.json()
            break
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                delay = RETRY_BASE_DELAY * (2 ** attempt)
                logger.warning("GDELT rate limited, retrying in %ds", delay)
                await asyncio.sleep(delay)
                continue
            raise
    else:
        logger.error("GDELT max retries exceeded for keyword: %s", keyword)
        return 0

    articles = data.get("articles", [])
    inserted = 0

    for article in articles:
        url = article.get("url", "").strip()
        title = article.get("title", "").strip()
        if not title or not url:
            continue

        source_name = article.get("source", "")[:100] or "GDELT"
        content = article.get("snippet", "")[:2000]

        published_at = _parse_gdelt_date(article.get("seendate"))

        added = await service.upsert_raw_article(
            pipeline="gdelt",
            source_name=source_name[:100],
            url=url,
            title=title,
            content=content or None,
            published_at=published_at,
        )
        if added:
            inserted += 1

    return inserted


def _parse_gdelt_date(date_str: str | None) -> datetime | None:
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str, "%Y%m%dT%H%M%S%z")
    except ValueError:
        try:
            from dateutil.parser import parse as parse_dt
            dt = parse_dt(date_str)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=UTC)
            return dt
        except Exception:
            return None
```

- [ ] **Step 2: Commit**

```bash
git add apps/api/src/agents/geo_news_agent/ingestion/gdelt_collector.py
git commit -m "feat(geo-news): add GDELT pipeline collector"
```

---

### Task 7: Dedup Utility

**Files:**
- Create: `apps/api/src/agents/geo_news_agent/dedup.py`

- [ ] **Step 1: Write Jaccard similarity dedup module**

Create `apps/api/src/agents/geo_news_agent/dedup.py`:

```python
from src.models.geo_event import RawGeoArticle


def _tokenize(text: str) -> set[str]:
    return set(text.lower().split())


def jaccard_similarity(a: str, b: str) -> float:
    tokens_a = _tokenize(a)
    tokens_b = _tokenize(b)
    if not tokens_a or not tokens_b:
        return 0.0
    intersection = tokens_a & tokens_b
    union = tokens_a | tokens_b
    return len(intersection) / len(union)


def deduplicate_articles(
    articles: list[RawGeoArticle],
    threshold: float = 0.7,
) -> list[RawGeoArticle]:
    if not articles:
        return articles

    seen: list[tuple[set[str], RawGeoArticle]] = []

    for article in articles:
        tokens = _tokenize(article.title)
        if not tokens:
            continue

        is_duplicate = False
        for existing_tokens, existing in seen:
            intersection = tokens & existing_tokens
            union = tokens | existing_tokens
            if union and len(intersection) / len(union) >= threshold:
                is_duplicate = True
                break

        if not is_duplicate:
            seen.append((tokens, article))

    return [article for _, article in seen]
```

- [ ] **Step 2: Commit**

```bash
git add apps/api/src/agents/geo_news_agent/dedup.py
git commit -m "feat(geo-news): add Jaccard similarity dedup utility"
```

---

### Task 8: LLM Event Extraction Pipeline

**Files:**
- Create: `apps/api/src/agents/geo_news_agent/extractor.py`

- [ ] **Step 1: Write the LLM event extractor**

Create `apps/api/src/agents/geo_news_agent/extractor.py`:

```python
import json
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from src.agents.geo_news_agent.dedup import deduplicate_articles
from src.core.llm import get_llm
from src.models.geo_event import RawGeoArticle
from src.models.geo_news_config import geo_news_config, GEO_CATEGORIES, GEO_REGIONS
from src.services.geo_news import GeoNewsService

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = f"""You are a geopolitical event analyst for an investment research platform. Your task is to analyze news articles and extract structured events that could impact financial markets.

For each article, provide a JSON analysis with these fields:
- index: article number (1-based)
- title: original title (preserve original language — Chinese stays Chinese, English stays English)
- summary: 1-2 sentence concise summary (preserve original language)
- impact_level: integer rating from investor perspective:
  * 1 = Low: routine diplomatic statements, minor political updates, daily news with no market signal → DISCARD
  * 2 = Medium: policy changes with measurable market impact, conflict escalation, trade tensions → normal display
  * 3 = High: war outbreaks, major sanctions, severe supply disruptions, crisis events → prominent display
- categories: list from [{", ".join(GEO_CATEGORIES)}]
- region: one of [{", ".join(GEO_REGIONS)}]
- time_sensitivity: "hours" (urgent, <1 day relevance), "days" (relevant for ~1 week), "weeks" (longer-term structural shift)

IMPORTANT RULES:
1. Evaluate purely from an investor perspective — does this affect stocks, oil, FX, commodities, bond yields?
2. Be conservative: most news is impact_level 1. Only assign 2 or 3 if there is clear market relevance.
3. Preserve the original article language in title and summary.
4. Return valid JSON only. No markdown, no explanation outside JSON.

Output format:
{{"events": [{{"index": 1, "title": "...", "summary": "...", "impact_level": 2, "categories": ["..."], "region": "...", "time_sensitivity": "days"}}]}}"""


async def extract_geo_events(db: AsyncSession) -> int:
    service = GeoNewsService(db)
    articles = await service.get_unprocessed_articles(limit=100)

    if not articles:
        logger.info("No unprocessed articles found")
        return 0

    articles = deduplicate_articles(articles, threshold=geo_news_config.dedup_threshold)
    logger.info("After dedup: %d articles to process", len(articles))

    total_inserted = 0
    processed_ids: list[int] = []

    batch_size = geo_news_config.batch_size
    for i in range(0, len(articles), batch_size):
        batch = articles[i : i + batch_size]
        try:
            events = await _extract_batch(batch)
            for event_data in events:
                if event_data.get("impact_level", 1) < 2:
                    continue

                raw_article = _find_article_by_index(batch, event_data.get("index"))
                sensitivity = event_data.get("time_sensitivity", "days")
                ttl_map = {
                    "hours": geo_news_config.sensitivity_hours_ttl,
                    "days": geo_news_config.sensitivity_days_ttl,
                    "weeks": geo_news_config.sensitivity_weeks_ttl,
                }
                ttl_hours = ttl_map.get(sensitivity, geo_news_config.sensitivity_days_ttl)
                expires_at = datetime.now(UTC) + timedelta(hours=ttl_hours)

                source = raw_article.pipeline if raw_article else "unknown"
                source_name = raw_article.source_name if raw_article else "Unknown"
                source_url = raw_article.url if raw_article else ""

                insert_data = {
                    "source": source,
                    "source_name": source_name,
                    "source_url": source_url,
                    "title": event_data.get("title", ""),
                    "summary": event_data.get("summary", ""),
                    "impact_level": event_data.get("impact_level", 2),
                    "categories": json.dumps(event_data.get("categories", [])),
                    "region": event_data.get("region"),
                    "event_date": raw_article.published_at if raw_article and raw_article.published_at else datetime.now(UTC),
                    "expires_at": expires_at,
                }

                result = await service.create_geo_event(insert_data)
                if result:
                    total_inserted += 1

        except Exception:
            logger.exception("Failed to extract batch starting at index %d", i)

        processed_ids.extend(a.id for a in batch)

    await service.mark_articles_processed(processed_ids)
    await db.commit()

    deactivated = await service.deactivate_expired_events()
    cleaned = await service.cleanup_processed_articles()
    await db.commit()

    logger.info(
        "Extraction completed: %d events inserted, %d deactivated, %d cleaned",
        total_inserted, deactivated, cleaned,
    )
    return total_inserted


async def _extract_batch(articles: list[RawGeoArticle]) -> list[dict]:
    from langchain_core.prompts import ChatPromptTemplate

    llm = get_llm(model=geo_news_config.llm_model, temperature=0.1, max_tokens=2000)

    articles_text = "\n\n".join(
        f"[Article {i+1}] Source: {a.source_name}\nTitle: {a.title}\n"
        + (f"Content: {(a.content or '')[:500]}" if a.content else "")
        for i, a in enumerate(articles)
    )

    user_prompt = f"Analyze these {len(articles)} news articles and extract structured geopolitical events:\n\n{articles_text}"

    prompt = ChatPromptTemplate.from_messages([
        ("system", SYSTEM_PROMPT),
        ("human", "{user_prompt}"),
    ])

    chain = prompt | llm
    response = await chain.ainvoke({"user_prompt": user_prompt})
    content = response.content

    return _parse_events_response(content, len(articles))


def _parse_events_response(content: str, expected_count: int) -> list[dict]:
    text = content.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        start = 1
        end = len(lines) - 1
        if lines[0].startswith("```json"):
            start = 1
        for i in range(len(lines) - 1, 0, -1):
            if lines[i].strip() == "```":
                end = i
                break
        text = "\n".join(lines[start:end]).strip()

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        logger.exception("Failed to parse LLM JSON response")
        return []

    events = parsed.get("events", [])
    if not events and isinstance(parsed, list):
        events = parsed

    return events


def _find_article_by_index(articles: list[RawGeoArticle], index: int | None) -> RawGeoArticle | None:
    if index is not None and 1 <= index <= len(articles):
        return articles[index - 1]
    return articles[0] if articles else None
```

- [ ] **Step 2: Commit**

```bash
git add apps/api/src/agents/geo_news_agent/extractor.py
git commit -m "feat(geo-news): add LLM event extraction pipeline"
```

---

### Task 9: Scheduler Jobs

**Files:**
- Create: `apps/api/src/agents/geo_news_agent/jobs.py`
- Modify: `apps/api/src/core/scheduler.py`

- [ ] **Step 1: Write scheduler job wrappers**

Create `apps/api/src/agents/geo_news_agent/jobs.py`:

```python
import asyncio
import logging

from src.core.job_logger import JobLogger

logger = logging.getLogger(__name__)


def ingest_rss_job():
    log_id = JobLogger.start("ingest_geo_rss", "GeoNews RSS collection")
    try:
        asyncio.run(_ingest_rss_async(log_id))
    except Exception as exc:
        JobLogger.fail(log_id, str(exc))
        raise


def ingest_gnews_job():
    log_id = JobLogger.start("ingest_geo_gnews", "GeoNews GNews collection")
    try:
        asyncio.run(_ingest_gnews_async(log_id))
    except Exception as exc:
        JobLogger.fail(log_id, str(exc))
        raise


def ingest_gdelt_job():
    log_id = JobLogger.start("ingest_geo_gdelt", "GeoNews GDELT collection")
    try:
        asyncio.run(_ingest_gdelt_async(log_id))
    except Exception as exc:
        JobLogger.fail(log_id, str(exc))
        raise


def extract_geo_events_job():
    log_id = JobLogger.start("extract_geo_events", "GeoNews LLM extraction")
    try:
        asyncio.run(_extract_async(log_id))
    except Exception as exc:
        JobLogger.fail(log_id, str(exc))
        raise


async def _ingest_rss_async(log_id: int | None):
    from src.core.database import async_session
    from src.agents.geo_news_agent.ingestion.rss_collector import collect_rss

    async with async_session() as session:
        count = await collect_rss(session)
        JobLogger.finish(log_id, records_affected=count, meta={"new_articles": count})


async def _ingest_gnews_async(log_id: int | None):
    from src.core.database import async_session
    from src.agents.geo_news_agent.ingestion.gnews_collector import collect_gnews

    async with async_session() as session:
        count = await collect_gnews(session)
        JobLogger.finish(log_id, records_affected=count, meta={"new_articles": count})


async def _ingest_gdelt_async(log_id: int | None):
    from src.core.database import async_session
    from src.agents.geo_news_agent.ingestion.gdelt_collector import collect_gdelt

    async with async_session() as session:
        count = await collect_gdelt(session)
        JobLogger.finish(log_id, records_affected=count, meta={"new_articles": count})


async def _extract_async(log_id: int | None):
    from src.core.database import async_session
    from src.agents.geo_news_agent.extractor import extract_geo_events

    async with async_session() as session:
        count = await extract_geo_events(session)
        JobLogger.finish(log_id, records_affected=count, meta={"events_inserted": count})
```

- [ ] **Step 2: Register scheduler jobs in scheduler.py**

Add to `apps/api/src/core/scheduler.py`, in the `register_public_market_jobs` function (or create a new function `register_geo_news_jobs`) and call it during app startup:

```python
from src.agents.geo_news_agent.jobs import (
    ingest_rss_job,
    ingest_gnews_job,
    ingest_gdelt_job,
    extract_geo_events_job,
)
from src.models.geo_news_config import geo_news_config


def register_geo_news_jobs() -> None:
    scheduler.add_job(
        ingest_rss_job,
        "interval",
        minutes=geo_news_config.rss_interval_minutes,
        id="ingest_geo_rss",
        replace_existing=True,
    )
    logger.info("Registered ingest_geo_rss job (interval: %d min)", geo_news_config.rss_interval_minutes)

    scheduler.add_job(
        ingest_gnews_job,
        "interval",
        hours=geo_news_config.gnews_interval_hours,
        id="ingest_geo_gnews",
        replace_existing=True,
    )
    logger.info("Registered ingest_geo_gnews job (interval: %d hours)", geo_news_config.gnews_interval_hours)

    scheduler.add_job(
        ingest_gdelt_job,
        "interval",
        hours=geo_news_config.gdelt_interval_hours,
        id="ingest_geo_gdelt",
        replace_existing=True,
    )
    logger.info("Registered ingest_geo_gdelt job (interval: %d hours)", geo_news_config.gdelt_interval_hours)

    scheduler.add_job(
        extract_geo_events_job,
        "interval",
        minutes=geo_news_config.extraction_interval_minutes,
        id="extract_geo_events",
        replace_existing=True,
    )
    logger.info("Registered extract_geo_events job (interval: %d min)", geo_news_config.extraction_interval_minutes)
```

Then add a call to `register_geo_news_jobs()` in the `lifespan` function in `main.py`.

- [ ] **Step 3: Commit**

```bash
git add apps/api/src/agents/geo_news_agent/jobs.py apps/api/src/core/scheduler.py apps/api/src/main.py
git commit -m "feat(geo-news): add scheduler jobs for RSS, GNews, GDELT, and extraction"
```

---

### Task 10: API Router

**Files:**
- Create: `apps/api/src/routers/geo_news.py`
- Modify: `apps/api/src/main.py`

- [ ] **Step 1: Write the API router**

Create `apps/api/src/routers/geo_news.py`:

```python
from datetime import UTC, datetime

from fastapi import APIRouter, Query

from src.dependencies import DBSession, GeoNewsServiceDep
from src.schemas.geo_news import GeoEventListResponse, GeoEventQueryParams

router = APIRouter(prefix="/geo-news", tags=["geo-news"])


@router.get("/events", response_model=GeoEventListResponse)
async def list_geo_events(
    service: GeoNewsServiceDep,
    impact_level: int | None = Query(None, ge=2, le=3, description="Filter by impact level (2 or 3)"),
    category: str | None = Query(None, description="Filter by category"),
    region: str | None = Query(None, description="Filter by region"),
    limit: int = Query(20, ge=1, le=50),
    offset: int = Query(0, ge=0),
):
    events, total, level3_count, level2_count, last_updated = await service.get_active_events(
        impact_level=impact_level,
        category=category,
        region=region,
        limit=limit,
        offset=offset,
    )
    return GeoEventListResponse(
        events=events,
        total=total,
        level3_count=level3_count,
        level2_count=level2_count,
        last_updated=last_updated,
    )
```

- [ ] **Step 2: Mount router in main.py**

Add to `apps/api/src/main.py` imports:

```python
from src.routers import geo_news
```

Add to router registrations:

```python
app.include_router(geo_news.router, prefix=settings.API_V1_PREFIX)
```

- [ ] **Step 3: Commit**

```bash
git add apps/api/src/routers/geo_news.py apps/api/src/main.py
git commit -m "feat(geo-news): add public API endpoint for geo events"
```

---

### Task 11: Admin Ingestion Endpoints

**Files:**
- Modify: `apps/api/src/routers/geo_news.py`

- [ ] **Step 1: Add admin ingestion endpoints to geo_news.py**

Append to `apps/api/src/routers/geo_news.py`:

```python
import asyncio
from src.core.database import async_session
from src.agents.geo_news_agent.ingestion.rss_collector import collect_rss
from src.agents.geo_news_agent.ingestion.gnews_collector import collect_gnews
from src.agents.geo_news_agent.ingestion.gdelt_collector import collect_gdelt
from src.agents.geo_news_agent.extractor import extract_geo_events


@router.post("/ingest/rss", status_code=200)
async def trigger_rss_ingestion():
    async with async_session() as session:
        count = await collect_rss(session)
    return {"status": "ok", "pipeline": "rss", "new_articles": count}


@router.post("/ingest/news", status_code=200)
async def trigger_gnews_ingestion():
    async with async_session() as session:
        count = await collect_gnews(session)
    return {"status": "ok", "pipeline": "gnews", "new_articles": count}


@router.post("/ingest/gdelt", status_code=200)
async def trigger_gdelt_ingestion():
    async with async_session() as session:
        count = await collect_gdelt(session)
    return {"status": "ok", "pipeline": "gdelt", "new_articles": count}


@router.post("/ingest/extract", status_code=200)
async def trigger_extraction():
    async with async_session() as session:
        count = await extract_geo_events(session)
    return {"status": "ok", "pipeline": "extract", "events_inserted": count}
```

- [ ] **Step 2: Commit**

```bash
git add apps/api/src/routers/geo_news.py
git commit -m "feat(geo-news): add admin ingestion trigger endpoints"
```

---

### Task 12: Frontend TypeScript Types

**Files:**
- Create: `apps/web/src/types/geo-news.ts`
- Modify: `apps/web/src/types/api.ts`

- [ ] **Step 1: Create geo-news TypeScript types**

Create `apps/web/src/types/geo-news.ts`:

```typescript
export type ImpactLevel = 2 | 3;

export interface GeoEvent {
  id: number;
  source_name: string;
  source_url: string;
  title: string;
  summary: string;
  impact_level: ImpactLevel;
  categories: string | null;
  region: string | null;
  event_date: string;
  is_active: boolean;
}

export interface GeoEventListResponse {
  events: GeoEvent[];
  total: number;
  level3_count: number;
  level2_count: number;
  last_updated: string | null;
}
```

- [ ] **Step 2: Commit**

```bash
git add apps/web/src/types/geo-news.ts
git commit -m "feat(geo-news): add frontend TypeScript types for geo news API"
```

---

### Task 13: i18n Strings

**Files:**
- Modify: `apps/web/src/messages/en.json` (path: `apps/web/messages/en.json`)
- Modify: `apps/web/src/messages/zh.json` (path: `apps/web/messages/zh.json`)

- [ ] **Step 1: Add English i18n strings**

Add to `apps/web/messages/en.json` under the `"board"` key, add a `"geoNews"` nested object:

```json
"geoNews": {
  "eyebrow": "Geopolitical events",
  "title": "Today's geopolitical landscape",
  "unavailable": "No geopolitical events available",
  "loading": "Loading events...",
  "sectionUnavailable": "Geopolitical events are temporarily unavailable.",
  "lastUpdated": "Last updated",
  "activeEvents": "active events",
  "highImpact": "High Impact",
  "mediumImpact": "Medium Impact",
  "allEvents": "All Events",
  "filterHighImpact": "High Impact Only",
  "source": "Source",
  "region": "Region",
  "categories": "Categories",
  "readOriginal": "Read original"
}
```

- [ ] **Step 2: Add Chinese i18n strings**

Add to `apps/web/messages/zh.json` under the `"board"` key:

```json
"geoNews": {
  "eyebrow": "地缘政治事件",
  "title": "今日地缘局势",
  "unavailable": "暂无地缘政治事件",
  "loading": "加载中...",
  "sectionUnavailable": "地缘政治事件暂不可用，请稍后重试。",
  "lastUpdated": "更新时间",
  "activeEvents": "条活跃事件",
  "highImpact": "高影响",
  "mediumImpact": "中等影响",
  "allEvents": "全部事件",
  "filterHighImpact": "仅高影响",
  "source": "来源",
  "region": "地区",
  "categories": "分类",
  "readOriginal": "查看原文"
}
```

- [ ] **Step 3: Commit**

```bash
git add apps/web/messages/en.json apps/web/messages/zh.json
git commit -m "feat(geo-news): add i18n strings for geo news section"
```

---

### Task 14: Frontend Components — GeoEventCard

**Files:**
- Create: `apps/web/src/components/geo-news/GeoEventCard.tsx`

- [ ] **Step 1: Write the GeoEventCard component**

Create `apps/web/src/components/geo-news/GeoEventCard.tsx`:

```tsx
"use client";

import { ChevronDown, ExternalLink } from "lucide-react";
import { useState } from "react";

import type { GeoEvent, ImpactLevel } from "@/types/geo-news";

const CATEGORY_LABELS: Record<string, string> = {
  military: "Military",
  sanctions: "Sanctions",
  energy: "Energy",
  trade_policy: "Trade Policy",
  geopolitics: "Geopolitics",
  macro_economy: "Macro Economy",
  supply_disruption: "Supply Disruption",
  regulation: "Regulation",
};

const REGION_LABELS: Record<string, string> = {
  middle_east: "Middle East",
  east_asia: "East Asia",
  europe: "Europe",
  americas: "Americas",
  africa: "Africa",
  global: "Global",
};

function parseCategories(categories: string | null): string[] {
  if (!categories) return [];
  try {
    const parsed = JSON.parse(categories);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function formatEventDate(dateStr: string, locale: string): string {
  const date = new Date(dateStr);
  if (Number.isNaN(date.getTime())) return dateStr;
  return new Intl.DateTimeFormat(locale, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function ImpactBadge({ level }: { level: ImpactLevel }) {
  if (level === 3) {
    return (
      <span className="inline-flex items-center rounded-full bg-terracotta px-2 py-0.5 text-[11px] font-medium uppercase tracking-[0.12em] text-white">
        High Impact
      </span>
    );
  }
  return (
    <span className="inline-flex items-center rounded-full bg-warm-sand px-2 py-0.5 text-[11px] font-medium text-charcoal-warm">
      Medium Impact
    </span>
  );
}

export default function GeoEventCard({
  event,
  locale,
}: Readonly<{
  event: GeoEvent;
  locale: string;
}>): React.JSX.Element {
  const [expanded, setExpanded] = useState(false);
  const isHighImpact = event.impact_level === 3;
  const cats = parseCategories(event.categories);

  return (
    <article
      className={`rounded-xl border bg-white transition-colors ${
        isHighImpact
          ? "border-l-[3px] border-l-terracotta border-t-0 border-r-0 border-b-0 border-divider"
          : "border-l-[2px] border-l-stone-gray border-t-0 border-r-0 border-b-0 border-divider"
      } ${isHighImpact ? "p-5" : "p-4"}`}
    >
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className="w-full text-left"
      >
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <ImpactBadge level={event.impact_level} />
              {event.region && (
                <span className="text-[11px] text-warm-gray">
                  {REGION_LABELS[event.region] || event.region}
                </span>
              )}
            </div>
            <h3
              className={`mt-2 leading-snug text-ink ${
                isHighImpact
                  ? "font-serif text-lg font-medium"
                  : "text-base font-medium"
              }`}
            >
              {event.title}
            </h3>
            <p className="mt-1 text-xs text-warm-gray">
              {event.source_name} · {formatEventDate(event.event_date, locale)}
            </p>
          </div>
          <ChevronDown
            className={`h-4 w-4 shrink-0 text-warm-gray transition-transform ${
              expanded ? "rotate-180" : ""
            }`}
          />
        </div>
      </button>

      {expanded && (
        <div className="mt-3 border-t border-divider pt-3 space-y-3">
          <p className="text-sm leading-relaxed text-charcoal/80">{event.summary}</p>

          {cats.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              {cats.map((cat) => (
                <span
                  key={cat}
                  className="rounded-full bg-warm-sand px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-charcoal-warm"
                >
                  {CATEGORY_LABELS[cat] || cat}
                </span>
              ))}
            </div>
          )}

          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3 text-xs text-warm-gray">
              {event.region && (
                <span>
                  <span className="font-medium text-charcoal/70">Region: </span>
                  {REGION_LABELS[event.region] || event.region}
                </span>
              )}
            </div>
            <a
              href={event.source_url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 text-xs font-medium text-terracotta hover:text-terracotta-dark"
            >
              Read original
              <ExternalLink className="h-3 w-3" />
            </a>
          </div>
        </div>
      )}
    </article>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add apps/web/src/components/geo-news/GeoEventCard.tsx
git commit -m "feat(geo-news): add GeoEventCard expandable component"
```

---

### Task 15: Frontend Components — GeoNewsFilter

**Files:**
- Create: `apps/web/src/components/geo-news/GeoNewsFilter.tsx`

- [ ] **Step 1: Write the filter toggle component**

Create `apps/web/src/components/geo-news/GeoNewsFilter.tsx`:

```tsx
"use client";

type FilterLevel = "all" | "high";

export default function GeoNewsFilter({
  level,
  onChange,
  allLabel,
  highLabel,
}: Readonly<{
  level: FilterLevel;
  onChange: (level: FilterLevel) => void;
  allLabel: string;
  highLabel: string;
}>): React.JSX.Element {
  return (
    <div className="flex gap-2">
      <button
        type="button"
        onClick={() => onChange("all")}
        className={`rounded-lg px-3 py-1.5 text-xs font-medium transition-colors ${
          level === "all"
            ? "bg-ink text-warm-silver"
            : "bg-warm-sand text-charcoal-warm hover:bg-warm-sand/80"
        }`}
      >
        {allLabel}
      </button>
      <button
        type="button"
        onClick={() => onChange("high")}
        className={`rounded-lg px-3 py-1.5 text-xs font-medium transition-colors ${
          level === "high"
            ? "bg-terracotta text-white"
            : "bg-warm-sand text-charcoal-warm hover:bg-warm-sand/80"
        }`}
      >
        {highLabel}
      </button>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add apps/web/src/components/geo-news/GeoNewsFilter.tsx
git commit -m "feat(geo-news): add GeoNewsFilter toggle component"
```

---

### Task 16: Frontend Components — GeoNewsSection

**Files:**
- Create: `apps/web/src/components/geo-news/GeoNewsSection.tsx`

- [ ] **Step 1: Write the main GeoNewsSection component**

Create `apps/web/src/components/geo-news/GeoNewsSection.tsx`:

```tsx
"use client";

import { AlertCircle, Loader2 } from "lucide-react";
import { useState } from "react";
import { useLocale, useTranslations } from "next-intl";

import { useApi } from "@/hooks/useApi";
import type { GeoEventListResponse } from "@/types/geo-news";
import GeoEventCard from "./GeoEventCard";
import GeoNewsFilter from "./GeoNewsFilter";

type FilterLevel = "all" | "high";

function formatDate(locale: string, value: string | null): string {
  if (!value) return "";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return new Intl.DateTimeFormat(locale, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(parsed);
}

export default function GeoNewsSection(): React.JSX.Element {
  const locale = useLocale();
  const t = useTranslations("board.geoNews");
  const [filter, setFilter] = useState<FilterLevel>("all");

  const impactParam = filter === "high" ? "3" : undefined;
  const events = useApi<GeoEventListResponse>(
    `/api/v1/geo-news/events?limit=20${impactParam ? `&impact_level=${impactParam}` : ""}`,
  );

  const data = events.data;

  if (events.loading) {
    return (
      <section className="rounded-2xl border border-divider bg-white p-5 shadow-sm md:p-6">
        <div className="flex min-h-48 flex-col items-center justify-center gap-3">
          <Loader2 className="h-8 w-8 animate-spin text-terracotta" />
          <p className="text-sm text-warm-gray">{t("loading")}</p>
        </div>
      </section>
    );
  }

  if (events.error || !data) {
    return (
      <section className="rounded-2xl border border-divider bg-white p-5 shadow-sm md:p-6">
        <div className="flex min-h-48 flex-col items-center justify-center gap-3">
          <AlertCircle className="h-8 w-8 text-accent-red" />
          <p className="text-sm text-warm-gray">{t("sectionUnavailable")}</p>
        </div>
      </section>
    );
  }

  return (
    <section className="rounded-2xl border border-divider bg-white p-5 shadow-sm md:p-6">
      <div className="mb-4 flex items-start justify-between gap-3">
        <div>
          <p className="text-xs font-medium uppercase tracking-[0.24em] text-warm-gray">
            {t("eyebrow")}
          </p>
          <h2 className="mt-1 text-2xl font-serif font-medium tracking-tight text-ink">
            {t("title")}
          </h2>
          <p className="mt-1 text-xs text-warm-gray">
            {t("lastUpdated")}: {formatDate(locale, data.last_updated)} · {data.total} {t("activeEvents")}
          </p>
        </div>
        <GeoNewsFilter
          level={filter}
          onChange={setFilter}
          allLabel={t("allEvents")}
          highLabel={t("filterHighImpact")}
        />
      </div>

      {data.events.length === 0 ? (
        <p className="py-8 text-center text-sm text-warm-gray">{t("unavailable")}</p>
      ) : (
        <div className="space-y-3">
          {data.events.map((event) => (
            <GeoEventCard key={event.id} event={event} locale={locale} />
          ))}
        </div>
      )}
    </section>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add apps/web/src/components/geo-news/GeoNewsSection.tsx
git commit -m "feat(geo-news): add GeoNewsSection main component"
```

---

### Task 17: Integrate GeoNewsSection into Board Page

**Files:**
- Modify: `apps/web/src/app/[locale]/board/page.tsx`

- [ ] **Step 1: Import and add GeoNewsSection to the board page**

Add the import at the top of `apps/web/src/app/[locale]/board/page.tsx`:

```tsx
import GeoNewsSection from "@/components/geo-news/GeoNewsSection";
```

Then insert `<GeoNewsSection />` between the Macro `MetricSection` and Assets `MetricSection`. In the JSX, find the `{snapshots.assets ? (` block and add `<GeoNewsSection />` right before it:

```tsx
{snapshots.macro ? (
  <MetricSection snapshot={snapshots.macro} copy={copy} locale={locale} />
) : macroSnapshot.loading ? (
  <SectionLoadingState title={copy.sections.macro} message={boardT("loading")} />
) : (
  <SectionUnavailableState
    title={copy.sections.macro}
    message={boardT("sectionUnavailable")}
    onRetry={macroSnapshot.refetch}
    retryLabel={boardT("retry")}
  />
)}

<GeoNewsSection />

{snapshots.assets ? (
  <MetricSection snapshot={snapshots.assets} copy={copy} locale={locale} />
) : ...}
```

- [ ] **Step 2: Commit**

```bash
git add apps/web/src/app/[locale]/board/page.tsx
git commit -m "feat(geo-news): integrate GeoNewsSection into board page between Macro and Assets"
```

---

### Task 18: Integration Test — Manual API Verification

**Files:** None (manual testing)

- [ ] **Step 1: Start the API server and verify the endpoint**

```bash
cd apps/api && uv run uvicorn src.main:app --reload --port 8000
```

Open http://localhost:8000/docs and find the `/api/v1/geo-news/events` endpoint. Verify it returns an empty list with the correct structure:

```json
{
  "events": [],
  "total": 0,
  "level3_count": 0,
  "level2_count": 0,
  "last_updated": null
}
```

- [ ] **Step 2: Test manual ingestion trigger**

```bash
curl -X POST http://localhost:8000/api/v1/geo-news/ingest/rss
curl -X POST http://localhost:8000/api/v1/geo-news/ingest/extract
```

Verify the response structure. Check the database for inserted records.

- [ ] **Step 3: Test the frontend board page**

```bash
cd apps/web && pnpm dev
```

Open http://localhost:3000/board and verify the GeoNewsSection renders (even with no data, should show the empty state).

- [ ] **Step 4: Run linting**

```bash
cd apps/api && uv run ruff check src/
cd apps/web && pnpm lint
```

Fix any linting errors.

- [ ] **Step 5: Commit any lint fixes**

```bash
git add -A && git commit -m "fix: address lint errors from geo-news integration"
```

---

## Self-Review Checklist

**Spec coverage:**
- [x] Data model (geo_events, raw_geo_articles) → Task 1
- [x] Three ingestion pipelines (RSS, GNews, GDELT) → Tasks 4, 5, 6
- [x] Unified extraction pipeline with LLM → Task 8
- [x] Impact level system (1=discard, 2=medium, 3=high) → Task 8 (LLM prompt) + Task 3 (query filters)
- [x] Category and region enums → Task 8 (LLM prompt) + Task 2 (schemas)
- [x] Event expiry mechanism → Task 8 (deactivate_expired_events)
- [x] Public API endpoint → Task 10
- [x] Admin trigger endpoints → Task 11
- [x] Frontend board rendering → Tasks 14-17
- [x] Visual hierarchy (Level 3 terracotta, Level 2 stone gray) → Task 14
- [x] Expandable detail cards → Task 14
- [x] Filter toggle (All / High Impact) → Task 15, Task 16
- [x] Scheduler jobs → Task 9
- [x] Configuration → Task 1 (GeoNewsConfig)
- [x] LLM prompt design → Task 8
- [x] Dedup → Task 7
- [x] i18n → Task 13

**Placeholder scan:** No TBDs, TODOs, or placeholder steps found.

**Type consistency:** All model field names, schema fields, and TypeScript types are consistent across tasks. The `categories` field uses JSON-serialized list throughout. The `impact_level` int type is consistent (2 or 3). API response field names match between Python schemas and TypeScript types.