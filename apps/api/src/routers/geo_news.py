from fastapi import APIRouter, Query

from src.core.database import async_session
from src.dependencies import GeoNewsServiceDep
from src.schemas.geo_news import GeoEventListResponse
from src.agents.geo_news_agent.ingestion.rss_collector import collect_rss
from src.agents.geo_news_agent.ingestion.gnews_collector import collect_gnews
from src.agents.geo_news_agent.ingestion.gdelt_collector import collect_gdelt
from src.agents.geo_news_agent.extractor import extract_geo_events

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