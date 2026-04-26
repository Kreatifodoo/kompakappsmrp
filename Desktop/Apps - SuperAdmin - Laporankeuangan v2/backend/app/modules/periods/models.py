"""Period closure event log.

Each row is an immutable record of a close or reopen action — the
authoritative trail for "who closed January through Jan 31, when, and
why was it later reopened."
"""

import uuid
from datetime import date, datetime

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class PeriodClosureEvent(Base):
    __tablename__ = "period_closure_events"
    __table_args__ = (
        Index("ix_period_closure_events_tenant_at", "tenant_id", "performed_at"),
        CheckConstraint("action IN ('close','reopen')", name="ck_period_closure_events_action"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    # The closed_through date that resulted from this action (NULL if
    # the reopen cleared closures entirely)
    through_date: Mapped[date | None] = mapped_column(Date)
    # The previous closed_through value, for diffing
    previous_through_date: Mapped[date | None] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(String(1000))
    performed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    performed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
