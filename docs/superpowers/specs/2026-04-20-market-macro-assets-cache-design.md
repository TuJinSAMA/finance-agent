# Public Market Macro/Assets Cache Design

## 1. Goal

Refactor the public `/board` data delivery for macro and asset sections so the frontend no longer triggers live upstream fetches.

This change introduces:

1. Two dedicated public APIs instead of one combined board API:
   - `/api/v1/public/market-macro`
   - `/api/v1/public/market-assets`
2. Redis-backed snapshot caching for each dataset.
3. A separate scheduler process that refreshes snapshots every 15 minutes.
4. API routes that read from Redis only and never call upstream market data sources directly.

## 2. Scope

### In Scope

- Split the existing public board backend contract into two API surfaces:
  - Macro:
    - `VIX`
    - `US10Y`
    - `DXY`
    - `2Y-10Y Spread`
  - Assets:
    - `S&P 500`
    - `NASDAQ`
    - `Gold`
    - `WTI`
    - `BTC`
- Update `/board` to request these two new APIs in parallel.
- Add Redis snapshot storage and stale-data handling.
- Add a standalone scheduler entrypoint that refreshes both snapshots every 15 minutes.

### Out of Scope

- China and FX section changes:
  - `CSI 300`
  - `USD/CNY`
- Full upstream source migration to `akshare` in this phase.
- Database persistence for public market snapshots.
- Backward compatibility for `/api/v1/public/market-board`.

## 3. Requirements

### Functional Requirements

1. Frontend requests for macro/assets data must never directly trigger upstream fetches.
2. Public APIs must return the latest cached snapshot from Redis.
3. A standalone scheduler process must refresh both snapshot groups every 15 minutes.
4. Scheduler startup must attempt an immediate refresh so caches are populated quickly after deployment.
5. Macro and assets groups must refresh independently so one group can succeed even if the other fails.
6. Partial metric failures within a group must not invalidate the whole group response.

### Non-Functional Requirements

1. Reduce upstream request frequency to lower anti-bot/rate-limit risk.
2. Keep the design simple and compatible with the current FastAPI + Redis architecture.
3. Preserve degraded service via stale cache when refresh jobs fail temporarily.
4. Avoid introducing database schema changes for this phase.

## 4. API Design

### 4.1 New Endpoints

- `GET /api/v1/public/market-macro`
- `GET /api/v1/public/market-assets`

### 4.2 Response Shape

Both endpoints return a group-scoped snapshot model:

```json
{
  "group": "macro",
  "status": "ok",
  "as_of": "2026-04-20T10:30:00Z",
  "last_success_at": "2026-04-20T10:30:02Z",
  "source": "yfinance",
  "items": [
    {
      "name": "VIX",
      "symbol": "^VIX",
      "value": 18.42,
      "display": "18.42",
      "change_pct": -1.13,
      "status": "ok"
    }
  ]
}
```

### 4.3 Group Status Rules

- `ok`: snapshot age is within 15 minutes of the current time.
- `stale`: snapshot age is over 15 minutes but within 45 minutes.
- `empty`: no valid cached snapshot exists.

If a snapshot is `empty`, the API returns `503` instead of a success payload.

### 4.4 Metric Status Rules

Metric-level `status` remains independent from group-level `status`.

- `ok`: metric value available in the last refresh.
- `unavailable`: metric fetch failed during the last completed refresh.
- `stale`: optional runtime rewrite when serving stale cached content.

To keep semantics simple, the stored snapshot preserves original metric states from refresh time. When the API serves a stale group snapshot, it can rewrite non-empty metric statuses from `ok` to `stale` in the response.

## 5. Redis Design

### 5.1 Keys

- `public:market:macro:v1`
- `public:market:assets:v1`

### 5.2 Stored Payload

Each Redis key stores a JSON-serialized snapshot object.

Each payload contains:

- `group`
- `status`
- `as_of`
- `last_success_at`
- `source`
- `items`

### 5.3 TTL Strategy

- Refresh cadence: every 15 minutes
- Redis TTL: 45 minutes

Rationale:

- One or two failed refresh cycles should not immediately blank the frontend.
- The API can still return stale snapshots while the scheduler recovers.

## 6. Service Architecture

### 6.1 Service Split

The current `public_board.py` combined builder should be split into clearer group-level builders:

- `build_macro_snapshot()`
- `build_assets_snapshot()`

Each builder is responsible for:

1. Fetching the raw quotes for its group.
2. Computing derived metrics:
   - `2Y-10Y Spread` for macro
3. Normalizing items into API-ready metric objects.
4. Returning a snapshot payload ready for Redis persistence.

### 6.2 Redis Access Layer

