"""Signal model - represents a work candidate from GitHub."""

from enum import Enum
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from workbench.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from workbench.models.attempt import Attempt


class SignalState(str, Enum):
    """Signal state in the workflow."""

    PENDING = "pending"  # Newly synced, awaiting triage
    QUEUED = "queued"  # Ready for processing
    IN_PROGRESS = "in_progress"  # Currently being attempted
    COMPLETED = "completed"  # Successfully resolved
    BLOCKED = "blocked"  # Needs human intervention
    SKIPPED = "skipped"  # Marked as not worth attempting
    ARCHIVED = "archived"  # Historical record


class Signal(Base, UUIDMixin, TimestampMixin):
    """A signal represents a work candidate, typically from a GitHub issue."""

    __tablename__ = "signals"
    __table_args__ = (
        UniqueConstraint("repo", "issue_number", name="uq_signals_repo_issue"),
    )

    # GitHub source identification
    source: Mapped[str] = mapped_column(String(50), default="github", nullable=False)
    repo: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    issue_number: Mapped[int] = mapped_column(Integer, nullable=False)
    external_id: Mapped[str | None] = mapped_column(String(255), index=True)

    # Content
    title: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str | None] = mapped_column(Text)

    # Flexible metadata storage
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}"
    )
    project_fields_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}"
    )

    # State management
    state: Mapped[SignalState] = mapped_column(
        String(20), default=SignalState.PENDING, nullable=False, index=True
    )
    priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Relationships
    attempts: Mapped[list["Attempt"]] = relationship(
        "Attempt", back_populates="signal", cascade="all, delete-orphan"
    )

    @property
    def github_url(self) -> str:
        """Get the GitHub URL for this signal."""
        return f"https://github.com/{self.repo}/issues/{self.issue_number}"

    def __repr__(self) -> str:
        return f"<Signal {self.repo}#{self.issue_number}: {self.title[:50]}>"
