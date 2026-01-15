"""Attempt schemas for API request/response."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from workbench.models.attempt import AttemptStatus
from workbench.schemas.signal import Signal


class AttemptBase(BaseModel):
    """Base attempt fields."""

    signal_id: UUID


class AttemptCreate(AttemptBase):
    """Request body for creating an attempt."""

    runner_config: dict[str, Any] = Field(
        default_factory=dict,
        description="Configuration for Claude Code runner",
    )


class Attempt(AttemptBase):
    """Attempt response model."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    status: AttemptStatus
    attempt_number: int
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_ms: int | None = None
    pr_url: str | None = None
    pr_number: int | None = None
    branch_name: str | None = None
    summary_json: dict[str, Any] = Field(default_factory=dict)
    runner_metadata_json: dict[str, Any] = Field(default_factory=dict)
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime


class AttemptWithSignal(Attempt):
    """Attempt with embedded signal info."""

    signal: Signal


class AttemptListParams(BaseModel):
    """Query parameters for listing attempts."""

    signal_id: UUID | None = None
    status: AttemptStatus | None = None
    statuses: list[AttemptStatus] | None = None
    has_pr: bool | None = None
    sort_by: str = Field(default="started_at", pattern="^(started_at|finished_at|created_at)$")
    sort_order: str = Field(default="desc", pattern="^(asc|desc)$")
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)

    @property
    def offset(self) -> int:
        """Calculate offset for database query."""
        return (self.page - 1) * self.page_size


class AttemptOutput(BaseModel):
    """Structured output from an attempt."""

    status: str  # SUCCESS | NEEDS_HUMAN | FAILED | NOOP
    pr_url: str | None = None
    what_changed: list[str] = Field(default_factory=list)
    commands_run: list[str] = Field(default_factory=list)
    checks: dict[str, Any] = Field(default_factory=dict)
    questions: list[dict[str, Any]] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)
    error_message: str | None = None
    metrics: dict[str, Any] = Field(default_factory=dict)
