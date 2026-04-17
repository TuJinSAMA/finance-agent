# AlphaDesk Market Board Pivot Design

## 1. Context

Current product default entry is landing + authenticated dashboard flow.  
Current business issue is low retention and conversion due to early login friction before users see immediate value.

This design pivots the entry path to a public market board page:
- First-time users can see useful market context without login.
- Existing recommendation workflow remains available behind authenticated pages.

## 2. Goals

1. Make public market insight the default first-screen experience.
2. Reduce login friction while preserving authenticated recommendation workflows.
3. Rename existing dashboard semantics to "Recommendations" for clearer product language.
4. Keep migration low-risk with compatibility redirects and feature-flagged rollback.

## 3. Non-Goals

1. No redesign of recommendation logic or backend scoring pipeline.
2. No portfolio feature expansion in this phase.
3. No multi-provider public board aggregation in v1 (single provider only).

## 4. Chosen Product Direction

### 4.1 Entry and Navigation

1. Add new public page: `/{locale}/board` (no login required).
2. Set default site entry (`/` and `/{locale}`) to `/{locale}/board`.
3. Rename current dashboard route and semantics:
   - `/{locale}/dashboard` -> `/{locale}/recommendations`
4. Keep backward compatibility:
   - `/{locale}/dashboard` redirects to `/{locale}/recommendations`.
5. Keep current landing page but hide from default path:
   - move to `/{locale}/landing` as a reserve page.

### 4.2 Authentication Boundaries

Only user-domain pages remain protected:
- `/{locale}/recommendations`
- `/{locale}/portfolio`
- other existing authenticated workflow pages

Public board remains fully accessible without Clerk auth.

## 5. Public Board Information Architecture (v1)

Board format follows a compact global-macro snapshot:

1. Header
- Date (`YYYY-MM-DD`)
- Market state label (example: `Risk-Off 偏避险`)
- Last updated time (`as_of`)

2. Macro indicators
- VIX
- US 10Y yield
- DXY
- 2Y-10Y spread

3. Key assets
- S&P 500
- NASDAQ
- Gold
- WTI crude
- BTC

4. Custom block
- CSI 300
- USD/CNY

## 6. Backend API Design

### 6.1 Endpoint

- `GET /api/v1/public/market-board`
- Unauthenticated, read-only, safe for homepage use.

### 6.2 Response Shape

Response is structured by rendering blocks:
- `market_state`: date, label, summary text
- `macro`: list of macro indicators
- `assets`: list of key assets
- `custom`: list of custom watch indicators
- `as_of`: snapshot timestamp
- `source`: provider info

### 6.3 Data Source Policy (Locked for v1)

V1 data source is **yfinance only**.

No AKShare/Tushare/multi-provider fallback in this phase.

Proposed ticker mapping (v1):
- VIX: `^VIX`
- US10Y: `^TNX`
- DXY: `DX-Y.NYB`
- S&P 500: `^GSPC`
- NASDAQ: `^IXIC`
- Gold: `GC=F`
- WTI: `CL=F`
- BTC: `BTC-USD`
- CSI 300: `000300.SS`
- USD/CNY: `CNY=X`

2Y-10Y spread:
- compute from available yfinance Treasury proxies
- if missing one leg, return `unavailable` for spread field only

## 7. Caching and Resilience

### 7.1 Cache

- Server-side cache with TTL 10 minutes (acceptable range: 5-15 minutes).
- Cache key is single global board snapshot for v1.

### 7.2 Partial Failure Handling

1. Single metric failure must not fail the entire response.
2. Failed metrics return availability marker (`unavailable` or stale metadata).
3. If live refresh fails completely, return the latest successful cached snapshot.

### 7.3 Frontend Degradation

1. Show skeleton while loading.
2. Show metric-level placeholder for unavailable values.
3. Show `as_of` clearly when data is stale.

## 8. Market State Labeling (v1 Rule-Based)

Use deterministic rule logic for explainability in v1:
- Example signal blend: high VIX + rising yields + equity weakness -> `Risk-Off 偏避险`
- keep output explicit and traceable

No LLM judgment in v1 board state generation.

## 9. Frontend Behavior

### 9.1 New Board Page

- Add new board page under locale routes.
- Render in dense card rows matching compact terminal-like snapshot style.
- Display date, market-state tag, and update time at top.

### 9.2 Recommendations Page Rename

- Keep existing dashboard content logic.
- Rename route and navigation label to Recommendations (推荐股票).

### 9.3 Conversion Entry

On board page:
- Primary CTA: `登录查看个性化推荐`
- Supporting text: public macro view vs logged-in personalized recommendations

No forced login modal in v1.

## 10. Middleware and Routing Migration

1. Update middleware default redirect target from dashboard/landing flow to board.
2. Keep auth protection matcher scoped to recommendation/portfolio/private pages only.
3. Add compatibility redirect from old dashboard path to recommendations.

## 11. Rollout and Rollback

### 11.1 Rollout

Use a feature switch:
- `FEATURE_PUBLIC_BOARD`

When enabled:
- board is default entry
- recommendations page uses new route naming

### 11.2 Rollback

If board API stability issues occur:
1. Disable `FEATURE_PUBLIC_BOARD`.
2. Restore previous default entry behavior.
3. Keep board route available but non-default.

## 12. Acceptance Criteria

1. Unauthenticated visit to `/` lands on `/{locale}/board`.
2. Board renders without login and shows global macro snapshot blocks.
3. Authenticated users can still access recommendations and portfolio pages.
4. `/{locale}/dashboard` redirects to `/{locale}/recommendations`.
5. Board API returns renderable payload even when one or more metrics fail.
6. Board UI displays data timestamp and handles stale/unavailable fields gracefully.

## 13. Scope Check

This specification is intentionally constrained to a single implementation cycle:
- routing pivot
- new public board page
- yfinance-only public board API
- dashboard semantic rename to recommendations

No additional product-surface expansion is included.
