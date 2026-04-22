# Geo News Module Design Spec

## Summary

Add a geopolitical news module to the public board page (`/board`) that surfaceqe investement-relevant events from 20+ global news sources via 3 pipelines (RSS, GNews, GDELT). Events are processed by LLM to extract structured data, rated by market impact level, and displayed with visual hierarchy on the board.

## Motivation

- Investment researchers spend 30+ minutes daily scanning multiple news sources to piece together a geopolitical picture
- No existing tool connects geopolitical events with market impact — news is news, quotes are quotes
- The board should let users understand today's situation in 30 seconds and decide whether deeper research is needed

## Architecture: Three Pipelines + Unified Extraction

```
RSS Pipeline ──┐
GNews Pipeline ─┼──► raw_geo_articles (temporary) ──► Event Extractor (LLM) ──► geo_events (Level 2/3 only)
GDELT Pipeline ─┘         ↑                               │
                           │                          Level 1 → discard
                      dedup & merge
```

Three ingestion pipelines run independently, each writing raw articles to a temporary table. A unified extraction pipeline reads unprocessed articles, deduplicates by title similarity, sends batches to LLM for structured extraction and impact rating, then writes Level 2/3 events to the final `geo_events` table. Level 1 events are discarded at ingestion time.

## Data Model

### Table: `geo_events` (final events displayed on board)

| Column | Type | Description |
|--------|------|-------------|
| id | Integer, PK, autoincrement | Primary key |
| source | String(20), NOT NULL | Pipeline identifier: "rss", "gnews", "gdelt" |
| source_name | String(100), NOT NULL | Original source name: "BBC", "Reuters", "GDELT", etc. |
| source_url | String(500), NOT NULL | Original article URL for traceability |
| title | Text, NOT NULL | Original title (preserved in original language) |
| summary | Text, NOT NULL | LLM-generated structured summary (preserved in original language) |
| impact_level | Integer, NOT NULL | 2 = medium (normal display), 3 = high (prominent display). Level 1 never stored |
| categories | String(500) | JSON-serialized list: `["military", "energy", "sanctions"]` |
| region | String(50), nullable | LLM-extracted region: "middle_east", "east_asia", etc. |
| event_date | DateTime(tz=True), NOT NULL | Original article publish time (UTC) |
| is_active | Boolean, default=True | Whether event is still timely |
| expires_at | DateTime(tz=True), nullable | Auto-expiry based on time_sensitivity |
| created_at | DateTime(tz=True), default=now() | Record creation time |

**Unique constraint**: `(source_url)` — same URL only stored once, regardless of which pipeline found it.

**Indexes**: `idx_geo_events_active_level_date` on `(is_active, impact_level DESC, event_date DESC)` for board queries.

### Table: `raw_geo_articles` (temporary, for extraction pipeline)

| Column | Type | Description |
|--------|------|-------------|
| id | Integer, PK, autoincrement | Primary key |
| pipeline | String(20), NOT NULL | "rss", "gnews", "gdelt" |
| source_name | String(100), NOT NULL | Source name |
| url | String(500), NOT NULL | Original URL |
| title | Text, NOT NULL | Original title |
| content | Text, nullable | Raw content/description |
| published_at | DateTime(tz=True), nullable | Original publish time |
| fetched_at | DateTime(tz=True), NOT NULL | When we scraped it |
| is_processed | Boolean, default=False | Whether extraction pipeline processed this |
| created_at | DateTime(tz=True), default=now() | Record creation time |

**Unique constraint**: `(pipeline, url)` — dedup at ingestion time per pipeline.

**Cleanup**: Raw articles older than 48 hours and marked `is_processed=True` are periodically purged.

## Impact Level System

Three levels, evaluated from an investor's perspective — does this event affect financial markets?

| Level | Name | Definition | Display |
|-------|------|------------|---------|
| 1 | Low | Routine diplomatic statements, minor political updates, daily news with no market signal | **Filtered out, never stored** |
| 2 | Medium | Policy changes with measurable market impact, conflict escalation, trade tensions | Normal display on board |
| 3 | High | War outbreaks, major sanctions, severe supply disruptions, crisis events | Prominent display with visual emphasis |

**Category enum**: `military`, `sanctions`, `energy`, `trade_policy`, `geopolitics`, `macro_economy`, `supply_disruption`, `regulation`

**Region enum**: `middle_east`, `east_asia`, `europe`, `americas`, `africa`, `global`

