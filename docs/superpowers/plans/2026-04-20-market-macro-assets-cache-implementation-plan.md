# Market Macro/Assets Cache Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the live public market board fetch path with two Redis-backed public APIs for macro and assets data, refreshed every 15 minutes by a separate scheduler process.

**Architecture:** Split the current combined board service into group-scoped snapshot builders for macro and assets, add Redis read/write helpers plus stale-state handling, expose two public read-only routes, and run quote refreshes in a standalone APScheduler process rather than inside FastAPI request handling. Update the frontend board page to fetch the two group APIs independently so one section can degrade without blanking the other.

**Tech Stack:** FastAPI, Pydantic v2, Redis asyncio client, APScheduler, yfinance, pytest, Next.js 16, React 19, TypeScript

---

## File Structure

### Backend

- Modify: `apps/api/src/schemas/public_board.py`
  - Replace the combined board response with reusable metric + group snapshot models.
- Modify: `apps/api/src/services/public_board.py`
  - Split into macro/assets snapshot builders and remove request-time caching logic.
- Create: `apps/api/src/services/public_market_cache.py`
  - Redis serialization, key naming, stale marking, and read/write helpers.
- Modify: `apps/api/src/routers/public.py`
  - Replace `/market-board` with `/market-macro` and `/market-assets`.
- Modify: `apps/api/src/core/scheduler.py`
  - Register two 15-minute recurring jobs for market macro/assets refresh.
- Create: `apps/api/src/run_scheduler.py`
  - Standalone scheduler process entrypoint.
- Modify: `apps/api/src/main.py`
  - Keep Redis initialization for API process, but ensure no scheduler startup occurs here.
- Modify: `apps/api/package.json`
  - Add a script for launching the standalone scheduler.

### Frontend

- Modify: `apps/web/src/types/api.ts`
  - Add group snapshot response types for macro/assets.
- Modify: `apps/web/src/app/[locale]/board/page.tsx`
  - Fetch macro/assets separately and render section-level failure/stale states.

### Tests

- Modify: `apps/api/tests/test_public_board_service.py`
  - Refocus service tests around snapshot builder outputs.
- Create: `apps/api/tests/test_public_market_cache.py`
  - Validate Redis cache read/write and stale behavior.
- Create: `apps/api/tests/test_public_routes.py`
  - Validate route behavior for fresh, stale, and missing cache.

## Task 1: Lock Group Snapshot Schemas With Tests

**Files:**
- Modify: `apps/api/src/schemas/public_board.py`
- Modify: `apps/api/tests/test_public_board_service.py`

- [ ] **Step 1: Write failing schema-focused tests for group snapshots**

```python
# apps/api/tests/test_public_board_service.py
from datetime import UTC, datetime

from src.schemas.public_board import MarketGroupSnapshot
from src.schemas.public_board import MarketMetric


def test_market_group_snapshot_serializes_macro_payload() -> None:
    payload = MarketGroupSnapshot(
        group="macro",
        status="ok",
        as_of=datetime(2026, 4, 20, 10, 30, tzinfo=UTC),
        last_success_at=datetime(2026, 4, 20, 10, 31, tzinfo=UTC),
        source="yfinance",
        items=[
            MarketMetric(
                name="VIX",
                symbol="^VIX",
                value=18.42,
                display="18.42",
                change_pct=-1.13,
                status="ok",
            )
        ],
    )

    dumped = payload.model_dump()

    assert dumped["group"] == "macro"
    assert dumped["status"] == "ok"
    assert dumped["items"][0]["name"] == "VIX"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/ricky/Documents/BaixingAI/finance-agent/apps/api && uv run pytest tests/test_public_board_service.py::test_market_group_snapshot_serializes_macro_payload -q`

Expected: FAIL with `ImportError` or `AttributeError` because `MarketGroupSnapshot` is not defined yet.

- [ ] **Step 3: Implement the minimal schema changes**

