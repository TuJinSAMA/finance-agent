import logging

from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.background import BackgroundScheduler

from src.core.config import settings

logger = logging.getLogger(__name__)

jobstores = {
    "default": SQLAlchemyJobStore(
        url=settings.DATABASE_URL_SYNC,
        tablename="apscheduler_jobs",
    ),
}

executors = {
    "default": ThreadPoolExecutor(max_workers=10),
}

job_defaults = {
    "coalesce": True,
    "max_instances": 1,
    "misfire_grace_time": 60,
}

scheduler = BackgroundScheduler(
    jobstores=jobstores,
    executors=executors,
    job_defaults=job_defaults,
)


# ── sample jobs ──────────────────────────────────────────────


def tick():
    logger.info("APScheduler heartbeat — scheduler is alive")


def register_default_jobs():
    """Add built-in jobs if they don't already exist (idempotent)."""
    if not scheduler.get_job("heartbeat"):
        scheduler.add_job(
            tick,
            "interval",
            minutes=1,
            id="heartbeat",
            replace_existing=True,
        )
        logger.info("Registered heartbeat job (runs every 1 min)")


def register_data_agent_jobs():
    """Register Data Agent scheduled jobs (idempotent)."""
    from src.agents.data_agent.jobs import (
        daily_quotes_job,
        technical_indicators_job,
        weekly_sync_job,
    )

    if not scheduler.get_job("daily_quotes"):
        scheduler.add_job(
            daily_quotes_job,
            "cron",
            hour=15,
            minute=30,
            day_of_week="mon-fri",
            id="daily_quotes",
            replace_existing=True,
        )
        logger.info("Registered daily_quotes job (weekdays 15:30)")

    if not scheduler.get_job("technical_indicators"):
        scheduler.add_job(
            technical_indicators_job,
            "cron",
            hour=16,
            minute=30,
            day_of_week="mon-fri",
            id="technical_indicators",
            replace_existing=True,
        )
        logger.info("Registered technical_indicators job (weekdays 16:30)")

    if not scheduler.get_job("weekly_stock_sync"):
        scheduler.add_job(
            weekly_sync_job,
            "cron",
            hour=17,
            minute=0,
            day_of_week="mon",
            id="weekly_stock_sync",
            replace_existing=True,
        )
        logger.info("Registered weekly_stock_sync job (Monday 17:00)")


def register_orchestrator_jobs():
    """Register Orchestrator scheduled jobs (idempotent)."""
    from src.agents.orchestrator.jobs import daily_screening_job

    if not scheduler.get_job("daily_screening"):
        scheduler.add_job(
            daily_screening_job,
            "cron",
            hour=16,
            minute=0,
            day_of_week="mon-fri",
            id="daily_screening",
            replace_existing=True,
        )
        logger.info("Registered daily_screening job (weekdays 16:00)")


def register_event_agent_jobs():
    """Register Event Agent scheduled jobs (idempotent)."""
    from src.agents.event_agent.jobs import morning_event_scan_job

    if not scheduler.get_job("morning_event_scan"):
        scheduler.add_job(
            morning_event_scan_job,
            "cron",
            hour=6,
            minute=30,
            day_of_week="mon-fri",
            id="morning_event_scan",
            replace_existing=True,
        )
        logger.info("Registered morning_event_scan job (weekdays 06:30)")


def register_recommendation_jobs():
    """Register recommendation pipeline + performance tracking jobs (idempotent)."""
    from src.agents.orchestrator.jobs import (
        daily_recommendation_job,
        rec_performance_tracking_job,
    )

    if not scheduler.get_job("daily_recommendation"):
        scheduler.add_job(
            daily_recommendation_job,
            "cron",
            hour=7,
            minute=30,
            day_of_week="mon-fri",
            id="daily_recommendation",
            replace_existing=True,
        )
        logger.info("Registered daily_recommendation job (weekdays 07:30)")

    if not scheduler.get_job("rec_performance_tracking"):
        scheduler.add_job(
            rec_performance_tracking_job,
            "cron",
            hour=15,
            minute=45,
            day_of_week="mon-fri",
            id="rec_performance_tracking",
            replace_existing=True,
        )
        logger.info("Registered rec_performance_tracking job (weekdays 15:45)")
