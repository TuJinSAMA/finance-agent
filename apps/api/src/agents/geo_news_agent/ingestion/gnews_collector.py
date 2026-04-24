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