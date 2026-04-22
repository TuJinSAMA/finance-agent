# Market Metric Persistence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist all public board market metrics to PostgreSQL and expose a history query API so the frontend can render trend charts.

**Architecture:** Add a `market_metric_values` table for narrow-row time-series storage. Extend the existing scheduler refresh functions to write metric rows to the database after Redis caching. Add a new `/public/market-metrics/history` API endpoint for querying metric history by name and time range.

**Tech Stack:** SQLAlchemy 2.0 async, FastAPI, PostgreSQL, Alembic migrations, Pydantic v2 schemas.

---

## File Structure

| Action | Path | Purpose |
|---|---|---|
| Create | `src/models/market_metric_value.py` | SQLAlchemy model for `market_metric_values` |
| Modify | `src/models/__init__.py` | Re-export new model |
| Create | `src/services/market_metric_store.py` | Persistence and query service |
| Modify | `src/schemas/public_board.py` | Add `MetricDataPoint`, `MetricHistoryResponse` |
| Modify | `src/dependencies.py` | Add `MarketMetricServiceDep` dependency |
| Modify | `src/routers/public.py` | Add `GET /public/market-metrics/history` |
| Modify | `src/core/scheduler.py` | Call `persist_group_metrics` after Redis write |
| Create | `alembic/versions/...` | Auto-generated migration for `market_metric_values` |

---

### Task 1: Create MarketMetricValue Model

**Files:**
- Create: `src/models/market_metric_value.py`
- Modify: `src/models/__init__.py`

- [ ] **Step 1: Create model file**

Create `src/models/market_metric_value.py`:

```python
from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, DateTime, Index, Numeric, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base


class MarketMetricValue(Base):
    __tablename__ = "market_metric_values"
    __table_args__ = (
        UniqueConstraint("name", "as_of"),
        Index("idx_mmv_name_as_of", "name", "as_of"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    group: Mapped[str] = mapped_column(String(10), nullable=False)
    name: Mapped[str] = mapped_column(String(30), nullable=False)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    value: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    change_pct: Mapped[Decimal | None] = mapped_column(Numeric(8, 4), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
```

- [ ] **Step 2: Re-export in `src/models/__init__.py`**

Add to imports and `__all__`:

```python
from src.models.market_metric_value import MarketMetricValue

# Add to __all__ list:
"MarketMetricValue",
```

The final `src/models/__init__.py` should look like:

```python
from src.models.base import Base, TimestampMixin, UUIDMixin
from src.models.event import StockEvent
from src.models.job_log import JobExecutionLog
from src.models.market_metric_value import MarketMetricValue
from src.models.portfolio import Portfolio, PortfolioAlert, PortfolioHolding
from src.models.recommendation import Recommendation, UserRecommendation
from src.models.stock import (
    Stock,
    StockDailyQuote,
    StockFundamental,
    StockTechnicalIndicator,
)
from src.models.user import User
from src.models.watchlist import Watchlist, WatchlistSnapshot

__all__ = [
    "Base",
    "TimestampMixin",
    "UUIDMixin",
    "User",
    "Stock",
    "StockDailyQuote",
    "StockTechnicalIndicator",
    "StockFundamental",
    "StockEvent",
    "Watchlist",
    "WatchlistSnapshot",
    "Recommendation",
    "UserRecommendation",
    "Portfolio",
    "PortfolioHolding",
    "PortfolioAlert",
    "JobExecutionLog",
    "MarketMetricValue",
]
```

- [ ] **Step 3: Commit**

```bash
git add src/models/market_metric_value.py src/models/__init__.py
git commit -m "feat: add MarketMetricValue model for time-series metric storage"
```

---

### Task 2: Add Pydantic Schemas

**Files:**
- Modify: `src/schemas/public_board.py`

- [ ] **Step 1: Add `MetricDataPoint` and `MetricHistoryResponse` schemas**

Add these two classes at the end of `src/schemas/public_board.py`:

