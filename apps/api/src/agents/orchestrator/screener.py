"""
量化筛选引擎 — Orchestrator 核心。
纯 SQL + Python 数值计算，不涉及 LLM。

两层漏斗：
  Layer 1  硬性条件过滤  ~5000 → ~1000
  Layer 2  多因子打分    ~1000 → Top 50（关注池）
"""

import logging
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.agents.screener_config import screener_config as cfg
from src.models.stock import (
    Stock,
    StockDailyQuote,
    StockFundamental,
    StockTechnicalIndicator,
)
from src.models.watchlist import Watchlist, WatchlistSnapshot

logger = logging.getLogger(__name__)


def _to_float(val) -> float:
    if val is None:
        return 0.0
    if isinstance(val, Decimal):
        return float(val)
    return float(val)


class StockScreener:
    """量化筛选引擎。"""

    # ── Layer 1 ────────────────────────────────────────

    async def layer1_hard_filter(
        self, db: AsyncSession, trade_date: date
    ) -> list[int]:
        """
        硬性条件过滤。约 5000 → 800-1200 只。

        排除：ST、退市整理、北交所、次新股（<60 个交易日）、
        日均成交额不足、近 5 日有涨跌停、停牌。
        """
        date_20d_ago = trade_date - timedelta(days=30)
        date_5d_ago = trade_date - timedelta(days=8)
        date_60d_ago = trade_date - timedelta(days=90)

        excluded_exchanges = ",".join(f"'{e}'" for e in cfg.excluded_exchanges)

        query = text(f"""
            SELECT s.id
            FROM stocks s
            JOIN (
                SELECT stock_id, AVG(amount) AS avg_amount_20d
                FROM stock_daily_quotes
                WHERE trade_date > :date_20d_ago
                GROUP BY stock_id
            ) liquidity ON s.id = liquidity.stock_id
            WHERE s.is_st = FALSE
              AND s.is_delisting = FALSE
              AND s.exchange NOT IN ({excluded_exchanges})
              AND (s.list_date IS NULL OR s.list_date < :date_60d_ago)
              AND liquidity.avg_amount_20d >= :min_amount
              AND s.id NOT IN (
                  SELECT DISTINCT stock_id
                  FROM stock_daily_quotes
                  WHERE trade_date > :date_5d_ago
                    AND (pct_change >= 9.9 OR pct_change <= -9.9)
              )
              AND s.id IN (
                  SELECT stock_id
                  FROM stock_daily_quotes
                  WHERE trade_date = (
                      SELECT MAX(trade_date) FROM stock_daily_quotes
                      WHERE trade_date <= :trade_date
                  )
                  AND volume > 0
              )
        """)

        result = await db.execute(
            query,
            {
                "date_20d_ago": date_20d_ago,
                "date_5d_ago": date_5d_ago,
                "date_60d_ago": date_60d_ago,
                "min_amount": cfg.min_daily_amount,
                "trade_date": trade_date,
            },
        )
        stock_ids = [row[0] for row in result.fetchall()]
        logger.info(
            "Layer 1 hard filter: %d stocks passed (trade_date=%s)",
            len(stock_ids),
            trade_date,
        )
        return stock_ids

    # ── Layer 2 ────────────────────────────────────────

    async def layer2_multi_factor_scoring(
        self,
        db: AsyncSession,
        stock_ids: list[int],
        trade_date: date,
    ) -> list[dict]:
        """
        多因子打分。对 Layer 1 筛出的股票做 6 因子评分，
        行业内 Z-score 标准化后加权汇总，返回 Top 50。
        """
        quotes_map = await self._batch_get_recent_quotes(
            db, stock_ids, trade_date, days=30
        )
        technicals_map = await self._batch_get_technicals(db, stock_ids, trade_date)
        fundamentals_map = await self._batch_get_fundamentals(db, stock_ids)

        industry_map = await self._batch_get_industries(db, stock_ids)

        scores: list[dict] = []
        for stock_id in stock_ids:
            q = quotes_map.get(stock_id)
            t = technicals_map.get(stock_id)
            f = fundamentals_map.get(stock_id)

            if not q or len(q) < cfg.momentum_window:
                continue

            factors = {
                "momentum": self._calc_momentum(q),
                "volume_trend": self._calc_volume_trend(q),
                "valuation": self._calc_valuation(f),
                "quality": self._calc_quality(f),
                "volatility": self._calc_volatility(q),
                "technical": self._calc_technical(t, q),
            }

            scores.append(
                {
                    "stock_id": stock_id,
                    "industry": industry_map.get(stock_id, "unknown"),
                    "factors": factors,
                }
            )

        scores = self._industry_zscore_normalize(scores)

        weights = {
            "momentum": cfg.weight_momentum,
            "volume_trend": cfg.weight_volume_trend,
            "valuation": cfg.weight_valuation,
            "quality": cfg.weight_profitability,
            "volatility": cfg.weight_volatility,
            "technical": cfg.weight_technical,
        }
        for s in scores:
            s["quant_score"] = sum(
                s["factors"][k] * weights[k] for k in weights
            )

        scores.sort(key=lambda x: x["quant_score"], reverse=True)
        top = scores[: cfg.watchlist_size]

        logger.info(
            "Layer 2 scoring: %d stocks scored, Top %d selected (trade_date=%s)",
            len(scores),
            len(top),
            trade_date,
        )
        return top

    # ── Watchlist Update ───────────────────────────────

    async def update_watchlist(
        self,
        db: AsyncSession,
        trade_date: date,
        top50: list[dict],
    ) -> dict:
        """
        更新关注池（diff 模式）并保存快照。
        返回 {"added": int, "removed": int, "kept": int}。
        """
        new_stock_ids = {s["stock_id"] for s in top50}
        score_lookup = {s["stock_id"]: s for s in top50}

        current_active = await db.execute(
            select(Watchlist).where(Watchlist.status == "active")
        )
        current_records = {w.stock_id: w for w in current_active.scalars().all()}
        current_ids = set(current_records.keys())

        added_ids = new_stock_ids - current_ids
        removed_ids = current_ids - new_stock_ids
        kept_ids = new_stock_ids & current_ids

        for sid in added_ids:
            s = score_lookup[sid]
            db.add(
                Watchlist(
                    stock_id=sid,
                    added_date=trade_date,
                    quant_score=round(s["quant_score"], 4),
                    factor_scores=self._round_factors(s["factors"]),
                    status="active",
                )
            )

        if removed_ids:
            await db.execute(
                update(Watchlist)
                .where(Watchlist.stock_id.in_(removed_ids))
                .where(Watchlist.status == "active")
                .values(
                    status="removed",
                    removed_date=trade_date,
                    removed_reason="跌出Top50",
                )
            )

        for sid in kept_ids:
            s = score_lookup[sid]
            record = current_records[sid]
            record.quant_score = round(s["quant_score"], 4)
            record.factor_scores = self._round_factors(s["factors"])

        snapshots = []
        for rank, s in enumerate(top50, 1):
            snapshots.append(
                {
                    "snapshot_date": trade_date,
                    "stock_id": s["stock_id"],
                    "quant_score": round(s["quant_score"], 4),
                    "rank_in_list": rank,
                }
            )

        if snapshots:
            stmt = pg_insert(WatchlistSnapshot).values(snapshots)
            stmt = stmt.on_conflict_do_update(
                index_elements=["snapshot_date", "stock_id"],
                set_={
                    "quant_score": stmt.excluded.quant_score,
                    "rank_in_list": stmt.excluded.rank_in_list,
                },
            )
            await db.execute(stmt)

        await db.flush()

        summary = {
            "added": len(added_ids),
            "removed": len(removed_ids),
            "kept": len(kept_ids),
        }
        logger.info("Watchlist updated: %s (trade_date=%s)", summary, trade_date)
        return summary

    # ── Pipeline ───────────────────────────────────────

    async def run_daily_screening(
        self, db: AsyncSession, trade_date: date
    ) -> dict:
        """完整筛选流水线：Layer 1 → Layer 2 → 更新关注池。"""
        logger.info("Starting daily screening for %s", trade_date)

        stock_ids = await self.layer1_hard_filter(db, trade_date)
        if not stock_ids:
            logger.warning("Layer 1 returned 0 stocks, aborting screening")
            return {"layer1_count": 0, "layer2_count": 0, "watchlist": {}}

        top50 = await self.layer2_multi_factor_scoring(db, stock_ids, trade_date)
        watchlist_summary = await self.update_watchlist(db, trade_date, top50)

        result = {
            "layer1_count": len(stock_ids),
            "layer2_count": len(top50),
            "watchlist": watchlist_summary,
        }
        logger.info("Daily screening completed: %s", result)
        return result

    # ── Batch Data Loaders ─────────────────────────────

    async def _batch_get_recent_quotes(
        self,
        db: AsyncSession,
        stock_ids: list[int],
        trade_date: date,
        days: int = 30,
    ) -> dict[int, list]:
        """批量获取近 N 天行情，按 stock_id 分组。"""
        date_from = trade_date - timedelta(days=int(days * 1.5))
        result_map: dict[int, list] = defaultdict(list)

        for chunk in self._chunked(stock_ids, cfg.db_batch_chunk_size):
            rows = await db.execute(
                select(
                    StockDailyQuote.stock_id,
                    StockDailyQuote.trade_date,
                    StockDailyQuote.close,
                    StockDailyQuote.volume,
                    StockDailyQuote.amount,
                    StockDailyQuote.pct_change,
                )
                .where(StockDailyQuote.stock_id.in_(chunk))
                .where(StockDailyQuote.trade_date > date_from)
                .where(StockDailyQuote.trade_date <= trade_date)
                .order_by(
                    StockDailyQuote.stock_id,
                    StockDailyQuote.trade_date.asc(),
                )
            )
            for row in rows.all():
                result_map[row[0]].append(row)

        return dict(result_map)

    async def _batch_get_technicals(
        self,
        db: AsyncSession,
        stock_ids: list[int],
        trade_date: date,
    ) -> dict[int, object]:
        """批量获取最新技术指标（trade_date 当天或之前最近的一条）。"""
        result_map: dict[int, object] = {}

        for chunk in self._chunked(stock_ids, cfg.db_batch_chunk_size):
            subq = (
                select(
                    StockTechnicalIndicator.stock_id,
                    StockTechnicalIndicator.trade_date,
                    StockTechnicalIndicator.macd,
                    StockTechnicalIndicator.macd_signal,
                    StockTechnicalIndicator.macd_hist,
                    StockTechnicalIndicator.boll_upper,
                    StockTechnicalIndicator.boll_mid,
                    StockTechnicalIndicator.boll_lower,
                )
                .where(StockTechnicalIndicator.stock_id.in_(chunk))
                .where(StockTechnicalIndicator.trade_date <= trade_date)
                .distinct(StockTechnicalIndicator.stock_id)
                .order_by(
                    StockTechnicalIndicator.stock_id,
                    StockTechnicalIndicator.trade_date.desc(),
                )
            )
            rows = await db.execute(subq)
            for row in rows.all():
                result_map[row[0]] = row

        return result_map

    async def _batch_get_fundamentals(
        self,
        db: AsyncSession,
        stock_ids: list[int],
    ) -> dict[int, object]:
        """批量获取最新基本面数据（每只股票取 report_date 最新的一条）。"""
        result_map: dict[int, object] = {}

        for chunk in self._chunked(stock_ids, cfg.db_batch_chunk_size):
            subq = (
                select(
                    StockFundamental.stock_id,
                    StockFundamental.pe_ttm,
                    StockFundamental.roe,
                    StockFundamental.gross_margin,
                    StockFundamental.net_margin,
                    StockFundamental.operating_cf,
                )
                .where(StockFundamental.stock_id.in_(chunk))
                .distinct(StockFundamental.stock_id)
                .order_by(
                    StockFundamental.stock_id,
                    StockFundamental.report_date.desc(),
                )
            )
            rows = await db.execute(subq)
            for row in rows.all():
                result_map[row[0]] = row

        return result_map

    async def _batch_get_industries(
        self,
        db: AsyncSession,
        stock_ids: list[int],
    ) -> dict[int, str]:
        """批量获取股票所属行业。"""
        result_map: dict[int, str] = {}
        for chunk in self._chunked(stock_ids, cfg.db_batch_chunk_size):
            rows = await db.execute(
                select(Stock.id, Stock.industry).where(Stock.id.in_(chunk))
            )
            for row in rows.all():
                result_map[row[0]] = row[1] or "unknown"
        return result_map

    # ── Factor Calculations ────────────────────────────

    @staticmethod
    def _calc_momentum(quotes: list) -> float:
        """近 20 日涨幅（排除最近 5 日），避免追高。"""
        n = len(quotes)
        if n < cfg.momentum_window:
            return 0.0

        recent_idx = n - cfg.momentum_exclude_recent - 1
        start_idx = max(0, n - cfg.momentum_window)

        close_start = _to_float(quotes[start_idx][2])
        close_end = _to_float(quotes[recent_idx][2])

        if close_start == 0:
            return 0.0
        return (close_end / close_start) - 1.0

    @staticmethod
    def _calc_volume_trend(quotes: list) -> float:
        """5 日均量 / 20 日均量，衡量放量程度。"""
        n = len(quotes)
        if n < cfg.volume_trend_long:
            return 1.0

        short_vols = [_to_float(q[3]) for q in quotes[-cfg.volume_trend_short:]]
        long_vols = [_to_float(q[3]) for q in quotes[-cfg.volume_trend_long:]]

        avg_short = sum(short_vols) / len(short_vols) if short_vols else 0
        avg_long = sum(long_vols) / len(long_vols) if long_vols else 0

        if avg_long == 0:
            return 1.0
        return avg_short / avg_long

    @staticmethod
    def _calc_valuation(fundamental) -> float:
        """PE_TTM 取负值（PE 越低越好）。无数据返回 0。"""
        if fundamental is None:
            return 0.0
        pe = _to_float(fundamental[1])  # pe_ttm
        if pe <= 0:
            return 0.0
        return -pe

    @staticmethod
    def _calc_quality(fundamental) -> float:
        """盈利质量综合分：ROE * 0.4 + 毛利率 * 0.3 + (经营现金流/净利润近似) * 0.3。"""
        if fundamental is None:
            return 0.0
        roe = _to_float(fundamental[2])
        gross_margin = _to_float(fundamental[3])
        operating_cf = _to_float(fundamental[5])

        # operating_cf / net_profit 近似：用 net_margin 做归一化参考
        # 当 net_margin > 0 时，cf_ratio = operating_cf 符号（正为好）
        cf_score = 1.0 if operating_cf > 0 else -1.0 if operating_cf < 0 else 0.0

        return roe * 0.4 + gross_margin * 0.3 + cf_score * 0.3

    @staticmethod
    def _calc_volatility(quotes: list) -> float:
        """近 20 日日收益率标准差，取负值（越低越好）。"""
        n = len(quotes)
        window = min(cfg.volatility_window, n)
        pct_changes = [_to_float(q[5]) for q in quotes[-window:] if q[5] is not None]

        if len(pct_changes) < 5:
            return 0.0

        mean = sum(pct_changes) / len(pct_changes)
        variance = sum((x - mean) ** 2 for x in pct_changes) / len(pct_changes)
        std = variance**0.5

        return -std

    @staticmethod
    def _calc_technical(tech, quotes: list) -> float:
        """
        技术形态得分 = 布林带位置 + MACD 信号。
        布林带位置：(close - lower) / (upper - lower)，0-1 范围，0.2-0.5 为佳。
        MACD 金叉得分 +1，死叉 -1。
        """
        score = 0.0

        if tech is not None:
            boll_upper = _to_float(tech[5])
            boll_lower = _to_float(tech[7])
            boll_range = boll_upper - boll_lower

            if boll_range > 0 and quotes:
                close = _to_float(quotes[-1][2])
                boll_position = (close - boll_lower) / boll_range
                # 0.2-0.5 为最佳区间（低位但不是超卖）
                if 0.2 <= boll_position <= 0.5:
                    score += 1.0
                elif 0.0 <= boll_position < 0.2:
                    score += 0.5
                elif 0.5 < boll_position <= 0.8:
                    score += 0.3
                else:
                    score -= 0.5

            macd_hist = _to_float(tech[4])
            macd = _to_float(tech[2])
            macd_signal = _to_float(tech[3])

            # 金叉：MACD > signal 且 hist > 0
            if macd > macd_signal and macd_hist > 0:
                score += 1.0
            elif macd < macd_signal and macd_hist < 0:
                score -= 0.5

        return score

    # ── Z-Score Normalization ──────────────────────────

    @staticmethod
    def _industry_zscore_normalize(scores: list[dict]) -> list[dict]:
        """行业内 Z-score 标准化。行业样本不足 3 只的，用全市场 Z-score。"""
        factor_names = [
            "momentum", "volume_trend", "valuation",
            "quality", "volatility", "technical",
        ]

        # 按行业分组
        industry_groups: dict[str, list[int]] = defaultdict(list)
        for i, s in enumerate(scores):
            industry_groups[s["industry"]].append(i)

        # 计算全市场均值和标准差作为 fallback
        global_stats: dict[str, tuple[float, float]] = {}
        for fname in factor_names:
            vals = [s["factors"][fname] for s in scores]
            if not vals:
                global_stats[fname] = (0.0, 1.0)
                continue
            mean = sum(vals) / len(vals)
            std = (sum((v - mean) ** 2 for v in vals) / len(vals)) ** 0.5
            global_stats[fname] = (mean, std if std > 0 else 1.0)

        for industry, indices in industry_groups.items():
            use_global = len(indices) < 3

            if use_global:
                for idx in indices:
                    for fname in factor_names:
                        mean, std = global_stats[fname]
                        raw = scores[idx]["factors"][fname]
                        scores[idx]["factors"][fname] = (raw - mean) / std
            else:
                for fname in factor_names:
                    vals = [scores[i]["factors"][fname] for i in indices]
                    mean = sum(vals) / len(vals)
                    std = (sum((v - mean) ** 2 for v in vals) / len(vals)) ** 0.5
                    if std == 0:
                        for i in indices:
                            scores[i]["factors"][fname] = 0.0
                    else:
                        for i in indices:
                            raw = scores[i]["factors"][fname]
                            scores[i]["factors"][fname] = (raw - mean) / std

        return scores

    # ── Helpers ────────────────────────────────────────

    @staticmethod
    def _chunked(lst: list, size: int):
        for i in range(0, len(lst), size):
            yield lst[i : i + size]

    @staticmethod
    def _round_factors(factors: dict) -> dict:
        return {k: round(v, 4) for k, v in factors.items()}
