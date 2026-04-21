# Scheduler & Public Board Module Refactoring Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Clean up dead code, fix global side-effects, improve thread safety, and unify concurrency strategy in the scheduler and public_board modules.

**Architecture:** Incremental refactoring — each task produces a working, testable state. No behavioral changes to external APIs. Dead code removal first, then scoping global side-effects, then concurrency improvements.

**Tech Stack:** Python 3.12+, FastAPI, APScheduler, Redis, requests, akshare, pytest

---

### Task 1: Remove dead code from scheduler.py ✅ DONE

**Files:**
- Modify: `apps/api/src/core/scheduler.py`

Delete the four empty-shell register functions and all commented-out code inside them. These functions have zero callers outside the file:

- `register_data_agent_jobs()` (lines 102–129)
- `register_orchestrator_jobs()` (lines 145–159)
- `register_event_agent_jobs()` (lines 162–176)
- `register_recommendation_jobs()` (lines 179–206)

Also remove these now-unused import aliases that only the deleted functions reference (check first):
- No additional imports to remove — the deleted functions didn't import anything beyond what active code uses.

- [x] **Step 1: Delete the four dead register functions**

Remove lines 102–206 from `apps/api/src/core/scheduler.py`. The file should end after `register_public_market_jobs` (line 100).

- [x] **Step 2: Run linter** — PASS
- [x] **Step 3: Run existing tests** — PASS (21 tests)
- [x] **Step 4: Commit** — Not yet committed (batched with other P0 changes)

---

### Task 2: Remove unused `_format_fx` and merge `normalize_metric` into `_build_metric` ✅ DONE

**Files:**
- Modify: `apps/api/src/services/public_board.py`
- Modify: `apps/api/tests/test_public_board_service.py`

`_format_fx` (line 666–667) is never called — delete it.

`normalize_metric` (lines 133–159) returns a raw `dict` that `_build_metric` (lines 358–375) immediately unpacks into `MarketMetric(...)`. Merge them: make `_build_metric` do the logic directly and remove `normalize_metric`.

- [x] **Step 1: Delete `_format_fx`** — Deleted unused function
- [x] **Step 2: Inline `normalize_metric` logic into `_build_metric`** — Done, deleted `normalize_metric`
- [x] **Step 3: Update test** — Renamed test, changed dict assertions to attribute assertions
- [x] **Step 4: Run tests** — PASS (5 tests in test_public_board_service.py)
- [x] **Step 5: Commit** — Not yet committed (batched)

---

### Task 3: Scope environment variable and monkey-patch side effects ✅ DONE

**Files:**
- Modify: `apps/api/src/services/public_board.py`

The module-level side effects (lines 20–25 and line 60) modify `os.environ` and monkey-patch `requests.get` / `requests.Session.get` at import time. This is dangerous for any co-located code that relies on proxy settings or the original `requests` behavior.

Strategy:
- Remove module-level `os.environ.pop` calls and `_install_akshare_proxy_bypass()`.
- Create a helper `_without_proxy()` that temporarily disables proxies inside akshare calls only.
- Use `unittest.mock.patch.dict` for env var scoping in the helper.
- For Yahoo Finance calls, the `_get_no_proxy_session()` already returns a session with `trust_env=False` — that's fine, keep it.
- The `_SESSION_GET_NO_PROXY` monkey-patch on `requests.Session.get` is needed because akshare calls `requests.Session().get(...)` internally. Instead of globally monkey-patching, wrap akshare calls in a context manager.

- [x] **Step 1: Removed module-level `os.environ.pop` calls and `_install_akshare_proxy_bypass()` call**
- [x] **Step 2: Created `_no_proxy_env()` sync context manager** — Replaces all monkey-patching and module-level env var pops
- [x] **Step 3: Wrapped `_load_quote_snapshot` body with `_no_proxy_env()`**
- [x] **Step 4: Removed `_NO_PROXY_SESSION_GET`, `_SESSION_GET_NO_PROXY`, `_original_requests_get`, `_original_requests_session_get`, `_install_akshare_proxy_bypass`** — Kept `_get_no_proxy_session()` for Yahoo Finance direct HTTP calls
- [x] **Step 5: Run tests** — PASS (21 tests)
- [x] **Step 6: Run linter** — PASS
- [x] **Step 7: Commit** — Not yet committed (batched)

---

### Task 4: Use shared Redis connection in scheduler instead of creating new connections per tick ✅ DONE

**Files:**
- Modify: `apps/api/src/core/scheduler.py`
- Modify: `apps/api/src/run_scheduler.py`

Currently `_scheduler_redis` creates a new Redis connection each time `redis=None` is passed. The `run_scheduler.py` calls the async functions without passing a Redis instance, so every scheduler tick opens and closes a Redis connection.

Strategy: Replace the per-tick context manager with a lazy-initialized shared Redis connection that persists across ticks. Close it only on scheduler shutdown.

