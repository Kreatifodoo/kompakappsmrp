"""Pydantic schemas for period closure."""

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class PeriodStatus(BaseModel):
    """Current closure state for the calling tenant."""

    closed_through: date | None
    is_locked: bool  # convenience: true when closed_through is not None


class ClosePeriodRequest(BaseModel):
    """Close everything dated on or before `through_date`."""

    through_date: date
    notes: str | None = Field(default=None, max_length=1000)


class ReopenPeriodRequest(BaseModel):
    """Reopen the period: set closed_through to a new (earlier) date,
    or pass `null` to clear all closures. A reason is mandatory — this
    is an exceptional admin action that must be auditable."""

    new_through_date: date | None = None
    reason: str = Field(min_length=1, max_length=1000)


class ClosureEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    action: Literal["close", "reopen"]
    through_date: date | None
    previous_through_date: date | None
    notes: str | None
    performed_by: UUID | None
    performed_at: datetime
