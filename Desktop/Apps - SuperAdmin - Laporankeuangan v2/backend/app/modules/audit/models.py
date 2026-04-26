"""Audit log model.

Append-only record of every create / update / delete on tracked business
tables. Captured via a SQLAlchemy `before_flush` listener (see
listener.py) so individual services don't need to call into audit code.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_tenant_occurred", "tenant_id", "occurred_at"),
        Index("ix_audit_logs_tenant_table_row", "tenant_id", "table_name", "row_id"),
        Index("ix_audit_logs_tenant_user", "tenant_id", "user_id", "occurred_at"),
        CheckConstraint(
            "action IN ('create','update','delete','post','void')",
            name="ck_audit_logs_action",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    request_id: Mapped[str | None] = mapped_column(String(64))
    table_name: Mapped[str] = mapped_column(String(64), nullable=False)
    row_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    changes: Mapped[dict] = mapped_column(JSON, nullable=False)

    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