```python
class MetricDataPoint(BaseModel):
    as_of: datetime
    value: float | None
    change_pct: float | None


class MetricHistoryResponse(BaseModel):
    metrics: dict[str, list[MetricDataPoint]]
```

- [ ] **Step 2: Commit**

```bash
git add src/schemas/public_board.py
git commit -m "feat: add MetricDataPoint and MetricHistoryResponse schemas"
```

---

### Task 3: Create MarketMetricStore Service

**Files:**
- Create: `src/services/market_metric_store.py`
- Modify: `src/dependencies.py`

- [ ] **Step 1: Create service file**

Create `src/services/market_metric_store.py`:

```python
from datetime import datetime
from decimal import Decimal

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.models.market_metric_value import MarketMetricValue
from src.schemas.public_board import MarketGroupSnapshot


class MarketMetricService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def persist_group_metrics(self, snapshot: MarketGroupSnapshot) -> None:
        if not snapshot.items:
            return
        rows = []
        for item in snapshot.items:
            rows.append({
                "as_of": snapshot.as_of,
                "group": snapshot.group,
                "name": item.name,
                "symbol": item.symbol,
                "value": Decimal(str(item.value)) if item.value is not None else None,
                "change_pct": Decimal(str(item.change_pct)) if item.change_pct is not None else None,
            })
        stmt = insert(MarketMetricValue).values(rows)
        stmt = stmt.on_conflict_do_update(
            constraint="market_metric_values_name_as_of_key",
            set_={
                "value": stmt.excluded.value,
                "change_pct": stmt.excluded.change_pct,
            },
        )
        await self.db.execute(stmt)
        await self.db.flush()

    async def query_metric_history(
        self,
        names: list[str],
        from_dt: datetime,
        to_dt: datetime,
    ) -> dict[str, list[dict]]:
        stmt = (
            select(MarketMetricValue)
            .where(
                MarketMetricValue.name.in_(names),
                MarketMetricValue.as_of >= from_dt,
                MarketMetricValue.as_of <= to_dt,
            )
            .order_by(MarketMetricValue.name, MarketMetricValue.as_of)
        )
        result = await self.db.execute(stmt)
        rows = result.scalars().all()

        metrics: dict[str, list[dict]] = {name: [] for name in names}
        for row in rows:
            if row.name not in metrics:
                metrics[row.name] = []
            metrics[row.name].append({
                "as_of": row.as_of,
                "value": float(row.value) if row.value is not None else None,
                "change_pct": float(row.change_pct) if row.change_pct is not None else None,
            })
        return metrics
```

- [ ] **Step 2: Add dependency in `src/dependencies.py`**

Add import and dependency function. The final `src/dependencies.py` should look like:

```python
from typing import Annotated

from fastapi import Depends
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.auth import get_current_user
from src.core.database import get_db
from src.core.redis import redis_manager
from src.models.user import User
from src.services.market_metric_store import MarketMetricService
from src.services.portfolio import PortfolioService
from src.services.user import UserService

DBSession = Annotated[AsyncSession, Depends(get_db)]

CurrentUser = Annotated[User, Depends(get_current_user)]


def get_user_service(db: DBSession) -> UserService:
    return UserService(db)


def get_portfolio_service(db: DBSession) -> PortfolioService:
    return PortfolioService(db)


def get_market_metric_service(db: DBSession) -> MarketMetricService:
    return MarketMetricService(db)


def get_redis() -> Redis:
    return redis_manager.redis


UserServiceDep = Annotated[UserService, Depends(get_user_service)]
PortfolioServiceDep = Annotated[PortfolioService, Depends(get_portfolio_service)]
MarketMetricServiceDep = Annotated[MarketMetricService, Depends(get_market_metric_service)]
RedisDep = Annotated[Redis, Depends(get_redis)]
```

- [ ] **Step 3: Commit**

