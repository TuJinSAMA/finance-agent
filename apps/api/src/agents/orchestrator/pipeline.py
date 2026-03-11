"""
每日推荐流水线 — 把一切串起来。

07:30 执行：综合评分 → 推荐理由生成 → 保存全局推荐 → 个性化推荐分发
15:45 执行：更新历史推荐的事后表现（T+1 / T+5 收益）
"""

import logging
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.agents.orchestrator.scorer import RecommendationScorer
from src.agents.reporting_agent.generator import RecommendationReportGenerator
from src.models.portfolio import Portfolio, PortfolioHolding
from src.models.recommendation import Recommendation, UserRecommendation
from src.models.stock import StockDailyQuote
from src.models.user import User
from src.models.watchlist import Watchlist

logger = logging.getLogger(__name__)


async def daily_recommendation_pipeline(
    db: AsyncSession,
    trade_date: date,
) -> dict:
    """
    完整的每日推荐流水线。

    Step 1: 综合评分 → Top 5
    Step 2: LLM 生成推荐理由
    Step 3: 保存全局推荐
    Step 4: 个性化推荐分发
    Step 5: 更新关注池推荐计数
    """
    logger.info("=== Daily Recommendation Pipeline Start (trade_date=%s) ===", trade_date)

    # Step 1: 综合评分
    scorer = RecommendationScorer()
    top_picks = await scorer.score_and_rank(db, trade_date)

    if not top_picks:
        logger.warning("No picks generated, pipeline aborted")
        return {"picks": 0, "users": 0}

    logger.info("Step 1 complete: %d picks scored", len(top_picks))

    # Step 2: LLM 生成推荐理由
    generator = RecommendationReportGenerator()
    top_picks = await generator.generate_for_batch(db, top_picks, trade_date)
    logger.info("Step 2 complete: reasons generated")

    # Step 3: 保存全局推荐
    await _save_recommendations(db, trade_date, top_picks)
    logger.info("Step 3 complete: global recommendations saved")

    # Step 4: 个性化推荐分发
    user_count = await _distribute_user_recommendations(db, trade_date)
    logger.info("Step 4 complete: distributed to %d users", user_count)

    # Step 5: 更新关注池推荐计数
    await _update_watchlist_rec_counts(db, trade_date, top_picks)
    logger.info("Step 5 complete: watchlist counts updated")

    await db.flush()

    # Step 6: 发送邮件推送（异步，失败不影响主流程）
    email_result = await _send_email_notifications(db, top_picks, trade_date)
    logger.info("Step 6 complete: email notifications %s", email_result)

    result = {"picks": len(top_picks), "users": user_count}
    logger.info("=== Pipeline Complete: %s ===", result)
    return result


async def _save_recommendations(
    db: AsyncSession,
    trade_date: date,
    picks: list[dict],
) -> None:
    """保存全局推荐到 recommendations 表。"""
    # 获取推荐时价格（前一个交易日收盘价）
    stock_ids = [p["stock_id"] for p in picks]
    price_map = await _get_latest_prices(db, stock_ids, trade_date)

    for pick in picks:
        rec = Recommendation(
            rec_date=trade_date,
            stock_id=pick["stock_id"],
            quant_score=round(Decimal(str(pick["quant_score"])), 4),
            catalyst_score=round(Decimal(str(pick["catalyst_score"])), 4),
            final_score=round(Decimal(str(pick["final_score"])), 4),
            rank=pick.get("rank"),
            reason_short=pick.get("reason_short", ""),
            reason_detail=pick.get("reason_detail", ""),
            price_at_rec=price_map.get(pick["stock_id"]),
        )
        db.add(rec)

    await db.flush()


async def _distribute_user_recommendations(
    db: AsyncSession,
    trade_date: date,
) -> int:
    """为每个活跃用户生成个性化推荐记录（过滤掉已持有的股票）。"""
    rec_result = await db.execute(
        select(Recommendation).where(Recommendation.rec_date == trade_date)
    )
    recommendations = rec_result.scalars().all()
    if not recommendations:
        return 0

    user_result = await db.execute(
        select(User).where(User.is_active.is_(True))
    )
    users = user_result.scalars().all()
    if not users:
        return 0

    # 批量查询所有用户的持仓 stock_id: {user_id: set[stock_id]}
    holding_result = await db.execute(
        select(Portfolio.user_id, PortfolioHolding.stock_id)
        .join(PortfolioHolding, Portfolio.id == PortfolioHolding.portfolio_id)
    )
    user_holdings: dict = {}
    for row in holding_result.all():
        user_holdings.setdefault(row[0], set()).add(row[1])

    for user in users:
        held_stock_ids = user_holdings.get(user.id, set())
        for rec in recommendations:
            if rec.stock_id in held_stock_ids:
                continue
            user_rec = UserRecommendation(
                user_id=user.id,
                recommendation_id=rec.id,
                rec_date=trade_date,
            )
            db.add(user_rec)

    await db.flush()
    return len(users)


async def _update_watchlist_rec_counts(
    db: AsyncSession,
    trade_date: date,
    picks: list[dict],
) -> None:
    """更新关注池中推荐股票的推荐计数和最后推荐日期。"""
    for pick in picks:
        await db.execute(
            update(Watchlist)
            .where(Watchlist.stock_id == pick["stock_id"])
            .where(Watchlist.status == "active")
            .values(
                recommended_count=Watchlist.recommended_count + 1,
                last_recommended=trade_date,
            )
        )