## Ingestion Pipelines

### RSS Pipeline (`/api/v1/geo-news/ingest/rss`)

- Scrapes 19 RSS feeds (12 English mainstream, 5 Chinese financial via RSSHub, 2 global market)
- Uses `feedparser` library to parse XML feeds
- Each feed: fetch latest articles not yet in `raw_geo_articles`
- Write to `raw_geo_articles` with `pipeline="rss"`
- Frequency: every 15-30 minutes
- No rate limit, but respect crawl-delay from RSS sources

### GNews Pipeline (`/api/v1/geo-news/ingest/news`)

- 5 search keyword groups, each returning up to 10 articles:
  1. `iran war military strike` → military actions
  2. `hormuz strait oil tanker` → energy/shipping
  3. `iran us sanctions nuclear` → sanctions/nuclear
  4. `iran israel military` → Israel-related
  5. `gulf oil supply disruption` → supply disruption
- Free tier: 100 requests/day, each call uses 5 API quota
- Max 12-20 calls/day to stay within limits
- Write to `raw_geo_articles` with `pipeline="gnews"`
- Frequency: every 2 hours

### GDELT Pipeline (`/api/v1/geo-news/ingest/gdelt`)

- Uses GDELT API article mode, filtering by keywords: iran, oil, military
- Returns article-level data (URL + context), not structured events
- LLM extraction happens in the unified pipeline
- Write to `raw_geo_articles` with `pipeline="gdelt"`
- Frequency: every 6 hours
- Exponential backoff on 429 errors (2s → 4s → 8s)

## Event Extraction Pipeline

### Flow

1. **Fetch unprocessed**: Query `raw_geo_articles WHERE is_processed=False`
2. **Deduplicate by title**: Jaccard similarity >= 0.7 → merge, keep earliest article
3. **Batch send to LLM**: 5-10 articles per batch, using Claude Haiku for cost efficiency
4. **LLM prompt** extracts structured JSON per event:
   ```json
   {
     "events": [
       {
         "index": 1,
         "title": "original title (preserve language)",
         "summary": "1-2 sentence summary (preserve language)",
         "impact_level": 2,
         "categories": ["military", "sanctions"],
         "region": "middle_east",
         "time_sensitivity": "hours"
       }
     ]
   }
   ```
5. **Filter**: `impact_level=1` → discard entirely (never written to `geo_events`)
6. **Write**: `impact_level=2 or 3` → insert into `geo_events`
7. **Mark processed**: Set `is_processed=True` on all processed `raw_geo_articles` regardless of outcome
8. **Set expiry**: Based on `time_sensitivity`:
   - `hours` → `expires_at = now + 24h`
   - `days` → `expires_at = now + 7d`
   - `weeks` → `expires_at = now + 30d`

### LLM Prompt Design Principles

- Evaluate from investor perspective: does this affect markets (stocks, oil, FX, commodities)?
- Explicit level definitions as above (Level 1 = routine → discard, Level 2 = measurable market impact, Level 3 = crisis/severe disruption)
- Must assign categories from the predefined enum
- Must assign region from the predefined enum
- Must determine time_sensitivity (hours/days/weeks)
- Preserve original article language in title and summary
- Model: `google/gemini-3.1-flash-lite-preview` (via OpenRouter) for cost efficiency

## API Endpoints

### Public (no auth required, used by /board)

**`GET /api/v1/geo-news/events`**

Query parameters:
- `impact_level` (optional): filter to `2` or `3`, default returns all (2+3)
- `category` (optional): filter by category
- `region` (optional): filter by region
- `limit` (optional): default 20, max 50
- `offset` (optional): pagination offset

Response:
```json
{
  "events": [
    {
      "id": 42,
      "source_name": "Reuters",
      "source_url": "https://...",
      "title": "...",
      "summary": "...",
      "impact_level": 3,
      "categories": ["military", "energy"],
      "region": "middle_east",
      "event_date": "2026-04-22T08:30:00Z",
      "is_active": true
    }
  ],
  "total": 15,
  "level3_count": 3,
  "level2_count": 12,
  "last_updated": "2026-04-22T10:00:00Z"
}
```

### Admin (auth required)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/geo-news/ingest/rss` | POST | Manually trigger RSS ingestion |
| `/api/v1/geo-news/ingest/news` | POST | Manually trigger GNews ingestion |
| `/api/v1/geo-news/ingest/gdelt` | POST | Manually trigger GDELT ingestion |
| `/api/v1/geo-news/ingest/extract` | POST | Manually trigger event extraction |

