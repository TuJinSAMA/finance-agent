# Market Board Pivot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `/{locale}/board` the default public entry, expose a yfinance-backed public board API, and rename authenticated dashboard UX to recommendations without breaking old links.

**Architecture:** Add a dedicated FastAPI public board module (`schema + service + router`) with yfinance-only data fetch and server-side TTL cache. In Next.js, add a new board page that consumes the public API, then migrate authenticated routes from `dashboard` semantics to `recommendations` while keeping compatibility redirects from old paths.

**Tech Stack:** FastAPI, Pydantic v2, yfinance, Next.js 16 App Router, next-intl, Clerk, TypeScript, Tailwind CSS v4

---

## File Structure and Responsibilities

- `apps/api/src/schemas/public_board.py`
  - Public board response contract (`market_state`, `macro`, `assets`, `custom`, `as_of`, `source`).
- `apps/api/src/services/public_board.py`
  - yfinance-only snapshot builder, metric-level fault tolerance, 10-minute in-memory TTL cache, rule-based risk label.
- `apps/api/src/routers/public.py`
  - Unauthenticated `GET /public/market-board` endpoint.
- `apps/api/src/main.py`
  - Router registration for new public board API.
- `apps/api/tests/test_public_board_service.py`
  - Service-level tests for risk-state rules, metric fallback behavior, and cache behavior.
- `apps/api/pyproject.toml`
  - Add `pytest` and `pytest-asyncio` in dev dependency group.

- `apps/web/src/types/api.ts`
  - Add market board TypeScript interfaces.
- `apps/web/src/app/[locale]/board/page.tsx`
  - New public market board UI (no auth required).
- `apps/web/src/app/[locale]/recommendations/layout.tsx`
  - Authenticated recommendations shell (migrated from dashboard layout).
- `apps/web/src/app/[locale]/recommendations/page.tsx`
  - Existing recommendation list page under new route.
- `apps/web/src/app/[locale]/recommendations/portfolio/page.tsx`
  - Existing portfolio page under new nested route.
- `apps/web/src/app/[locale]/dashboard/page.tsx`
  - Compatibility redirect to `/recommendations`.
- `apps/web/src/app/[locale]/dashboard/layout.tsx`
  - Compatibility layout redirect guard (or removed if route subtree fully redirected).
- `apps/web/src/app/[locale]/dashboard/portfolio/page.tsx`
  - Compatibility redirect to `/recommendations/portfolio`.
- `apps/web/src/app/[locale]/landing/page.tsx`
  - Previous landing content moved here.
- `apps/web/src/app/[locale]/page.tsx`
  - Thin redirect to `/board` as app-level fallback.
- `apps/web/src/middleware.ts`
  - Update protected route matcher and default root redirect target.
- `apps/web/messages/en.json`
  - Add board page copy and nav label rename (`dashboard` -> `recommendations`).
- `apps/web/messages/zh.json`
  - Chinese equivalents.

---

### Task 1: Add Backend Test Harness and Lock Public Board Contract

**Files:**
- Modify: `apps/api/pyproject.toml`
- Create: `apps/api/tests/test_public_board_service.py`
- Test: `apps/api/tests/test_public_board_service.py`

- [ ] **Step 1: Add failing service tests for risk-state and metric fallback**

```python
# apps/api/tests/test_public_board_service.py
from src.services.public_board import classify_market_state, normalize_metric


def test_classify_market_state_risk_off_when_vix_high_and_equities_down():
    label = classify_market_state(vix=27.3, us10y_change_bps=8.0, spx_change_pct=-1.2)
    assert label == "Risk-Off 偏避险"


def test_normalize_metric_marks_unavailable_on_none_value():
    metric = normalize_metric(name="VIX", symbol="^VIX", value=None, change_pct=None)
    assert metric["status"] == "unavailable"
    assert metric["value"] is None
```

- [ ] **Step 2: Run tests to verify failure (module not implemented yet)**

