"""Celery tasks for sending transactional emails via SMTP."""

from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr

import structlog

from app.config import settings
from app.modules.notifications import templates
from app.worker.celery_app import celery_app

logger = structlog.get_logger()


def _send_smtp(to_email: str, subject: str, html_body: str) -> None:
    """Low-level SMTP send. Raises on failure (Celery will retry)."""
    if not settings.EMAIL_ENABLED:
        logger.info("email_skipped_disabled", to=to_email, subject=subject)
        return
    if not settings.SMTP_HOST:
        logger.warning("email_skipped_no_smtp_host", to=to_email)
        return

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = formataddr((settings.SMTP_FROM_NAME, settings.SMTP_FROM_EMAIL))
    msg["To"] = to_email
    msg.set_content("Email ini berformat HTML. Silakan gunakan klien email yang mendukung HTML.")
    msg.add_alternative(html_body, subtype="html")

    context = ssl.create_default_context()
    if settings.SMTP_PORT == 465:
        with smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT, context=context, timeout=15) as smtp:
            if settings.SMTP_USER:
                smtp.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            smtp.send_message(msg)
    else:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15) as smtp:
            if settings.SMTP_USE_TLS:
                smtp.starttls(context=context)
            if settings.SMTP_USER:
                smtp.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            smtp.send_message(msg)

    logger.info("email_sent", to=to_email, subject=subject)


# ─── Celery tasks (auto-retry on failure) ────────────────────────────────

@celery_app.task(
    bind=True, name="notifications.send_welcome",
    max_retries=3, default_retry_delay=60, autoretry_for=(smtplib.SMTPException, OSError),
)
def send_welcome_task(self, to_email: str, user_name: str, tenant_name: str, login_url: str | None = None) -> None:
    subject, html = templates.welcome_email(user_name, tenant_name, login_url)
    _send_smtp(to_email, subject, html)


@celery_app.task(
    bind=True, name="notifications.send_invoice_posted",
    max_retries=3, default_retry_delay=60, autoretry_for=(smtplib.SMTPException, OSError),
)
def send_invoice_posted_task(
    self, to_email: str, customer_name: str, invoice_no: str,
    total: float, due_date: str | None, tenant_name: str, view_url: str | None = None,
) -> None:
    subject, html = templates.invoice_posted_email(
        customer_name, invoice_no, total, due_date, tenant_name, view_url
    )
    _send_smtp(to_email, subject, html)


@celery_app.task(
    bind=True, name="notifications.send_payment_received",
    max_retries=3, default_retry_delay=60, autoretry_for=(smtplib.SMTPException, OSError),
)
def send_payment_received_task(
    self, to_email: str, customer_name: str, payment_no: str,
    amount: float, payment_date: str, tenant_name: str,
) -> None:
    subject, html = templates.payment_received_email(
        customer_name, payment_no, amount, payment_date, tenant_name
    )
    _send_smtp(to_email, subject, html)


@celery_app.task(
    bind=True, name="notifications.send_report_ready",
    max_retries=3, default_retry_delay=60, autoretry_for=(smtplib.SMTPException, OSError),
)
def send_report_ready_task(
    self, to_email: str, user_name: str, report_type: str, fmt: str, download_url: str,
) -> None:
    subject, html = templates.report_ready_email(user_name, report_type, fmt, download_url)
    _send_smtp(to_email, subject, html)


@celery_app.task(
    bind=True, name="notifications.send_password_reset",
    max_retries=3, default_retry_delay=60, autoretry_for=(smtplib.SMTPException, OSError),
)
def send_password_reset_task(self, to_email: str, user_name: str, reset_url: str) -> None:
    subject, html = templates.password_reset_email(user_name, reset_url)
    _send_smtp(to_email, subject, html)
