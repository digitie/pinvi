"""`/webhooks/resend` — Resend 이벤트 webhook.

`docs/integrations/resend.md` §6. Svix 서명 검증은 Sprint 5에 실제 검증 활성화.
Sprint 2는 페이로드 파싱 + email_queue 상태 업데이트만.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request, status
from sqlalchemy import update

from app.core.config import settings
from app.core.deps import DbSession
from app.core.logging import get_logger
from app.core.time import utc_now
from app.models.email_queue import EmailQueue

router = APIRouter(prefix="/webhooks/resend", tags=["webhooks"])
log = get_logger("resend_webhook")


@router.post("", status_code=status.HTTP_200_OK)
async def resend_webhook(request: Request, db: DbSession) -> dict[str, bool]:
    body = await request.json()

    # 서명 검증 — Sprint 5에 활성화
    if settings.tripmate_resend_webhook_secret:
        signature = request.headers.get("Resend-Signature") or request.headers.get(
            "svix-signature"
        )
        if not signature:
            log.warning("resend_webhook.missing_signature")

    event_type = body.get("type")
    data: dict[str, Any] = body.get("data", {})
    entity_ref = data.get("headers", {}).get("X-Entity-Ref-ID")

    if not isinstance(entity_ref, str):
        log.info("resend_webhook.no_entity_ref", event_type=event_type)
        return {"ok": True}

    now = utc_now()
    if event_type == "email.delivered":
        await db.execute(
            update(EmailQueue)
            .where(EmailQueue.email_id == entity_ref)
            .values(status="delivered", delivered_at=now)
        )
    elif event_type == "email.bounced":
        bounce_type = data.get("bounce", {}).get("type")
        await db.execute(
            update(EmailQueue)
            .where(EmailQueue.email_id == entity_ref)
            .values(status="bounced", bounced_at=now, bounce_type=bounce_type)
        )
    elif event_type == "email.complained":
        await db.execute(
            update(EmailQueue)
            .where(EmailQueue.email_id == entity_ref)
            .values(status="complained")
        )

    await db.commit()
    log.info("resend_webhook.processed", event_type=event_type, entity_ref=entity_ref)
    return {"ok": True}