```python
# apps/api/src/schemas/public_board.py
from datetime import datetime
from typing import Literal

from pydantic import BaseModel


MetricStatus = Literal["ok", "unavailable", "stale"]
GroupStatus = Literal["ok", "stale", "empty"]
SnapshotGroup = Literal["macro", "assets"]


class MarketMetric(BaseModel):
    name: str
    symbol: str
    value: float | None
    display: str | None = None
    change_pct: float | None = None
    status: MetricStatus


class MarketGroupSnapshot(BaseModel):
    group: SnapshotGroup
    status: GroupStatus
    as_of: datetime
    last_success_at: datetime
    source: str
    items: list[MarketMetric]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/ricky/Documents/BaixingAI/finance-agent/apps/api && uv run pytest tests/test_public_board_service.py::test_market_group_snapshot_serializes_macro_payload -q`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add apps/api/src/schemas/public_board.py apps/api/tests/test_public_board_service.py
git commit -m "test(api): lock market group snapshot schema"
```

## Task 2: Split Public Board Service Into Macro/Assets Builders

**Files:**
- Modify: `apps/api/src/services/public_board.py`
- Modify: `apps/api/tests/test_public_board_service.py`

- [ ] **Step 1: Write failing tests for macro and assets snapshot builders**

```python
# apps/api/tests/test_public_board_service.py
import asyncio
from datetime import UTC, datetime

from src.services import public_board
from src.services.public_board import QuoteSnapshot


def test_build_macro_snapshot_handles_partial_failures(monkeypatch) -> None:
    quotes = {
        public_board.YFINANCE_SYMBOLS["VIX"]: QuoteSnapshot(18.0, 19.0, -5.26),
        public_board.YFINANCE_SYMBOLS["US10Y"]: QuoteSnapshot(43.2, 42.7, 1.17),
        public_board.YFINANCE_SYMBOLS["DXY"]: None,
        public_board.US2Y_SYMBOL: QuoteSnapshot(40.1, 39.8, 0.75),
    }

    async def fake_safe_fetch_quote(symbol: str):
        return quotes[symbol]

    monkeypatch.setattr(public_board, "_safe_fetch_quote", fake_safe_fetch_quote)

    snapshot = asyncio.run(
        public_board.build_macro_snapshot(datetime(2026, 4, 20, 10, 30, tzinfo=UTC))
    )

    assert snapshot.group == "macro"
    assert snapshot.status == "ok"
    assert len(snapshot.items) == 4
    assert next(item for item in snapshot.items if item.name == "DXY").status == "unavailable"
    assert next(item for item in snapshot.items if item.name == "2Y-10Y Spread").display.endswith("bps")


def test_build_assets_snapshot_returns_five_metrics(monkeypatch) -> None:
    quotes = {
        public_board.YFINANCE_SYMBOLS["SPX"]: QuoteSnapshot(5200.0, 5170.0, 0.58),
        public_board.YFINANCE_SYMBOLS["NASDAQ"]: QuoteSnapshot(16300.0, 16200.0, 0.62),
        public_board.YFINANCE_SYMBOLS["GOLD"]: QuoteSnapshot(2320.0, 2310.0, 0.43),
        public_board.YFINANCE_SYMBOLS["WTI"]: QuoteSnapshot(81.2, 80.5, 0.87),
        public_board.YFINANCE_SYMBOLS["BTC"]: QuoteSnapshot(84500.0, 84000.0, 0.60),
    }

    async def fake_safe_fetch_quote(symbol: str):
        return quotes[symbol]

    monkeypatch.setattr(public_board, "_safe_fetch_quote", fake_safe_fetch_quote)

    snapshot = asyncio.run(
        public_board.build_assets_snapshot(datetime(2026, 4, 20, 10, 30, tzinfo=UTC))
    )

    assert snapshot.group == "assets"
    assert len(snapshot.items) == 5
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/ricky/Documents/BaixingAI/finance-agent/apps/api && uv run pytest tests/test_public_board_service.py -q`

Expected: FAIL because `build_macro_snapshot` and `build_assets_snapshot` do not exist yet.

- [ ] **Step 3: Implement minimal macro/assets snapshot builders**

```python
# apps/api/src/services/public_board.py
from src.schemas.public_board import MarketGroupSnapshot
from src.schemas.public_board import MarketMetric


