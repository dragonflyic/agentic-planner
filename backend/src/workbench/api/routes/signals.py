"""Signal management API routes."""

from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from workbench.api.deps import DbSession
from workbench.models import Attempt, Signal, SignalState
from workbench.schemas import (
    PaginatedResponse,
    SignalCreate,
    SignalUpdate,
    SignalWithStatus,
)
from workbench.schemas.signal import Signal as SignalSchema

router = APIRouter()


@router.get("/", response_model=PaginatedResponse[SignalWithStatus])
async def list_signals(
    db: DbSession,
    state: SignalState | None = None,
    repo: str | None = None,
    search: str | None = None,
    sort_by: str = Query("created_at", pattern="^(created_at|updated_at|priority)$"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> PaginatedResponse[SignalWithStatus]:
    """List signals with optional filtering, sorting, and pagination."""
    # Build base query - eagerly load attempts and their clarifications to avoid lazy loading
    query = select(Signal).options(
        selectinload(Signal.attempts).selectinload(Attempt.clarifications)
    )

    # Apply filters
    if state:
        query = query.where(Signal.state == state)
    if repo:
        query = query.where(Signal.repo.ilike(f"%{repo}%"))
    if search:
        query = query.where(
            Signal.title.ilike(f"%{search}%") | Signal.body.ilike(f"%{search}%")
        )

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query) or 0

    # Apply sorting
    sort_column = getattr(Signal, sort_by)
    if sort_order == "desc":
        query = query.order_by(sort_column.desc())
    else:
        query = query.order_by(sort_column.asc())

    # Apply pagination
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size)

    # Execute query
    result = await db.execute(query)
    signals = result.scalars().all()

    # Build response with status info
    items = []
    for signal in signals:
        # Get latest attempt info
        latest_attempt = None
        if signal.attempts:
            latest_attempt = max(signal.attempts, key=lambda a: a.attempt_number)

        pending_clarifications = 0
        if latest_attempt:
            pending_clarifications = len(latest_attempt.pending_clarifications)

        items.append(
            SignalWithStatus(
                id=signal.id,
                source=signal.source,
                repo=signal.repo,
                issue_number=signal.issue_number,
                external_id=signal.external_id,
                title=signal.title,
                body=signal.body,
                metadata_json=signal.metadata_json,
                project_fields_json=signal.project_fields_json,
                state=signal.state,
                priority=signal.priority,
                created_at=signal.created_at,
                updated_at=signal.updated_at,
                latest_attempt_id=latest_attempt.id if latest_attempt else None,
                latest_attempt_status=latest_attempt.status if latest_attempt else None,
                latest_attempt_started=latest_attempt.started_at if latest_attempt else None,
                latest_pr_url=latest_attempt.pr_url if latest_attempt else None,
                attempt_count=len(signal.attempts),
                pending_clarifications=pending_clarifications,
            )
        )

    return PaginatedResponse.create(items, total, page, page_size)


@router.get("/{signal_id}", response_model=SignalWithStatus)
async def get_signal(db: DbSession, signal_id: UUID) -> SignalWithStatus:
    """Get a single signal by ID with status information."""
    query = (
        select(Signal)
        .options(selectinload(Signal.attempts).selectinload(Attempt.clarifications))
        .where(Signal.id == signal_id)
    )
    result = await db.execute(query)
    signal = result.scalar_one_or_none()

    if not signal:
        raise HTTPException(status_code=404, detail="Signal not found")

    # Get latest attempt info
    latest_attempt = None
    if signal.attempts:
        latest_attempt = max(signal.attempts, key=lambda a: a.attempt_number)

    pending_clarifications = 0
    if latest_attempt:
        pending_clarifications = len(latest_attempt.pending_clarifications)

    return SignalWithStatus(
        id=signal.id,
        source=signal.source,
        repo=signal.repo,
        issue_number=signal.issue_number,
        external_id=signal.external_id,
        title=signal.title,
        body=signal.body,
        metadata_json=signal.metadata_json,
        project_fields_json=signal.project_fields_json,
        state=signal.state,
        priority=signal.priority,
        created_at=signal.created_at,
        updated_at=signal.updated_at,
        latest_attempt_id=latest_attempt.id if latest_attempt else None,
        latest_attempt_status=latest_attempt.status if latest_attempt else None,
        latest_attempt_started=latest_attempt.started_at if latest_attempt else None,
        latest_pr_url=latest_attempt.pr_url if latest_attempt else None,
        attempt_count=len(signal.attempts),
        pending_clarifications=pending_clarifications,
    )


@router.post("/", response_model=SignalSchema, status_code=201)
async def create_signal(db: DbSession, signal_in: SignalCreate) -> Signal:
    """Create a new signal manually."""
    signal = Signal(
        source=signal_in.source,
        repo=signal_in.repo,
        issue_number=signal_in.issue_number,
        external_id=signal_in.external_id,
        title=signal_in.title,
        body=signal_in.body,
        metadata_json=signal_in.metadata_json,
        project_fields_json=signal_in.project_fields_json,
        priority=signal_in.priority,
    )
    db.add(signal)
    await db.flush()
    await db.refresh(signal)
    return signal


@router.patch("/{signal_id}", response_model=SignalSchema)
async def update_signal(
    db: DbSession, signal_id: UUID, signal_in: SignalUpdate
) -> Signal:
    """Update signal properties."""
    query = select(Signal).where(Signal.id == signal_id)
    result = await db.execute(query)
    signal = result.scalar_one_or_none()

    if not signal:
        raise HTTPException(status_code=404, detail="Signal not found")

    # Update only provided fields
    update_data = signal_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(signal, field, value)

    await db.flush()
    await db.refresh(signal)
    return signal


@router.post("/{signal_id}/queue", response_model=SignalSchema)
async def queue_signal(
    db: DbSession, signal_id: UUID, priority: int = Query(0)
) -> Signal:
    """Move signal to queued state, ready for processing."""
    query = select(Signal).where(Signal.id == signal_id)
    result = await db.execute(query)
    signal = result.scalar_one_or_none()

    if not signal:
        raise HTTPException(status_code=404, detail="Signal not found")

    signal.state = SignalState.QUEUED
    signal.priority = priority

    await db.flush()
    await db.refresh(signal)
    return signal


@router.delete("/{signal_id}", status_code=204)
async def delete_signal(db: DbSession, signal_id: UUID) -> None:
    """Delete a signal."""
    query = select(Signal).where(Signal.id == signal_id)
    result = await db.execute(query)
    signal = result.scalar_one_or_none()

    if not signal:
        raise HTTPException(status_code=404, detail="Signal not found")

    await db.delete(signal)