Run:
```bash
cd apps/api && uv run pytest tests/test_public_board_service.py -q
```
Expected: FAIL with `ModuleNotFoundError: No module named 'src.services.public_board'`.

- [ ] **Step 3: Add test dependencies in `pyproject.toml` dev group**

```toml
[dependency-groups]
dev = [
  "ruff>=0.15.4",
  "pytest>=8.3.0",
  "pytest-asyncio>=0.24.0"
]
```

- [ ] **Step 4: Re-run tests (still expected fail until implementation task)**

Run:
```bash
cd apps/api && uv run pytest tests/test_public_board_service.py -q
```
Expected: FAIL for missing implementation symbols, but test runner boots.

- [ ] **Step 5: Commit scaffold**

```bash
git add apps/api/pyproject.toml apps/api/tests/test_public_board_service.py
git commit -m "test(api): add public board service contract tests"
```

---

### Task 2: Implement Public Board Service (yfinance-only) and Router

**Files:**
- Create: `apps/api/src/schemas/public_board.py`
- Create: `apps/api/src/services/public_board.py`
- Create: `apps/api/src/routers/public.py`
- Modify: `apps/api/src/main.py`
- Test: `apps/api/tests/test_public_board_service.py`

- [ ] **Step 1: Create response schemas (Pydantic v2)**

```python
# apps/api/src/schemas/public_board.py
from datetime import datetime
from pydantic import BaseModel


class MarketMetric(BaseModel):
    name: str
    symbol: str
    value: float | None
    display: str | None
    change_pct: float | None
    status: str  # ok | unavailable | stale


class MarketState(BaseModel):
    date: str
    label: str
    summary: str


class PublicMarketBoardResponse(BaseModel):
    market_state: MarketState
    macro: list[MarketMetric]
    assets: list[MarketMetric]
    custom: list[MarketMetric]
    as_of: datetime
    source: str
```

- [ ] **Step 2: Implement minimal service to satisfy failing tests**

```python
# apps/api/src/services/public_board.py (initial)
from datetime import UTC, datetime


def classify_market_state(vix: float | None, us10y_change_bps: float | None, spx_change_pct: float | None) -> str:
    if (vix or 0) >= 25 and (us10y_change_bps or 0) > 0 and (spx_change_pct or 0) < 0:
        return "Risk-Off 偏避险"
    return "Neutral 中性"


def normalize_metric(name: str, symbol: str, value: float | None, change_pct: float | None) -> dict:
    if value is None:
        return {
            "name": name,
            "symbol": symbol,
            "value": None,
            "display": None,
            "change_pct": change_pct,
            "status": "unavailable",
        }
    return {
        "name": name,
        "symbol": symbol,
        "value": value,
        "display": f"{value}",
        "change_pct": change_pct,
        "status": "ok",
    }
```

- [ ] **Step 3: Add yfinance snapshot fetch + 10-minute cache + partial-failure handling**

```python
# apps/api/src/services/public_board.py (extend)
import asyncio
from datetime import UTC, datetime, timedelta
import yfinance as yf

_CACHE: dict[str, object] = {"as_of": None, "payload": None}
TTL = timedelta(minutes=10)

SYMBOLS = {
    "VIX": "^VIX",
    "US10Y": "^TNX",
    "DXY": "DX-Y.NYB",
    "SPX": "^GSPC",
    "NASDAQ": "^IXIC",
    "GOLD": "GC=F",
    "WTI": "CL=F",
    "BTC": "BTC-USD",
    "CSI300": "000300.SS",
    "USDCNY": "CNY=X",
}


async def _fetch_last(symbol: str) -> tuple[float | None, float | None]:
    def _load() -> tuple[float | None, float | None]:
        hist = yf.Ticker(symbol).history(period="5d", interval="1d")
        if hist is None or hist.empty:
            return None, None
        close = float(hist["Close"].iloc[-1])
        prev = float(hist["Close"].iloc[-2]) if len(hist) > 1 else None
        change = ((close - prev) / prev * 100) if prev else None
        return close, change

    return await asyncio.to_thread(_load)
```