async def build_macro_snapshot(as_of: datetime) -> MarketGroupSnapshot:
    vix_quote, us10y_quote, dxy_quote, us2y_quote = await asyncio.gather(
        _safe_fetch_quote(YFINANCE_SYMBOLS["VIX"]),
        _safe_fetch_quote(YFINANCE_SYMBOLS["US10Y"]),
        _safe_fetch_quote(YFINANCE_SYMBOLS["DXY"]),
        _safe_fetch_quote(US2Y_SYMBOL),
    )

    items = [
        MarketMetric(**_metric_from_quote("VIX", YFINANCE_SYMBOLS["VIX"], vix_quote, _format_number)),
        MarketMetric(
            **_metric_from_quote(
                "US 10Y",
                YFINANCE_SYMBOLS["US10Y"],
                us10y_quote,
                _format_percent,
                transform=_tnx_to_percent,
            )
        ),
        MarketMetric(**_metric_from_quote("DXY", YFINANCE_SYMBOLS["DXY"], dxy_quote, _format_number)),
        MarketMetric(**_build_spread_metric(us2y_quote, us10y_quote)),
    ]

    return MarketGroupSnapshot(
        group="macro",
        status="ok",
        as_of=as_of,
        last_success_at=datetime.now(UTC),
        source=SOURCE_NAME,
        items=items,
    )


