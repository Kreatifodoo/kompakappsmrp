"""BOM lifecycle service (Sprint M1).

Lifecycle: draft → active → obsolete. At most one BOM may be `active` per
(tenant, item) — DB enforces via partial unique index, but this service
auto-obsoletes the previously-active BOM so the activation transaction
succeeds atomically.

Sprint M2 will add ManufacturingOrderService alongside this class.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    ConflictError,
    NotFoundError,
    ValidationError,
)
from app.modules.inventory.repository import InventoryRepository
from app.modules.manufacturing.models import BOM, BOMLine
from app.modules.manufacturing.repository import ManufacturingRepository
from app.modules.manufacturing.schemas import BOMCreate, BOMUpdate


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
                notes=ln.notes,
            )
            for idx, ln in enumerate(payload.lines)
        ]
        return await self.repo.add_bom(bom)

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
                    notes=ln.notes,
                )
                for idx, ln in enumerate(payload.lines)
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
