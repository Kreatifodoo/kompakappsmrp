"""Pydantic schemas for audit log queries."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

AuditAction = Literal["create", "update", "delete", "post", "void"]


class AuditLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID | None
    request_id: str | None
    table_name: str
    row_id: UUID
    action: AuditAction
    changes: dict
    occurred_at: datetime
