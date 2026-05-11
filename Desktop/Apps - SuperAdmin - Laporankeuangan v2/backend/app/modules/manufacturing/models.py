"""Manufacturing models: BOM, BOMLine (Sprint M1).

Sprint M2 will add ManufacturingOrder + MOComponent in this same file.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
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


# ═══════════════════════════════════════════════════════════════════
# Manufacturing Order (Sprint M2)
# ═══════════════════════════════════════════════════════════════════

class ManufacturingOrder(Base):
    __tablename__ = "manufacturing_orders"
    __table_args__ = (
        UniqueConstraint("tenant_id", "mo_no", name="uq_mo_tenant_no"),
        Index("ix_mo_tenant_status", "tenant_id", "status"),
        Index("ix_mo_bom", "bom_id"),
        CheckConstraint(
            "status IN ('draft','confirmed','in_progress','done','cancelled')",
            name="ck_mo_status",
        ),
        CheckConstraint("qty_planned > 0", name="ck_mo_qty_planned_positive"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    mo_no: Mapped[str] = mapped_column(String(30), nullable=False)
    bom_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("boms.id", ondelete="RESTRICT"),
        nullable=False,
    )
    item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("items.id", ondelete="RESTRICT"),
        nullable=False,
    )
    warehouse_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("warehouses.id", ondelete="RESTRICT"),
        nullable=False,
    )
    qty_planned: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    qty_produced: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0")
    )
    planned_start: Mapped[date | None] = mapped_column(Date)
    planned_end: Mapped[date | None] = mapped_column(Date)
    actual_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    actual_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="draft"
    )
    backflush: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    notes: Mapped[str | None] = mapped_column(String(1000))
    # journals partitioned — plain UUID
    issue_journal_entry_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    receipt_journal_entry_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    done_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_reason: Mapped[str | None] = mapped_column(String(500))

    components: Mapped[list["MOComponent"]] = relationship(
        back_populates="mo",
        cascade="all, delete-orphan",
    )


class MOComponent(Base):
    __tablename__ = "mo_components"
    __table_args__ = (
        Index("ix_moc_mo", "mo_id"),
        CheckConstraint("qty_planned > 0", name="ck_moc_qty_planned_positive"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    mo_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("manufacturing_orders.id", ondelete="CASCADE"),
        nullable=False,
    )
    bom_line_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("bom_lines.id", ondelete="SET NULL"),
    )
    item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("items.id", ondelete="RESTRICT"),
        nullable=False,
    )
    qty_planned: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    qty_issued: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0")
    )
    unit_cost: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0")
    )

    mo: Mapped[ManufacturingOrder] = relationship(back_populates="components")
