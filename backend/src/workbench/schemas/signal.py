"""Signal schemas for API request/response."""

from datetime import datetime
from typing import Any
from uuid import UUID

import re

from pydantic import BaseModel, ConfigDict, Field, model_validator

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
    """Request to sync signals from GitHub Project V2."""

    # Option 1: Direct URL
    project_url: str | None = Field(
        None,
        description="Full GitHub Project URL (e.g., https://github.com/orgs/dragonflyic/projects/1)",
    )

    # Option 2: Explicit parameters
    org: str | None = Field(None, description="GitHub organization login")
    project_number: int | None = Field(None, ge=1, description="Project number")

    # Filters
    repos: list[str] | None = Field(None, description="Filter to specific repos (owner/repo)")
    labels: list[str] | None = Field(None, description="Filter by labels")
    since: datetime | None = Field(None, description="Only sync items updated after")
    force_refresh: bool = Field(False, description="Force update all fields")

    @model_validator(mode="after")
    def validate_and_parse(self) -> "GitHubSyncRequest":
        """Parse URL if provided, validate that either URL or explicit params exist."""
        # Parse project URL if provided
        if self.project_url:
            # Match: https://github.com/orgs/{org}/projects/{number}[/views/{view}]
            pattern = r"https://github\.com/orgs/([^/]+)/projects/(\d+)"
            match = re.match(pattern, self.project_url)
            if match:
                self.org = match.group(1)
                self.project_number = int(match.group(2))
            else:
                raise ValueError(
                    f"Invalid project URL format: {self.project_url}. "
                    "Expected: https://github.com/orgs/<org>/projects/<number>"
                )

        # Validate we have required params
        if not self.org or not self.project_number:
            raise ValueError(
                "Either project_url or both org and project_number are required"
            )

        return self


class GitHubSyncResponse(BaseModel):
    """Response from GitHub sync operation."""

    job_id: UUID
    repos_queued: list[str]
    message: str
