"""Bridge in-process events → realtime broadcaster.

Each `publish(event_type, payload)` from existing services that includes
`tenant_id` will be forwarded to all live WebSocket subscribers of that
tenant via Redis pub/sub.
"""

from __future__ import annotations

import logging
from uuid import UUID

from app.core.events import subscribe
from app.core.realtime import broadcaster

logger = logging.getLogger(__name__)

# Event types we want to push to clients. Extend as needed.
_TENANT_EVENTS = {
    "tenant.registered",
    "sales_invoice.posted",
    "sales_invoice.voided",
    "purchase_invoice.posted",
    "purchase_invoice.voided",
    "payment.received",
    "payment.disbursed",
    "journal.posted",
    "journal.voided",
    "report.ready",
    # Inventory
    "stock_movement.posted",
    "stock_transfer.posted",
    "stock_transfer.voided",
}


async def _forward(event_type: str, payload: dict) -> None:
    tid_raw = payload.get("tenant_id")
    if not tid_raw:
        return
    try:
        tenant_id = UUID(str(tid_raw))
    except (ValueError, TypeError):
        return
    await broadcaster.broadcast(tenant_id, event_type, payload)


# Register a forwarder for each event type. We use closures so each handler
# carries its own `event_type` (the publish() API doesn't pass the type to
# subscribers in the current event-bus implementation).
def _register() -> None:
    for et in _TENANT_EVENTS:
        def _make_handler(event_type: str):
            @subscribe(event_type)
            async def _handler(payload: dict) -> None:  # noqa: ARG001
                await _forward(event_type, payload)
            _handler.__name__ = f"realtime_forward_{event_type.replace('.', '_')}"
            return _handler
        _make_handler(et)


_register()
