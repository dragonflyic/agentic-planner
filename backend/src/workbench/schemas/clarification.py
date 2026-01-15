"""Clarification schemas for API request/response."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from workbench.schemas.attempt import Attempt


class ClarificationBase(BaseModel):
    """Base clarification fields."""

    attempt_id: UUID
    question_id: str = Field(..., max_length=255)
    question_text: str
    question_context: str | None = None
    default_answer: str | None = None
    anchors_json: dict[str, Any] = Field(default_factory=dict)


class ClarificationCreate(ClarificationBase):
    """Request body for creating a clarification (from runner)."""

    pass


class ClarificationSubmit(BaseModel):
    """Request body for submitting a human answer."""

    answer_text: str | None = None
    accepted_default: bool = False
    answered_by: str | None = None


class Clarification(ClarificationBase):
    """Clarification response model."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    accepted_default: bool
    answer_text: str | None = None
    answered_at: datetime | None = None
    answered_by: str | None = None
    created_at: datetime
    updated_at: datetime

    @property
    def is_answered(self) -> bool:
        """Check if this clarification has been answered."""
        return self.answer_text is not None or self.accepted_default


class ClarificationWithAttempt(Clarification):
    """Clarification with attempt context."""

    attempt: Attempt
