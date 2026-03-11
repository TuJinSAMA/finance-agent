# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**AlphaDesk** — AI 驱动的 A 股每日选股推荐系统（MVP 阶段）。每天早晨 8 点前为用户提供 3-5 只经过量化筛选和催化剂分析的股票推荐，每只附有结构化的推荐理由。目标用户：有一定股票投资经验但缺少系统化分析能力的个人投资者。

### 核心用户故事

1. 用户每天早上打开应用，看到今日推荐的 3-5 只股票，每只有一句话摘要和可展开的详细分析
2. 用户可以记录自己的持仓（手动输入），系统据此做个性化过滤（不重复推荐已持有的股票）并对持仓股票的重大事件发出异动提醒
3. 用户可以查看历史推荐的事后表现（T+1、T+5 收益追踪），建立对系统的信任

## Multi-Agent Architecture

系统由 4 个 Agent + 1 个 Orchestrator 组成：

- **Data Agent** — 市场数据 ETL。数据源为 AKShare（免费）。覆盖：股票列表同步、日线行情拉取、技术指标计算（MA/MACD/RSI/布林带/ATR）、基本面数据拉取。不含分析逻辑。
- **Event Agent** — 新闻/公告抓取 + LLM 催化剂分析。Scanner 子模块（AKShare 抓取）+ Analyzer 子模块（LLM 结构化分析，输出 sentiment/impact_score/catalyst_type 等字段）。
- **Portfolio Agent** — 用户持仓管理 + 异动监控。持仓股票出现重大事件（impact_score >= 6）时生成 alert。
- **Reporting Agent** — 生成面向用户的推荐理由（调用 LLM）+ 邮件推送内容渲染。
- **Orchestrator** — 调度中枢（非 Agent）。负责：量化筛选引擎（两层漏斗）、综合评分（量化 60% + 催化剂 40%）、行业分散化、反疲劳机制、每日推荐流水线编排、定时任务注册和管理。

### 每日运行流水线

| 时间 | 步骤 |
|------|------|
| 15:30 | Data Agent 拉取当日收盘行情 |
| 16:00 | Orchestrator 执行量化筛选，更新关注池（Top 50） |
| 16:30 | Data Agent 计算技术指标 |
| 06:30 | Event Agent 扫描合并事件（关注池 + 用户持仓去重后统一扫描） |
| 07:30 | Orchestrator 综合评分 → Top 5 → Reporting Agent 生成推荐理由 → 个性化过滤 → 写入用户推荐 |
| 08:00 | 推送通知（应用内 + 邮件） |
| 15:45 | 更新历史推荐的事后表现（T+1 / T+5 收益） |

### 量化筛选引擎（Orchestrator 核心）

**第一层——硬性条件过滤**（~5000 → ~1000）：排除 ST、次新股（上市<60日）、日均成交额<5000万、近5日有涨跌停、停牌、北交所。全部在 SQL 中完成。

**第二层——多因子打分**（~1000 → Top 50 关注池）：6 个因子，行业内 Z-score 标准化后加权汇总。

| 因子 | 权重 | 说明 |
|------|------|------|
| 动量 | 25% | 近20日涨幅（排除近5日，避免追高） |
| 成交量趋势 | 15% | 5日均量/20日均量 |
| 估值 | 20% | PE_TTM 行业内分位数 |
| 盈利质量 | 20% | ROE + 毛利率 + 经营现金流/净利润 |
| 波动率 | 10% | 近20日日收益率标准差（越低越好） |
| 技术形态 | 10% | 布林带位置 + MACD 金叉/死叉 |

关注池 → 最终推荐还会做：**行业分散化**（Top 5 中同行业不超过 2 只）、**反疲劳**（5天内已推荐2次的降级，除非有新催化剂）。

### 关键设计决策

1. **关注池与持仓合并扫描** — 每日 06:30 将关注池股票 ID 和所有用户持仓股票 ID 取并集去重后统一调用 Event Agent 扫描，避免重复且确保持仓股票也有事件覆盖。
2. **推荐分两层表** — `recommendations`（全局推荐，每日 5 条，不区分用户）+ `user_recommendations`（个性化推荐，过滤掉用户已持有的股票）。
3. **LLM 调用集中在两处** — Event Agent 的催化剂分析、Reporting Agent 的推荐理由生成。其他所有逻辑（筛选、评分、排序）都是确定性的 Python/SQL 计算。
4. **定时任务用 APScheduler**（MVP 阶段） — 通过 SQLAlchemyJobStore 持久化到 PostgreSQL，在 FastAPI lifespan 中启动。
5. **交易日判断** — A 股有节假日调休，系统启动时加载全年交易日历到内存，每个 job 执行前先检查。

