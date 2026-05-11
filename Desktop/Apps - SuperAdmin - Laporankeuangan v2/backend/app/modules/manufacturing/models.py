"""Manufacturing models: BOM, BOMLine (Sprint M1).

Sprint M2 will add ManufacturingOrder + MOComponent in this same file.
"""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


# ═══════════════════════════════════════════════════════════════════
# Bill of Materials
# ═══════════════════════════════════════════════════════════════════

class BOM(Base):
    __tablename__ = "boms"
    __table_args__ = (
        UniqueConstraint("tenant_id", "bom_code", name="uq_bom_tenant_code"),
        Index("ix_bom_tenant_item", "tenant_id", "item_id"),
        CheckConstraint(
            "status IN ('draft','active','obsolete')", name="ck_bom_status"
        ),
        CheckConstraint("qty_output > 0", name="ck_bom_qty_output_positive"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    bom_code: Mapped[str] = mapped_column(String(40), nullable=False)
    item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("items.id", ondelete="RESTRICT"),
        nullable=False,
    )
    qty_output: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("1")
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="draft"
    )
    notes: Mapped[str | None] = mapped_column(String(1000))
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    lines: Mapped[list["BOMLine"]] = relationship(
        back_populates="bom",
        cascade="all, delete-orphan",
        order_by="BOMLine.line_no",
    )


class BOMLine(Base):
    __tablename__ = "bom_lines"
    __table_args__ = (
        Index("ix_boml_bom", "bom_id"),
        CheckConstraint("qty_required > 0", name="ck_boml_qty_positive"),
        CheckConstraint(
            "scrap_pct >= 0 AND scrap_pct < 100", name="ck_boml_scrap_range"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    bom_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("boms.id", ondelete="CASCADE"),
        nullable=False,
    )
    line_no: Mapped[int] = mapped_column(Integer, nullable=False)
    item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("items.id", ondelete="RESTRICT"),
        nullable=False,
    )
    qty_required: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    scrap_pct: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False, default=Decimal("0")
    )
    notes: Mapped[str | None] = mapped_column(String(500))

    bom: Mapped[BOM] = relationship(back_populates="lines")
