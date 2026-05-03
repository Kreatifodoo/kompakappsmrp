"""HTTP routes for Notifications: test endpoint + delivery status."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr

from app.config import settings
from app.deps import CurrentUser, require_permission
from app.modules.notifications.tasks import send_welcome_task

router = APIRouter(prefix="/notifications", tags=["notifications"])


class TestEmailRequest(BaseModel):
    to_email: EmailStr


class TestEmailResponse(BaseModel):
    queued: bool
    task_id: str
    email_enabled: bool
    smtp_host: str


@router.post(
    "/test-email",
    response_model=TestEmailResponse,
    summary="Send a test welcome email — admin only. Useful for verifying SMTP config.",
)
async def send_test_email(
    body: TestEmailRequest,
    current: CurrentUser = Depends(require_permission("tenant.admin")),
) -> TestEmailResponse:
    if not settings.SMTP_HOST:
        raise HTTPException(
            status_code=503,
            detail="SMTP not configured. Set SMTP_HOST/SMTP_USER/SMTP_PASSWORD env vars.",
        )
    task = send_welcome_task.delay(
        to_email=body.to_email,
        user_name="Test User",
        tenant_name="Kompak Accounting (Test)",
        login_url=settings.APP_PUBLIC_URL,
    )
    return TestEmailResponse(
        queued=True,
        task_id=task.id,
        email_enabled=settings.EMAIL_ENABLED,
        smtp_host=settings.SMTP_HOST,
    )
