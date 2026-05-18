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
    operations: Mapped[list["BOMOperation"]] = relationship(
        back_populates="bom",
        cascade="all, delete-orphan",
        order_by="BOMOperation.seq",
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
    # Sprint M4: optional standard unit cost. When set on ALL lines of a BOM,
    # the MO uses standard costing with variance recognition on completion.
    std_unit_cost: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
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
    # Sprint M4: standard costing & variance
    std_total_cost: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    variance_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    variance_journal_entry_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    # Sprint M5: labor cost
    labor_total_cost: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    labor_journal_entry_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
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
    operations: Mapped[list["MOOperation"]] = relationship(
        back_populates="mo",
        cascade="all, delete-orphan",
        order_by="MOOperation.seq",
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
    # Sprint M4: snapshot from bom_line.std_unit_cost at MO confirm time
    std_unit_cost: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))

    mo: Mapped[ManufacturingOrder] = relationship(back_populates="components")


# ═══════════════════════════════════════════════════════════════════
# Work Center + Operations (Sprint M5)
# ═══════════════════════════════════════════════════════════════════

from sqlalchemy import Boolean as _Boolean  # local alias if not imported above


class WorkCenter(Base):
    __tablename__ = "work_centers"
    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_wc_tenant_code"),
        Index("ix_wc_tenant_active", "tenant_id", "is_active"),
        CheckConstraint("cost_per_hour >= 0", name="ck_wc_cph_nonneg"),
        CheckConstraint("capacity_hours_per_day > 0", name="ck_wc_capacity_positive"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    code: Mapped[str] = mapped_column(String(40), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    cost_per_hour: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, default=Decimal("0")
    )
    capacity_hours_per_day: Mapped[Decimal] = mapped_column(
        Numeric(8, 2), nullable=False, default=Decimal("8")
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    notes: Mapped[str | None] = mapped_column(String(500))
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class BOMOperation(Base):
    __tablename__ = "bom_operations"
    __table_args__ = (
        Index("ix_bomop_bom", "bom_id"),
        CheckConstraint("time_minutes >= 0", name="ck_bomop_time_nonneg"),
        CheckConstraint("setup_minutes >= 0", name="ck_bomop_setup_nonneg"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    bom_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("boms.id", ondelete="CASCADE"),
        nullable=False,
    )
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    work_center_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("work_centers.id", ondelete="RESTRICT"),
        nullable=False,
    )
    time_minutes: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False, default=Decimal("0")
    )
    setup_minutes: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False, default=Decimal("0")
    )
    notes: Mapped[str | None] = mapped_column(String(500))

    bom: Mapped[BOM] = relationship(back_populates="operations")


class MOOperation(Base):
    __tablename__ = "mo_operations"
    __table_args__ = (
        Index("ix_moop_mo", "mo_id"),
        CheckConstraint(
            "status IN ('pending','in_progress','done')", name="ck_moop_status"
        ),
        CheckConstraint("planned_time_min >= 0", name="ck_moop_planned_nonneg"),
        CheckConstraint("actual_time_min >= 0", name="ck_moop_actual_nonneg"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    mo_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("manufacturing_orders.id", ondelete="CASCADE"),
        nullable=False,
    )
    bom_operation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("bom_operations.id", ondelete="SET NULL"),
    )
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    work_center_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("work_centers.id", ondelete="RESTRICT"),
        nullable=False,
    )
    planned_time_min: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    actual_time_min: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False, default=Decimal("0")
    )
    cost_per_hour_snapshot: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending"
    )
    notes: Mapped[str | None] = mapped_column(String(500))

    mo: Mapped[ManufacturingOrder] = relationship(back_populates="operations")


# ═══════════════════════════════════════════════════════════════════
# Scrap (Sprint M6)
# ═══════════════════════════════════════════════════════════════════

class MfgScrap(Base):
    __tablename__ = "mfg_scraps"
    __table_args__ = (
        UniqueConstraint("tenant_id", "scrap_no", name="uq_scrap_tenant_no"),
        Index("ix_scrap_tenant_status", "tenant_id", "status"),
        Index("ix_scrap_mo", "mo_id"),
        CheckConstraint(
            "status IN ('draft','posted','void')", name="ck_scrap_status"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    scrap_no: Mapped[str] = mapped_column(String(30), nullable=False)
    scrap_date: Mapped[date] = mapped_column(Date, nullable=False)
    warehouse_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("warehouses.id", ondelete="RESTRICT"),
        nullable=False,
    )
    mo_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("manufacturing_orders.id", ondelete="SET NULL"),
    )
    reason: Mapped[str | None] = mapped_column(String(500))
    notes: Mapped[str | None] = mapped_column(String(1000))
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="draft"
    )
    # journal_entries partitioned — plain UUID
    journal_entry_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    posted_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    void_reason: Mapped[str | None] = mapped_column(String(500))

    lines: Mapped[list["MfgScrapLine"]] = relationship(
        back_populates="scrap",
        cascade="all, delete-orphan",
    )


class MfgScrapLine(Base):
    __tablename__ = "mfg_scrap_lines"
    __table_args__ = (
        Index("ix_scrapl_scrap", "scrap_id"),
        CheckConstraint("qty > 0", name="ck_scrapl_qty_positive"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    scrap_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("mfg_scraps.id", ondelete="CASCADE"),
        nullable=False,
    )
    item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("items.id", ondelete="RESTRICT"),
        nullable=False,
    )
    qty: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    unit_cost: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0")
    )
    notes: Mapped[str | None] = mapped_column(String(500))

    scrap: Mapped[MfgScrap] = relationship(back_populates="lines")
