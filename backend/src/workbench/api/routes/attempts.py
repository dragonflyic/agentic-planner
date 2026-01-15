"""Attempt management API routes."""

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from workbench.api.deps import DbSession
from workbench.models import Attempt, AttemptStatus, Job, JobStatus, JobType, Signal
from workbench.schemas import (
    Attempt as AttemptSchema,
    AttemptCreate,
    AttemptWithSignal,
    PaginatedResponse,
)

router = APIRouter()


@router.get("/", response_model=PaginatedResponse[AttemptWithSignal])
async def list_attempts(
    db: DbSession,
    signal_id: UUID | None = None,
    status: AttemptStatus | None = None,
    has_pr: bool | None = None,
    sort_by: str = Query("created_at", pattern="^(started_at|finished_at|created_at)$"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> PaginatedResponse[AttemptWithSignal]:
    """List attempts with optional filtering."""
    # Build base query
    query = select(Attempt).options(selectinload(Attempt.signal))

    # Apply filters
    if signal_id:
        query = query.where(Attempt.signal_id == signal_id)
    if status:
        query = query.where(Attempt.status == status)
    if has_pr is not None:
        if has_pr:
            query = query.where(Attempt.pr_url.isnot(None))
        else:
            query = query.where(Attempt.pr_url.is_(None))

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query) or 0

    # Apply sorting
    sort_column = getattr(Attempt, sort_by)
    if sort_order == "desc":
        query = query.order_by(sort_column.desc())
    else:
        query = query.order_by(sort_column.asc())

    # Apply pagination
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size)

    # Execute query
    result = await db.execute(query)
    attempts = result.scalars().all()

    # Build response
    items = [
        AttemptWithSignal.model_validate(attempt)
        for attempt in attempts
    ]

    return PaginatedResponse.create(items, total, page, page_size)


@router.get("/{attempt_id}", response_model=AttemptWithSignal)
async def get_attempt(db: DbSession, attempt_id: UUID) -> AttemptWithSignal:
    """Get attempt details with signal information."""
    query = (
        select(Attempt)
        .options(selectinload(Attempt.signal))
        .where(Attempt.id == attempt_id)
    )
    result = await db.execute(query)
    attempt = result.scalar_one_or_none()

    if not attempt:
        raise HTTPException(status_code=404, detail="Attempt not found")

    return AttemptWithSignal.model_validate(attempt)


@router.post("/", response_model=AttemptSchema, status_code=201)
async def create_attempt(db: DbSession, attempt_in: AttemptCreate) -> Attempt:
    """
    Trigger a new attempt for a signal.

    Creates the attempt record and enqueues a job to run Claude Code.
    """
    # Verify signal exists
    signal_query = select(Signal).where(Signal.id == attempt_in.signal_id)
    signal_result = await db.execute(signal_query)
    signal = signal_result.scalar_one_or_none()

    if not signal:
        raise HTTPException(status_code=404, detail="Signal not found")

    # Get the next attempt number
    count_query = select(func.count()).where(Attempt.signal_id == attempt_in.signal_id)
    attempt_count = await db.scalar(count_query) or 0
    attempt_number = attempt_count + 1

    # Create the attempt
    attempt = Attempt(
        signal_id=attempt_in.signal_id,
        attempt_number=attempt_number,
        status=AttemptStatus.PENDING,
        runner_metadata_json=attempt_in.runner_config,
    )
    db.add(attempt)
    await db.flush()

    # Create a job to run the attempt
    job = Job(
        type=JobType.RUN_ATTEMPT,
        payload={
            "attempt_id": str(attempt.id),
            "signal_id": str(signal.id),
            "repo": signal.repo,
            "issue_number": signal.issue_number,
            "title": signal.title,
            "body": signal.body,
        },
        attempt_id=attempt.id,
    )
    db.add(job)

    # Update signal state
    signal.state = "in_progress"

    await db.flush()
    await db.refresh(attempt)
    return attempt


@router.post("/{attempt_id}/cancel", response_model=AttemptSchema)
async def cancel_attempt(db: DbSession, attempt_id: UUID) -> Attempt:
    """Request cancellation of a running attempt."""
    query = select(Attempt).where(Attempt.id == attempt_id)
    result = await db.execute(query)
    attempt = result.scalar_one_or_none()

    if not attempt:
        raise HTTPException(status_code=404, detail="Attempt not found")

    if attempt.status not in [AttemptStatus.PENDING, AttemptStatus.RUNNING]:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot cancel attempt in {attempt.status} status",
        )

    # Mark as failed with cancellation message
    attempt.status = AttemptStatus.FAILED
    attempt.error_message = "Cancelled by user"
    attempt.finished_at = datetime.now(timezone.utc)

    # Cancel any pending jobs for this attempt
    job_query = select(Job).where(
        Job.attempt_id == attempt_id,
        Job.status.in_([JobStatus.PENDING, JobStatus.CLAIMED]),
    )
    job_result = await db.execute(job_query)
    jobs = job_result.scalars().all()
    for job in jobs:
        job.status = JobStatus.FAILED
        job.error = "Cancelled by user"

    await db.flush()
    await db.refresh(attempt)
    return attempt


@router.get("/{attempt_id}/clarifications")
async def list_attempt_clarifications(
    db: DbSession,
    attempt_id: UUID,
    pending_only: bool = Query(False),
) -> list[dict]:
    """List clarifications for an attempt."""
    query = (
        select(Attempt)
        .options(selectinload(Attempt.clarifications))
        .where(Attempt.id == attempt_id)
    )
    result = await db.execute(query)
    attempt = result.scalar_one_or_none()

    if not attempt:
        raise HTTPException(status_code=404, detail="Attempt not found")

    clarifications = attempt.clarifications
    if pending_only:
        clarifications = [c for c in clarifications if not c.is_answered]

    return [
        {
            "id": str(c.id),
            "question_id": c.question_id,
            "question_text": c.question_text,
            "question_context": c.question_context,
            "default_answer": c.default_answer,
            "accepted_default": c.accepted_default,
            "answer_text": c.answer_text,
            "answered_at": c.answered_at.isoformat() if c.answered_at else None,
            "is_answered": c.is_answered,
        }
        for c in clarifications
    ]
