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
    from src.core.database import job_async_session
    from src.agents.geo_news_agent.ingestion.rss_collector import collect_rss

    async with job_async_session() as session:
        count = await collect_rss(session)
        JobLogger.finish(log_id, records_affected=count, meta={"new_articles": count})


async def _ingest_gnews_async(log_id: int | None):
    from src.core.database import job_async_session
    from src.agents.geo_news_agent.ingestion.gnews_collector import collect_gnews

    async with job_async_session() as session:
        count = await collect_gnews(session)
        JobLogger.finish(log_id, records_affected=count, meta={"new_articles": count})


async def _ingest_gdelt_async(log_id: int | None):
    from src.core.database import job_async_session
    from src.agents.geo_news_agent.ingestion.gdelt_collector import collect_gdelt

    async with job_async_session() as session:
        count = await collect_gdelt(session)
        JobLogger.finish(log_id, records_affected=count, meta={"new_articles": count})


async def _extract_async(log_id: int | None):
    from src.core.database import job_async_session
    from src.agents.geo_news_agent.extractor import extract_geo_events

    async with job_async_session() as session:
        count = await extract_geo_events(session)
        JobLogger.finish(log_id, records_affected=count, meta={"events_inserted": count})