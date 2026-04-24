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
    logger.info("Rss collection completed: %d new articles", total_inserted)
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