Add a small cache helper dedicated to public market snapshots, for example:

- `write_market_snapshot(group, snapshot)`
- `read_market_snapshot(group)`
- `mark_snapshot_stale(snapshot, now)`

This keeps Redis serialization logic out of routers and out of fetch/build functions.

### 6.3 Router Responsibilities

The new public routers should only:

1. Read the relevant Redis key.
2. Deserialize and validate it.
3. Decide whether it is `ok`, `stale`, or unavailable.
4. Return the response or `503`.

Routers must not:

- fetch upstream market data
- build snapshots
- backfill missing cache on demand

## 7. Scheduler Process Design

### 7.1 Execution Model

Use a separate scheduler process, not the FastAPI server process.

The scheduler process should:

1. Initialize Redis.
2. Register two recurring jobs:
   - refresh macro snapshot
   - refresh assets snapshot
3. Run both refresh jobs once on startup.
4. Continue refreshing every 15 minutes.

### 7.2 Job Separation

Use two independent jobs instead of one combined job:

- `refresh_public_market_macro`
- `refresh_public_market_assets`

Rationale:

- one group can succeed while the other fails
- failures are easier to observe and retry
- source migration can evolve group-by-group later

### 7.3 Failure Handling

If one metric fails during a group refresh:

- write the metric as `unavailable`
- still write the rest of the successful snapshot

If the entire group refresh fails:

- do not overwrite the existing Redis key with empty data
- keep the last successful snapshot until TTL expiry
- log the failure clearly

## 8. Frontend Design

### 8.1 Data Fetching

`/board` should request both endpoints in parallel:

- `/api/v1/public/market-macro`
- `/api/v1/public/market-assets`

### 8.2 Rendering Rules

- Macro section renders from macro API only.
- Assets section renders from assets API only.
- One section failing must not hide the other section.

### 8.3 UX for Degraded Data

If a group is stale:

- still render it
- expose its stale state in the UI

If a group is unavailable:

- render an inline unavailable/error state for that section only

This is better than the current all-or-nothing board failure mode.

## 9. Data Source Strategy For This Phase

This phase focuses on delivery architecture, not full upstream replacement.

Initial implementation should preserve the current quote-building approach where practical, while moving all live upstream access into the scheduler process.

Planned later work can swap individual metrics or whole groups to `akshare` or mixed providers without changing the public API or frontend contract.

## 10. Files Likely To Change

Backend:

- `apps/api/src/services/public_board.py`
- `apps/api/src/schemas/public_board.py`
- `apps/api/src/routers/public.py`
- `apps/api/src/core/scheduler.py`
- `apps/api/src/core/redis.py`
- `apps/api/src/main.py`
- new standalone scheduler entrypoint under `apps/api/src/`

Frontend:

- `apps/web/src/types/api.ts`
- `apps/web/src/app/[locale]/board/page.tsx`

Tests:

- `apps/api/tests/test_public_board_service.py`
- new tests for Redis-backed route behavior and stale cache handling

## 11. Testing Strategy

### Backend

1. Snapshot builder tests:
   - macro snapshot with full data
   - assets snapshot with partial failures
   - spread calculation remains correct
2. Cache read tests:
   - fresh snapshot returns `ok`
   - stale snapshot returns `stale`
   - missing snapshot returns `503`
3. Scheduler job tests:
   - successful refresh writes Redis key
   - failed refresh preserves old key

### Frontend

1. `/board` handles both APIs succeeding.
2. `/board` handles macro failing but assets succeeding.
3. `/board` handles stale group rendering.

## 12. Risks And Mitigations

### Risk: scheduler is down

Impact:
- data stops refreshing

Mitigation:
- stale cache window of 45 minutes
- section-level stale indication
- explicit logging around refresh failures

### Risk: upstream source becomes unstable

Impact:
- individual metrics or whole groups may fail refresh

Mitigation:
- partial metric tolerance
- independent group jobs
- last successful snapshot retained

### Risk: Redis cache shape drifts over time

Impact:
- API deserialization errors after future changes

Mitigation:
- versioned Redis keys with `:v1`
- schema validation at read time

## 13. Acceptance Criteria

1. `/board` no longer depends on a single combined `/market-board` API.
2. Macro and assets data are fetched from two separate public APIs.
3. Public APIs do not call upstream market data sources during request handling.
4. A separate scheduler process refreshes both groups every 15 minutes.
5. Snapshots are stored in Redis with a 45-minute TTL.
6. Partial metric failures still produce a usable group payload.
7. Stale cached data is served when refreshes temporarily fail.
8. Missing or expired cache returns section-level unavailability instead of triggering live upstream fetch.
