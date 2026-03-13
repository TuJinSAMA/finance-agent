"""
JobLogger — 定时任务执行日志工具类。

用法示例（在 jobs.py 的同步入口中）：

    from src.core.job_logger import JobLogger

    def some_job():
        log_id = JobLogger.start("some_job", "任务名称")
        try:
            result = asyncio.run(_some_job_async())
            JobLogger.finish(log_id, records_affected=result.get("count"), meta=result)
        except Exception as exc:
            JobLogger.fail(log_id, str(exc))
            raise

    def some_skipped_job():
        JobLogger.skip("some_job", "任务名称", reason="非交易日")
"""

import logging
from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from src.core.config import settings

logger = logging.getLogger(__name__)

# 使用同步引擎写入日志（jobs.py 运行在同步线程中，无法使用 asyncpg）
_sync_engine = create_engine(
    settings.DATABASE_URL_SYNC,
    pool_size=2,
    max_overflow=0,
    pool_pre_ping=True,
)


class JobLogger:
    """定时任务执行日志记录器（同步接口）。"""

    @staticmethod
    def start(job_id: str, job_name: str) -> int | None:
        """
        记录任务开始，返回 log_id（用于后续 finish/fail 调用）。
        写入失败时返回 None，不影响任务执行。
        """
        from src.models.job_log import JobExecutionLog

        try:
            with Session(_sync_engine) as session:
                log = JobExecutionLog(
                    job_id=job_id,
                    job_name=job_name,
                    status="running",
                    started_at=datetime.now(tz=timezone.utc),
                )
                session.add(log)
                session.commit()
                session.refresh(log)
                return log.id
        except Exception:
            logger.exception("JobLogger.start failed for job_id=%s", job_id)
            return None

    @staticmethod
    def finish(
        log_id: int | None,
        records_affected: int | None = None,
        meta: dict | None = None,
    ) -> None:
        """记录任务成功完成。"""
        if log_id is None:
            return
        from src.models.job_log import JobExecutionLog

        try:
            with Session(_sync_engine) as session:
                log = session.get(JobExecutionLog, log_id)
                if log is None:
                    return
                now = datetime.now(tz=timezone.utc)
                log.status = "success"
                log.finished_at = now
                log.duration_seconds = (now - log.started_at).total_seconds()
                log.records_affected = records_affected
                log.meta = meta
                session.commit()
        except Exception:
            logger.exception("JobLogger.finish failed for log_id=%d", log_id)

    @staticmethod
    def fail(log_id: int | None, error_message: str) -> None:
        """记录任务失败。"""
        if log_id is None:
            return
        from src.models.job_log import JobExecutionLog

        try:
            with Session(_sync_engine) as session:
                log = session.get(JobExecutionLog, log_id)
                if log is None:
                    return
                now = datetime.now(tz=timezone.utc)
                log.status = "failed"
                log.finished_at = now
                log.duration_seconds = (now - log.started_at).total_seconds()
                # 截断过长的错误信息
                log.error_message = error_message[:2000] if error_message else None
                session.commit()
        except Exception:
            logger.exception("JobLogger.fail failed for log_id=%d", log_id)

    @staticmethod
    def skip(job_id: str, job_name: str, reason: str = "非交易日") -> None:
        """记录任务因条件不满足而跳过（如非交易日）。"""
        from src.models.job_log import JobExecutionLog

        try:
            now = datetime.now(tz=timezone.utc)
            with Session(_sync_engine) as session:
                log = JobExecutionLog(
                    job_id=job_id,
                    job_name=job_name,
                    status="skipped",
                    started_at=now,
                    finished_at=now,
                    duration_seconds=0.0,
                    meta={"reason": reason},
                )
                session.add(log)
                session.commit()
        except Exception:
            logger.exception("JobLogger.skip failed for job_id=%s", job_id)