## Project Structure

This is a pnpm monorepo managed by Turbo with two applications:

- `apps/web` - Next.js 16 frontend (React 19, TypeScript, Tailwind CSS 4, Clerk auth, next-intl i18n)
- `apps/api` - Python FastAPI backend (Python 3.12+, SQLAlchemy async, Alembic, APScheduler, LangChain)
- `packages/` - Shared packages (currently empty)

## Development Commands

All commands should be run from the repository root:

```bash
# Install dependencies
pnpm install

# Start both apps in development mode
pnpm dev

# Build all apps
pnpm build

# Lint all apps
pnpm lint
```

### Web App (Next.js)

Located in `apps/web/`:

```bash
# Development server runs on http://localhost:3000
cd apps/web && pnpm dev

# Build for production
cd apps/web && pnpm build

# Start production server
cd apps/web && pnpm start

# Lint with ESLint
cd apps/web && pnpm lint
```

### API App (FastAPI)

Located in `apps/api/`. Uses `uv` for Python package management:

```bash
# Development server runs on http://localhost:8000 with hot reload
cd apps/api && pnpm dev

# Lint with Ruff
cd apps/api && pnpm lint

# Database migrations
cd apps/api && pnpm db:migrate              # Run pending migrations
cd apps/api && pnpm db:rollback             # Rollback one migration
cd apps/api && pnpm db:revision "description"  # Create new migration (autogenerate)
```

## Web Architecture

Located in `apps/web/src/`:

- **`app/`** - Next.js App Router pages and layouts
  - `layout.tsx` - Root layout (ClerkProvider, global CSS)
  - `page.tsx` - Root redirect to `/zh`
  - `[locale]/layout.tsx` - Locale layout (NextIntlClientProvider)
  - `[locale]/page.tsx` - Landing page (hero, product intro, workflow)
  - `[locale]/dashboard/` - Protected dashboard (requires auth)
- **`components/`** - Shared components (e.g. `LanguageSwitcher`)
- **`middleware.ts`** - Clerk auth + next-intl locale middleware

### Key Libraries

| Library | Purpose |
|---------|---------|
| `@clerk/nextjs` | Authentication (sign-in, user management, protected routes) |
| `next-intl` | i18n with `zh`/`en` locales, messages in `messages/*.json` |
| `framer-motion` | Page animations |
| `lucide-react` | Icons |
| `tailwindcss` v4 | Styling |

### i18n (next-intl)

- Locales: `zh`, `en` (default: `en`)
- Messages: `apps/web/messages/zh.json`, `apps/web/messages/en.json`
- Config: `i18n.ts` (root), `i18n/config.ts`, `i18n/request.ts`
- Navigation helpers: `navigation.ts` (`Link`, `redirect`, `usePathname`, `useRouter`)
- Locale prefix strategy: `as-needed`

### Auth (Clerk)

- `ClerkProvider` wraps root layout
- Protected routes: `/(.*)/dashboard(.*)`, `/dashboard(.*)`
- Signed-in users on home page are redirected to `/dashboard`
- Clerk webhooks synced to API backend (`user.created`, `user.updated`, `user.deleted`)

## API Architecture (Layered)

The API follows a layered architecture under `apps/api/src/`:

- **`core/`** - Infrastructure
  - `config.py` - Pydantic Settings (`DATABASE_URL`, `CLERK_WEBHOOK_SIGNING_SECRET`, `CLERK_JWKS_URL`, `OPENROUTER_API_KEY`, `LLM_MODEL`, `LLM_TEMPERATURE`, `LLM_MAX_TOKENS`, `DEBUG`, `API_V1_PREFIX`)
  - `database.py` - Async engine (asyncpg), `async_session`, `get_db`
  - `exceptions.py` - `AppException`, `NotFoundException`, `AlreadyExistsException`
  - `middleware.py` - `RequestLoggingMiddleware` (logging + `X-Process-Time` header)
  - `auth.py` - Clerk JWT authentication (`get_current_user` dependency, JWKS public key caching, Bearer token verification)
  - `scheduler.py` - APScheduler (BackgroundScheduler, SQLAlchemy job store, heartbeat + data agent + orchestrator + event agent + recommendation jobs)
  - `llm.py` - LangChain + OpenRouter LLM 封装 (`get_llm()` 工厂函数, `chat_json()` 结构化 JSON 调用)
