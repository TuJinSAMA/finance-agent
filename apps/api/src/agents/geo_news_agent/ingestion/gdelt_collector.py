import asyncio
import logging
from datetime import UTC, datetime

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