- [ ] **Step 4: Expose unauthenticated endpoint**

```python
# apps/api/src/routers/public.py
from fastapi import APIRouter
from src.schemas.public_board import PublicMarketBoardResponse
from src.services.public_board import get_public_market_board

router = APIRouter(prefix="/public", tags=["public"])


@router.get("/market-board", response_model=PublicMarketBoardResponse)
async def get_market_board() -> PublicMarketBoardResponse:
    return await get_public_market_board()
```

- [ ] **Step 5: Register router in app startup**

```python
# apps/api/src/main.py
from src.routers import admin, notifications, portfolio, public, recommendations, users, webhooks

app.include_router(public.router, prefix=settings.API_V1_PREFIX)
```

- [ ] **Step 6: Run backend tests to verify pass**

Run:
```bash
cd apps/api && uv run pytest tests/test_public_board_service.py -q
```
Expected: PASS (`2 passed`).

- [ ] **Step 7: Run lint for API**

Run:
```bash
cd apps/api && pnpm lint
```
Expected: Ruff passes.

- [ ] **Step 8: Commit API feature**

```bash
git add apps/api/src/schemas/public_board.py apps/api/src/services/public_board.py apps/api/src/routers/public.py apps/api/src/main.py
git commit -m "feat(api): add yfinance-backed public market board endpoint"
```

---

### Task 3: Add Frontend API Types and Build Public Board Page

**Files:**
- Modify: `apps/web/src/types/api.ts`
- Create: `apps/web/src/app/[locale]/board/page.tsx`
- Test: `apps/web/src/app/[locale]/board/page.tsx` via build/lint

- [ ] **Step 1: Add failing type usage in board page first**

```tsx
// apps/web/src/app/[locale]/board/page.tsx
import type { PublicMarketBoardResponse } from "@/types/api";
```

- [ ] **Step 2: Run TypeScript build to verify failure before adding types**

Run:
```bash
cd apps/web && pnpm build
```
Expected: FAIL with `PublicMarketBoardResponse` not exported from `@/types/api`.

- [ ] **Step 3: Add TypeScript contracts to `api.ts`**

```ts
export interface MarketMetric {
  name: string;
  symbol: string;
  value: number | null;
  display: string | null;
  change_pct: number | null;
  status: "ok" | "unavailable" | "stale";
}

export interface PublicMarketBoardResponse {
  market_state: { date: string; label: string; summary: string };
  macro: MarketMetric[];
  assets: MarketMetric[];
  custom: MarketMetric[];
  as_of: string;
  source: string;
}
```

- [ ] **Step 4: Implement board page UI with graceful degradation**

```tsx
// apps/web/src/app/[locale]/board/page.tsx
"use client";

import { useTranslations } from "next-intl";
import { useApi } from "@/hooks/useApi";
import type { PublicMarketBoardResponse } from "@/types/api";

export default function BoardPage() {
  const t = useTranslations("board");
  const { data, loading, error, refetch } = useApi<PublicMarketBoardResponse>("/api/v1/public/market-board");

  if (loading) return <div className="p-6">{t("loading")}</div>;
  if (error || !data) return <button onClick={refetch}>{t("retry")}</button>;

  return (
    <div className="max-w-5xl mx-auto p-4 md:p-8 space-y-4">
      <header className="bg-white border border-divider rounded-xl p-4">
        <p className="text-sm text-warm-gray">{data.market_state.date}</p>
        <h1 className="text-xl font-serif text-ink">{data.market_state.label}</h1>
        <p className="text-sm text-warm-gray">{t("asOf", { time: new Date(data.as_of).toLocaleString() })}</p>
      </header>
      {/* render macro/assets/custom grids with unavailable fallback */}
    </div>
  );
}
```

- [ ] **Step 5: Run web lint and build**

Run:
```bash
cd apps/web && pnpm lint
cd apps/web && pnpm build
```
Expected: both pass.

