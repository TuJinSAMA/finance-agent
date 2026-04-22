# Scheduler Market-Hours-Aware Refresh Design

## 1. Goal

Replace the current flat 15-minute interval refresh strategy with a market-hours-aware approach. Different asset classes have vastly different trading windows — refreshing S&P 500 at 2-minute intervals on a Saturday is wasteful, while BTC should update frequently even overnight. Each refresh job should self-adjust its next interval based on the current market session.

## 2. Background

### 2.1 Current Architecture

The scheduler runs two APScheduler `interval` jobs:

- `refresh_public_market_macro` — every 15 min, fetches VIX / US10Y / DXY / US2Y → builds 4 metrics (including 2Y-10Y Spread)
- `refresh_public_market_assets` — every 15 min, fetches SPX / NASDAQ / GOLD / WTI / BTC → builds 5 metrics

Both jobs use a fixed interval registered at startup, regardless of whether the underlying markets are open.

### 2.2 The Problem

All 9 metrics share the same 15-minute cadence, but their trading hours are radically different:

- **BTC** trades 24/7/365 — always worth refreshing
- **Gold & WTI futures** have near-24h electronic sessions — some value overnight
- **US Treasuries, DXY, VIX** trade primarily during US hours
- **S&P 500 & NASDAQ** only trade meaningfully 9:30–16:00 ET (6.5 h/day)

A fixed interval either wastes upstream API calls during off-hours, or is too slow during peak trading.

### 2.3 Constraint: Single Process, Dynamic Intervals

The scheduler runs as a standalone process. APScheduler `interval` triggers are set their period at registration time. To change frequency dynamically, we use **`scheduler.reschedule_job()`** — each job, after executing, computes the appropriate next interval based on the current time and reschedules itself.

## 3. Asset Classification

### 3.1 Three Trading-Session Groups

| Group | Metrics | Rationale |
|-------|---------|-----------|
| **crypto** | BTC | 24/7 market, never closes |
| **extended** | VIX, DXY, US10Y, US2Y (→Spread), Gold, WTI | Near-24h electronic sessions, but thin liquidity overnight & weekends |
| **equity** | S&P 500, NASDAQ | Only meaningful during US equity session (9:30–16:00 ET); pre/post-market has some value |

### 3.2 Why Not Keep the Current Macro/Assets Split?

The current split (macro = VIX/US10Y/DXY/Spread, assets = SPX/NASDAQ/Gold/WTI/BTC) groups by **display category**, not by **trading rhythm**. Gold and BTC are in the same "assets" group but have completely different trading windows. To optimize refresh frequency, we must split by trading rhythm.

This means the scheduler will have **3 refresh jobs** instead of 2, and the cache layer will store **3 Redis keys** instead of 2. The API and frontend will still present data as "macro" and "assets" sections — the mapping from internal cache groups to display groups happens at read time.

## 4. Session Detection

### 4.1 Timezone

All session calculations use **US Eastern Time (America/New_York)**, which is the canonical timezone for all markets involved.

### 4.2 Session Definitions

```
Session         | ET Time Range          | Days
--------------- | ---------------------- | ------
us_regular      | 09:30 – 16:00          | Mon–Fri
us_extended     | 04:00 – 09:30 OR       | Mon–Fri
                | 16:00 – 20:00          |
overnight       | 20:00 – 04:00 next day | Mon–Fri
weekend         | all day                | Sat–Sun
```

### 4.3 Session Detection Function

```python
from datetime import datetime
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")

def current_session() -> str:
    """Return the current market session as one of:
    'us_regular', 'us_extended', 'overnight', 'weekend'
    """
    now_et = datetime.now(ET)
    if now_et.weekday() >= 5:
        return "weekend"

    t = now_et.hour * 60 + now_et.minute
    if 9 * 60 + 30 <= t < 16 * 60:
        return "us_regular"
    if 4 * 60 <= t < 9 * 60 + 30 or 16 * 60 <= t < 20 * 60:
        return "us_extended"
    return "overnight"
```

## 5. Interval Strategy

### 5.1 Per-Group, Per-Session Intervals (minutes)

| Session | crypto | extended | equity |
|---------|--------|----------|--------|
| us_regular | 2 | 3 | 3 |
| us_extended | 5 | 10 | 15 |
| overnight | 10 | 30 | 60 |
| weekend | 10 | 60 | skip |

