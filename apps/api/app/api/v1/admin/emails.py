"""`/admin/emails/*` — email_queue 조회 + 재발송 trigger."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select

from app.core.deps import DbSession
from app.core.rbac import require_role
from app.models.email_queue import EmailQueue
from app.models.user import User
from app.schemas.admin import AdminEmailDeliverability
from app.schemas.envelope import Envelope
from app.services.email_deliverability import build_email_deliverability_summary

router = APIRouter(prefix="/admin/emails", tags=["admin"])


class EmailQueueEntry(BaseModel):
    email_id: uuid.UUID
    to_email: str
    template: str
    status: Literal[
        "pending",
        "sent",
        "delivered",
        "delivery_delayed",
        "bounced",
        "complained",
        "suppressed",
        "failed",
    ]
    attempts: int
    last_error: str | None
    resend_id: str | None
    bounce_type: str | None
    scheduled_at: datetime
    sent_at: datetime | None


@router.get("", response_model=Envelope[list[EmailQueueEntry]])
async def list_emails(
    _admin: Annotated[User, Depends(require_role("admin", "operator"))],
    db: DbSession,
    status_filter: str | None = None,
    limit: int = 50,
) -> Envelope[list[EmailQueueEntry]]:
    q = select(EmailQueue).order_by(EmailQueue.scheduled_at.desc()).limit(limit)
    if status_filter:
        q = q.where(EmailQueue.status == status_filter)
    result = await db.execute(q)
    rows = list(result.scalars())
    return Envelope.of([_to_entry(r) for r in rows])


@router.get("/deliverability", response_model=Envelope[AdminEmailDeliverability])
async def get_email_deliverability(
    _admin: Annotated[User, Depends(require_role("admin", "operator"))],
    db: DbSession,
) -> Envelope[AdminEmailDeliverability]:
    return Envelope.of(await build_email_deliverability_summary(db))


@router.post("/{email_id}/resend", response_model=Envelope[EmailQueueEntry])
async def resend_email(
    email_id: uuid.UUID,
    _admin: Annotated[User, Depends(require_role("admin"))],
    db: DbSession,
) -> Envelope[EmailQueueEntry]:
    row = await db.scalar(select(EmailQueue).where(EmailQueue.email_id == email_id))
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "Not found."},
        )
    row.status = "pending"
    row.attempts = 0
    row.last_error = None
    row.scheduled_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(row)
    return Envelope.of(_to_entry(row))


def _to_entry(r: EmailQueue) -> EmailQueueEntry:
    return EmailQueueEntry(
        email_id=r.email_id,
        to_email=r.to_email,
        template=r.template,
        status=r.status,
        attempts=r.attempts,
        last_error=r.last_error,
        resend_id=r.resend_id,
        bounce_type=r.bounce_type,
        scheduled_at=r.scheduled_at,
        sent_at=r.sent_at,
    )