- [ ] **Step 6: Commit board UI**

```bash
git add apps/web/src/types/api.ts apps/web/src/app/[locale]/board/page.tsx
git commit -m "feat(web): add public market board page"
```

---

### Task 4: Migrate Dashboard Semantics to Recommendations with Compatibility Redirects

**Files:**
- Create: `apps/web/src/app/[locale]/recommendations/layout.tsx`
- Create: `apps/web/src/app/[locale]/recommendations/page.tsx`
- Create: `apps/web/src/app/[locale]/recommendations/portfolio/page.tsx`
- Modify: `apps/web/src/app/[locale]/dashboard/layout.tsx`
- Modify: `apps/web/src/app/[locale]/dashboard/page.tsx`
- Modify: `apps/web/src/app/[locale]/dashboard/portfolio/page.tsx`
- Test: route behavior in browser and build

- [ ] **Step 1: Add compatibility redirect pages first (failing route expectation before new route exists)**

```tsx
// apps/web/src/app/[locale]/dashboard/page.tsx
import { redirect } from "next/navigation";

export default function DashboardLegacyRedirect() {
  redirect("/recommendations");
}
```

```tsx
// apps/web/src/app/[locale]/dashboard/portfolio/page.tsx
import { redirect } from "next/navigation";

export default function DashboardPortfolioLegacyRedirect() {
  redirect("/recommendations/portfolio");
}
```

- [ ] **Step 2: Duplicate existing dashboard pages into `recommendations` route tree**

```bash
mkdir -p 'apps/web/src/app/[locale]/recommendations/portfolio'
cp 'apps/web/src/app/[locale]/dashboard/layout.tsx' 'apps/web/src/app/[locale]/recommendations/layout.tsx'
cp 'apps/web/src/app/[locale]/dashboard/page.tsx' 'apps/web/src/app/[locale]/recommendations/page.tsx'
cp 'apps/web/src/app/[locale]/dashboard/portfolio/page.tsx' 'apps/web/src/app/[locale]/recommendations/portfolio/page.tsx'
```

- [ ] **Step 3: Update nav hrefs in new recommendations layout**

```tsx
// apps/web/src/app/[locale]/recommendations/layout.tsx
const navItems = [
  { icon: LayoutDashboard, href: "/recommendations", labelKey: "recommendations" },
  { icon: Briefcase, href: "/recommendations/portfolio", labelKey: "portfolio" },
];
```

- [ ] **Step 4: Run build to ensure route tree is healthy**

Run:
```bash
cd apps/web && pnpm build
```
Expected: PASS; `/dashboard` routes compile as redirects and `/recommendations` routes render original content.

- [ ] **Step 5: Commit route migration**

```bash
git add apps/web/src/app/[locale]/recommendations apps/web/src/app/[locale]/dashboard/page.tsx apps/web/src/app/[locale]/dashboard/layout.tsx apps/web/src/app/[locale]/dashboard/portfolio/page.tsx
git commit -m "refactor(web): rename dashboard surface to recommendations"
```

---

### Task 5: Set Board as Default Entry and Hide Landing Behind `/landing`

**Files:**
- Modify: `apps/web/src/middleware.ts`
- Create: `apps/web/src/app/[locale]/landing/page.tsx`
- Modify: `apps/web/src/app/[locale]/page.tsx`
- Test: middleware redirect behavior

- [ ] **Step 1: Move existing landing content to dedicated `/landing` route**

```bash
mkdir -p 'apps/web/src/app/[locale]/landing'
cp 'apps/web/src/app/[locale]/page.tsx' 'apps/web/src/app/[locale]/landing/page.tsx'
```

- [ ] **Step 2: Replace locale root page with hard redirect fallback**

```tsx
// apps/web/src/app/[locale]/page.tsx
import { redirect } from "next/navigation";

export default function LocaleRootRedirect() {
  redirect("/board");
}
```

- [ ] **Step 3: Update middleware default redirect + protected route matcher**