- [x] **Step 1: Add module-level `get_scheduler_redis()` and `close_scheduler_redis()` to scheduler.py**
- [x] **Step 2: Update `refresh_market_macro_snapshot` and `refresh_market_assets_snapshot` to use `redis or await get_scheduler_redis()`** — Removed `_scheduler_redis` context manager
- [x] **Step 3: Update `run_scheduler.py` to close Redis on shutdown** — Added `close_scheduler_redis()` call in `finally` block
- [x] **Step 4: Update test** — Replaced `test_refresh_market_macro_snapshot_closes_internal_redis_client` with `test_get_scheduler_redis_reuses_connection` and `test_refresh_market_macro_snapshot_uses_shared_redis`
- [x] **Step 5: Run tests** — PASS (22 tests)
- [x] **Step 6: Commit** — Not yet committed (batched)

---

### Task 5: Fix cache lock granularity and simplify caching functions ✅ DONE

**Files:**
- Modify: `apps/api/src/services/public_board.py`

The three caching functions (`_get_cached_treasury_df`, `_get_cached_global_index_df`, `_get_cached_crypto_df`) had a race condition: they release the lock between the read-check and the write, allowing duplicate upstream fetches. Simplified by holding the lock for the full check-then-fetch-then-write cycle.

- [x] **Step 1: Rewrite `_get_cached_treasury_df`** — Holds lock for entire check-fetch-write cycle
- [x] **Step 2: Rewrite `_get_cached_global_index_df`** — Holds lock for entire check-fetch-write cycle
- [x] **Step 3: Rewrite `_get_cached_crypto_df`** — Holds lock for entire check-fetch-write cycle
- [x] **Step 4: Run tests** — PASS (22 tests)
- [x] **Step 5: Commit** — Not yet committed (batched)

---

### Task 6: Unify concurrency strategy in `build_assets_snapshot` ✅ DONE

**Files:**
- Modify: `apps/api/src/services/public_board.py`

`build_macro_snapshot` uses `asyncio.gather` for parallel fetching, but `build_assets_snapshot` used sequential `await + asyncio.sleep` calls totaling ~8s. Replaced with `asyncio.gather`-based parallel fetching. The `_FETCH_SEMAPHORE` already limits concurrency to 3.

- [x] **Step 1: Remove `YAHOO_FETCH_DELAY_SECONDS` constant** — Deleted line `YAHOO_FETCH_DELAY_SECONDS = 2.0`
- [x] **Step 2: Rewrite `build_assets_snapshot` to use `asyncio.gather`** — Replaced sequential awaits with parallel gather
- [x] **Step 3: Run tests** — PASS (5 tests in test_public_board_service.py)
- [x] **Step 4: Commit** — Not yet committed (batched)

---

### Task 7: Consolidate symbol constants and remove redundancy ✅ DONE

**Files:**
- Modify: `apps/api/src/services/public_board.py`

`YAHOO_SYMBOLS` (Yahoo symbols → same Yahoo symbols, mostly identity mappings) was confusing. Replaced with `YAHOO_CHART_SYMBOLS: frozenset[str]` — a set of which Yahoo symbols have chart API support.

- [x] **Step 1: Replace `YAHOO_SYMBOLS` with `YAHOO_CHART_SYMBOLS`** — `frozenset` of Yahoo chart symbols
- [x] **Step 2: Update `_load_quote_snapshot`** — Changed `symbol in YAHOO_SYMBOLS` to `symbol in YAHOO_CHART_SYMBOLS`
- [x] **Step 3: Simplify `_load_yahoo_quote`** — Removed `YAHOO_SYMBOLS.get(symbol)` lookup, symbol is passed directly
- [x] **Step 4: Run tests** — PASS (22 tests)
- [x] **Step 5: Commit** — Not yet committed (batched)

---

### Task 8: Replace hardcoded timeout in `_safe_fetch_quote` with constant ✅ DONE (merged into Task 2)

**Files:**
- Modify: `apps/api/src/services/public_board.py`

Line 384 uses `timeout=10.0` as a magic number, while `YAHOO_FETCH_TIMEOUT_SECONDS` is defined but only used in `_load_yahoo_quote`. Use the constant consistently.

- [x] **Step 1: Added `FETCH_OVERALL_TIMEOUT_SECONDS = 15.0` constant** — Replaced hardcoded `timeout=10.0` in `_safe_fetch_quote`
- [x] **Step 2: Updated test** — Changed monkeypatch target from `YFINANCE_FETCH_TIMEOUT_SECONDS` to `FETCH_OVERALL_TIMEOUT_SECONDS`
- [x] **Step 3: Run tests** — PASS
- [x] **Commit** — Not yet committed (batched)

---

## Summary of priority order

| Task | Priority | Risk | Description |
|------|----------|------|-------------|
| 1 | P0 | Low | Remove dead code (4 empty register functions + 70 lines of comments) ✅ |
| 2 | P0 | Low | Remove unused `_format_fn` and merge `normalize_metric` into `_build_metric` ✅ |
| 3 | P0 | Medium | Scope global env-var / monkey-patch side effects ✅ |
| 4 | P1 | Low | Shared Redis connection in scheduler ✅ |
| 5 | P1 | Medium | Fix cache lock granularity (thread safety) ✅ |
| 6 | P2 | Low | Unify concurrency strategy (asyncio.gather for assets) ✅ |
| 7 | P2 | Low | Consolidate symbol constants ✅ |
| 8 | P3 | Low | Replace hardcoded timeout magic number ✅ (merged into Task 2) |

All tasks complete. Changes are uncommitted and batched.