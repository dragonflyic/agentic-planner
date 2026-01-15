"""Job schemas for API request/response."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from workbench.models.job import JobStatus, JobType


class JobBase(BaseModel):
    """Base job fields."""

    type: JobType
    payload: dict[str, Any] = Field(default_factory=dict)
    priority: int = Field(default=0)
    max_retries: int = Field(default=3, ge=0, le=10)


class JobCreate(JobBase):
    """Request body for creating a job."""

    scheduled_for: datetime | None = None
    attempt_id: UUID | None = None


class Job(JobBase):
    """Job response model."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    status: JobStatus
    retry_count: int
    scheduled_for: datetime
    worker_id: str | None = None
    claimed_at: datetime | None = None
    heartbeat_at: datetime | None = None
    completed_at: datetime | None = None
    result: dict[str, Any] | None = None
    error: str | None = None
    attempt_id: UUID | None = None
    created_at: datetime
    updated_at: datetime


class JobMetrics(BaseModel):
    """Aggregated job queue metrics."""

    type: JobType
    status: JobStatus
    count: int
    avg_duration_seconds: float | None = None


class JobQueueStats(BaseModel):
    """Overall queue statistics."""

    pending_count: int
    running_count: int
    completed_today: int
    failed_today: int
    metrics_by_type: list[JobMetrics] = Field(default_factory=list)
