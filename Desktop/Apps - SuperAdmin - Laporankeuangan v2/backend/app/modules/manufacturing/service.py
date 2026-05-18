"""BOM lifecycle service (Sprint M1).

Lifecycle: draft → active → obsolete. At most one BOM may be `active` per
(tenant, item) — DB enforces via partial unique index, but this service
auto-obsoletes the previously-active BOM so the activation transaction
succeeds atomically.

Sprint M2 will add ManufacturingOrderService alongside this class.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    ConflictError,
    NotFoundError,
    ValidationError,
)
from app.modules.accounting.repository import AccountingRepository
from app.modules.accounting.service import AccountingService
from app.modules.inventory.repository import InventoryRepository
from app.modules.inventory.schemas import StockMovementCreate
from app.modules.inventory.service import InventoryService
from app.modules.manufacturing.models import (
    BOM,
    BOMLine,
    BOMOperation,
    ManufacturingOrder,
    MOComponent,
    MOOperation,
    WorkCenter,
)
from app.modules.manufacturing.repository import ManufacturingRepository
from app.modules.manufacturing.schemas import (
    BOMCreate,
    BOMUpdate,
    MOCreate,
    MOIssueRequest,
    MOOperationsUpdateRequest,
    WorkCenterIn,
    WorkCenterUpdate,
)
from app.modules.periods.service import assert_period_open


CENT = Decimal("0.01")
QTY4 = Decimal("0.0001")
# Allow up to 20% overproduction without rejecting
OVER_PRODUCE_TOLERANCE = Decimal("1.20")


class BOMService:
    def __init__(self, session: AsyncSession, tenant_id: UUID, user_id: UUID):
        self.session = session
        self.tenant_id = tenant_id
        self.user_id = user_id
        self.repo = ManufacturingRepository(session, tenant_id)
        self.inv_repo = InventoryRepository(session, tenant_id)

    # ─── Validation helpers ───────────────────────────────
    async def _validate_items(self, output_item_id: UUID, line_items: list[UUID]) -> None:
        """All items must exist & belong to this tenant, and output item
        must not appear as one of its own components (no direct recursion)."""
        if output_item_id in line_items:
            raise ValidationError(
                "BOM output item cannot appear as one of its own components"
            )
        # Check existence
        for iid in {output_item_id, *line_items}:
            item = await self.inv_repo.get_item(iid)
            if not item:
                raise NotFoundError(f"Item {iid} not found")

    # ─── Create ───────────────────────────────────────────
    async def create_bom(self, payload: BOMCreate) -> BOM:
        line_items = [ln.item_id for ln in payload.lines]
        await self._validate_items(payload.item_id, line_items)

        # Generate bom_code from output item's SKU if not provided
        if not payload.bom_code:
            item = await self.inv_repo.get_item(payload.item_id)
            sku = (getattr(item, "sku", None) or "ITEM").upper().replace(" ", "-")[:20]
            bom_code = await self.repo.next_bom_code(sku)
        else:
            bom_code = payload.bom_code

        bom = BOM(
            tenant_id=self.tenant_id,
            bom_code=bom_code,
            item_id=payload.item_id,
            qty_output=payload.qty_output,
            version=payload.version,
            status="draft",
            notes=payload.notes,
            created_by=self.user_id,
        )
        bom.lines = [
            BOMLine(
                line_no=idx + 1,
                item_id=ln.item_id,
                qty_required=ln.qty_required,
                scrap_pct=ln.scrap_pct,
                std_unit_cost=ln.std_unit_cost,
                notes=ln.notes,
            )
            for idx, ln in enumerate(payload.lines)
        ]
        # Sprint M5: optional routing
        if payload.operations:
            await self._validate_work_centers([op.work_center_id for op in payload.operations])
            bom.operations = [
                BOMOperation(
                    seq=idx + 1,
                    name=op.name,
                    work_center_id=op.work_center_id,
                    time_minutes=op.time_minutes,
                    setup_minutes=op.setup_minutes,
                    notes=op.notes,
                )
                for idx, op in enumerate(payload.operations)
            ]
        return await self.repo.add_bom(bom)

    async def _validate_work_centers(self, wc_ids: list[UUID]) -> None:
        for wid in set(wc_ids):
            wc = await self.repo.get_work_center(wid)
            if not wc:
                raise ValidationError(f"Work center {wid} not found")
            if not wc.is_active:
                raise ValidationError(f"Work center '{wc.code}' is inactive")

    # ─── Update (draft only) ──────────────────────────────
    async def update_bom(self, bom_id: UUID, payload: BOMUpdate) -> BOM:
        bom = await self.repo.get_bom(bom_id)
        if not bom:
            raise NotFoundError("BOM not found")
        if bom.status != "draft":
            raise ValidationError(
                f"Cannot edit BOM in status '{bom.status}' — only draft is editable"
            )

        if payload.bom_code is not None:
            bom.bom_code = payload.bom_code
        if payload.qty_output is not None:
            bom.qty_output = payload.qty_output
        if payload.version is not None:
            bom.version = payload.version
        if payload.notes is not None:
            bom.notes = payload.notes

        if payload.lines is not None:
            await self._validate_items(bom.item_id, [ln.item_id for ln in payload.lines])
            if len(payload.lines) < 1:
                raise ValidationError("BOM must have at least one line")
            # Replace lines (cascade-delete via orphan)
            bom.lines = [
                BOMLine(
                    line_no=idx + 1,
                    item_id=ln.item_id,
                    qty_required=ln.qty_required,
                    scrap_pct=ln.scrap_pct,
                    std_unit_cost=ln.std_unit_cost,
                    notes=ln.notes,
                )
                for idx, ln in enumerate(payload.lines)
            ]

        # Sprint M5: replace operations if provided (empty list = clear)
        if payload.operations is not None:
            if payload.operations:
                await self._validate_work_centers([op.work_center_id for op in payload.operations])
            bom.operations = [
                BOMOperation(
                    seq=idx + 1,
                    name=op.name,
                    work_center_id=op.work_center_id,
                    time_minutes=op.time_minutes,
                    setup_minutes=op.setup_minutes,
                    notes=op.notes,
                )
                for idx, op in enumerate(payload.operations)
            ]

        await self.session.flush()
        return bom

    # ─── Activate ─────────────────────────────────────────
    async def activate_bom(self, bom_id: UUID) -> BOM:
        bom = await self.repo.get_bom(bom_id)
        if not bom:
            raise NotFoundError("BOM not found")
        if bom.status == "active":
            raise ConflictError("BOM already active")
        if bom.status == "obsolete":
            raise ValidationError("Obsolete BOM cannot be reactivated; clone it instead")
        if not bom.lines:
            raise ValidationError("Cannot activate a BOM with no lines")

        # Sprint M4: standard cost must be all-or-nothing across lines.
        with_std    = [ln for ln in bom.lines if ln.std_unit_cost is not None]
        without_std = [ln for ln in bom.lines if ln.std_unit_cost is None]
        if with_std and without_std:
            raise ValidationError(
                "Standard cost must be set on ALL lines or NONE — mixed BOMs not allowed. "
                f"Lines with std_unit_cost: {len(with_std)}, without: {len(without_std)}"
            )

        # Auto-obsolete any other active BOM for the same item (single
        # statement; the partial unique index would otherwise reject)
        existing_active = await self.repo.get_active_bom_for_item(bom.item_id)
        if existing_active and existing_active.id != bom.id:
            existing_active.status = "obsolete"
            await self.session.flush()

        bom.status = "active"
        await self.session.flush()
        return bom

    # ─── Obsolete ─────────────────────────────────────────
    async def obsolete_bom(self, bom_id: UUID) -> BOM:
        bom = await self.repo.get_bom(bom_id)
        if not bom:
            raise NotFoundError("BOM not found")
        if bom.status == "obsolete":
            raise ConflictError("BOM already obsolete")
        bom.status = "obsolete"
        await self.session.flush()
        return bom

    # ─── Delete (draft only, no MO reference) ─────────────
    async def delete_bom(self, bom_id: UUID) -> None:
        bom = await self.repo.get_bom(bom_id)
        if not bom:
            raise NotFoundError("BOM not found")
        if bom.status != "draft":
            raise ValidationError(
                f"Cannot delete BOM in status '{bom.status}'. Obsolete it instead."
            )
        # Sprint M2 will add a check here that no MO references this BOM.
        await self.session.delete(bom)
        await self.session.flush()


# ═══════════════════════════════════════════════════════════════════
# Manufacturing Order Service (Sprint M2)
# ═══════════════════════════════════════════════════════════════════

class ManufacturingOrderService:
    """MO lifecycle:

        draft → confirmed → in_progress → done | cancelled

    Posting effects:
      - issue materials (manual at /issue, OR auto on /complete with backflush=true):
          per component:  stock-out (source='mfg_issue', cost from inventory layer)
          journal:        Dr WIP / Cr Inventory (raw)  @ qty × unit_cost
      - complete:
          stock-in finished goods (source='mfg_receipt') at total_cost / qty_produced
          journal:        Dr Inventory FG / Cr WIP     @ total_cost
      - cancel (in_progress with materials issued):
          reverse every mfg_issue with mfg_issue_void (in raw)
          void the issue journal
    """

    def __init__(self, session: AsyncSession, tenant_id: UUID, user_id: UUID):
        self.session = session
        self.tenant_id = tenant_id
        self.user_id = user_id
        self.repo = ManufacturingRepository(session, tenant_id)
        self.inv_repo = InventoryRepository(session, tenant_id)
        self.inv_svc = InventoryService(session, tenant_id, user_id)
        self.acct_repo = AccountingRepository(session, tenant_id)
        self.acct_svc = AccountingService(session, tenant_id, user_id)

    # ─── Create draft MO ──────────────────────────────────
    async def create_mo(self, payload: MOCreate) -> ManufacturingOrder:
        # Resolve BOM: explicit bom_id OR active BOM for item_id
        bom: BOM | None
        if payload.bom_id:
            bom = await self.repo.get_bom(payload.bom_id)
            if not bom:
                raise NotFoundError("BOM not found")
            if bom.status == "obsolete":
                raise ValidationError("Cannot create MO from an obsolete BOM")
        elif payload.item_id:
            bom = await self.repo.get_active_bom_for_item(payload.item_id)
            if not bom:
                raise ValidationError(
                    f"No active BOM for item {payload.item_id}. Activate a BOM first."
                )
        else:
            raise ValidationError("Either bom_id or item_id must be provided")
        if not bom.lines:
            raise ValidationError("BOM has no lines — cannot produce")

        # Period gate
        if payload.planned_start:
            await assert_period_open(self.session, self.tenant_id, payload.planned_start)

        # Warehouse validation
        warehouse = await self.inv_repo.get_warehouse(payload.warehouse_id)
        if not warehouse or not warehouse.is_active:
            raise ValidationError("Warehouse not found or inactive")

        # Output item must be the BOM's output
        output_item_id = bom.item_id
        if payload.item_id and payload.item_id != output_item_id:
            raise ValidationError(
                "item_id mismatch: provided item does not match BOM output"
            )

        # Compute per-line planned qty:
        # qty_planned_component = bom_line.qty_required
        #                       * (mo.qty_planned / bom.qty_output)
        #                       * (1 + scrap_pct / 100)
        ratio = (payload.qty_planned / bom.qty_output).quantize(QTY4)
        components: list[MOComponent] = []
        # Sprint M4: aggregate standard cost. If any line has std_unit_cost
        # set, ALL must (enforced at activate); otherwise None propagates.
        std_total = Decimal("0")
        any_std = False
        all_std = True
        for ln in bom.lines:
            scrap_mult = Decimal("1") + (ln.scrap_pct / Decimal("100"))
            qty = (ln.qty_required * ratio * scrap_mult).quantize(QTY4)
            if ln.std_unit_cost is not None:
                any_std = True
                std_total += (qty * ln.std_unit_cost).quantize(CENT)
            else:
                all_std = False
            components.append(MOComponent(
                bom_line_id=ln.id,
                item_id=ln.item_id,
                qty_planned=qty,
                std_unit_cost=ln.std_unit_cost,
            ))
        std_total_cost = std_total.quantize(CENT) if (any_std and all_std) else None

        # MO no
        year = (payload.planned_start or date.today()).year
        mo_no = payload.mo_no or await self.repo.next_mo_no(year)

        mo = ManufacturingOrder(
            tenant_id=self.tenant_id,
            mo_no=mo_no,
            bom_id=bom.id,
            item_id=output_item_id,
            warehouse_id=warehouse.id,
            qty_planned=payload.qty_planned,
            qty_produced=Decimal("0"),
            planned_start=payload.planned_start,
            planned_end=payload.planned_end,
            status="draft",
            backflush=payload.backflush,
            notes=payload.notes,
            std_total_cost=std_total_cost,
            created_by=self.user_id,
        )
        mo.components = components

        # Sprint M5: snapshot routing operations
        ops: list[MOOperation] = []
        for idx, bom_op in enumerate(bom.operations or []):
            wc = await self.repo.get_work_center(bom_op.work_center_id)
            cph = wc.cost_per_hour if wc else Decimal("0")
            # planned_time_min = (per-unit × qty_planned) + setup_once
            planned = (
                bom_op.time_minutes * payload.qty_planned + bom_op.setup_minutes
            ).quantize(Decimal("0.01"))
            ops.append(MOOperation(
                bom_operation_id=bom_op.id,
                seq=idx + 1,
                name=bom_op.name,
                work_center_id=bom_op.work_center_id,
                planned_time_min=planned,
                actual_time_min=Decimal("0"),
                cost_per_hour_snapshot=cph,
                status="pending",
            ))
        mo.operations = ops
        return await self.repo.add_mo(mo)

    # ─── Confirm ──────────────────────────────────────────
    async def confirm_mo(self, mo_id: UUID) -> ManufacturingOrder:
        mo = await self.repo.get_mo(mo_id)
        if not mo:
            raise NotFoundError("MO not found")
        if mo.status != "draft":
            raise ValidationError(
                f"Only draft MO can be confirmed (current: {mo.status})"
            )
        mo.status = "confirmed"
        mo.confirmed_at = datetime.now(UTC)
        await self.session.flush()

        try:
            from app.core.events import publish
            await publish("mfg_order.confirmed", {
                "tenant_id": str(self.tenant_id),
                "mo_id": str(mo.id),
                "mo_no": mo.mo_no,
                "item_id": str(mo.item_id),
                "qty_planned": float(mo.qty_planned),
            })
        except Exception:
            pass
        return mo

    # ─── Start ────────────────────────────────────────────
    async def start_mo(self, mo_id: UUID) -> ManufacturingOrder:
        mo = await self.repo.get_mo(mo_id)
        if not mo:
            raise NotFoundError("MO not found")
        if mo.status != "confirmed":
            raise ValidationError(
                f"Only confirmed MO can be started (current: {mo.status})"
            )
        mo.status = "in_progress"
        mo.actual_start = datetime.now(UTC)
        await self.session.flush()

        try:
            from app.core.events import publish
            await publish("mfg_order.started", {
                "tenant_id": str(self.tenant_id),
                "mo_id": str(mo.id),
                "mo_no": mo.mo_no,
            })
        except Exception:
            pass
        return mo

    # ─── Issue materials (explicit, optional in backflush mode) ─
    async def _issue_inner(
        self,
        mo: ManufacturingOrder,
        lines: list[tuple[UUID, Decimal]],
        issue_date: date,
    ) -> Decimal:
        """Issue materials for given (component_id, qty) tuples. Returns total cost.

        Per line: stock-out at inventory's avg/FIFO, capture unit_cost on the
        component row, post one journal (Dr WIP / Cr Inv per item) at end.
        """
        wip = await self.acct_repo.get_mapping("wip")
        inv_acc = await self.acct_repo.get_mapping("inventory")
        if not wip or not inv_acc:
            raise ValidationError(
                "Account mappings missing: configure 'wip' and 'inventory' first."
            )

        await assert_period_open(self.session, self.tenant_id, issue_date)

        # Pre-fetch components keyed by id
        comp_map = {c.id: c for c in mo.components}
        total_cost = Decimal("0")
        journal_lines: list[tuple[UUID, Decimal, Decimal]] = []

        for component_id, qty in lines:
            if qty <= 0:
                raise ValidationError(f"Issue qty must be > 0 for component {component_id}")
            comp = comp_map.get(component_id)
            if not comp:
                raise ValidationError(f"Component {component_id} not in MO")
            remaining = (comp.qty_planned or Decimal("0")) - (comp.qty_issued or Decimal("0"))
            if qty > remaining + Decimal("0.0001"):
                raise ValidationError(
                    f"Issue qty {qty} exceeds remaining {remaining} for component item {comp.item_id}"
                )

            mvm = await self.inv_svc.post_movement(
                StockMovementCreate(
                    item_id=comp.item_id,
                    warehouse_id=mo.warehouse_id,
                    movement_date=issue_date,
                    direction="out",
                    qty=qty,
                    unit_cost=Decimal("0"),
                    notes=f"MO {mo.mo_no} issue",
                ),
                source="mfg_issue",
                source_id=mo.id,
            )
            line_cost = (mvm.qty * mvm.unit_cost).quantize(CENT)
            # Update component aggregate unit_cost (weighted)
            prev_total = (comp.unit_cost or Decimal("0")) * (comp.qty_issued or Decimal("0"))
            new_qty = (comp.qty_issued or Decimal("0")) + mvm.qty
            new_avg = ((prev_total + line_cost) / new_qty).quantize(QTY4) if new_qty > 0 else Decimal("0")
            comp.qty_issued = new_qty
            comp.unit_cost = new_avg
            total_cost += line_cost

        if total_cost > 0:
            # Single combined journal: Dr WIP (total) / Cr Inventory (total)
            entry = await self.acct_svc.post_system_journal(
                entry_date=issue_date,
                description=f"MO {mo.mo_no} material issue",
                lines=[
                    (wip.account_id, total_cost, Decimal("0")),
                    (inv_acc.account_id, Decimal("0"), total_cost),
                ],
                source="mfg_issue",
                source_id=mo.id,
            )
            # Overwrite issue_journal_entry_id with latest; for MVP we don't keep
            # a list of issue journals (multi-issue MO keeps only the last id).
            mo.issue_journal_entry_id = entry.id

        await self.session.flush()
        return total_cost

    async def issue_materials(self, mo_id: UUID, payload: MOIssueRequest) -> ManufacturingOrder:
        mo = await self.repo.get_mo(mo_id)
        if not mo:
            raise NotFoundError("MO not found")
        if mo.status != "in_progress":
            raise ValidationError(
                f"Materials can only be issued on in_progress MO (current: {mo.status})"
            )

        lines = [(ln.component_id, ln.qty) for ln in payload.lines]
        total = await self._issue_inner(mo, lines, date.today())

        try:
            from app.core.events import publish
            await publish("mfg_order.issued", {
                "tenant_id": str(self.tenant_id),
                "mo_id": str(mo.id),
                "mo_no": mo.mo_no,
                "total_cost": float(total),
            })
        except Exception:
            pass
        return mo

    # ─── Complete ─────────────────────────────────────────
    async def complete_mo(
        self, mo_id: UUID, qty_produced: Decimal, complete_date: date | None = None
    ) -> ManufacturingOrder:
        mo = await self.repo.get_mo(mo_id)
        if not mo:
            raise NotFoundError("MO not found")
        if mo.status != "in_progress":
            raise ValidationError(
                f"Only in_progress MO can be completed (current: {mo.status})"
            )
        if qty_produced <= 0:
            raise ValidationError("qty_produced must be > 0")
        max_qty = (mo.qty_planned * OVER_PRODUCE_TOLERANCE).quantize(QTY4)
        if qty_produced > max_qty:
            raise ValidationError(
                f"qty_produced {qty_produced} exceeds tolerance {max_qty} "
                f"(planned {mo.qty_planned} × 1.20)"
            )

        cdate = complete_date or date.today()
        await assert_period_open(self.session, self.tenant_id, cdate)

        wip = await self.acct_repo.get_mapping("wip")
        inv_acc = await self.acct_repo.get_mapping("inventory")
        if not wip or not inv_acc:
            raise ValidationError(
                "Account mappings missing: configure 'wip' and 'inventory' first."
            )

        # Backflush: auto-issue remaining components
        if mo.backflush:
            remaining_lines: list[tuple[UUID, Decimal]] = []
            for c in mo.components:
                rem = (c.qty_planned or Decimal("0")) - (c.qty_issued or Decimal("0"))
                if rem > Decimal("0"):
                    remaining_lines.append((c.id, rem))
            if remaining_lines:
                await self._issue_inner(mo, remaining_lines, cdate)

        # Total WIP cost = sum(component.qty_issued × component.unit_cost)
        # Re-read components after potential issue
        mo_refreshed = await self.repo.get_mo(mo.id)
        total_wip_material = sum(
            ((c.qty_issued or Decimal("0")) * (c.unit_cost or Decimal("0")))
            for c in mo_refreshed.components
        ).quantize(CENT) if mo_refreshed.components else Decimal("0")

        # Sprint M5: Labor cost from MO operations. Each op contributes
        # actual_time_min × cost_per_hour_snapshot / 60. Operations without
        # any actual_time recorded contribute nothing.
        total_labor = Decimal("0")
        for op in (mo_refreshed.operations or []):
            actual = op.actual_time_min or Decimal("0")
            if actual > 0:
                total_labor += (actual * op.cost_per_hour_snapshot / Decimal("60")).quantize(CENT)

        total_wip = (total_wip_material + total_labor).quantize(CENT)

        if total_wip <= 0:
            raise ValidationError(
                "Cannot complete MO with zero WIP cost — issue at least one component first "
                "(or enable backflush)."
            )

        # Sprint M5: post labor journal BEFORE FG receipt so WIP carries
        # the labor charge into the receipt entry.
        if total_labor > 0:
            labor_map = await self.acct_repo.get_mapping("mfg_labor_applied")
            if not labor_map:
                raise ValidationError(
                    "Labor cost detected but mapping 'mfg_labor_applied' is not "
                    "configured. Set it under Account Mappings before completing MOs "
                    "with operations time recorded."
                )
            labor_entry = await self.acct_svc.post_system_journal(
                entry_date=cdate,
                description=f"MO {mo.mo_no} labor applied to WIP",
                lines=[
                    (wip.account_id, total_labor, Decimal("0")),
                    (labor_map.account_id, Decimal("0"), total_labor),
                ],
                source="mfg_labor",
                source_id=mo.id,
            )
            mo.labor_journal_entry_id = labor_entry.id
            mo.labor_total_cost = total_labor
            # Auto-mark any pending operation with actual_time>0 as done
            for op in (mo_refreshed.operations or []):
                if (op.actual_time_min or Decimal("0")) > 0 and op.status != "done":
                    op.status = "done"

        # Sprint M4: determine costing mode. If MO has std_total_cost set
        # AND every component has std_unit_cost, run STANDARD costing.
        use_std = (
            mo.std_total_cost is not None
            and mo_refreshed.components
            and all(c.std_unit_cost is not None for c in mo_refreshed.components)
        )

        if use_std:
            # Standard cost per produced unit = std_total_cost / qty_planned
            # (std_total_cost was computed at MO create from qty_planned, materials only)
            std_per_unit = (mo.std_total_cost / mo.qty_planned).quantize(QTY4)
            # Variance: material_actual - material_std. Labor goes into WIP at
            # actual on both sides, so it doesn't contribute to variance.
            material_std_value = (std_per_unit * qty_produced).quantize(CENT)
            # FG value combines material_std + labor_actual; this is what the
            # FG inventory line is debited with.
            fg_value = (material_std_value + total_labor).quantize(CENT)
            unit_fg_cost = (fg_value / qty_produced).quantize(QTY4)
            variance = (total_wip_material - material_std_value).quantize(CENT)
        else:
            fg_value = total_wip   # actual (material + labor)
            unit_fg_cost = (total_wip / qty_produced).quantize(QTY4)
            variance = Decimal("0")

        # Stock-in finished goods at the chosen FG unit cost
        await self.inv_svc.post_movement(
            StockMovementCreate(
                item_id=mo.item_id,
                warehouse_id=mo.warehouse_id,
                movement_date=cdate,
                direction="in",
                qty=qty_produced,
                unit_cost=unit_fg_cost,
                notes=f"MO {mo.mo_no} FG receipt",
            ),
            source="mfg_receipt",
            source_id=mo.id,
        )

        # Journal lines:
        #   Standard mode (variance != 0):
        #     Dr Inv FG (material_std + labor)
        #     Cr WIP    (total_wip = material_actual + labor)
        #     + balance to Variance account: Dr if unfavorable, Cr if favorable.
        #   Actual mode (variance == 0):
        #     Dr Inv FG / Cr WIP @ total_wip
        journal_lines: list[tuple[UUID, Decimal, Decimal]] = []
        journal_lines.append((inv_acc.account_id, fg_value, Decimal("0")))
        journal_lines.append((wip.account_id, Decimal("0"), total_wip))
        if variance != 0:
            var_map = await self.acct_repo.get_mapping("mfg_variance")
            if not var_map:
                raise ValidationError(
                    "Variance detected but account mapping 'mfg_variance' is not "
                    "configured. Set it under Account Mappings before completing "
                    "standard-cost MOs."
                )
            if variance > 0:
                # Unfavorable: actual > standard → debit variance (more cost recognized)
                journal_lines.append((var_map.account_id, variance, Decimal("0")))
            else:
                # Favorable: actual < standard → credit variance
                journal_lines.append((var_map.account_id, Decimal("0"), -variance))

        entry = await self.acct_svc.post_system_journal(
            entry_date=cdate,
            description=f"MO {mo.mo_no} finished goods receipt"
                        + (f" (variance {variance:+})" if variance != 0 else ""),
            lines=journal_lines,
            source="mfg_receipt",
            source_id=mo.id,
        )
        mo.receipt_journal_entry_id = entry.id
        if variance != 0:
            # In MVP we record one combined entry for both FG receipt and
            # variance recognition; variance_journal_entry_id mirrors the
            # receipt journal so reports can drill in without join.
            mo.variance_journal_entry_id = entry.id
            mo.variance_amount = variance
        mo.qty_produced = qty_produced
        mo.actual_end = datetime.now(UTC)
        mo.done_at = datetime.now(UTC)
        mo.status = "done"
        await self.session.flush()

        try:
            from app.core.events import publish
            await publish("mfg_order.completed", {
                "tenant_id": str(self.tenant_id),
                "mo_id": str(mo.id),
                "mo_no": mo.mo_no,
                "qty_produced": float(qty_produced),
                "total_cost": float(total_wip),
                "labor_cost": float(total_labor),
                "unit_cost": float(unit_fg_cost),
                "variance": float(variance),
                "costing_mode": "standard" if use_std else "actual",
            })
        except Exception:
            pass
        return mo

    # ─── Cancel ───────────────────────────────────────────
    async def cancel_mo(self, mo_id: UUID, reason: str) -> ManufacturingOrder:
        mo = await self.repo.get_mo(mo_id)
        if not mo:
            raise NotFoundError("MO not found")
        if mo.status == "cancelled":
            raise ConflictError("MO already cancelled")
        if mo.status == "done":
            raise ValidationError(
                "Cannot cancel a done MO — create a reversal flow manually"
            )

        # If materials were issued, reverse them
        any_issued = any(
            (c.qty_issued or Decimal("0")) > 0 for c in mo.components
        )
        if mo.status == "in_progress" and any_issued:
            today = date.today()
            await assert_period_open(self.session, self.tenant_id, today)
            for c in mo.components:
                if (c.qty_issued or Decimal("0")) <= 0:
                    continue
                await self.inv_svc.post_movement(
                    StockMovementCreate(
                        item_id=c.item_id,
                        warehouse_id=mo.warehouse_id,
                        movement_date=today,
                        direction="in",
                        qty=c.qty_issued,
                        unit_cost=c.unit_cost or Decimal("0"),
                        notes=f"Cancel MO {mo.mo_no} reverse issue",
                    ),
                    source="mfg_issue_void",
                    source_id=mo.id,
                )
            # Void the issue journal
            if mo.issue_journal_entry_id:
                try:
                    await self.acct_svc.void_system_journal(
                        "mfg_issue", mo.id, f"Cancelled: {reason}"
                    )
                except Exception:
                    pass
            # Zero out component issue counters
            for c in mo.components:
                c.qty_issued = Decimal("0")

        mo.status = "cancelled"
        mo.cancelled_at = datetime.now(UTC)
        mo.cancel_reason = reason
        await self.session.flush()

        try:
            from app.core.events import publish
            await publish("mfg_order.cancelled", {
                "tenant_id": str(self.tenant_id),
                "mo_id": str(mo.id),
                "mo_no": mo.mo_no,
                "reason": reason,
            })
        except Exception:
            pass
        return mo

    # ─── MO operations update (Sprint M5) ────────────────
    async def update_mo_operations(
        self, mo_id: UUID, payload: MOOperationsUpdateRequest
    ) -> ManufacturingOrder:
        mo = await self.repo.get_mo(mo_id)
        if not mo:
            raise NotFoundError("MO not found")
        if mo.status not in ("confirmed", "in_progress"):
            raise ValidationError(
                f"Can only update operations on confirmed/in_progress MO (current: {mo.status})"
            )
        op_map = {op.id: op for op in (mo.operations or [])}
        for upd in payload.operations:
            op = op_map.get(upd.id)
            if not op:
                raise ValidationError(f"Operation {upd.id} not in this MO")
            if upd.actual_time_min is not None:
                op.actual_time_min = upd.actual_time_min
            if upd.status is not None:
                op.status = upd.status
            if upd.notes is not None:
                op.notes = upd.notes
        await self.session.flush()
        return mo


# ═══════════════════════════════════════════════════════════════════
# Work Center Service (Sprint M5)
# ═══════════════════════════════════════════════════════════════════

class WorkCenterService:
    def __init__(self, session: AsyncSession, tenant_id: UUID, user_id: UUID):
        self.session = session
        self.tenant_id = tenant_id
        self.user_id = user_id
        self.repo = ManufacturingRepository(session, tenant_id)

    async def create(self, payload: WorkCenterIn) -> WorkCenter:
        # Check unique code
        existing = await self.repo.list_work_centers()
        if any(w.code == payload.code for w in existing):
            raise ConflictError(f"Work center code '{payload.code}' already exists")
        wc = WorkCenter(
            tenant_id=self.tenant_id,
            code=payload.code,
            name=payload.name,
            cost_per_hour=payload.cost_per_hour,
            capacity_hours_per_day=payload.capacity_hours_per_day,
            is_active=payload.is_active,
            notes=payload.notes,
            created_by=self.user_id,
        )
        return await self.repo.add_work_center(wc)

    async def update(self, wc_id: UUID, payload: WorkCenterUpdate) -> WorkCenter:
        wc = await self.repo.get_work_center(wc_id)
        if not wc:
            raise NotFoundError("Work center not found")
        if payload.code is not None and payload.code != wc.code:
            existing = await self.repo.list_work_centers()
            if any(w.code == payload.code and w.id != wc_id for w in existing):
                raise ConflictError(f"Work center code '{payload.code}' already exists")
            wc.code = payload.code
        if payload.name is not None:
            wc.name = payload.name
        if payload.cost_per_hour is not None:
            wc.cost_per_hour = payload.cost_per_hour
        if payload.capacity_hours_per_day is not None:
            wc.capacity_hours_per_day = payload.capacity_hours_per_day
        if payload.is_active is not None:
            wc.is_active = payload.is_active
        if payload.notes is not None:
            wc.notes = payload.notes
        await self.session.flush()
        return wc


# ═══════════════════════════════════════════════════════════════════
# Scrap Service (Sprint M6)
# ═══════════════════════════════════════════════════════════════════

class ScrapService:
    """Records inventory loss (spoilage, defects, QC reject).

    On post:
      • For each line, stock-out via InventoryService (source='mfg_scrap')
        and capture the resulting unit_cost from the inventory layer.
      • Post one journal: Dr mfg_scrap_loss / Cr inventory @ total.

    Standalone — no WIP involvement even when mo_id is set; mo_id is
    purely informational so users can drill from an MO to its scraps.
    """

    def __init__(self, session: AsyncSession, tenant_id: UUID, user_id: UUID):
        self.session = session
        self.tenant_id = tenant_id
        self.user_id = user_id
        self.repo = ManufacturingRepository(session, tenant_id)
        self.inv_repo = InventoryRepository(session, tenant_id)
        self.inv_svc = InventoryService(session, tenant_id, user_id)
        self.acct_repo = AccountingRepository(session, tenant_id)
        self.acct_svc = AccountingService(session, tenant_id, user_id)

    async def create_scrap(self, payload):
        from app.modules.manufacturing.models import MfgScrap, MfgScrapLine
        await assert_period_open(self.session, self.tenant_id, payload.scrap_date)

        warehouse = await self.inv_repo.get_warehouse(payload.warehouse_id)
        if not warehouse or not warehouse.is_active:
            raise ValidationError("Warehouse not found or inactive")

        if payload.mo_id:
            mo = await self.repo.get_mo(payload.mo_id)
            if not mo:
                raise NotFoundError("Referenced MO not found")

        # Validate items exist
        for ln in payload.lines:
            it = await self.inv_repo.get_item(ln.item_id)
            if not it:
                raise NotFoundError(f"Item {ln.item_id} not found")

        scrap_no = payload.scrap_no or await self.repo.next_scrap_no(payload.scrap_date.year)
        scrap = MfgScrap(
            tenant_id=self.tenant_id,
            scrap_no=scrap_no,
            scrap_date=payload.scrap_date,
            warehouse_id=warehouse.id,
            mo_id=payload.mo_id,
            reason=payload.reason,
            notes=payload.notes,
            status="draft",
            created_by=self.user_id,
        )
        scrap.lines = [
            MfgScrapLine(
                item_id=ln.item_id,
                qty=ln.qty,
                unit_cost=ln.unit_cost or Decimal("0"),
                notes=ln.notes,
            )
            for ln in payload.lines
        ]
        return await self.repo.add_scrap(scrap)

    async def post_scrap(self, scrap_id: UUID):
        scrap = await self.repo.get_scrap(scrap_id)
        if not scrap:
            raise NotFoundError("Scrap not found")
        if scrap.status == "posted":
            raise ConflictError("Scrap already posted")
        if scrap.status == "void":
            raise ValidationError("Voided scrap cannot be posted")
        await assert_period_open(self.session, self.tenant_id, scrap.scrap_date)

        inv_map = await self.acct_repo.get_mapping("inventory")
        loss_map = await self.acct_repo.get_mapping("mfg_scrap_loss")
        if not inv_map or not loss_map:
            raise ValidationError(
                "Account mappings missing: configure 'inventory' and 'mfg_scrap_loss' first."
            )

        total_cost = Decimal("0")
        for ln in scrap.lines:
            mvm = await self.inv_svc.post_movement(
                StockMovementCreate(
                    item_id=ln.item_id,
                    warehouse_id=scrap.warehouse_id,
                    movement_date=scrap.scrap_date,
                    direction="out",
                    qty=ln.qty,
                    unit_cost=ln.unit_cost or Decimal("0"),
                    notes=f"Scrap {scrap.scrap_no} line",
                ),
                source="mfg_scrap",
                source_id=scrap.id,
            )
            # Capture actual unit_cost from inventory layer if user didn't override
            if not ln.unit_cost or ln.unit_cost == 0:
                ln.unit_cost = mvm.unit_cost
            total_cost += (mvm.qty * mvm.unit_cost).quantize(CENT)

        if total_cost > 0:
            entry = await self.acct_svc.post_system_journal(
                entry_date=scrap.scrap_date,
                description=f"Scrap {scrap.scrap_no}"
                            + (f" — {scrap.reason}" if scrap.reason else ""),
                lines=[
                    (loss_map.account_id, total_cost, Decimal("0")),
                    (inv_map.account_id, Decimal("0"), total_cost),
                ],
                source="mfg_scrap",
                source_id=scrap.id,
            )
            scrap.journal_entry_id = entry.id

        scrap.status = "posted"
        scrap.posted_at = datetime.now(UTC)
        scrap.posted_by = self.user_id
        await self.session.flush()

        try:
            from app.core.events import publish
            await publish("mfg_scrap.posted", {
                "tenant_id": str(self.tenant_id),
                "scrap_id": str(scrap.id),
                "scrap_no": scrap.scrap_no,
                "mo_id": str(scrap.mo_id) if scrap.mo_id else None,
                "total_cost": float(total_cost),
            })
        except Exception:
            pass
        return scrap

    async def void_scrap(self, scrap_id: UUID, reason: str):
        scrap = await self.repo.get_scrap(scrap_id)
        if not scrap:
            raise NotFoundError("Scrap not found")
        if scrap.status == "void":
            raise ConflictError("Scrap already void")
        await assert_period_open(self.session, self.tenant_id, scrap.scrap_date)

        if scrap.status == "posted":
            # Reverse stock movements (re-stock at recorded unit_cost)
            for ln in scrap.lines:
                await self.inv_svc.post_movement(
                    StockMovementCreate(
                        item_id=ln.item_id,
                        warehouse_id=scrap.warehouse_id,
                        movement_date=scrap.scrap_date,
                        direction="in",
                        qty=ln.qty,
                        unit_cost=ln.unit_cost or Decimal("0"),
                        notes=f"Void Scrap {scrap.scrap_no}",
                    ),
                    source="mfg_scrap_void",
                    source_id=scrap.id,
                )
            if scrap.journal_entry_id:
                await self.acct_svc.void_system_journal(
                    "mfg_scrap", scrap.id, f"Voided: {reason}"
                )

        scrap.status = "void"
        scrap.voided_at = datetime.now(UTC)
        scrap.void_reason = reason
        await self.session.flush()

        try:
            from app.core.events import publish
            await publish("mfg_scrap.voided", {
                "tenant_id": str(self.tenant_id),
                "scrap_id": str(scrap.id),
                "scrap_no": scrap.scrap_no,
                "reason": reason,
            })
        except Exception:
            pass
        return scrap


# ═══════════════════════════════════════════════════════════════════
# MO Cost Analysis Report (Sprint M-Reports)
# ═══════════════════════════════════════════════════════════════════

class MOCostAnalysisService:
    """Aggregates per-MO cost breakdown: material actual vs standard,
    variance, labor, scrap (via mo_id), total + unit cost.

    All values are computed from already-posted data; this is a
    read-only report.
    """

    def __init__(self, session: AsyncSession, tenant_id: UUID):
        self.session = session
        self.tenant_id = tenant_id
        self.repo = ManufacturingRepository(session, tenant_id)

    async def analyze(
        self,
        *,
        date_from: date | None = None,
        date_to: date | None = None,
        status: str | None = None,
        limit: int = 500,
    ) -> list[dict]:
        from app.modules.manufacturing.models import MfgScrap, MfgScrapLine
        # Date filter: by done_at if filtering, else planned_start fallback
        # Use planned_start which is always set
        mos = await self.repo.list_mos(
            status=status,
            date_from=date_from,
            date_to=date_to,
            limit=limit,
        )
        if not mos:
            return []

        # Pre-fetch scrap totals per MO in one query
        from sqlalchemy import select, func as sa_func
        mo_ids = [m.id for m in mos]
        scrap_rows = (
            await self.session.execute(
                select(
                    MfgScrap.mo_id.label("mo_id"),
                    sa_func.coalesce(sa_func.sum(MfgScrapLine.qty * MfgScrapLine.unit_cost), 0).label("total"),
                )
                .join(MfgScrapLine, MfgScrapLine.scrap_id == MfgScrap.id)
                .where(
                    MfgScrap.tenant_id == self.tenant_id,
                    MfgScrap.mo_id.in_(mo_ids),
                    MfgScrap.status == "posted",
                )
                .group_by(MfgScrap.mo_id)
            )
        ).all()
        scrap_by_mo: dict[UUID, Decimal] = {r.mo_id: Decimal(str(r.total)) for r in scrap_rows}

        out: list[dict] = []
        for mo in mos:
            material_actual = sum(
                ((c.qty_issued or Decimal("0")) * (c.unit_cost or Decimal("0")))
                for c in (mo.components or [])
            )
            material_std = mo.std_total_cost  # may be None
            variance = mo.variance_amount     # may be None
            labor = mo.labor_total_cost or Decimal("0")
            scrap_total = scrap_by_mo.get(mo.id, Decimal("0"))
            total_cost = (material_actual + labor).quantize(CENT)
            qty_produced = mo.qty_produced or Decimal("0")
            unit_cost = (total_cost / qty_produced).quantize(QTY4) if qty_produced > 0 else None
            variance_pct = None
            if material_std and material_std != 0 and variance is not None:
                variance_pct = float(
                    (variance / material_std * Decimal("100")).quantize(Decimal("0.01"))
                )
            out.append({
                "mo_id": str(mo.id),
                "mo_no": mo.mo_no,
                "item_id": str(mo.item_id),
                "warehouse_id": str(mo.warehouse_id),
                "status": mo.status,
                "qty_planned": float(mo.qty_planned),
                "qty_produced": float(qty_produced),
                "planned_start": mo.planned_start.isoformat() if mo.planned_start else None,
                "done_at": mo.done_at.isoformat() if mo.done_at else None,
                "material_actual": float(material_actual.quantize(CENT) if isinstance(material_actual, Decimal) else Decimal(str(material_actual))),
                "material_std":    float(material_std) if material_std is not None else None,
                "variance":        float(variance) if variance is not None else None,
                "variance_pct":    variance_pct,
                "labor":           float(labor),
                "scrap_total":     float(scrap_total),
                "total_cost":      float(total_cost),
                "unit_cost":       float(unit_cost) if unit_cost is not None else None,
                "costing_mode":    "standard" if material_std is not None else "actual",
            })
        return out
