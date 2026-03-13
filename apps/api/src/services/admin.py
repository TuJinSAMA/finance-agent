import logging
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.job_log import JobExecutionLog
from src.models.recommendation import Recommendation
from src.schemas.admin import (
    JobExecutionLogRead,
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

        # 一次性查询每个 job 最近一条执行记录
        latest_logs = await self._get_latest_logs(
            [jid for jid, _, _ in job_defs], target_date
        )

        for job_id, label, schedule_time in job_defs:
            job = scheduler.get_job(job_id)
            if not job:
                steps.append(PipelineStepStatus(
                    step=job_id,
                    label=f"{label}（{schedule_time}）",
                    status="not_scheduled",
                ))
                continue

            last_log = latest_logs.get(job_id)
            if last_log:
                status = last_log.status  # success / failed / skipped / running
                last_run = last_log.started_at
                detail = last_log.error_message if last_log.status == "failed" else None
            else:
                status = "pending"
                last_run = None
                detail = f"No execution record for {target_date}"

            steps.append(PipelineStepStatus(
                step=job_id,
                label=f"{label}（{schedule_time}）",
                status=status,
                last_run=last_run,
                next_run=job.next_run_time,
                detail=detail,
                last_log=JobExecutionLogRead.model_validate(last_log) if last_log else None,
            ))

        return steps

    async def _get_latest_logs(
        self, job_ids: list[str], target_date: date
    ) -> dict[str, JobExecutionLog]:
        """查询指定日期每个 job 最近一条执行记录（按 started_at 降序取第一条）。"""
        from datetime import datetime, time, timezone

        day_start = datetime.combine(target_date, time.min).replace(tzinfo=timezone.utc)
        day_end = datetime.combine(target_date, time.max).replace(tzinfo=timezone.utc)

        result = await self.db.execute(
            select(JobExecutionLog)
            .where(JobExecutionLog.job_id.in_(job_ids))
            .where(JobExecutionLog.started_at >= day_start)
            .where(JobExecutionLog.started_at <= day_end)
            .order_by(JobExecutionLog.started_at.desc())
        )
        logs = result.scalars().all()

        # 每个 job_id 只保留最新一条
        latest: dict[str, JobExecutionLog] = {}
        for log in logs:
            if log.job_id not in latest:
                latest[log.job_id] = log
        return latest

    async def get_pipeline_logs(self, target_date: date) -> list[PipelineLogEntry]:
        """从 job_execution_logs 读取当日所有任务执行记录。"""
        from datetime import datetime, time, timezone

        day_start = datetime.combine(target_date, time.min).replace(tzinfo=timezone.utc)
        day_end = datetime.combine(target_date, time.max).replace(tzinfo=timezone.utc)

        result = await self.db.execute(
            select(JobExecutionLog)
            .where(JobExecutionLog.started_at >= day_start)
            .where(JobExecutionLog.started_at <= day_end)
            .order_by(JobExecutionLog.started_at.asc())
        )
        execution_logs = result.scalars().all()

        logs: list[PipelineLogEntry] = []
        for log in execution_logs:
            detail: dict = {
                "status": log.status,
                "duration_seconds": log.duration_seconds,
                "records_affected": log.records_affected,
            }
            if log.meta:
                detail.update(log.meta)
            if log.error_message:
                detail["error_message"] = log.error_message

            logs.append(PipelineLogEntry(
                date=target_date,
                step=log.job_id,
                label=log.job_name,
                detail=detail,
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
