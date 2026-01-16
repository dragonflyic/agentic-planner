"""Clarification management API routes."""

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from workbench.api.deps import DbSession
from workbench.models import (
    Attempt,
    AttemptStatus,
    Clarification,
    Job,
    JobType,
    Signal,
)
from workbench.schemas import (
    Clarification as ClarificationSchema,
    ClarificationSubmit,
    ClarificationWithAttempt,
)
from workbench.schemas.attempt import Attempt as AttemptSchema

router = APIRouter()


@router.get("/pending", response_model=list[ClarificationWithAttempt])
async def list_pending_clarifications(
    db: DbSession,
    repo: str | None = None,
) -> list[ClarificationWithAttempt]:
    """List all unanswered clarifications across all attempts."""
    query = (
        select(Clarification)
        .options(selectinload(Clarification.attempt).selectinload(Attempt.signal))
        .where(
            Clarification.answer_text.is_(None),
            Clarification.accepted_default == False,  # noqa: E712
        )
    )

    if repo:
        query = query.join(Clarification.attempt).join(Attempt.signal).where(
            Signal.repo.ilike(f"%{repo}%")
        )

    query = query.order_by(Clarification.created_at.desc())

    result = await db.execute(query)
    clarifications = result.scalars().all()

    return [
        ClarificationWithAttempt.model_validate(c)
        for c in clarifications
    ]


@router.get("/{clarification_id}", response_model=ClarificationWithAttempt)
async def get_clarification(
    db: DbSession, clarification_id: UUID
) -> ClarificationWithAttempt:
    """Get clarification details with attempt context."""
    query = (
        select(Clarification)
        .options(selectinload(Clarification.attempt).selectinload(Attempt.signal))
        .where(Clarification.id == clarification_id)
    )
    result = await db.execute(query)
    clarification = result.scalar_one_or_none()

    if not clarification:
        raise HTTPException(status_code=404, detail="Clarification not found")

    return ClarificationWithAttempt.model_validate(clarification)


@router.post("/{clarification_id}/submit", response_model=ClarificationSchema)
async def submit_clarification(
    db: DbSession,
    clarification_id: UUID,
    submission: ClarificationSubmit,
) -> Clarification:
    """Submit a human answer to a clarification question."""
    query = select(Clarification).where(Clarification.id == clarification_id)
    result = await db.execute(query)
    clarification = result.scalar_one_or_none()

    if not clarification:
        raise HTTPException(status_code=404, detail="Clarification not found")

    if clarification.is_answered:
        raise HTTPException(
            status_code=400,
            detail="Clarification has already been answered",
        )

    # Must provide either answer_text or accept default
    if not submission.answer_text and not submission.accepted_default:
        raise HTTPException(
            status_code=400,
            detail="Must provide answer_text or set accepted_default=true",
        )

    if submission.accepted_default and not clarification.default_answer:
        raise HTTPException(
            status_code=400,
            detail="Cannot accept default - no default answer available",
        )

    # Update clarification
    clarification.answer_text = submission.answer_text
    clarification.accepted_default = submission.accepted_default
    clarification.answered_at = datetime.now(timezone.utc)
    clarification.answered_by = submission.answered_by

    await db.flush()
    await db.refresh(clarification)
    return clarification


@router.post("/{clarification_id}/retry", response_model=AttemptSchema)
async def retry_with_clarification(
    db: DbSession,
    clarification_id: UUID,
) -> Attempt:
    """
    Retry the attempt after providing clarification.

    Creates a new attempt with the clarification answers pre-loaded.
    """
    # Get clarification with attempt and signal
    query = (
        select(Clarification)
        .options(selectinload(Clarification.attempt).selectinload(Attempt.signal))
        .where(Clarification.id == clarification_id)
    )
    result = await db.execute(query)
    clarification = result.scalar_one_or_none()

    if not clarification:
        raise HTTPException(status_code=404, detail="Clarification not found")

    if not clarification.is_answered:
        raise HTTPException(
            status_code=400,
            detail="Clarification must be answered before retry",
        )

    old_attempt = clarification.attempt
    signal = old_attempt.signal

    # Get all answered clarifications from the old attempt
    clarifications_query = (
        select(Clarification)
        .where(Clarification.attempt_id == old_attempt.id)
    )
    clarifications_result = await db.execute(clarifications_query)
    all_clarifications = clarifications_result.scalars().all()

    # Build clarification context for the new attempt
    clarification_context = []
    for c in all_clarifications:
        if c.is_answered:
            clarification_context.append({
                "question": c.question_text,
                "answer": c.effective_answer,
            })

    # Create new attempt
    new_attempt = Attempt(
        signal_id=signal.id,
        attempt_number=old_attempt.attempt_number + 1,
        status=AttemptStatus.PENDING,
        runner_metadata_json={
            **old_attempt.runner_metadata_json,
            "clarifications": clarification_context,
            "retry_of": str(old_attempt.id),
        },
    )
    db.add(new_attempt)
    await db.flush()

    # Create job to run the new attempt
    job = Job(
        type=JobType.RETRY_ATTEMPT,
        payload={
            "attempt_id": str(new_attempt.id),
            "signal_id": str(signal.id),
            "repo": signal.repo,
            "issue_number": signal.issue_number,
            "title": signal.title,
            "body": signal.body,
            "clarifications": clarification_context,
            "previous_attempt_id": str(old_attempt.id),
        },
        attempt_id=new_attempt.id,
    )
    db.add(job)

    await db.flush()
    await db.refresh(new_attempt)
    return new_attempt
