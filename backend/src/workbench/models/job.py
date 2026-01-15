"""Job model - PostgreSQL-based job queue."""

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from workbench.models.base import Base, TimestampMixin, UUIDMixin


class JobType(str, Enum):
    """Type of job to be processed."""

    SYNC_SIGNALS = "sync_signals"  # Sync from GitHub
    RUN_ATTEMPT = "run_attempt"  # Execute Claude Code
    RETRY_ATTEMPT = "retry_attempt"  # Retry after clarification
    CLEANUP = "cleanup"  # Maintenance tasks


class JobStatus(str, Enum):
    """Status of a job in the queue."""

    PENDING = "pending"  # Awaiting pickup
    CLAIMED = "claimed"  # Worker has claimed
    RUNNING = "running"  # Actively processing
    COMPLETED = "completed"  # Finished successfully
    FAILED = "failed"  # Finished with error
    DEAD = "dead"  # Exceeded retry limit


class Job(Base, UUIDMixin, TimestampMixin):
    """A job in the PostgreSQL-based queue."""

    __tablename__ = "jobs"

    # Job definition
    type: Mapped[JobType] = mapped_column(String(50), nullable=False, index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")

    # Queue management
    status: Mapped[JobStatus] = mapped_column(
        String(20), default=JobStatus.PENDING, nullable=False, index=True
    )
    priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_retries: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Scheduling
    scheduled_for: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default="now()",
        index=True,
    )

    # Worker tracking
    worker_id: Mapped[str | None] = mapped_column(String(255))
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Completion
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    error: Mapped[str | None] = mapped_column(Text)

    # Optional reference to attempt (for attempt-related jobs)
    attempt_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))

    @property
    def can_retry(self) -> bool:
        """Check if job can be retried."""
        return self.retry_count < self.max_retries

    def __repr__(self) -> str:
        return f"<Job {self.id} type={self.type} status={self.status}>"