- **`models/`** - SQLAlchemy ORM models
  - `base.py` - `Base`, `UUIDMixin`, `TimestampMixin`
  - `user.py` - `User` (clerk_id, email, username, first_name, last_name, avatar_url, is_active)
  - `stock.py` - `Stock` (market=CN_A/US/JP/KR/CRYPTO, exchange=SH/SZ/BJ/...), `StockDailyQuote`, `StockTechnicalIndicator`, `StockFundamental` (integer PKs)
  - `event.py` - `StockEvent` (事件表：新闻/公告, LLM 分析结果 sentiment/impact_score/catalyst_type 等)
  - `watchlist.py` - `Watchlist` (关注池, status=active/removed, factor_scores JSONB, catalyst_summary JSONB), `WatchlistSnapshot` (每日快照)
  - `recommendation.py` - `Recommendation` (全局推荐, 含评分/理由/事后表现), `UserRecommendation` (用户个性化推荐, user_id UUID FK)
  - `portfolio.py` - `Portfolio` (用户组合, user_id UUID FK), `PortfolioHolding` (持仓明细, stock_id INT FK, quantity/avg_cost), `PortfolioAlert` (异动提醒, event_id INT FK, alert_type/is_read)
- **`agents/`** - Agent modules
  - `screener_config.py` - Screening engine constants (thresholds, weights, rate limits — no magic numbers)
  - `data_agent/` - Data Agent (market data ETL, no analysis logic)
    - `providers/akshare_provider.py` - All AKShare API calls centralized here (swap-friendly for future data sources)
    - `fetcher.py` - `DataAgent` class: stock list sync, daily quotes, history backfill
    - `indicators.py` - Technical indicator computation (MA/MACD/RSI/Bollinger/ATR, pure pandas)
    - `fundamentals.py` - Fundamental data fetch (batch valuation + per-stock financials)
    - `trading_calendar.py` - A-share trading calendar (in-memory cache)
    - `jobs.py` - APScheduler job wrappers (daily_quotes, technical_indicators, weekly_sync)
  - `event_agent/` - Event Agent (新闻扫描 + LLM 催化剂分析)
    - `scanner.py` - `EventScanner` class: AKShare 新闻抓取, 去重入库 (ON CONFLICT DO NOTHING)
    - `analyzer.py` - `CatalystAnalyzer` class: LLM 批量分析 (同一股票事件打包), 结构化 JSON 输出 (sentiment/impact_score/catalyst_type)
    - `jobs.py` - APScheduler job wrapper (morning_event_scan: 合并关注池+持仓扫描 → 分析 → 更新 watchlist catalyst_summary → 持仓事件联动 alert)
  - `portfolio_agent/` - Portfolio Agent (用户持仓管理 + 异动监控)
    - `monitor.py` - `PortfolioMonitor` class: 持仓事件联动 (impact_score >= 6 → 生成 PortfolioAlert, 内联在 morning_event_scan 末尾调用)
  - `reporting_agent/` - Reporting Agent (推荐理由生成, LLM)
    - `generator.py` - `RecommendationReportGenerator` class: 为推荐股票生成 reason_short + reason_detail (LLM via chat_json)
  - `orchestrator/` - Orchestrator (quantitative screening + recommendation pipeline)
    - `screener.py` - `StockScreener` class: Layer 1 hard filter (SQL) + Layer 2 multi-factor scoring (6 factors, industry Z-score) + watchlist diff update + daily pipeline
    - `scorer.py` - `RecommendationScorer` class: 综合评分 (quant 60% + catalyst 40%), 行业分散化, 反疲劳机制
    - `pipeline.py` - `daily_recommendation_pipeline()`: 综合评分 → LLM 理由生成 → 保存推荐 → 用户分发; `update_recommendation_performance()`: T+1/T+5 收益追踪
    - `jobs.py` - APScheduler job wrappers (daily_screening, daily_recommendation, rec_performance_tracking)
- **`schemas/`** - Pydantic request/response schemas
  - `base.py` - `BaseSchema`, `BaseReadSchema`
  - `user.py` - `UserCreate`, `UserUpdate`, `UserRead`
  - `recommendation.py` - `RecommendationRead`, `RecommendationListResponse`, `PipelineTriggerResponse`, `StockBrief`
  - `portfolio.py` - `PortfolioCreate`, `PortfolioRead`, `PortfolioDetailRead`, `PortfolioSummary`, `HoldingCreate`, `HoldingRead`, `HoldingUpdate`, `AlertRead`
- **`services/`** - Business logic layer
  - `user.py` - `UserService` (CRUD + Clerk-specific: `upsert_by_clerk_id`, `soft_delete_by_clerk_id`)
  - `portfolio.py` - `PortfolioService` (portfolio CRUD, holding CRUD with ownership check, P&L calculation from latest quotes, alert read/mark)
