"""SQLAlchemy event listener that writes AuditLog rows on every flush.

Tracks: create / update / delete on registered model classes. State
transitions on a `status` column are reclassified as 'post' or 'void'
when the new value matches.

Tenant-scope safety:
- Skips objects without `tenant_id` (defensive — all tracked classes
  should have it)
- The AuditLog row carries the same tenant_id as the source row, so
  RLS on audit_logs filters identically to the source table

Context:
- `current_user_id` and `current_request_id` are contextvars set by the
  request middleware (`_apply_tenant_context`) per HTTP request. CLI
  scripts that go through `transaction()` leave these as None →
  user_id NULL on the audit row (= "system action"), which is a
  legitimate distinction in the data.
"""

from __future__ import annotations

from contextvars import ContextVar
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import event, inspect
from sqlalchemy.orm import Session

from app.modules.audit.models import AuditLog

current_user_id: ContextVar[UUID | None] = ContextVar("audit_current_user_id", default=None)
current_request_id: ContextVar[str | None] = ContextVar("audit_current_request_id", default=None)

# Set populated by `register_tracked()` at startup. We store the *types*
# so isinstance checks remain fast.
_TRACKED_TYPES: set[type] = set()

# Fields we never want in the audit diff (timestamps + tenant_id since
# it's already on the audit row).
_EXCLUDED_FIELDS = {"created_at", "updated_at", "tenant_id"}


def track(*classes: type) -> None:
    """Register one or more model classes as audit-tracked."""
    for cls in classes:
        _TRACKED_TYPES.add(cls)


def _serialize(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, bool | int | float | str):
        return value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, dict):
        return {k: _serialize(v) for k, v in value.items()}
    if isinstance(value, list | tuple | set):
        return [_serialize(v) for v in value]
    return str(value)


def _column_keys(obj: Any) -> list[str]:
    return [c.key for c in inspect(obj.__class__).mapper.column_attrs]


def _full_state(obj: Any) -> dict:
    out = {}
    for key in _column_keys(obj):
        if key in _EXCLUDED_FIELDS:
            continue
        out[key] = _serialize(getattr(obj, key))
    return out


def _compute_diff(obj: Any) -> dict:
    state = inspect(obj)
    diff = {}
    for key in _column_keys(obj):
        if key in _EXCLUDED_FIELDS:
            continue
        history = state.attrs[key].load_history()
        if not history.has_changes():
            continue
        old = history.deleted[0] if history.deleted else None
        new = history.added[0] if history.added else None
        diff[key] = {"old": _serialize(old), "new": _serialize(new)}
    return diff


def _make_audit(obj: Any, action: str, changes: dict) -> AuditLog | None:
    tenant_id = getattr(obj, "tenant_id", None)
    if tenant_id is None:
        return None
    row_id = getattr(obj, "id", None)
    if row_id is None:
        return None
    return AuditLog(
        tenant_id=tenant_id,
        user_id=current_user_id.get(),
        request_id=current_request_id.get(),
        table_name=obj.__tablename__,
        row_id=row_id,
        action=action,
        changes=changes,
    )


def _classify_update_action(diff: dict) -> str:
    """If a 'status' field flipped to 'posted' or 'void', tag the action
    accordingly so downstream queries can filter state transitions."""
    if "status" not in diff:
        return "update"
    new_status = diff["status"].get("new")
    if new_status == "posted":
        return "post"
    if new_status == "void":
        return "void"
    return "update"


@event.listens_for(Session, "before_flush")
def _audit_listener(session: Session, _flush_context, _instances) -> None:  # noqa: ANN001
    audits: list[AuditLog] = []

    for obj in session.new:
        if isinstance(obj, AuditLog):
            continue
        if type(obj) not in _TRACKED_TYPES:
            continue
        a = _make_audit(obj, "create", _full_state(obj))
        if a is not None:
            audits.append(a)

    for obj in session.dirty:
        if isinstance(obj, AuditLog):
            continue
        if type(obj) not in _TRACKED_TYPES:
            continue
        if not session.is_modified(obj, include_collections=False):
            continue
        diff = _compute_diff(obj)
        if not diff:
            continue
        action = _classify_update_action(diff)
        a = _make_audit(obj, action, diff)
        if a is not None:
            audits.append(a)

    for obj in session.deleted:
        if isinstance(obj, AuditLog):
            continue
        if type(obj) not in _TRACKED_TYPES:
            continue
        a = _make_audit(obj, "delete", _full_state(obj))
        if a is not None:
            audits.append(a)

    for a in audits:
        session.add(a)


def register_tracked() -> None:
    """Register every model class that should be audited.

    Called once at app startup (and from tests' conftest). Idempotent —
    re-registration is a no-op."""
    from app.modules.accounting.models import Account, AccountMapping, JournalEntry
    from app.modules.payments.models import Payment, PaymentApplication
    from app.modules.purchase.models import (
        PurchaseInvoice,
        PurchaseInvoiceLine,
        Supplier,
    )
    from app.modules.sales.models import Customer, SalesInvoice, SalesInvoiceLine

    track(
        Customer,
        SalesInvoice,
        SalesInvoiceLine,
        Supplier,
        PurchaseInvoice,
        PurchaseInvoiceLine,
        Account,
        AccountMapping,
        JournalEntry,
        Payment,
        PaymentApplication,
    )