### 5.2 Design Rationale

- **crypto / us_regular (2 min)**: BTC is the most volatile during US hours when institutional traders are active.
- **extended / us_regular (3 min)**: Treasuries, VIX, DXY, and commodity futures all see peak volume and spreads during US hours.
- **equity / us_regular (3 min)**: 6.5-hour window is the only time indices have real quotes; refresh aggressively.
- **equity / weekend (skip)**: Zero volume, zero price change. The job simply returns without fetching or rescheduling, letting the next scheduled tick handle it.
- **All overnight/weekend intervals are deliberately conservative** to reduce unnecessary API calls when price changes are minimal.

### 5.3 Equity "Skip" Semantics

When the equity job runs during a weekend, it should:

1. NOT fetch any data.
2. NOT reschedule itself (keep the current 60-min interval ticking).
3. Log at DEBUG level that it skipped due to weekend.

This ensures the job is still alive and will naturally resume when Monday arrives. The 60-min weekend tick is harmless — it just checks and skips.

## 6. Self-Adjusting Interval Mechanism

### 6.1 Core Pattern

Each refresh job follows this pattern:

```python
def refresh_crypto() -> None:
    asyncio.run(_refresh_crypto_snapshot())

    next_minutes = CRYPTO_INTERVAL_MAP[current_session()]
    scheduler.reschedule_job(
        "refresh_crypto",
        trigger="interval",
        minutes=next_minutes,
    )
```

After every execution, the job computes its own next interval and calls `reschedule_job`. This means:

- The interval **adapts at session boundaries** (e.g., when 09:30 ET arrives, the next tick after that will reschedule to the faster `us_regular` interval).
- There is at most **one interval-period of lag** at transition boundaries — acceptable for this use case.
- No external coordinator or cron daemon is needed.

### 6.2 Reschedule Timing Diagram

```
Timeline (ET)    Action                         Interval
─────────────────────────────────────────────────────────
08:00            job runs (us_extended)         → reschedule to 10 min
08:10            job runs (us_extended)         → reschedule to 10 min
09:30            job runs (us_regular)          → reschedule to 3 min
09:33            job runs (us_regular)          → reschedule to 3 min
...
16:00            job runs (us_extended)         → reschedule to 10 min
20:00            job runs (overnight)           → reschedule to 30 min
```

The transition from `us_extended` to `us_regular` happens one tick after 09:30 — the job that fires at ~09:30 will detect the session change and reschedule.

## 7. Service Layer Changes

### 7.1 New Snapshot Builders

Three new builders replace the current two:

```python
# src/services/public_board.py (additions)

async def build_crypto_snapshot(as_of: datetime) -> MarketGroupSnapshot:
    """BTC only — 24/7 market."""
    btc_quote = await _safe_fetch_quote(YFINANCE_SYMBOLS["BTC"])
    items = [_metric_from_quote("BTC", YFINANCE_SYMBOLS["BTC"], btc_quote, _format_number)]
    return MarketGroupSnapshot(group="crypto", status="ok", as_of=as_of,
                               last_success_at=as_of, source=SOURCE_NAME, items=items)


async def build_extended_snapshot(as_of: datetime) -> MarketGroupSnapshot:
    """VIX, DXY, US10Y, US2Y, Gold, WTI — near-24h markets."""
    quotes = await asyncio.gather(
        _safe_fetch_quote(YFINANCE_SYMBOLS["VIX"]),
        _safe_fetch_quote(YFINANCE_SYMBOLS["US10Y"]),
        _safe_fetch_quote(YFINANCE_SYMBOLS["DXY"]),
        _safe_fetch_quote(US2Y_SYMBOL),
        _safe_fetch_quote(YFINANCE_SYMBOLS["GOLD"]),
        _safe_fetch_quote(YFINANCE_SYMBOLS["WTI"]),
    )
    vix_q, us10y_q, dxy_q, us2y_q, gold_q, wti_q = quotes
    items = [
        _metric_from_quote("VIX", YFINANCE_SYMBOLS["VIX"], vix_q, _format_number),
        _metric_from_quote("US 10Y", YFINANCE_SYMBOLS["US10Y"], us10y_q, _format_percent),
        _metric_from_quote("DXY", YFINANCE_SYMBOLS["DXY"], dxy_q, _format_number),
        _build_spread_metric(us2y_q, us10y_q),
        _metric_from_quote("Gold", YFINANCE_SYMBOLS["GOLD"], gold_q, _format_number),
        _metric_from_quote("WTI", YFINANCE_SYMBOLS["WTI"], wti_q, _format_number),
    ]
    return MarketGroupSnapshot(group="extended", status="ok", as_of=as_of,
                               last_success_at=as_of, source=SOURCE_NAME, items=items)


async def build_equity_snapshot(as_of: datetime) -> MarketGroupSnapshot:
    """S&P 500, NASDAQ — US equity session only."""
    quotes = await asyncio.gather(
        _safe_fetch_quote(YFINANCE_SYMBOLS["SPX"]),
        _safe_fetch_quote(YFINANCE_SYMBOLS["NASDAQ"]),
    )
    spx_q, nasdaq_q = quotes
    items = [
        _metric_from_quote("S&P 500", YFINANCE_SYMBOLS["SPX"], spx_q, _format_number),
        _metric_from_quote("NASDAQ", YFINANCE_SYMBOLS["NASDAQ"], nasdaq_q, _format_number),
    ]
    return MarketGroupSnapshot(group="equity", status="ok", as_of=as_of,
                               last_success_at=as_of, source=SOURCE_NAME, items=items)
```