async def build_assets_snapshot(as_of: datetime) -> MarketGroupSnapshot:
    spx_quote, nasdaq_quote, gold_quote, wti_quote, btc_quote = await asyncio.gather(
        _safe_fetch_quote(YFINANCE_SYMBOLS["SPX"]),
        _safe_fetch_quote(YFINANCE_SYMBOLS["NASDAQ"]),
        _safe_fetch_quote(YFINANCE_SYMBOLS["GOLD"]),
        _safe_fetch_quote(YFINANCE_SYMBOLS["WTI"]),
        _safe_fetch_quote(YFINANCE_SYMBOLS["BTC"]),
    )

    items = [
        MarketMetric(**_metric_from_quote("S&P 500", YFINANCE_SYMBOLS["SPX"], spx_quote, _format_number)),
        MarketMetric(**_metric_from_quote("NASDAQ", YFINANCE_SYMBOLS["NASDAQ"], nasdaq_quote, _format_number)),
        MarketMetric(**_metric_from_quote("Gold", YFINANCE_SYMBOLS["GOLD"], gold_quote, _format_number)),
        MarketMetric(**_metric_from_quote("WTI", YFINANCE_SYMBOLS["WTI"], wti_quote, _format_number)),
        MarketMetric(**_metric_from_quote("BTC", YFINANCE_SYMBOLS["BTC"], btc_quote, _format_number)),
    ]

    return MarketGroupSnapshot(
        group="assets",
        status="ok",
        as_of=as_of,
        last_success_at=datetime.now(UTC),
        source=SOURCE_NAME,
        items=items,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/ricky/Documents/BaixingAI/finance-agent/apps/api && uv run pytest tests/test_public_board_service.py -q`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add apps/api/src/services/public_board.py apps/api/tests/test_public_board_service.py
git commit -m "refactor(api): split public market snapshot builders"
```

## Task 3: Add Redis Cache Helper For Snapshot Storage And Stale Reads

**Files:**
- Create: `apps/api/src/services/public_market_cache.py`
- Create: `apps/api/tests/test_public_market_cache.py`

- [ ] **Step 1: Write failing tests for Redis snapshot read/write and stale conversion**

```python
# apps/api/tests/test_public_market_cache.py
import json
from datetime import UTC, datetime, timedelta

from src.schemas.public_board import MarketGroupSnapshot
from src.schemas.public_board import MarketMetric
from src.services.public_market_cache import classify_snapshot_status
from src.services.public_market_cache import snapshot_cache_key


def test_snapshot_cache_key_uses_group_and_version() -> None:
    assert snapshot_cache_key("macro") == "public:market:macro:v1"
    assert snapshot_cache_key("assets") == "public:market:assets:v1"


def test_classify_snapshot_status_marks_old_data_stale() -> None:
    snapshot = MarketGroupSnapshot(
        group="macro",
        status="ok",
        as_of=datetime.now(UTC) - timedelta(minutes=20),
        last_success_at=datetime.now(UTC) - timedelta(minutes=20),
        source="yfinance",
        items=[
            MarketMetric(
                name="VIX",
                symbol="^VIX",
                value=18.0,
                display="18.0",
                change_pct=0.0,
                status="ok",
            )
        ],
    )

    status = classify_snapshot_status(snapshot, datetime.now(UTC))

    assert status == "stale"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/ricky/Documents/BaixingAI/finance-agent/apps/api && uv run pytest tests/test_public_market_cache.py -q`

Expected: FAIL because `public_market_cache.py` does not exist yet.

- [ ] **Step 3: Implement cache helper**

```python
# apps/api/src/services/public_market_cache.py
import json
from datetime import UTC, datetime, timedelta

from redis.asyncio import Redis

from src.schemas.public_board import MarketGroupSnapshot

CACHE_VERSION = "v1"
SNAPSHOT_TTL_SECONDS = 45 * 60
FRESH_WINDOW = timedelta(minutes=15)
STALE_WINDOW = timedelta(minutes=45)


def snapshot_cache_key(group: str) -> str:
    return f"public:market:{group}:{CACHE_VERSION}"


def classify_snapshot_status(snapshot: MarketGroupSnapshot, now: datetime) -> str:
    age = now - snapshot.as_of
    if age <= FRESH_WINDOW:
        return "ok"
    if age <= STALE_WINDOW:
        return "stale"
    return "empty"


async def write_market_snapshot(redis: Redis, snapshot: MarketGroupSnapshot) -> None:
    await redis.set(
        snapshot_cache_key(snapshot.group),
        snapshot.model_dump_json(),
        ex=SNAPSHOT_TTL_SECONDS,
    )


async def read_market_snapshot(redis: Redis, group: str) -> MarketGroupSnapshot | None:
    raw = await redis.get(snapshot_cache_key(group))
    if raw is None:
        return None
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    return MarketGroupSnapshot.model_validate_json(raw)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/ricky/Documents/BaixingAI/finance-agent/apps/api && uv run pytest tests/test_public_market_cache.py -q`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add apps/api/src/services/public_market_cache.py apps/api/tests/test_public_market_cache.py
git commit -m "feat(api): add redis cache helpers for public market snapshots"
```

## Task 4: Add Read-Only Public Routes For Macro And Assets

**Files:**
- Modify: `apps/api/src/routers/public.py`
- Create: `apps/api/tests/test_public_routes.py`
- Modify: `apps/api/src/dependencies.py`

- [ ] **Step 1: Write failing route tests for fresh and missing cache**

```python
# apps/api/tests/test_public_routes.py
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from src.main import app
from src.schemas.public_board import MarketGroupSnapshot
from src.schemas.public_board import MarketMetric


class FakeRedis:
    def __init__(self, payload: str | None):
        self.payload = payload

    async def get(self, key: str):
        return self.payload


def test_market_macro_route_returns_cached_snapshot(monkeypatch) -> None:
    snapshot = MarketGroupSnapshot(
        group="macro",
        status="ok",
        as_of=datetime(2026, 4, 20, 10, 30, tzinfo=UTC),
        last_success_at=datetime(2026, 4, 20, 10, 30, tzinfo=UTC),
        source="yfinance",
        items=[MarketMetric(name="VIX", symbol="^VIX", value=18.0, display="18.0", change_pct=0.0, status="ok")],
    )

    from src.dependencies import get_redis
    app.dependency_overrides[get_redis] = lambda: FakeRedis(snapshot.model_dump_json())

    client = TestClient(app)
    response = client.get("/api/v1/public/market-macro")

    assert response.status_code == 200
    assert response.json()["group"] == "macro"


def test_market_assets_route_returns_503_when_cache_missing(monkeypatch) -> None:
    from src.dependencies import get_redis
    app.dependency_overrides[get_redis] = lambda: FakeRedis(None)

    client = TestClient(app)
    response = client.get("/api/v1/public/market-assets")

    assert response.status_code == 503
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/ricky/Documents/BaixingAI/finance-agent/apps/api && uv run pytest tests/test_public_routes.py -q`

Expected: FAIL because the new routes are not implemented.

- [ ] **Step 3: Implement read-only routes**

```python
# apps/api/src/routers/public.py
from datetime import UTC, datetime

from fastapi import APIRouter
from fastapi import HTTPException

from src.dependencies import RedisDep
from src.schemas.public_board import MarketGroupSnapshot
from src.services.public_market_cache import classify_snapshot_status
from src.services.public_market_cache import read_market_snapshot

router = APIRouter(prefix="/public", tags=["public"])


async def _get_snapshot_or_503(redis: RedisDep, group: str) -> MarketGroupSnapshot:
    snapshot = await read_market_snapshot(redis, group)
    if snapshot is None:
        raise HTTPException(status_code=503, detail=f"{group} snapshot unavailable")

    status = classify_snapshot_status(snapshot, datetime.now(UTC))
    if status == "empty":
        raise HTTPException(status_code=503, detail=f"{group} snapshot unavailable")

    return snapshot.model_copy(update={"status": status})


@router.get("/market-macro", response_model=MarketGroupSnapshot)
async def get_market_macro(redis: RedisDep) -> MarketGroupSnapshot:
    return await _get_snapshot_or_503(redis, "macro")


@router.get("/market-assets", response_model=MarketGroupSnapshot)
async def get_market_assets(redis: RedisDep) -> MarketGroupSnapshot:
    return await _get_snapshot_or_503(redis, "assets")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/ricky/Documents/BaixingAI/finance-agent/apps/api && uv run pytest tests/test_public_routes.py -q`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add apps/api/src/routers/public.py apps/api/tests/test_public_routes.py apps/api/src/dependencies.py
git commit -m "feat(api): add read-only public market macro and assets routes"
```

## Task 5: Move Refresh Logic Into A Standalone Scheduler Process

**Files:**
- Modify: `apps/api/src/core/scheduler.py`
- Create: `apps/api/src/run_scheduler.py`
- Modify: `apps/api/package.json`

- [ ] **Step 1: Write a failing scheduler job test around Redis writes**

```python
# apps/api/tests/test_public_market_cache.py
import asyncio
from datetime import UTC, datetime

from src.schemas.public_board import MarketGroupSnapshot
from src.services import public_board
from src.services import public_market_cache


class FakeRedis:
    def __init__(self):
        self.writes = {}

    async def set(self, key, value, ex):
        self.writes[key] = {"value": value, "ex": ex}


def test_refresh_macro_snapshot_job_writes_cache(monkeypatch) -> None:
    fake_redis = FakeRedis()
    snapshot = MarketGroupSnapshot(
        group="macro",
        status="ok",
        as_of=datetime(2026, 4, 20, 10, 30, tzinfo=UTC),
        last_success_at=datetime(2026, 4, 20, 10, 30, tzinfo=UTC),
        source="yfinance",
        items=[],
    )

    async def fake_builder(as_of):
        return snapshot

    monkeypatch.setattr(public_board, "build_macro_snapshot", fake_builder)

    from src.run_scheduler import refresh_market_macro_snapshot
    asyncio.run(refresh_market_macro_snapshot(fake_redis))

    assert "public:market:macro:v1" in fake_redis.writes
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/ricky/Documents/BaixingAI/finance-agent/apps/api && uv run pytest tests/test_public_market_cache.py::test_refresh_macro_snapshot_job_writes_cache -q`

Expected: FAIL because `run_scheduler.py` and refresh job functions do not exist.

- [ ] **Step 3: Implement standalone scheduler entrypoint and jobs**

```python
# apps/api/src/run_scheduler.py
import asyncio
import logging
from datetime import UTC, datetime

from src.core.config import settings
from src.core.redis import redis_manager
from src.core.scheduler import scheduler
from src.services.public_board import build_assets_snapshot
from src.services.public_board import build_macro_snapshot
from src.services.public_market_cache import write_market_snapshot

logger = logging.getLogger(__name__)


async def refresh_market_macro_snapshot(redis=None) -> None:
    client = redis or redis_manager.redis
    snapshot = await build_macro_snapshot(datetime.now(UTC))
    await write_market_snapshot(client, snapshot)


async def refresh_market_assets_snapshot(redis=None) -> None:
    client = redis or redis_manager.redis
    snapshot = await build_assets_snapshot(datetime.now(UTC))
    await write_market_snapshot(client, snapshot)


def _run_async(coro_func):
    def wrapper():
        asyncio.run(coro_func())
    return wrapper


async def bootstrap_scheduler() -> None:
    await redis_manager.init(settings.REDIS_URL)
    await refresh_market_macro_snapshot()
    await refresh_market_assets_snapshot()

    if not scheduler.get_job("refresh_public_market_macro"):
        scheduler.add_job(
            _run_async(refresh_market_macro_snapshot),
            "interval",
            minutes=15,
            id="refresh_public_market_macro",
            replace_existing=True,
        )

    if not scheduler.get_job("refresh_public_market_assets"):
        scheduler.add_job(
            _run_async(refresh_market_assets_snapshot),
            "interval",
            minutes=15,
            id="refresh_public_market_assets",
            replace_existing=True,
        )

    scheduler.start()
```

```json
// apps/api/package.json
{
  "scripts": {
    "scheduler": "uv run python -m src.run_scheduler"
  }
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/ricky/Documents/BaixingAI/finance-agent/apps/api && uv run pytest tests/test_public_market_cache.py::test_refresh_macro_snapshot_job_writes_cache -q`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add apps/api/src/core/scheduler.py apps/api/src/run_scheduler.py apps/api/package.json apps/api/tests/test_public_market_cache.py
git commit -m "feat(api): add standalone scheduler for public market snapshots"
```

## Task 6: Remove Request-Time Combined Board Path

**Files:**
- Modify: `apps/api/src/services/public_board.py`
- Modify: `apps/api/src/routers/public.py`
- Modify: `apps/api/tests/test_public_board_service.py`

- [ ] **Step 1: Write a failing test that ensures no combined market-board API remains**

```python
# apps/api/tests/test_public_routes.py
from fastapi.testclient import TestClient

from src.main import app


def test_market_board_route_is_removed() -> None:
    client = TestClient(app)
    response = client.get("/api/v1/public/market-board")

    assert response.status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/ricky/Documents/BaixingAI/finance-agent/apps/api && uv run pytest tests/test_public_routes.py::test_market_board_route_is_removed -q`

Expected: FAIL while old route still exists.

- [ ] **Step 3: Remove the old route and request-time cache entry points**

```python
# apps/api/src/routers/public.py
# Delete:
# @router.get("/market-board", ...)

# apps/api/src/services/public_board.py
# Delete:
# - get_public_market_board
# - _get_cached_payload
# - _get_stale_cached_payload
# - _mark_payload_stale
# - _mark_metric_group_stale
#
# Keep only quote fetch helpers + group snapshot builders.
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/ricky/Documents/BaixingAI/finance-agent/apps/api && uv run pytest tests/test_public_routes.py apps/api/tests/test_public_board_service.py -q`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add apps/api/src/services/public_board.py apps/api/src/routers/public.py apps/api/tests/test_public_routes.py apps/api/tests/test_public_board_service.py
git commit -m "refactor(api): remove combined public market board path"
```

## Task 7: Update Frontend Types And Fetch Macro/Assets Separately

**Files:**
- Modify: `apps/web/src/types/api.ts`
- Modify: `apps/web/src/app/[locale]/board/page.tsx`

- [ ] **Step 1: Write the failing type usage in the board page**

```ts
// apps/web/src/app/[locale]/board/page.tsx
import type { MarketGroupSnapshotResponse } from "@/types/api";

const macroRequest = useApi<MarketGroupSnapshotResponse>("/api/v1/public/market-macro");
const assetsRequest = useApi<MarketGroupSnapshotResponse>("/api/v1/public/market-assets");
```

- [ ] **Step 2: Run typecheck/build to verify it fails**

Run: `cd /Users/ricky/Documents/BaixingAI/finance-agent/apps/web && pnpm build`

Expected: FAIL because `MarketGroupSnapshotResponse` is not defined and board page still expects the old combined payload.

- [ ] **Step 3: Implement the minimal frontend type and rendering split**

```ts
// apps/web/src/types/api.ts
export type MarketMetricStatus = "ok" | "unavailable" | "stale";
export type MarketGroupStatus = "ok" | "stale" | "empty";
export type SnapshotGroup = "macro" | "assets";

export interface MarketMetric {
  name: string;
  symbol: string;
  value: number | null;
  display: string | null;
  change_pct: number | null;
  status: MarketMetricStatus;
}

export interface MarketGroupSnapshotResponse {
  group: SnapshotGroup;
  status: MarketGroupStatus;
  as_of: string;
  last_success_at: string;
  source: string;
  items: MarketMetric[];
}
```

```tsx
// apps/web/src/app/[locale]/board/page.tsx
const macroRequest = useApi<MarketGroupSnapshotResponse>("/api/v1/public/market-macro");
const assetsRequest = useApi<MarketGroupSnapshotResponse>("/api/v1/public/market-assets");

const macroData = macroRequest.data;
const assetsData = assetsRequest.data;

<MetricSection title={copy.sections.macro} metrics={macroData?.items ?? []} copy={copy} />
<MetricSection title={copy.sections.assets} metrics={assetsData?.items ?? []} copy={copy} />
```

- [ ] **Step 4: Run build to verify it passes**

Run: `cd /Users/ricky/Documents/BaixingAI/finance-agent/apps/web && pnpm build`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/types/api.ts apps/web/src/app/[locale]/board/page.tsx
git commit -m "feat(web): fetch market macro and assets snapshots separately"
```

## Task 8: Add Section-Level Error And Stale UI States

**Files:**
- Modify: `apps/web/src/app/[locale]/board/page.tsx`
- Modify: `apps/web/messages/en.json`
- Modify: `apps/web/messages/zh.json`

- [ ] **Step 1: Write the failing UI usage for section-level degraded states**

```tsx
// apps/web/src/app/[locale]/board/page.tsx
{macroRequest.error ? (
  <SectionErrorState title={copy.sections.macro} message={copy.sectionUnavailable} onRetry={macroRequest.refetch} />
) : (
  <MetricSection title={copy.sections.macro} metrics={macroData?.items ?? []} copy={copy} />
)}
```

- [ ] **Step 2: Run build to verify it fails**

Run: `cd /Users/ricky/Documents/BaixingAI/finance-agent/apps/web && pnpm build`

Expected: FAIL because `SectionErrorState` and localized copy are not defined.

- [ ] **Step 3: Implement section-level degradation UI**

```tsx
// apps/web/src/app/[locale]/board/page.tsx
function SectionErrorState({
  title,
  message,
  onRetry,
}: Readonly<{ title: string; message: string; onRetry: () => void }>): React.JSX.Element {
  return (
    <section className="rounded-2xl border border-divider bg-white p-5 shadow-sm md:p-6">
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-lg font-serif font-medium text-ink">{title}</h2>
        <button type="button" onClick={onRetry} className="text-sm text-terracotta">
          Retry
        </button>
      </div>
      <p className="mt-4 text-sm text-warm-gray">{message}</p>
    </section>
  );
}
```

```json
// apps/web/messages/en.json
"board": {
  "sectionUnavailable": "This section is temporarily unavailable.",
  "staleLabel": "Delayed"
}
```

```json
// apps/web/messages/zh.json
"board": {
  "sectionUnavailable": "该分区数据暂时不可用。",
  "staleLabel": "延迟"
}
```

- [ ] **Step 4: Run build to verify it passes**

Run: `cd /Users/ricky/Documents/BaixingAI/finance-agent/apps/web && pnpm build`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/app/[locale]/board/page.tsx apps/web/messages/en.json apps/web/messages/zh.json
git commit -m "feat(web): add section-level degraded states for board snapshots"
```

## Task 9: Final Verification

**Files:**
- Test: `apps/api/tests/test_public_board_service.py`
- Test: `apps/api/tests/test_public_market_cache.py`
- Test: `apps/api/tests/test_public_routes.py`
- Test: `apps/web/src/app/[locale]/board/page.tsx`

- [ ] **Step 1: Run backend tests**

Run: `cd /Users/ricky/Documents/BaixingAI/finance-agent/apps/api && uv run pytest tests/test_public_board_service.py tests/test_public_market_cache.py tests/test_public_routes.py -q`

Expected: PASS

- [ ] **Step 2: Run frontend build**

Run: `cd /Users/ricky/Documents/BaixingAI/finance-agent/apps/web && pnpm build`

Expected: PASS

- [ ] **Step 3: Smoke test the API routes locally**

Run: `cd /Users/ricky/Documents/BaixingAI/finance-agent/apps/api && uv run python -m src.run_scheduler`

Expected: Redis keys `public:market:macro:v1` and `public:market:assets:v1` are written and scheduler remains running.

- [ ] **Step 4: Verify route responses manually**

Run: `curl -s http://localhost:8000/api/v1/public/market-macro | jq '{group,status,count:(.items|length),source}'`

Expected: JSON with `group: "macro"` and `count: 4`

Run: `curl -s http://localhost:8000/api/v1/public/market-assets | jq '{group,status,count:(.items|length),source}'`

Expected: JSON with `group: "assets"` and `count: 5`

- [ ] **Step 5: Commit**

```bash
git add apps/api/tests/test_public_board_service.py apps/api/tests/test_public_market_cache.py apps/api/tests/test_public_routes.py apps/web/src/app/[locale]/board/page.tsx apps/web/src/types/api.ts apps/web/messages/en.json apps/web/messages/zh.json apps/api/src/services/public_board.py apps/api/src/services/public_market_cache.py apps/api/src/routers/public.py apps/api/src/schemas/public_board.py apps/api/src/core/scheduler.py apps/api/src/run_scheduler.py apps/api/package.json
git commit -m "feat: split public market snapshots into redis-backed macro and assets services"
```

## Self-Review

### Spec Coverage

- Two public APIs: covered by Task 4 and Task 7.
- Redis-backed snapshots: covered by Task 3 and Task 5.
- Separate scheduler process: covered by Task 5.
- API routes never fetch upstream directly: enforced by Task 4 and Task 6.
- `/board` parallel fetch and section isolation: covered by Task 7 and Task 8.
- Stale cache strategy and 45-minute TTL: covered by Task 3 and Task 4.
- Removal of `/market-board` compatibility: covered by Task 6.

### Placeholder Scan

- No `TBD`, `TODO`, or deferred test placeholders remain.
- Each implementation task includes concrete file paths, code snippets, commands, and expected outcomes.

### Type Consistency

- Backend snapshot model name is `MarketGroupSnapshot`.
- Frontend response type name is `MarketGroupSnapshotResponse`.
- Cache keys use `public:market:<group>:v1` consistently across tasks.
