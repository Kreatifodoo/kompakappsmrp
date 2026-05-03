"""Event bus subscribers — translate domain events into email tasks.

These handlers run in-process when their event fires and dispatch
the actual email sending to Celery (so the API stays responsive).
"""

from __future__ import annotations

import structlog

from app.config import settings
from app.core.events import subscribe
from app.modules.notifications.tasks import (
    send_invoice_posted_task,
    send_payment_received_task,
    send_report_ready_task,
    send_welcome_task,
)

logger = structlog.get_logger()


@subscribe("tenant.registered")
async def _on_tenant_registered(payload: dict) -> None:
    """Send welcome email when a new tenant signs up."""
    email = payload.get("owner_email")
    if not email:
        return
    send_welcome_task.delay(
        to_email=email,
        user_name=payload.get("owner_name", "User"),
        tenant_name=payload.get("tenant_name", "your team"),
        login_url=settings.APP_PUBLIC_URL,
    )


@subscribe("sales_invoice.posted")
async def _on_invoice_posted(payload: dict) -> None:
    """Email invoice to customer when it's posted (status → posted)."""
    customer_email = payload.get("customer_email")
    if not customer_email:
        logger.debug("invoice_email_skipped_no_email", invoice_no=payload.get("invoice_no"))
        return
    send_invoice_posted_task.delay(
        to_email=customer_email,
        customer_name=payload.get("customer_name", "Customer"),
        invoice_no=payload.get("invoice_no", ""),
        total=float(payload.get("total", 0)),
        due_date=payload.get("due_date"),
        tenant_name=payload.get("tenant_name", "Kompak"),
        view_url=payload.get("view_url"),
    )


@subscribe("payment.received")
async def _on_payment_received(payload: dict) -> None:
    """Send receipt to customer when a payment is recorded against their invoice."""
    customer_email = payload.get("customer_email")
    if not customer_email:
        return
    send_payment_received_task.delay(
        to_email=customer_email,
        customer_name=payload.get("customer_name", "Customer"),
        payment_no=payload.get("payment_no", ""),
        amount=float(payload.get("amount", 0)),
        payment_date=payload.get("payment_date", ""),
        tenant_name=payload.get("tenant_name", "Kompak"),
    )


@subscribe("report.ready")
async def _on_report_ready(payload: dict) -> None:
    """Notify user when an async report has finished processing."""
    email = payload.get("user_email")
    if not email:
        return
    send_report_ready_task.delay(
        to_email=email,
        user_name=payload.get("user_name", "User"),
        report_type=payload.get("report_type", "report"),
        fmt=payload.get("fmt", "json"),
        download_url=payload.get("download_url", settings.APP_PUBLIC_URL),
    )
