"""Artifact model - stores logs, diffs, and other outputs from attempts."""

from enum import Enum
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, Integer, LargeBinary, String, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from workbench.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from workbench.models.attempt import Attempt


class ArtifactType(str, Enum):
    """Type of artifact."""

    LOG = "log"  # Execution log (streaming)
    DIFF = "diff"  # Git diff output
    PLAN = "plan"  # Generated plan JSON
    COST = "cost"  # Token usage/cost breakdown
    ERROR = "error"  # Error details
    SCREENSHOT = "screenshot"  # Visual artifacts
    CUSTOM = "custom"  # Extension point


class Artifact(Base, UUIDMixin, TimestampMixin):
    """An artifact captures output from an attempt (logs, diffs, etc.)."""

    __tablename__ = "artifacts"

    # Foreign keys
    attempt_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("attempts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Artifact metadata
    type: Mapped[ArtifactType] = mapped_column(String(20), nullable=False, index=True)
    name: Mapped[str | None] = mapped_column(String(255))
    mime_type: Mapped[str] = mapped_column(String(100), default="text/plain")

    # Content storage (use one of these)
    content_text: Mapped[str | None] = mapped_column(Text)
    content_blob: Mapped[bytes | None] = mapped_column(LargeBinary)
    content_path: Mapped[str | None] = mapped_column(String(500))
    size_bytes: Mapped[int | None] = mapped_column(Integer)

    # For streaming logs: sequence tracking
    sequence_num: Mapped[int | None] = mapped_column(Integer)
    is_final: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Relationships
    attempt: Mapped["Attempt"] = relationship("Attempt", back_populates="artifacts")

    @property
    def has_content(self) -> bool:
        """Check if artifact has content stored."""
        return any([self.content_text, self.content_blob, self.content_path])

    def __repr__(self) -> str:
        return f"<Artifact {self.id} type={self.type} attempt={self.attempt_id}>"
