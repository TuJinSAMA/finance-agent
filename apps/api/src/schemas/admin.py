from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel


class JobExecutionLogRead(BaseModel):
    id: int
    job_id: str
    job_name: str
    status: str
    started_at: datetime
    finished_at: datetime | None = None
    duration_seconds: float | None = None
    records_affected: int | None = None
    error_message: str | None = None
    meta: dict | None = None

    model_config = {"from_attributes": True}


class PipelineStepStatus(BaseModel):
    step: str
    label: str
    status: str  # "completed" | "pending" | "failed" | "skipped" | "not_scheduled"
    last_run: datetime | None = None
    next_run: datetime | None = None
    detail: str | None = None
    last_log: JobExecutionLogRead | None = None


class PipelineStatusResponse(BaseModel):
    date: date
    steps: list[PipelineStepStatus]


class PipelineLogEntry(BaseModel):
    date: date
    step: str
    label: str
    detail: dict | None = None


class PipelineLogResponse(BaseModel):
    date: date
    logs: list[PipelineLogEntry]


class RerunResponse(BaseModel):
    status: str
    step: str
    result: dict | None = None
    error: str | None = None


class RecommendationStatsResponse(BaseModel):
    total_recommendations: int
    total_days: int
    avg_picks_per_day: float

    t1_tracked: int
    t1_win_rate: float | None = None
    t1_avg_return: Decimal | None = None

    t5_tracked: int
    t5_win_rate: float | None = None
    t5_avg_return: Decimal | None = None

    recent_7d_win_rate: float | None = None
    recent_7d_avg_return: Decimal | None = None