async def _get_latest_prices(
    db: AsyncSession,
    stock_ids: list[int],
    trade_date: date,
) -> dict[int, Decimal]:
    """获取每只股票在 trade_date 当天或之前最近的收盘价。"""
    price_map: dict[int, Decimal] = {}
    if not stock_ids:
        return price_map

    # 取 trade_date 前一天（推荐日的参考价格）或当日可用的最新价格
    result = await db.execute(
        select(
            StockDailyQuote.stock_id,
            StockDailyQuote.close,
        )
        .where(StockDailyQuote.stock_id.in_(stock_ids))
        .where(StockDailyQuote.trade_date <= trade_date)
        .where(StockDailyQuote.close.is_not(None))
        .distinct(StockDailyQuote.stock_id)
        .order_by(StockDailyQuote.stock_id, StockDailyQuote.trade_date.desc())
    )
    for row in result.all():
        price_map[row[0]] = row[1]

    return price_map


async def update_recommendation_performance(
    db: AsyncSession,
    trade_date: date,
) -> dict:
    """
    更新历史推荐的事后表现。

    15:45 执行，用当日收盘价更新：
    - T+1 推荐（昨天推荐的）的 price_t1 和 return_t1
    - T+5 推荐（5 个交易日前推荐的）的 price_t5 和 return_t5
    """
    logger.info("Updating recommendation performance for trade_date=%s", trade_date)

    # 当日收盘价
    price_result = await db.execute(
        select(StockDailyQuote.stock_id, StockDailyQuote.close)
        .where(StockDailyQuote.trade_date == trade_date)
        .where(StockDailyQuote.close.is_not(None))
    )
    today_prices = {row[0]: row[1] for row in price_result.all()}

    if not today_prices:
        logger.warning("No prices available for %s, skipping performance update", trade_date)
        return {"t1_updated": 0, "t5_updated": 0}

    # 更新 T+1：往回搜索最多 5 天找到前一个有推荐的日期
    for offset in range(1, 6):
        check_date = trade_date - timedelta(days=offset)
        t1_result = await db.execute(
            select(Recommendation)
            .where(Recommendation.rec_date == check_date)
            .where(Recommendation.price_t1.is_(None))
        )
        t1_recs = t1_result.scalars().all()
        if t1_recs:
            break
    else:
        t1_recs = []

    t1_updated = 0
    for rec in t1_recs:
        close = today_prices.get(rec.stock_id)
        if close and rec.price_at_rec:
            rec.price_t1 = close
            rec.return_t1 = round(
                (close - rec.price_at_rec) / rec.price_at_rec, 4
            )
            t1_updated += 1

    # 更新 T+5：约 5 个交易日前的推荐
    for offset in range(5, 12):
        check_date = trade_date - timedelta(days=offset)
        t5_result = await db.execute(
            select(Recommendation)
            .where(Recommendation.rec_date == check_date)
            .where(Recommendation.price_t5.is_(None))
            .where(Recommendation.price_at_rec.is_not(None))
        )
        t5_recs = t5_result.scalars().all()
        if t5_recs:
            break
    else:
        t5_recs = []

    t5_updated = 0
    for rec in t5_recs:
        close = today_prices.get(rec.stock_id)
        if close and rec.price_at_rec:
            rec.price_t5 = close
            rec.return_t5 = round(
                (close - rec.price_at_rec) / rec.price_at_rec, 4
            )
            t5_updated += 1

    await db.flush()

    result = {"t1_updated": t1_updated, "t5_updated": t5_updated}
    logger.info("Performance update complete: %s", result)
    return result


async def _send_email_notifications(
    db: AsyncSession,
    picks: list[dict],
    trade_date: date,
) -> dict:
    """为所有有邮箱的活跃用户发送推荐邮件。"""
    from src.agents.reporting_agent.email_sender import send_batch_recommendation_emails
    from src.models.stock import Stock

    try:
        # 获取用户邮箱
        user_result = await db.execute(
            select(User.email).where(
                User.is_active.is_(True),
                User.email.is_not(None),
            )
        )
        emails = [row[0] for row in user_result.all() if row[0]]
        if not emails:
            return {"sent": 0, "failed": 0, "reason": "no_users_with_email"}

        stock_ids = [p["stock_id"] for p in picks]
        stock_result = await db.execute(
            select(Stock.id, Stock.name, Stock.code).where(Stock.id.in_(stock_ids))
        )
        stock_map = {row[0]: (row[1], row[2]) for row in stock_result.all()}

        email_recs = []
        for p in picks:
            name, code = stock_map.get(p["stock_id"], ("—", ""))
            email_recs.append({
                "rank": p.get("rank"),
                "stock_name": name,
                "stock_code": code,
                "final_score": p.get("final_score"),
                "reason_short": p.get("reason_short", ""),
            })

        return await send_batch_recommendation_emails(emails, email_recs, trade_date)
    except Exception:
        logger.exception("Email notification step failed (non-fatal)")
        return {"sent": 0, "failed": 0, "error": "exception"}
