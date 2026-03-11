import logging
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.recommendation import Recommendation
from src.models.watchlist import Watchlist, WatchlistSnapshot
from src.schemas.admin import (
    PipelineLogEntry,
    PipelineStepStatus,
    RecommendationStatsResponse,
)

logger = logging.getLogger(__name__)


class AdminService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_pipeline_status(self, target_date: date) -> list[PipelineStepStatus]:
        from src.core.scheduler import scheduler

        steps = []

        job_defs = [
            ("daily_quotes", "拉取日线行情", "15:30"),
            ("daily_screening", "量化筛选 → 关注池", "16:00"),
            ("technical_indicators", "计算技术指标", "16:30"),
            ("morning_event_scan", "事件扫描 + LLM 分析", "06:30"),
            ("daily_recommendation", "推荐流水线", "07:30"),
            ("rec_performance_tracking", "推荐表现追踪", "15:45"),
        ]

        for job_id, label, schedule_time in job_defs:
            job = scheduler.get_job(job_id)
            if not job:
                steps.append(PipelineStepStatus(
                    step=job_id,
                    label=f"{label}（{schedule_time}）",
                    status="not_scheduled",
                ))
                continue

            next_run = job.next_run_time

            has_data = await self._check_step_completion(job_id, target_date)
            status = "completed" if has_data else "pending"

            steps.append(PipelineStepStatus(
                step=job_id,
                label=f"{label}（{schedule_time}）",
                status=status,
                next_run=next_run,
                detail=f"Data {'found' if has_data else 'not found'} for {target_date}",
            ))

        return steps

    async def _check_step_completion(self, job_id: str, target_date: date) -> bool:
        if job_id == "daily_recommendation":
            count = await self.db.scalar(
                select(func.count())
                .select_from(Recommendation)
                .where(Recommendation.rec_date == target_date)
            )
            return (count or 0) > 0

        if job_id == "daily_screening":
            count = await self.db.scalar(
                select(func.count())
                .select_from(WatchlistSnapshot)
                .where(WatchlistSnapshot.snapshot_date == target_date)
            )
            return (count or 0) > 0

        if job_id == "rec_performance_tracking":
            count = await self.db.scalar(
                select(func.count())
                .select_from(Recommendation)
                .where(
                    Recommendation.price_t1.is_not(None),
                    Recommendation.rec_date >= target_date - timedelta(days=7),
                )
            )
            return (count or 0) > 0

        return False

    async def get_pipeline_logs(self, target_date: date) -> list[PipelineLogEntry]:
        logs: list[PipelineLogEntry] = []

        rec_count = await self.db.scalar(
            select(func.count())
            .select_from(Recommendation)
            .where(Recommendation.rec_date == target_date)
        ) or 0
        logs.append(PipelineLogEntry(
            date=target_date,
            step="daily_recommendation",
            label="推荐流水线",
            detail={"recommendations_count": rec_count},
        ))

        snapshot_count = await self.db.scalar(
            select(func.count())
            .select_from(WatchlistSnapshot)
            .where(WatchlistSnapshot.snapshot_date == target_date)
        ) or 0
        logs.append(PipelineLogEntry(
            date=target_date,
            step="daily_screening",
            label="量化筛选",
            detail={"watchlist_snapshot_count": snapshot_count},
        ))

        active_watchlist = await self.db.scalar(
            select(func.count())
            .select_from(Watchlist)
            .where(Watchlist.status == "active")
        ) or 0
        logs.append(PipelineLogEntry(
            date=target_date,
            step="watchlist_status",
            label="关注池状态",
            detail={"active_count": active_watchlist},
        ))

        return logs

    async def rerun_step(self, step: str, target_date: date) -> dict:
        """重跑指定的流水线步骤。"""
        if step == "daily_screening":
            from src.agents.orchestrator.screener import StockScreener
            screener = StockScreener()
            result = await screener.run_daily_screening(self.db, target_date)
            await self.db.commit()
            return result

        if step == "daily_recommendation":
            from src.agents.orchestrator.pipeline import daily_recommendation_pipeline
            result = await daily_recommendation_pipeline(self.db, target_date)
            await self.db.commit()
            return result

        if step == "rec_performance_tracking":
            from src.agents.orchestrator.pipeline import update_recommendation_performance
            result = await update_recommendation_performance(self.db, target_date)
            await self.db.commit()
            return result

        raise ValueError(f"Unknown step: {step}")

    async def get_recommendation_stats(self) -> RecommendationStatsResponse:
        total = await self.db.scalar(
            select(func.count()).select_from(Recommendation)
        ) or 0

        total_days = await self.db.scalar(
            select(func.count(func.distinct(Recommendation.rec_date)))
            .select_from(Recommendation)
        ) or 0

        avg_picks = total / total_days if total_days > 0 else 0.0

        # T+1 stats
        t1_result = await self.db.execute(
            select(
                func.count().label("cnt"),
                func.avg(Recommendation.return_t1).label("avg"),
                func.count().filter(Recommendation.return_t1 > 0).label("wins"),
            )
            .select_from(Recommendation)
            .where(Recommendation.return_t1.is_not(None))
        )
        t1_row = t1_result.one()
        t1_tracked = t1_row.cnt or 0
        t1_avg = round(Decimal(str(t1_row.avg)), 4) if t1_row.avg else None
        t1_win_rate = (t1_row.wins / t1_tracked) if t1_tracked > 0 else None

        # T+5 stats
        t5_result = await self.db.execute(
            select(
                func.count().label("cnt"),
                func.avg(Recommendation.return_t5).label("avg"),
                func.count().filter(Recommendation.return_t5 > 0).label("wins"),
            )
            .select_from(Recommendation)
            .where(Recommendation.return_t5.is_not(None))
        )
        t5_row = t5_result.one()
        t5_tracked = t5_row.cnt or 0
        t5_avg = round(Decimal(str(t5_row.avg)), 4) if t5_row.avg else None
        t5_win_rate = (t5_row.wins / t5_tracked) if t5_tracked > 0 else None

        # Recent 7d
        cutoff = date.today() - timedelta(days=7)
        recent_result = await self.db.execute(
            select(
                func.count().label("cnt"),
                func.avg(Recommendation.return_t1).label("avg"),
                func.count().filter(Recommendation.return_t1 > 0).label("wins"),
            )
            .select_from(Recommendation)
            .where(
                Recommendation.return_t1.is_not(None),
                Recommendation.rec_date >= cutoff,
            )
        )
        recent_row = recent_result.one()
        recent_cnt = recent_row.cnt or 0
        recent_7d_avg = round(Decimal(str(recent_row.avg)), 4) if recent_row.avg else None
        recent_7d_win = (recent_row.wins / recent_cnt) if recent_cnt > 0 else None

        return RecommendationStatsResponse(
            total_recommendations=total,
            total_days=total_days,
            avg_picks_per_day=round(avg_picks, 1),
            t1_tracked=t1_tracked,
            t1_win_rate=round(t1_win_rate, 4) if t1_win_rate is not None else None,
            t1_avg_return=t1_avg,
            t5_tracked=t5_tracked,
            t5_win_rate=round(t5_win_rate, 4) if t5_win_rate is not None else None,
            t5_avg_return=t5_avg,
            recent_7d_win_rate=round(recent_7d_win, 4) if recent_7d_win is not None else None,
            recent_7d_avg_return=recent_7d_avg,
        )
