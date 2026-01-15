"""Signal schemas for API request/response."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from workbench.models.signal import SignalState
from workbench.models.attempt import AttemptStatus


class SignalBase(BaseModel):
    """Base signal fields."""

    source: str = Field(default="github", max_length=50)
    repo: str = Field(..., max_length=255, description="Format: owner/repo")
    issue_number: int = Field(..., ge=1)
    title: str
    body: str | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    project_fields_json: dict[str, Any] = Field(default_factory=dict)


class SignalCreate(SignalBase):
    """Request body for creating a signal."""

    external_id: str | None = None
    priority: int = Field(default=0)


class SignalUpdate(BaseModel):
    """Request body for updating a signal."""

    state: SignalState | None = None
    priority: int | None = None
    title: str | None = None
    body: str | None = None
    metadata_json: dict[str, Any] | None = None
    project_fields_json: dict[str, Any] | None = None


class Signal(SignalBase):
    """Signal response model."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    external_id: str | None = None
    state: SignalState
    priority: int
    created_at: datetime
    updated_at: datetime

    @property
    def github_url(self) -> str:
        """Get the GitHub URL for this signal."""
        return f"https://github.com/{self.repo}/issues/{self.issue_number}"


class SignalWithStatus(Signal):
    """Signal with computed status from latest attempt."""

    latest_attempt_id: UUID | None = None
    latest_attempt_status: AttemptStatus | None = None
    latest_attempt_started: datetime | None = None
    latest_pr_url: str | None = None
    attempt_count: int = 0
    pending_clarifications: int = 0


class SignalListParams(BaseModel):
    """Query parameters for listing signals."""

    state: SignalState | None = None
    states: list[SignalState] | None = None
    repo: str | None = None
    search: str | None = Field(None, description="Search in title/body")
    sort_by: str = Field(default="created_at", pattern="^(created_at|updated_at|priority)$")
    sort_order: str = Field(default="desc", pattern="^(asc|desc)$")
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)

    @property
    def offset(self) -> int:
        """Calculate offset for database query."""
        return (self.page - 1) * self.page_size


class GitHubSyncRequest(BaseModel):
    """Request to sync signals from GitHub."""

    repos: list[str] = Field(..., min_length=1, description="List of owner/repo")
    labels: list[str] | None = None
    project_number: int | None = None
    since: datetime | None = None
    force_refresh: bool = False


class GitHubSyncResponse(BaseModel):
    """Response from GitHub sync operation."""

    job_id: UUID
    repos_queued: list[str]
    message: str
