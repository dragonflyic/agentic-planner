"""Signal management API routes."""

from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from workbench.api.deps import DbSession
from workbench.models import Attempt, JobType, Signal
from workbench.schemas import (
    GitHubSyncRequest,
    GitHubSyncResponse,
    PaginatedResponse,
    SignalCreate,
    SignalUpdate,
    SignalWithStatus,
)
from workbench.schemas.signal import Signal as SignalSchema
from workbench.services.job_service import JobService

router = APIRouter()


@router.get("/", response_model=PaginatedResponse[SignalWithStatus])
async def list_signals(
    db: DbSession,
    repo: str | None = None,
    search: str | None = None,
    ids: str | None = Query(None, description="Comma-separated list of signal IDs to filter by"),
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
    if ids:
        # Parse comma-separated IDs and filter
        try:
            id_list = [UUID(id_str.strip()) for id_str in ids.split(",") if id_str.strip()]
            if id_list:
                query = query.where(Signal.id.in_(id_list))
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid ID format in ids parameter")
    if repo:
        query = query.where(Signal.repo.ilike(f"%{repo}%"))
    if search:
        query = query.where(
            Signal.title.ilike(f"%{search}%") | Signal.body.ilike(f"%{search}%")
        )

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query) or 0

    # Apply sorting with secondary sort key for consistent ordering
    sort_column = getattr(Signal, sort_by)
    if sort_order == "desc":
        query = query.order_by(sort_column.desc(), Signal.id.asc())
    else:
        query = query.order_by(sort_column.asc(), Signal.id.asc())

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


@router.post("/sync", response_model=GitHubSyncResponse, status_code=202)
async def sync_from_github(
    db: DbSession,
    request: GitHubSyncRequest,
) -> GitHubSyncResponse:
    """
    Trigger a sync from a GitHub Project V2.

    Creates a SYNC_SIGNALS job that will be processed by a worker.
    The sync imports all issues from the project board as signals.

    You can provide either:
    - project_url: Full URL like https://github.com/orgs/dragonflyic/projects/1
    - org + project_number: Explicit parameters

    Optional filters:
    - repos: Only sync issues from specific repos
    - labels: Only sync issues with specific labels
    - since: Only sync items updated after this timestamp
    """
    job_service = JobService(db)

    # Build job payload
    payload = {
        "org": request.org,
        "project_number": request.project_number,
        "force_refresh": request.force_refresh,
    }

    if request.since:
        payload["since"] = request.since.isoformat()
    if request.labels:
        payload["label_filter"] = request.labels
    if request.repos:
        payload["repo_filter"] = request.repos

    # Create the sync job
    job = await job_service.create_job(
        job_type=JobType.SYNC_SIGNALS,
        payload=payload,
        priority=10,  # Higher priority than regular attempt jobs
    )

    await db.commit()

    return GitHubSyncResponse(
        job_id=job.id,
        repos_queued=request.repos or [],
        message=f"Sync job created for {request.org}/projects/{request.project_number}",
    )


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


@router.delete("/{signal_id}", status_code=204)
async def delete_signal(db: DbSession, signal_id: UUID) -> None:
    """Delete a signal."""
    query = select(Signal).where(Signal.id == signal_id)
    result = await db.execute(query)
    signal = result.scalar_one_or_none()

    if not signal:
        raise HTTPException(status_code=404, detail="Signal not found")

    await db.delete(signal)
