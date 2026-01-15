"""Job queue service using PostgreSQL FOR UPDATE SKIP LOCKED pattern."""

import socket
import os
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import text, update
from sqlalchemy.ext.asyncio import AsyncSession

from workbench.models import Job, JobStatus, JobType


class JobService:
    """Service for managing the PostgreSQL-based job queue."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self._worker_id: str | None = None

    @property
    def worker_id(self) -> str:
        """Get or generate a unique worker ID."""
        if self._worker_id is None:
            hostname = socket.gethostname()
            pid = os.getpid()
            self._worker_id = f"{hostname}-{pid}"
        return self._worker_id

    async def claim_job(
        self,
        job_types: list[JobType] | None = None,
    ) -> Job | None:
        """
        Claim the next available job using FOR UPDATE SKIP LOCKED.

        This ensures only one worker can claim each job, even with
        multiple workers polling concurrently.
        """
        # Build the query with optional type filter
        type_filter = ""
        params: dict[str, Any] = {
            "worker_id": self.worker_id,
            "now": datetime.now(timezone.utc),
        }

        if job_types:
            type_filter = "AND type = ANY(:job_types)"
            params["job_types"] = [t.value for t in job_types]

        # Use raw SQL for FOR UPDATE SKIP LOCKED
        query = text(f"""
            WITH next_job AS (
                SELECT id
                FROM jobs
                WHERE status = 'pending'
                  AND scheduled_for <= :now
                  AND retry_count < max_retries
                  {type_filter}
                ORDER BY priority DESC, scheduled_for ASC
                LIMIT 1
                FOR UPDATE SKIP LOCKED
            )
            UPDATE jobs
            SET status = 'claimed',
                worker_id = :worker_id,
                claimed_at = :now,
                heartbeat_at = :now,
                updated_at = :now
            FROM next_job
            WHERE jobs.id = next_job.id
            RETURNING jobs.*
        """)

        result = await self.db.execute(query, params)
        row = result.fetchone()

        if row is None:
            return None

        # Convert row to Job model
        return Job(
            id=row.id,
            type=JobType(row.type),
            payload=row.payload,
            status=JobStatus(row.status),
            priority=row.priority,
            max_retries=row.max_retries,
            retry_count=row.retry_count,
            scheduled_for=row.scheduled_for,
            worker_id=row.worker_id,
            claimed_at=row.claimed_at,
            heartbeat_at=row.heartbeat_at,
            completed_at=row.completed_at,
            result=row.result,
            error=row.error,
            attempt_id=row.attempt_id,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    async def start_job(self, job_id: UUID) -> bool:
        """Mark a job as running (transition from claimed to running)."""
        query = (
            update(Job)
            .where(Job.id == job_id, Job.status == JobStatus.CLAIMED)
            .values(
                status=JobStatus.RUNNING,
                heartbeat_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
        )
        result = await self.db.execute(query)
        return result.rowcount > 0

    async def complete_job(
        self,
        job_id: UUID,
        result: dict[str, Any] | None = None,
    ) -> bool:
        """Mark a job as completed with optional result data."""
        query = (
            update(Job)
            .where(
                Job.id == job_id,
                Job.status.in_([JobStatus.CLAIMED, JobStatus.RUNNING]),
            )
            .values(
                status=JobStatus.COMPLETED,
                completed_at=datetime.now(timezone.utc),
                result=result,
                updated_at=datetime.now(timezone.utc),
            )
        )
        result_obj = await self.db.execute(query)
        return result_obj.rowcount > 0

    async def fail_job(
        self,
        job_id: UUID,
        error: str,
        retry_delay_seconds: int = 60,
    ) -> bool:
        """
        Mark a job as failed.

        If retries remain, schedules it for retry. Otherwise marks as dead.
        """
        now = datetime.now(timezone.utc)

        # First, get the current job state
        job_query = text("""
            SELECT retry_count, max_retries
            FROM jobs
            WHERE id = :job_id
        """)
        result = await self.db.execute(job_query, {"job_id": job_id})
        row = result.fetchone()

        if row is None:
            return False

        retry_count = row.retry_count + 1
        can_retry = retry_count < row.max_retries

        if can_retry:
            # Schedule for retry with exponential backoff
            backoff = retry_delay_seconds * (2 ** row.retry_count)
            next_scheduled = now + timedelta(seconds=backoff)

            query = (
                update(Job)
                .where(
                    Job.id == job_id,
                    Job.status.in_([JobStatus.CLAIMED, JobStatus.RUNNING]),
                )
                .values(
                    status=JobStatus.PENDING,
                    error=error,
                    retry_count=retry_count,
                    scheduled_for=next_scheduled,
                    worker_id=None,
                    claimed_at=None,
                    heartbeat_at=None,
                    updated_at=now,
                )
            )
        else:
            # Mark as dead (exceeded retries)
            query = (
                update(Job)
                .where(
                    Job.id == job_id,
                    Job.status.in_([JobStatus.CLAIMED, JobStatus.RUNNING]),
                )
                .values(
                    status=JobStatus.DEAD,
                    error=error,
                    retry_count=retry_count,
                    completed_at=now,
                    updated_at=now,
                )
            )

        result_obj = await self.db.execute(query)
        return result_obj.rowcount > 0

    async def heartbeat(self, job_id: UUID) -> bool:
        """Update the heartbeat timestamp for a running job."""
        query = (
            update(Job)
            .where(
                Job.id == job_id,
                Job.status.in_([JobStatus.CLAIMED, JobStatus.RUNNING]),
            )
            .values(
                heartbeat_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
        )
        result = await self.db.execute(query)
        return result.rowcount > 0

    async def recover_stale_jobs(
        self,
        stale_threshold_seconds: int = 300,
    ) -> int:
        """
        Recover jobs that appear to be abandoned (no heartbeat).

        Returns the number of jobs recovered.
        """
        threshold = datetime.now(timezone.utc) - timedelta(seconds=stale_threshold_seconds)

        query = (
            update(Job)
            .where(
                Job.status.in_([JobStatus.CLAIMED, JobStatus.RUNNING]),
                Job.heartbeat_at < threshold,
                Job.retry_count < Job.max_retries,
            )
            .values(
                status=JobStatus.PENDING,
                error="Recovered from stale worker",
                retry_count=Job.retry_count + 1,
                worker_id=None,
                claimed_at=None,
                heartbeat_at=None,
                updated_at=datetime.now(timezone.utc),
            )
        )
        result = await self.db.execute(query)
        return result.rowcount

    async def create_job(
        self,
        job_type: JobType,
        payload: dict[str, Any],
        priority: int = 0,
        max_retries: int = 3,
        scheduled_for: datetime | None = None,
        attempt_id: UUID | None = None,
    ) -> Job:
        """Create a new job in the queue."""
        job = Job(
            type=job_type,
            payload=payload,
            priority=priority,
            max_retries=max_retries,
            scheduled_for=scheduled_for or datetime.now(timezone.utc),
            attempt_id=attempt_id,
        )
        self.db.add(job)
        await self.db.flush()
        await self.db.refresh(job)
        return job
