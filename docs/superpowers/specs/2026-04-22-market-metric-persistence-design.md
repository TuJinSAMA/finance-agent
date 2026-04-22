# Market Metric Persistence Design

## Background

The current dashboard (public board) fetches market metrics from external sources (Yahoo Finance, AkShare) via scheduled jobs and caches them in Redis. Redis TTLs are 30-60 minutes, so only the latest snapshot is ever available. There is no historical data — the frontend cannot show trends over time.

## Goal

Persist all market metric data points to PostgreSQL so the frontend can query historical values and render trend charts for any metric (VIX, BTC, S&P 500, etc.).

## Requirements

1. Persist all metrics from the 3 collection groups: crypto (BTC), extended (VIX, US 10Y, DXY, 2Y-10Y Spread, Gold, WTI), equity (S&P 500, NASDAQ)
2. Store raw data points indefinitely — no aggregation or expiration policy
3. Provide a generic query API for the frontend to fetch metric history by name and time range
4. Minimal changes to the existing scheduler and snapshot pipeline

## Storage Design

### Table: `market_metric_values`

Single narrow-row table — one row per metric per timestamp:

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | BIGSERIAL | PK | Auto-increment ID |
| `as_of` | TIMESTAMPTZ | NOT NULL | Collection timestamp (UTC) |
| `group` | VARCHAR(10) | NOT NULL | Snapshot group: crypto, extended, equity |
| `name` | VARCHAR(30) | NOT NULL | Display name: VIX, BTC, S&P 500, etc. |
| `symbol` | VARCHAR(20) | NOT NULL | Data source symbol: ^VIX, BTC-USD, etc. |
| `value` | NUMERIC(18,4) | NULLABLE | Current value (NULL if unavailable) |
| `change_pct` | NUMERIC(8,4) | NULLABLE | Percent change from previous period |

**Constraints:**
- `UNIQUE(name, as_of)` — prevents duplicate entries for the same metric at the same timestamp
- `INDEX(name, as_of)` — core index for trend queries

### Data Volume Estimate

~10 metrics × ~50 samples/day = ~500 rows/day ≈ 180K rows/year. Well within PostgreSQL comfort zone.

## Write Flow

Extend the existing scheduler pipeline:

```
scheduler job
  → build_*_snapshot()         # existing: fetch from external sources
  → write_market_snapshot()    # existing: write to Redis cache
  → persist_group_metrics()    # NEW: write to PostgreSQL
```

### New Module: `src/services/market_metric_store.py`

- `async def persist_group_metrics(db: AsyncSession, snapshot: MarketGroupSnapshot) -> None`
  - Maps each `MarketMetric` in the snapshot to a `MarketMetricValue` row
  - Uses `INSERT ... ON CONFLICT (name, as_of) DO UPDATE SET value=EXCLUDED.value, change_pct=EXCLUDED.change_pct`
  - Batch insert via `execute(insert_stmt.values([...]).on_conflict_do_update(...))`
  - Handles `value=None` (unavailable metrics) naturally

### Scheduler Modifications

Each `refresh_*` function in `scheduler.py` will:
1. Get an async DB session from the session factory
2. Call `build_*_snapshot()` (existing)
3. Call `write_market_snapshot()` (existing, writes Redis)
4. Call `persist_group_metrics(db, snapshot)` (new, writes PostgreSQL)
5. Close the DB session

The `refresh_market_macro_snapshot` and `refresh_market_assets_snapshot` functions are composites — they do NOT need separate persistence because their metrics are already persisted by the underlying `refresh_extended_snapshot` / `refresh_crypto_snapshot` / `refresh_equity_snapshot` calls.

**DB session lifecycle:** The scheduler runs in a background thread via APScheduler. We need an async session factory (`async_session` from `src.core.database`) that the scheduler's async wrapper can use. The existing `asyncio.run()` pattern in `_make_self_adjusting_job` will be extended to also pass a DB session.

## Query API

### Endpoint: `GET /public/market-metrics/history`

**Request Parameters:**

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `name` | string (repeatable) | Yes | — | Metric names to query |
| `from` | ISO 8601 datetime | No | 7 days ago | Start of time range |
| `to` | ISO 8601 datetime | No | now | End of time range |

**Response Schema:**

```json
{
  "metrics": {
    "VIX": [
      {"as_of": "2025-04-22T14:30:00Z", "value": 19.45, "change_pct": -1.23},
      {"as_of": "2025-04-22T14:33:00Z", "value": 19.52, "change_pct": -0.87}
    ],
    "BTC": [
      {"as_of": "2025-04-22T14:28:00Z", "value": 87500.0, "change_pct": 2.15}
    ]
  }
}
```

**Service:** `src/services/market_metric_store.py`

- `async def query_metric_history(db, names, from_dt, to_dt) -> dict[str, list[MetricDataPoint]]`
  - Single query with `WHERE name IN (:names) AND as_of BETWEEN :from AND :to ORDER BY as_of`
  - Group results by metric name

**Router Addition:** Add a new route in `src/routers/public.py`

**Schema Addition:** Add `MetricDataPoint` and `MetricHistoryResponse` to `src/schemas/public_board.py`

## Historical Data Backfill (Optional)

`scripts/backfill_market_metrics.py`:
- Accept `--days N` flag (default 30)
- Use existing data sources (akshare daily data, yfinance) to fetch daily close prices
- Bulk insert historical daily data points into `market_metric_values`
- This provides initial trend data; ongoing data comes from the scheduler

This is a best-effort step — data availability depends on external sources.

## Implementation Checklist

1. Create `MarketMetricValue` model in `src/models/market_metric_value.py`
2. Re-export in `src/models/__init__.py`
3. Create Pydantic schemas: `MetricDataPoint`, `MetricHistoryResponse` in `src/schemas/public_board.py`
4. Create `src/services/market_metric_store.py` with `persist_group_metrics()` and `query_metric_history()`
5. Add dependency in `src/dependencies.py`
6. Add `GET /public/market-metrics/history` route in `src/routers/public.py`
7. Modify `src/core/scheduler.py` to call `persist_group_metrics` after Redis write
8. Run `pnpm db:revision "add market_metric_values table"` to create migration
9. Run `pnpm db:migrate` to apply migration
10. (Optional) Create `scripts/backfill_market_metrics.py` for historical data