```bash
git add src/services/market_metric_store.py src/dependencies.py
git commit -m "feat: add MarketMetricService for persist and query metric history"
```

---

### Task 4: Add History Query API Endpoint

**Files:**
- Modify: `src/routers/public.py`

- [ ] **Step 1: Add the `/public/market-metrics/history` route**

Add imports at the top of `src/routers/public.py`:

```python
from datetime import UTC, timedelta
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from src.dependencies import MarketMetricServiceDep, RedisDep
from src.schemas.public_board import MarketGroupSnapshot, MarketMetric, MetricHistoryResponse
from src.services.public_board import ASSET_ITEM_NAMES_FROM_EXTENDED
from src.services.public_board import SOURCE_NAME
from src.services.public_market_cache import classify_snapshot_status, read_market_snapshot
```

Add the endpoint function after the existing `get_market_assets` function:

```python
@router.get("/market-metrics/history", response_model=MetricHistoryResponse)
async def get_market_metric_history(
    service: MarketMetricServiceDep,
    name: Annotated[list[str], Query(alias="name")],
    from_dt: datetime | None = None,
    to_dt: datetime | None = None,
) -> MetricHistoryResponse:
    now = datetime.now(UTC)
    start = from_dt or (now - timedelta(days=7))
    end = to_dt or now
    metrics = await service.query_metric_history(name, start, end)
    return MetricHistoryResponse(metrics=metrics)
```

Note: The existing imports for `asyncio`, `datetime`, `HTTPException`, `status` need updating — `datetime` is already imported but needs `UTC` and `timedelta`, and `Query` and `Annotated` need to be added to FastAPI imports.

- [ ] **Step 2: Commit**

```bash
git add src/routers/public.py
git commit -m "feat: add GET /public/market-metrics/history endpoint"
```

---

### Task 5: Integrate Persistence into Scheduler

**Files:**
- Modify: `src/core/scheduler.py`

- [ ] **Step 1: Modify scheduler to persist metrics after writing to Redis**

The key change: each `refresh_*` function needs to get a DB session and call `persist_group_metrics` after the Redis write. Since the scheduler runs in a background thread using `asyncio.run()`, we need to use the `async_session` factory directly.

Add import at the top of `src/core/scheduler.py`:

```python
from src.core.database import async_session
from src.services.market_metric_store import MarketMetricService
```

Modify each refresh function to also persist. For example, `refresh_crypto_snapshot` becomes:

```python
async def refresh_crypto_snapshot(redis: Redis | None = None) -> None:
    cache = redis or await get_scheduler_redis()
    snapshot = await build_crypto_snapshot(datetime.now(UTC))
    await write_market_snapshot(cache, snapshot)
    async with async_session() as db:
        service = MarketMetricService(db)
        await service.persist_group_metrics(snapshot)
    logger.info("Refreshed public market crypto snapshot")
```

Apply the same pattern to `refresh_extended_snapshot`, `refresh_equity_snapshot`, `refresh_market_macro_snapshot`, and `refresh_market_assets_snapshot`. Note: `refresh_market_macro_snapshot` and `refresh_market_assets_snapshot` are composite functions — they call the other refresh functions plus compose. Since the underlying refreshes already persist, these composite functions should NOT persist their composed snapshots (that would duplicate data). They only need the Redis write.

However, `refresh_market_assets_snapshot` calls `build_crypto_snapshot`, `build_equity_snapshot`, and `build_extended_snapshot` directly, NOT the `refresh_*` versions. So its composed items are NOT already persisted. We need to persist the individual group snapshots, not the composite "assets" group.

The cleanest approach: only the 3 core refresh functions (`crypto`, `extended`, `equity`) persist. The composite functions (`macro`, `assets`) do NOT persist because their metrics are subsets of the core groups.

Final scheduler modifications for the 3 core functions:

```python
from src.core.database import async_session
from src.services.market_metric_store import MarketMetricService

async def refresh_crypto_snapshot(redis: Redis | None = None) -> None:
    cache = redis or await get_scheduler_redis()
    snapshot = await build_crypto_snapshot(datetime.now(UTC))
    await write_market_snapshot(cache, snapshot)
    async with async_session() as db:
        service = MarketMetricService(db)
        await service.persist_group_metrics(snapshot)
    logger.info("Refreshed public market crypto snapshot")


async def refresh_extended_snapshot(redis: Redis | None = None) -> None:
    cache = redis or await get_scheduler_redis()
    snapshot = await build_extended_snapshot(datetime.now(UTC))
    await write_market_snapshot(cache, snapshot)
    async with async_session() as db:
        service = MarketMetricService(db)
        await service.persist_group_metrics(snapshot)
    logger.info("Refreshed public market extended snapshot")


async def refresh_equity_snapshot(redis: Redis | None = None) -> None:
    cache = redis or await get_scheduler_redis()
    snapshot = await build_equity_snapshot(datetime.now(UTC))
    await write_market_snapshot(cache, snapshot)
    async with async_session() as db:
        service = MarketMetricService(db)
        await service.persist_group_metrics(snapshot)
    logger.info("Refreshed public market equity snapshot")
```

`refresh_market_macro_snapshot` and `refresh_market_assets_snapshot` remain unchanged — they compose from Redis cache and don't need DB persistence.

- [ ] **Step 2: Commit**

```bash
git add src/core/scheduler.py
git commit -m "feat: persist market metrics to DB in scheduler refresh functions"
```

---

### Task 6: Create Database Migration

**Files:**
- Create: `alembic/versions/...` (auto-generated)

- [ ] **Step 1: Generate the migration**

```bash
cd apps/api && pnpm db:revision "add market_metric_values table"
```

- [ ] **Step 2: Review the generated migration**

Open the generated migration file and verify it creates the `market_metric_values` table with:
- `id` BIGSERIAL PK
- `as_of` TIMESTAMPTZ NOT NULL
- `group` VARCHAR(10) NOT NULL
- `name` VARCHAR(30) NOT NULL
- `symbol` VARCHAR(20) NOT NULL
- `value` NUMERIC(18,4) NULLABLE
- `change_pct` NUMERIC(8,4) NULLABLE
- `created_at` TIMESTAMPTZ NOT NULL DEFAULT now()
- UNIQUE constraint on `(name, as_of)`
- INDEX on `(name, as_of)`

- [ ] **Step 3: Run the migration**

```bash
cd apps/api && pnpm db:migrate
```

- [ ] **Step 4: Commit**

```bash
git add apps/api/alembic/versions/
git commit -m "feat: add migration for market_metric_values table"
```

---

### Task 7: Verify and Test

- [ ] **Step 1: Start the API and test the new endpoint**

```bash
cd apps/api && pnpm dev
```

Test the history endpoint:

```bash
curl "http://localhost:8000/api/v1/public/market-metrics/history?name=VIX&name=BTC"
```

Expected: a JSON response with `metrics` dict containing `VIX` and `BTC` arrays (may be empty if no data has been collected yet).

- [ ] **Step 2: Verify the scheduler writes to the database**

Wait for a scheduler cycle to run (or trigger one manually), then query:

```bash
cd apps/api && uv run python -c "
import asyncio
from src.core.database import async_session
from sqlalchemy import select, func
from src.models.market_metric_value import MarketMetricValue

async def check():
    async with async_session() as db:
        result = await db.execute(select(func.count()).select_from(MarketMetricValue))
        count = result.scalar()
        print(f'Total rows: {count}')
        result = await db.execute(select(MarketMetricValue).limit(5))
        for row in result.scalars():
            print(f'{row.name} @ {row.as_of} = {row.value}')

asyncio.run(check())
"
```

- [ ] **Step 3: Final commit if any fixes were needed**

```bash
git add -A && git commit -m "fix: adjust market metric persistence based on integration testing"
```