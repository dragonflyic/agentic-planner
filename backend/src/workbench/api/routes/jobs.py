"""Job queue management API routes."""

from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, select

from workbench.api.deps import DbSession
from workbench.models import Job, JobStatus, JobType
from workbench.schemas import Job as JobSchema, JobQueueStats, PaginatedResponse

router = APIRouter()


@router.get("/", response_model=PaginatedResponse[JobSchema])
async def list_jobs(
    db: DbSession,
    type: JobType | None = None,
    status: JobStatus | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> PaginatedResponse[JobSchema]:
    """List jobs with optional filtering."""
    query = select(Job)

    if type:
        query = query.where(Job.type == type)
    if status:
        query = query.where(Job.status == status)

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query) or 0

    # Apply sorting and pagination
    query = query.order_by(Job.created_at.desc())
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size)

    result = await db.execute(query)
    jobs = result.scalars().all()

    items = [JobSchema.model_validate(job) for job in jobs]
    return PaginatedResponse.create(items, total, page, page_size)


@router.get("/stats", response_model=JobQueueStats)
async def get_job_stats(db: DbSession) -> JobQueueStats:
    """Get job queue statistics."""
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    # Pending count
    pending_query = select(func.count()).where(Job.status == JobStatus.PENDING)
    pending_count = await db.scalar(pending_query) or 0

    # Running count
    running_query = select(func.count()).where(
        Job.status.in_([JobStatus.CLAIMED, JobStatus.RUNNING])
    )
    running_count = await db.scalar(running_query) or 0

    # Completed today
    completed_query = select(func.count()).where(
        Job.status == JobStatus.COMPLETED,
        Job.completed_at >= today_start,
    )
    completed_today = await db.scalar(completed_query) or 0

    # Failed today
    failed_query = select(func.count()).where(
        Job.status.in_([JobStatus.FAILED, JobStatus.DEAD]),
        Job.completed_at >= today_start,
    )
    failed_today = await db.scalar(failed_query) or 0

    return JobQueueStats(
        pending_count=pending_count,
        running_count=running_count,
        completed_today=completed_today,
        failed_today=failed_today,
        metrics_by_type=[],  # Could expand this later
    )


@router.get("/{job_id}", response_model=JobSchema)
async def get_job(db: DbSession, job_id: UUID) -> JobSchema:
    """Get job details."""
    query = select(Job).where(Job.id == job_id)
    result = await db.execute(query)
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    return JobSchema.model_validate(job)


@router.post("/{job_id}/retry", response_model=JobSchema)
async def retry_job(db: DbSession, job_id: UUID) -> JobSchema:
    """Manually retry a failed or dead job."""
    query = select(Job).where(Job.id == job_id)
    result = await db.execute(query)
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.status not in [JobStatus.FAILED, JobStatus.DEAD]:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot retry job in {job.status} status",
        )

    # Reset job for retry
    job.status = JobStatus.PENDING
    job.error = None
    job.worker_id = None
    job.claimed_at = None
    job.heartbeat_at = None
    job.completed_at = None
    job.result = None
    job.scheduled_for = datetime.now(timezone.utc)

    await db.flush()
    await db.refresh(job)
    return JobSchema.model_validate(job)


@router.delete("/{job_id}", status_code=204)
async def cancel_job(db: DbSession, job_id: UUID) -> None:
    """Cancel a pending job."""
    query = select(Job).where(Job.id == job_id)
    result = await db.execute(query)
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.status != JobStatus.PENDING:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot cancel job in {job.status} status",
        )

    await db.delete(job)


@router.post("/recover-stale")
async def recover_stale_jobs(
    db: DbSession,
    threshold_minutes: int = Query(5, ge=1, le=60),
) -> dict[str, int]:
    """Recover jobs that appear to be stale (no heartbeat)."""
    threshold = datetime.now(timezone.utc) - timedelta(minutes=threshold_minutes)

    # Find stale jobs
    stale_query = select(Job).where(
        Job.status.in_([JobStatus.CLAIMED, JobStatus.RUNNING]),
        Job.heartbeat_at < threshold,
        Job.retry_count < Job.max_retries,
    )
    result = await db.execute(stale_query)
    stale_jobs = result.scalars().all()

    recovered = 0
    for job in stale_jobs:
        job.status = JobStatus.PENDING
        job.worker_id = None
        job.claimed_at = None
        job.error = "Recovered from stale worker"
        job.retry_count += 1
        recovered += 1

    await db.flush()
    return {"recovered": recovered}
