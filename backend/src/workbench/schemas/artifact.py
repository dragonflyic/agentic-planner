"""Artifact schemas for API request/response."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from workbench.models.artifact import ArtifactType


class ArtifactBase(BaseModel):
    """Base artifact fields."""

    attempt_id: UUID
    type: ArtifactType
    name: str | None = None
    mime_type: str = Field(default="text/plain")


class ArtifactCreate(ArtifactBase):
    """Request body for creating an artifact."""

    content_text: str | None = None
    content_path: str | None = None
    sequence_num: int | None = None
    is_final: bool = False


class Artifact(ArtifactBase):
    """Artifact response model (without content)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    size_bytes: int | None = None
    sequence_num: int | None = None
    is_final: bool
    created_at: datetime


class ArtifactWithContent(Artifact):
    """Artifact with content loaded."""

    content_text: str | None = None
    content_url: str | None = None  # For blob/path-based content