## Frontend: Board Page

### Placement

New `GeoNewsSection` is inserted **between** the existing Macro section and Assets section on `/board`. This positions geopolitical events as the bridge between macro conditions and asset movements.

### Display Rules

- Only show events where `is_active=True` AND `impact_level >= 2`
- Sort by `impact_level DESC, event_date DESC` (highest impact, newest first)
- **Level 3 events** (high impact):
  - Left border: terracotta (`#c96442`) vertical bar, 3px wide
  - Title: `font-serif`, `font-medium`, `text-ink`
  - Badge: terracotta background, white text, "高影响" / "High Impact"
  - Slightly larger card padding
- **Level 2 events** (medium impact):
  - Left border: stone gray (`#87867f`) vertical bar, 2px wide
  - Title: `font-sans`, `font-medium`, `text-ink`
  - Badge: warm sand background (`#e8e6dc`), charcoal text, "中等影响" / "Medium Impact"
- **Click to expand** (stays on page):
  - Summary text
  - Category pills (warm sand background, small caps)
  - Region label
  - Source name + clickable source URL (opens in new tab)
  - Event date formatted with locale

### Section Header

- Eyebrow: "Geopolitical events" / "地缘政治事件"
- Title: "Today's geopolitical landscape" / "今日地缘局势"
- Metadata line: "last updated" timestamp + active event count
- Filter: two toggle buttons "High Impact" / "All Events"

### Visual Style

Follows AlphaDesk DESIGN.md:
- Container: `bg-white`, `border border-divider`, `rounded-2xl`, `shadow-sm`
- Section spacing: consistent with existing MetricSection
- Card layout: vertical stack, each card with left-border accent
- Typography: serif for section heading, sans for card content
- Colors: exclusively warm-toned palette, no cool blues/grays

## Scheduling

Using existing APScheduler infrastructure. Register 4 new jobs:

| Job ID | Interval | Function |
|--------|----------|----------|
| `ingest_geo_rss` | 15 min | RSS pipeline ingestion |
| `ingest_geo_gnews` | 2 hours | GNews pipeline ingestion |
| `ingest_geo_gdelt` | 6 hours | GDELT pipeline ingestion |
| `extract_geo_events` | 10 min | Extraction pipeline (LLM processing) |

Market-hours awareness: ingestion runs regardless of market hours (geopolitical events are 24/7), but extraction could be deprioritized during non-trading hours.

## Configuration

New config section in `GeoNewsConfig` (separate from `ScreenerConfig`):

```python
@dataclass(frozen=True)
class GeoNewsConfig:
    # RSS sources
    rss_feeds: list[str]           # 19 RSS feed URLs
    
    # GNews
    gnews_api_key: str = ""       # From env
    gnews_queries: list[str]       # 5 search keyword groups
    
    # GDELT
    gdelt_keywords: list[str]     # Filter keywords
    gdelt_max_articles: int = 50  # Max articles per fetch
    
    # Extraction
    llm_model: str = "google/gemini-3.1-flash-lite-preview"
    batch_size: int = 10
    dedup_threshold: float = 0.7
    extraction_interval_minutes: int = 10
    
    # Cleanup
    raw_article_ttl_hours: int = 48
    
    # Expiry
    sensitivity_hours_ttl: int = 24
    sensitivity_days_ttl: int = 7
    sensitivity_weeks_ttl: int = 30
    
    # Rate limits
    rss_interval_minutes: int = 15
    gnews_interval_hours: int = 2
    gdelt_interval_hours: int = 6
```

## LLM Cost Estimate

- Model: Google Gemini 3.1 Flash Lite Preview via OpenRouter
- Per batch: ~2000 input tokens, ~500 output tokens
- Daily volume: ~200-500 raw articles → 20-50 LLM calls
- Daily cost: < $0.01

## Key Decisions

1. **Language**: Preserve original article language (Chinese source → Chinese, English → English)
2. **Display**: Public board only, no auth required
3. **Filtering**: Level 1 discarded at ingestion time, never stored
4. **Interaction**: Click to expand details inline, with original source link for traceability
5. **Model**: `stock_events` and `geo_events` are completely independent tables
6. **Placement**: Between Macro and Assets sections on /board