```ts
// apps/web/src/middleware.ts
const isProtectedRoute = createRouteMatcher([
  '/(.*)/recommendations(.*)',
  '/recommendations(.*)',
]);

if (isHomePage(req)) {
  const url = req.nextUrl.clone();
  const pathLocale = locales.find((l) => req.nextUrl.pathname === `/${l}`);
  const locale = pathLocale || defaultLocale;
  url.pathname = locale === defaultLocale ? '/board' : `/${locale}/board`;
  return NextResponse.redirect(url);
}
```

- [ ] **Step 4: Verify redirect behavior manually in dev server**

Run:
```bash
cd apps/web && pnpm dev
```
Checks:
- open `/` -> redirects to `/board`
- open `/zh` -> redirects to `/zh/board`
- open `/dashboard` -> redirects to `/recommendations`
- open `/landing` -> renders old landing content

- [ ] **Step 5: Commit entry pivot**

```bash
git add apps/web/src/middleware.ts apps/web/src/app/[locale]/landing/page.tsx apps/web/src/app/[locale]/page.tsx
git commit -m "feat(web): set public board as default entry and move landing page"
```

---

### Task 6: Update i18n Copy and Final Verification

**Files:**
- Modify: `apps/web/messages/en.json`
- Modify: `apps/web/messages/zh.json`
- Test: i18n key coverage + build + API endpoint smoke

- [ ] **Step 1: Add board namespace and rename nav labels**

```json
// apps/web/messages/en.json
{
  "nav": {
    "recommendations": "Recommendations",
    "portfolio": "Portfolio"
  },
  "board": {
    "title": "Market Board",
    "loading": "Loading market snapshot...",
    "retry": "Retry",
    "asOf": "Updated at {time}",
    "loginCta": "Sign in for personalized recommendations"
  }
}
```

```json
// apps/web/messages/zh.json
{
  "nav": {
    "recommendations": "推荐股票",
    "portfolio": "我的持仓"
  },
  "board": {
    "title": "市场看板",
    "loading": "正在加载市场快照...",
    "retry": "重试",
    "asOf": "更新时间：{time}",
    "loginCta": "登录查看个性化推荐"
  }
}
```

- [ ] **Step 2: Run key existence and JSON integrity checks**

Run:
```bash
node -e "const fs=require('fs'); JSON.parse(fs.readFileSync('apps/web/messages/en.json','utf8')); JSON.parse(fs.readFileSync('apps/web/messages/zh.json','utf8')); console.log('ok')"
rg -n '"board"|"recommendations"' apps/web/messages/en.json apps/web/messages/zh.json
```
Expected: `ok` and grep hits in both locale files.

- [ ] **Step 3: Run full monorepo verification**

Run:
```bash
pnpm lint
pnpm build
```
Expected: all workspaces pass.

- [ ] **Step 4: Run API smoke for public board response shape**

Run:
```bash
cd apps/api && pnpm dev
curl -s http://localhost:8000/api/v1/public/market-board | jq '{market_state, macro_count:(.macro|length), assets_count:(.assets|length), custom_count:(.custom|length), source}'
```
Expected: returns `market_state`, non-zero metric counts, and `source: "yfinance"`.

- [ ] **Step 5: Commit i18n + verification updates**

```bash
git add apps/web/messages/en.json apps/web/messages/zh.json
git commit -m "feat(web): localize market board and recommendations navigation"
```

---

## Spec Coverage Self-Review

- Default entry to `/{locale}/board`: covered by Task 5.
- New unauthenticated public API (`/api/v1/public/market-board`): covered by Task 2.
- V1 yfinance-only data source: locked in Task 2 symbol map and service implementation.
- Recommendations rename + dashboard compatibility redirect: covered by Task 4.
- Landing hidden at `/landing`: covered by Task 5.
- Partial failure and stale/unavailable rendering: backend in Task 2, frontend in Task 3.
- i18n and conversion CTA updates: covered by Task 6.

No uncovered spec requirements found.
