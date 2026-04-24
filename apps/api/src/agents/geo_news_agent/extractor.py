import json
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from src.agents.geo_news_agent.dedup import deduplicate_articles
from src.core.llm import aclose_llm, get_llm
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
{{{{"events": [{{{{"index": 1, "title": "...", "summary": "...", "impact_level": 2, "categories": ["..."], "region": "...", "time_sensitivity": "days"}}}}]}}}}"""


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
    try:
        response = await chain.ainvoke({"user_prompt": user_prompt})
        content = response.content
        return _parse_events_response(content, len(articles))
    finally:
        await aclose_llm(llm)


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
