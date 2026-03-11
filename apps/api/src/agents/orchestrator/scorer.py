"""
综合评分器 — 融合量化得分与催化剂分析，生成最终推荐列表。

输入：关注池（Watchlist active）+ 催化剂摘要
输出：Top N 推荐列表（含行业分散化 + 反疲劳机制）
"""

import logging
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from src.agents.screener_config import screener_config as cfg
from src.models.recommendation import Recommendation
from src.models.watchlist import Watchlist

logger = logging.getLogger(__name__)


def _to_float(val) -> float:
    if val is None:
        return 0.0
    if isinstance(val, Decimal):
        return float(val)
    return float(val)


class RecommendationScorer:
    """综合评分器：融合量化得分和催化剂分析，生成最终推荐列表。"""

    async def score_and_rank(
        self,
        db: AsyncSession,
        trade_date: date,
        top_n: int | None = None,
    ) -> list[dict]:
        """
        从关注池中选出今日推荐的 Top N 只股票。

        返回 list[dict]，每个 dict 包含：
        stock_id, industry, quant_score, catalyst_score, final_score
        """
        if top_n is None:
            top_n = cfg.recommendation_count

        watchlist_items = await self._get_active_watchlist(db)
        if not watchlist_items:
            logger.warning("Active watchlist is empty, cannot generate recommendations")
            return []

        scored = []
        quant_values = []
        catalyst_values = []

        for w in watchlist_items:
            quant = _to_float(w.quant_score)
            catalyst = self._extract_catalyst_score(w, trade_date)
            quant_values.append(quant)
            catalyst_values.append(catalyst)
            scored.append({
                "stock_id": w.stock_id,
                "industry": w.stock.industry or "unknown" if w.stock else "unknown",
                "quant_raw": quant,
                "catalyst_raw": catalyst,
                "has_new_catalyst": catalyst != 0,
            })

        q_min, q_max = min(quant_values), max(quant_values)
        c_min, c_max = min(catalyst_values), max(catalyst_values)

        for i, item in enumerate(scored):
            item["quant_score"] = self._normalize(item["quant_raw"], q_min, q_max)
            item["catalyst_score"] = self._normalize(item["catalyst_raw"], c_min, c_max)
            item["final_score"] = (
                item["quant_score"] * cfg.score_weight_quant
                + item["catalyst_score"] * cfg.score_weight_catalyst
            )

        scored.sort(key=lambda x: x["final_score"], reverse=True)

        result = self._apply_diversification(scored, top_n=top_n)
        result = await self._apply_anti_fatigue(db, result, trade_date, scored)

        for rank, item in enumerate(result, 1):
            item["rank"] = rank

        logger.info(
            "Scoring complete: %d watchlist → %d recommendations (trade_date=%s)",
            len(watchlist_items), len(result), trade_date,
        )
        return result

    @staticmethod
    def _extract_catalyst_score(watchlist_item: Watchlist, trade_date: date) -> float:
        """从 watchlist 的 catalyst_summary 中提取催化剂得分。"""
        cs = watchlist_item.catalyst_summary
        if not cs:
            return 0.0
        catalyst_date = watchlist_item.catalyst_date
        if catalyst_date and (trade_date - catalyst_date).days > cfg.event_lookback_days:
            return 0.0

        sentiment = cs.get("top_sentiment", "")
        impact = float(cs.get("top_impact_score", 0))

        if sentiment == "bullish":
            return impact
        elif sentiment == "bearish":
            return -impact
        return impact * 0.3  # neutral 给微弱正分

    @staticmethod
    def _normalize(value: float, min_val: float, max_val: float) -> float:
        """归一化到 0-100 区间。"""
        if max_val == min_val:
            return 50.0
        return ((value - min_val) / (max_val - min_val)) * 100

    def _apply_diversification(
        self,
        scored: list[dict],
        top_n: int,
    ) -> list[dict]:
        """行业分散化：贪心算法，同行业不超过 max_same_industry 只。"""
        selected = []
        industry_count: dict[str, int] = {}

        for item in scored:
            industry = item.get("industry", "unknown")
            if industry_count.get(industry, 0) >= cfg.max_same_industry:
                continue
            selected.append(item)
            industry_count[industry] = industry_count.get(industry, 0) + 1
            if len(selected) >= top_n:
                break

        return selected

    async def _apply_anti_fatigue(
        self,
        db: AsyncSession,
        selected: list[dict],
        trade_date: date,
        full_pool: list[dict],
    ) -> list[dict]:
        """
        反疲劳机制：最近 N 天内已推荐 >= M 次的股票降级（除非有新催化剂）。
        被降级的位置从 full_pool 中补充。
        """
        cutoff_date = trade_date - timedelta(days=cfg.anti_fatigue_days)

        selected_ids = [s["stock_id"] for s in selected]
        if not selected_ids:
            return selected

        result = await db.execute(
            select(Recommendation.stock_id, func.count().label("cnt"))
            .where(Recommendation.rec_date >= cutoff_date)
            .where(Recommendation.rec_date < trade_date)
            .where(Recommendation.stock_id.in_(selected_ids))
            .group_by(Recommendation.stock_id)
        )
        recent_counts = {row[0]: row[1] for row in result.all()}

        fatigued_indices = []
        for i, item in enumerate(selected):
            cnt = recent_counts.get(item["stock_id"], 0)
            if cnt >= cfg.anti_fatigue_max_count and not item.get("has_new_catalyst"):
                fatigued_indices.append(i)

        if not fatigued_indices:
            return selected

        logger.info("Anti-fatigue: removing %d fatigued stocks", len(fatigued_indices))

        selected_ids_set = {s["stock_id"] for s in selected}
        remaining = [s for i, s in enumerate(selected) if i not in fatigued_indices]

        industry_count: dict[str, int] = {}
        for item in remaining:
            ind = item.get("industry", "unknown")
            industry_count[ind] = industry_count.get(ind, 0) + 1

        needed = len(selected) - len(remaining)
        for candidate in full_pool:
            if needed <= 0:
                break
            if candidate["stock_id"] in selected_ids_set:
                continue
            ind = candidate.get("industry", "unknown")
            if industry_count.get(ind, 0) >= cfg.max_same_industry:
                continue
            cnt = recent_counts.get(candidate["stock_id"], 0)
            if cnt >= cfg.anti_fatigue_max_count and not candidate.get("has_new_catalyst"):
                continue
            remaining.append(candidate)
            selected_ids_set.add(candidate["stock_id"])
            industry_count[ind] = industry_count.get(ind, 0) + 1
            needed -= 1

        return remaining

    @staticmethod
    async def _get_active_watchlist(db: AsyncSession) -> list[Watchlist]:
        """获取当前活跃关注池，预加载 stock 关系。"""
        result = await db.execute(
            select(Watchlist)
            .options(joinedload(Watchlist.stock))
            .where(Watchlist.status == "active")
            .order_by(Watchlist.quant_score.desc())
        )
        return list(result.scalars().unique().all())
