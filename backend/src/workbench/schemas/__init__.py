"""Pydantic schemas for API request/response validation."""

from workbench.schemas.common import PaginatedResponse, PaginationParams
from workbench.schemas.signal import (
    GitHubSyncRequest,
    GitHubSyncResponse,
    Signal,
    SignalCreate,
    SignalListParams,
    SignalUpdate,
    SignalWithStatus,
)
from workbench.schemas.attempt import (
    Attempt,
    AttemptCreate,
    AttemptListParams,
    AttemptWithSignal,
)
from workbench.schemas.clarification import (
    Clarification,
    ClarificationCreate,
    ClarificationSubmit,
    ClarificationWithAttempt,
)
from workbench.schemas.job import Job, JobCreate, JobQueueStats
from workbench.schemas.artifact import Artifact, ArtifactCreate, ArtifactWithContent

__all__ = [
    # Common
    "PaginatedResponse",
    "PaginationParams",
    # Signal
    "GitHubSyncRequest",
    "GitHubSyncResponse",
    "Signal",
    "SignalCreate",
    "SignalUpdate",
    "SignalListParams",
    "SignalWithStatus",
    # Attempt
    "Attempt",
    "AttemptCreate",
    "AttemptListParams",
    "AttemptWithSignal",
    # Clarification
    "Clarification",
    "ClarificationCreate",
    "ClarificationSubmit",
    "ClarificationWithAttempt",
    # Job
    "Job",
    "JobCreate",
    "JobQueueStats",
    # Artifact
    "Artifact",
    "ArtifactCreate",
    "ArtifactWithContent",
]