### 7.2 Backward Compatibility

The existing `build_macro_snapshot` and `build_assets_snapshot` remain for the startup bootstrap and as convenience wrappers. They will be reimplemented as composites:

```python
async def build_macro_snapshot(as_of: datetime) -> MarketGroupSnapshot:
    """Compose macro display group from extended group metrics."""
    extended = await build_extended_snapshot(as_of)
    macro_items = [item for item in extended.items if item.name in ("VIX", "US 10Y", "DXY", "2Y-10Y Spread")]
    return extended.model_copy(update={"group": "macro", "items": macro_items})


async def build_assets_snapshot(as_of: datetime) -> MarketGroupSnapshot:
    """Compose assets display group from crypto + equity + extended group metrics."""
    crypto, equity, extended = await asyncio.gather(
        build_crypto_snapshot(as_of),
        build_equity_snapshot(as_of),
        build_extended_snapshot(as_of),
    )
    asset_items = [item for item in extended.items if item.name in ("Gold", "WTI")]
    asset_items += crypto.items + equity.items
    return MarketGroupSnapshot(group="assets", status="ok", as_of=as_of,
                               last_success_at=as_of, source=SOURCE_NAME, items=asset_items)
```

> **Note**: `build_macro_snapshot` and `build_assets_snapshot` are only used during startup and for the API read path. The scheduler's recurring jobs will use the three new builders directly. The composite wrappers exist so the startup bootstrap can populate both display groups from one pass.

## 8. Cache Layer Changes

### 8.1 New Redis Keys

Add two new keys alongside the existing two:

| Key | Group | Contents |
|-----|-------|----------|
| `public:market:macro:v1` | macro (display) | VIX, US10Y, DXY, Spread |
| `public:market:assets:v1` | assets (display) | SPX, NASDAQ, Gold, WTI, BTC |
| `public:market:crypto:v1` | crypto (trading) | BTC |
| `public:market:extended:v1` | extended (trading) | VIX, DXY, US10Y, US2Y, Gold, WTI |
| `public:market:equity:v1` | equity (trading) | SPX, NASDAQ |

### 8.2 TTL Strategy

Current TTL is 45 minutes. With faster refresh intervals (as low as 2 min), we should adjust:

| Group | TTL | Rationale |
|-------|-----|-----------|
| crypto | 30 min | 2-min refresh means even 3 failures leave 24 min of data |
| extended | 60 min | Up to 30-min intervals; need larger buffer |
| equity | 60 min | Weekend skip means equity data can be 48+ h old on Monday; 60-min TTL handles the weekend case when the API serves stale data |

### 8.3 SnapshotGroup Schema Update

`SnapshotGroup` in `schemas/public_board.py` currently is:

```python
SnapshotGroup = Literal["macro", "assets"]
```

It needs to become:

```python
SnapshotGroup = Literal["macro", "assets", "crypto", "extended", "equity"]
```

### 8.4 Read Path: Mapping Cache Groups to Display Groups

The API routes still serve `/market-macro` and `/market-assets`. The read path composes from the new keys:

- **`/market-macro`**: Read `public:market:extended:v1`, filter to VIX/US10Y/DXY/Spread, rewrite `group` to `"macro"`.
- **`/market-assets`**: Read `public:market:crypto:v1` + `public:market:equity:v1` + `public:market:extended:v1` (for Gold/WTI), merge items, rewrite `group` to `"assets"`.

This keeps the API contract identical. The frontend sees no change.

## 9. Scheduler Implementation

### 9.1 Session & Interval Configuration

```python
# src/core/scheduler.py (new constants)

from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")

SESSION_ORDER = ["us_regular", "us_extended", "overnight", "weekend"]

INTERVAL_MAP: dict[str, dict[str, int]] = {
    #           session       → minutes
    "crypto": {
        "us_regular": 2,
        "us_extended": 5,
        "overnight": 10,
        "weekend": 10,
    },
    "extended": {
        "us_regular": 3,
        "us_extended": 10,
        "overnight": 30,
        "weekend": 60,
    },
    "equity": {
        "us_regular": 3,
        "us_extended": 15,
        "overnight": 60,
        "weekend": 60,  # job will skip, but must keep ticking
    },
}
```

### 9.2 Session Detection

```python
def _current_session() -> str:
    now_et = datetime.now(ET)
    if now_et.weekday() >= 5:
        return "weekend"
    t = now_et.hour * 60 + now_et.minute
    if 9 * 60 + 30 <= t < 16 * 60:
        return "us_regular"
    if 4 * 60 <= t < 9 * 60 + 30 or 16 * 60 <= t < 20 * 60:
        return "us_extended"
    return "overnight"
```

### 9.3 Self-Adjusting Job Pattern

```python
def _make_self_adjusting_job(group: str, async_builder_coro) -> Callable[[], None]:
    """Create a self-adjusting APScheduler job wrapper.

    After each execution:
    1. Runs the async snapshot builder and writes to Redis.
    2. Detects the current market session.
    3. Calls `scheduler.reschedule_job()` with the appropriate interval.
    """
    job_id = f"refresh_{group}"

    def job() -> None:
        session = _current_session()

        # Weekend skip for equity group
        if group == "equity" and session == "weekend":
            logger.debug("Skipping equity refresh — weekend")
            return  # do NOT reschedule; next tick will check again

        asyncio.run(async_builder_coro())

        next_minutes = INTERVAL_MAP[group][session]
        scheduler.reschedule_job(
            job_id,
            trigger="interval",
            minutes=next_minutes,
        )
        logger.info("Refreshed %s snapshot, next run in %d min (session=%s)",
                     group, next_minutes, session)

    return job
```

### 9.4 Job Registration

```python
def register_public_market_jobs() -> None:
    """Register public market refresh jobs (idempotent)."""

    # Initial intervals — will self-adjust after first execution
    INITIAL_INTERVALS = {"crypto": 5, "extended": 10, "equity": 15}

    for group, minutes in INITIAL_INTERVALS.items():
        job_id = f"refresh_{group}"
        builder = _GROUP_BUILDERS[group]  # mapping from group name to async builder
        wrapper = _make_self_adjusting_job(group, builder)
        scheduler.add_job(
            wrapper,
            "interval",
            minutes=minutes,
            id=job_id,
            replace_existing=True,
        )
        logger.info("Registered %s job (initial interval: %d min)", job_id, minutes)
```

### 9.5 Startup Bootstrap

On startup, the scheduler should immediately refresh all three groups to populate the cache:

```python
async def _run_startup_refreshes() -> None:
    await refresh_crypto_snapshot()
    await refresh_extended_snapshot()
    await refresh_equity_snapshot()
```

The startup refresh also triggers the first `reschedule_job`, establishing the correct interval based on the session at startup time.

## 10. Stale Data Handling

### 10.1 FRESH_WINDOW and STALE_WINDOW

The current cache classification uses fixed windows (15 min fresh, 45 min stale). With variable refresh intervals, these should become per-group:

| Group | FRESH_WINDOW | STALE_WINDOW |
|-------|-------------|-------------|
| crypto | 5 min | 30 min |
| extended | 15 min | 60 min |
| equity | 15 min | 60 min |

### 10.2 API Route Changes

The route handler for `/market-macro` and `/market-assets` needs to:

1. Read the underlying cache keys (crypto, extended, equity).
2. Use the appropriate FRESH_WINDOW/STALE_WINDOW per group.
3. Merge and re-label as macro/assets.

## 11. US Market Holiday Handling (Future)

This design does not handle US market holidays (e.g., July 4th, Christmas). On holidays, the `us_regular` session will still be detected, but equity and extended markets will be closed.

**Proposed future enhancement**: Maintain a small set of known US market holidays. On a holiday, treat the session as `weekend` for equity and extended groups.

For the MVP, this is acceptable — on holidays, the upstream sources will simply return the previous close, and the data will still be served correctly (just with unnecessary refreshes).

## 12. Files To Change

| File | Change |
|------|--------|
| `apps/api/src/core/scheduler.py` | Add session detection, interval maps, self-adjusting job pattern; replace 2 jobs with 3 |
| `apps/api/src/services/public_board.py` | Add `build_crypto_snapshot`, `build_extended_snapshot`, `build_equity_snapshot`; update `build_macro_snapshot`/`build_assets_snapshot` as composites |
| `apps/api/src/schemas/public_board.py` | Extend `SnapshotGroup` to include `"crypto"`, `"extended"`, `"equity"` |
| `apps/api/src/services/public_market_cache.py` | Add per-group TTL and FRESH/STALE windows; add cache keys for new groups |
| `apps/api/src/routers/public.py` | Update read path to compose macro/assets from new cache groups |
| `apps/api/src/run_scheduler.py` | Update startup bootstrap to refresh 3 groups |
| `apps/api/tests/test_public_board_service.py` | Add tests for new builders; update existing composite tests |
| `apps/api/tests/test_public_market_cache.py` | Add tests for per-group TTL/classification |

## 13. Migration Strategy

### Phase 1: Add New Builders & Cache Keys (Non-Breaking)

- Add the three new builders alongside the existing two.
- Add new Redis keys without removing old ones.
- Extend `SnapshotGroup` type.
- Both old and new keys coexist.

### Phase 2: Switch Scheduler to New Jobs (Swap)

- Replace the two old jobs with three self-adjusting jobs.
- Startup bootstrap writes both old keys (for API compat) and new keys.
- API routes still read from old keys.

### Phase 3: Switch API Routes to New Keys (Cut Over)

- API routes read from new keys and compose macro/assets.
- Stop writing old keys.
- Remove old `build_macro_snapshot` / `build_assets_snapshot` if no longer needed.

This phased approach ensures no downtime and easy rollback at each step.

## 14. Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| `reschedule_job` race condition | Job might miss a tick during reschedule | APScheduler handles this atomically; `coalesce=True` and `max_instances=1` prevent double-fires |
| Session detection at boundary (09:29:59 vs 09:30:00) | One-tick delay at session transition | Acceptable — worst case 60 seconds of wrong interval |
| Upstream API rate limiting | More frequent calls during US hours could trigger limits | `_FETCH_SEMAPHORE` already limits concurrency; retry with backoff handles transient blocks |
| DST transition (ET ←→ EDT) | `zoneinfo` handles this automatically | No manual offset needed; `America/New_York` is DST-aware |
| Stale data on Monday morning after weekend skip | Equity data could be 48h old | 60-min TTL is sufficient for stale-serving; startup bootstrap refreshes immediately on deploy |

## 15. Acceptance Criteria

1. Three scheduler jobs exist: `refresh_crypto`, `refresh_extended`, `refresh_equity`.
2. Each job self-adjusts its interval via `reschedule_job` after every execution.
3. Intervals follow the strategy defined in §5.1.
4. Equity job skips execution on weekends.
5. API routes `/market-macro` and `/market-assets` return identical response shapes as before.
6. Cache keys for crypto, extended, and equity groups are written and readable.
7. Per-group TTL and FRESH/STALE windows are applied correctly.
8. Existing tests pass; new tests cover session detection, interval adjustment, and skip logic.
