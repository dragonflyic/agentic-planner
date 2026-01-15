"""Attempt model - represents a Claude Code execution against a signal."""

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from workbench.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from workbench.models.artifact import Artifact
    from workbench.models.clarification import Clarification
    from workbench.models.signal import Signal


class AttemptStatus(str, Enum):
    """Status of an attempt."""

    PENDING = "pending"  # Created but not started
    RUNNING = "running"  # Currently executing
    SUCCESS = "success"  # Completed successfully with PR
    NEEDS_HUMAN = "needs_human"  # Requires clarification
    FAILED = "failed"  # Error during execution
    NOOP = "noop"  # No changes needed/possible


class Attempt(Base, UUIDMixin, TimestampMixin):
    """An attempt represents a Claude Code execution against a signal."""

    __tablename__ = "attempts"

    # Foreign keys
    signal_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("signals.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Status tracking
    status: Mapped[AttemptStatus] = mapped_column(
        String(20), default=AttemptStatus.PENDING, nullable=False, index=True
    )
    attempt_number: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    # Timing
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Results
    pr_url: Mapped[str | None] = mapped_column(String(500))
    pr_number: Mapped[int | None] = mapped_column(Integer)
    branch_name: Mapped[str | None] = mapped_column(String(255))

    # Detailed results
    summary_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}"
    )
    runner_metadata_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}"
    )
    error_message: Mapped[str | None] = mapped_column(Text)

    # Relationships
    signal: Mapped["Signal"] = relationship("Signal", back_populates="attempts")
    clarifications: Mapped[list["Clarification"]] = relationship(
        "Clarification", back_populates="attempt", cascade="all, delete-orphan"
    )
    artifacts: Mapped[list["Artifact"]] = relationship(
        "Artifact", back_populates="attempt", cascade="all, delete-orphan"
    )

    @property
    def duration_ms(self) -> int | None:
        """Calculate duration in milliseconds."""
        if self.started_at and self.finished_at:
            delta = self.finished_at - self.started_at
            return int(delta.total_seconds() * 1000)
        return None

    @property
    def pending_clarifications(self) -> list["Clarification"]:
        """Get unanswered clarifications."""
        return [c for c in self.clarifications if c.answer_text is None and not c.accepted_default]

    def __repr__(self) -> str:
        return f"<Attempt {self.id} signal={self.signal_id} status={self.status}>"
