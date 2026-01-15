"""Clarification model - human answers to stuck conditions."""

from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from workbench.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from workbench.models.attempt import Attempt


class Clarification(Base, UUIDMixin, TimestampMixin):
    """A clarification captures a question from Claude and the human answer."""

    __tablename__ = "clarifications"
    __table_args__ = (
        UniqueConstraint("attempt_id", "question_id", name="uq_clarifications_attempt_question"),
    )

    # Foreign keys
    attempt_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("attempts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Question identification
    question_id: Mapped[str] = mapped_column(String(255), nullable=False)
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    question_context: Mapped[str | None] = mapped_column(Text)

    # Default handling
    default_answer: Mapped[str | None] = mapped_column(Text)
    accepted_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Human response
    answer_text: Mapped[str | None] = mapped_column(Text)
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    answered_by: Mapped[str | None] = mapped_column(String(255))

    # UI anchoring for replay
    anchors_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}"
    )

    # Relationships
    attempt: Mapped["Attempt"] = relationship("Attempt", back_populates="clarifications")

    @property
    def is_answered(self) -> bool:
        """Check if this clarification has been answered."""
        return self.answer_text is not None or self.accepted_default

    @property
    def effective_answer(self) -> str | None:
        """Get the effective answer (user answer or accepted default)."""
        if self.answer_text is not None:
            return self.answer_text
        if self.accepted_default and self.default_answer is not None:
            return self.default_answer
        return None

    def __repr__(self) -> str:
        return f"<Clarification {self.id} question_id={self.question_id} answered={self.is_answered}>"