- **`routers/`** - API route handlers
  - `users.py` - `/api/v1/users` (list, get, create, update, delete)
  - `recommendations.py` - `/api/v1/recommendations` (trigger-pipeline, today, history)
  - `portfolio.py` - `/api/v1/portfolio` (get portfolio, add/update/remove holding, get alerts, mark read) — all endpoints require Clerk JWT auth
  - `webhooks.py` - `/api/webhooks/clerk` (Clerk webhook receiver via Svix)
- **`dependencies.py`** - FastAPI dependency injection (DB session, service factories, `CurrentUser` via Clerk JWT)
- **`main.py`** - App entry point, lifespan (trading calendar init, APScheduler start/stop for data agent + orchestrator + event agent + recommendation), middleware, router mounting, `/health` endpoint

### Key Libraries

| Library | Purpose |
|---------|---------|
| `fastapi` + `uvicorn` | Web framework + ASGI server |
| `sqlalchemy[asyncio]` + `asyncpg` | Async ORM + PostgreSQL driver |
| `alembic` | Database migrations |
| `pydantic-settings` | Environment config |
| `apscheduler` + `psycopg2-binary` | Background job scheduling (SQLAlchemy job store) |
| `svix` | Clerk webhook signature verification |
| `pyjwt[crypto]` + `httpx` | Clerk JWT verification (RS256 via JWKS) |
| `akshare` + `pandas` | A-share market data source + data processing |
| `langchain` + `langchain-openai` | LLM integration via OpenRouter (catalyst analysis in Event Agent) |
| `ruff` (dev) | Python linting |

### Database

PostgreSQL with SQLAlchemy 2.0 async + asyncpg. Migrations via Alembic (`apps/api/alembic/`).
Environment variables loaded from `.env` (dev) or `.env.prod` (prod). See `.env.example`.

Stock data tables (`stocks`, `stock_daily_quotes`, `stock_technical_indicators`, `stock_fundamentals`), event table (`stock_events`), watchlist tables (`watchlist`, `watchlist_snapshots`), recommendation tables (`recommendations`, `user_recommendations`), and portfolio tables (`portfolios`, `portfolio_holdings`, `portfolio_alerts`) use integer auto-increment PKs for performance with high-volume data and frequent JOINs. `user_recommendations.user_id`, `portfolios.user_id`, and `portfolio_alerts.user_id` are UUID FKs referencing `users.id`.

### Scheduled Jobs

| Job ID | Schedule | Owner | Description |
|--------|----------|-------|-------------|
| `daily_quotes` | Weekdays 15:30 | Data Agent | Fetch daily closing quotes for all stocks |
| `daily_screening` | Weekdays 16:00 | Orchestrator | Layer 1 hard filter + Layer 2 multi-factor scoring → update watchlist (Top 50) |
| `technical_indicators` | Weekdays 16:30 | Data Agent | Compute technical indicators for all stocks |
| `weekly_stock_sync` | Monday 17:00 | Data Agent | Sync stock list + industry mapping + valuation data |
| `morning_event_scan` | Weekdays 06:30 | Event Agent | 合并扫描(关注池+持仓) → AKShare 新闻抓取 → LLM 催化剂分析 → 更新 watchlist catalyst_summary → 持仓异动 alert 生成 |
| `daily_recommendation` | Weekdays 07:30 | Orchestrator | 综合评分 → LLM 推荐理由生成 → 保存全局推荐 → 用户个性化推荐分发 |
| `rec_performance_tracking` | Weekdays 15:45 | Orchestrator | 更新历史推荐的 T+1/T+5 事后表现（收益率追踪） |

Each job checks the trading calendar before executing (non-trading days are skipped).

### Backfill Script

```bash
cd apps/api && uv run python -m scripts.backfill_history --days 180
cd apps/api && uv run python -m scripts.backfill_history --step quotes  # Run specific step only
```

### Adding a New Entity

1. Create model in `src/models/new_entity.py`, re-export in `src/models/__init__.py`
2. Create schemas in `src/schemas/new_entity.py`, re-export in `src/schemas/__init__.py`
3. Create service in `src/services/new_entity.py`
4. Add dependency in `src/dependencies.py`
5. Create router in `src/routers/new_entity.py`, mount in `src/main.py`
6. Generate migration: `pnpm db:revision "add new_entity table"`

## Code Style & Linting

- **Web**: ESLint with `eslint-config-next` (core-web-vitals and typescript configs)
- **API**: Ruff for Python linting

## Path Aliases

- **Web**: `@/*` maps to `./src/*` (configured in `apps/web/tsconfig.json`)
- **API**: Use absolute imports from `src/` (e.g., `from src.core.config import settings`)
