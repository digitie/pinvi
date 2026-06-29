"""Email deliverability, suppression, and Resend webhook state."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from email.utils import parseaddr
from typing import Any, Literal, cast

from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.resend import create_resend_client
from app.core.config import settings
from app.models.email_deliverability import EmailSuppression, ResendWebhookEvent
from app.models.email_queue import EmailQueue
from app.models.user import User
from app.models.user_consent import UserConsent
from app.schemas.admin import (
    AdminEmailDeliverability,
    AdminEmailDeliverabilityCheck,
    AdminEmailDeliverabilityDomain,
    AdminEmailDeliverabilityQueue,
    AdminEmailDeliverabilitySuppression,
    AdminEmailDeliverabilityWebhook,
)
from app.services.hash_chain import sha256_hex

EmailQueueStatus = Literal[
    "pending",
    "sent",
    "delivered",
    "delivery_delayed",
    "bounced",
    "complained",
    "suppressed",
    "failed",
]

_RESEND_EVENT_STATUS: dict[str, EmailQueueStatus] = {
    "email.delivered": "delivered",
    "email.delivery_delayed": "delivery_delayed",
    "email.failed": "failed",
    "email.bounced": "bounced",
    "email.complained": "complained",
    "email.suppressed": "suppressed",
}
_STATUS_PRECEDENCE: dict[str, int] = {
    "pending": 0,
    "sent": 10,
    "delivery_delayed": 20,
    "delivered": 30,
    "failed": 40,
    "suppressed": 90,
    "bounced": 100,
    "complained": 110,
}
_RECENT_WEBHOOK_WINDOW = timedelta(hours=24)


@dataclass(frozen=True, slots=True)
class EmailSuppressionDecision:
    status: EmailQueueStatus
    reason: str


def normalize_email(email: str) -> str:
    return email.strip().lower()


def email_hash(email: str) -> str:
    return sha256_hex(normalize_email(email))


async def get_active_email_suppression(
    db: AsyncSession,
    *,
    email: str,
) -> EmailSuppression | None:
    return cast(
        EmailSuppression | None,
        await db.scalar(
            select(EmailSuppression).where(
                EmailSuppression.email_hash == email_hash(email),
                EmailSuppression.released_at.is_(None),
            )
        ),
    )


async def get_email_suppression_decision(
    db: AsyncSession,
    row: EmailQueue,
) -> EmailSuppressionDecision | None:
    if row.user_id is not None:
        user = await db.scalar(select(User).where(User.user_id == row.user_id))
        if user is not None and user.email_status != "active":
            status: EmailQueueStatus = "suppressed"
            if user.email_status == "bounced":
                status = "bounced"
            elif user.email_status == "complained":
                status = "complained"
            return EmailSuppressionDecision(
                status=status,
                reason=f"user_email_status:{user.email_status}",
            )

    suppression = await get_active_email_suppression(db, email=row.to_email)
    if suppression is not None:
        return EmailSuppressionDecision(
            status="suppressed",
            reason=f"suppression:{suppression.reason}",
        )

    if row.template.startswith("marketing"):
        has_marketing_consent = False
        if row.user_id is not None:
            consent = await db.scalar(
                select(UserConsent).where(
                    UserConsent.user_id == row.user_id,
                    UserConsent.consent_type == "marketing",
                    UserConsent.withdrawn_at.is_(None),
                )
            )
            has_marketing_consent = consent is not None
        if not has_marketing_consent:
            return EmailSuppressionDecision(
                status="suppressed",
                reason="missing_marketing_consent",
            )

    return None


async def upsert_email_suppression(
    db: AsyncSession,
    *,
    email: str,
    reason: Literal["hard_bounce", "complaint", "provider_suppressed", "manual"],
    source: Literal["resend", "admin"] = "resend",
    provider_event_id: str | None = None,
    seen_at: datetime | None = None,
) -> EmailSuppression:
    now = seen_at or datetime.now(UTC)
    hashed = email_hash(email)
    row = await db.scalar(select(EmailSuppression).where(EmailSuppression.email_hash == hashed))
    if row is None:
        row = EmailSuppression(
            email_hash=hashed,
            reason=reason,
            source=source,
            provider_event_id=provider_event_id,
            first_seen_at=now,
            last_seen_at=now,
        )
        db.add(row)
        await db.flush()
        return row

    row.reason = reason
    row.source = source
    row.provider_event_id = provider_event_id
    row.last_seen_at = now
    row.released_at = None
    row.released_by_user_id = None
    row.release_reason = None
    return row


async def record_resend_webhook_event(
    db: AsyncSession,
    *,
    event_id: str,
    svix_id: str | None,
    event_type: str,
    entity_ref: uuid.UUID | None,
    resend_email_id: str | None,
    event_created_at: datetime | None,
    payload_summary: dict[str, Any],
) -> bool:
    stmt = (
        pg_insert(ResendWebhookEvent)
        .values(
            event_id=event_id,
            svix_id=svix_id,
            event_type=event_type,
            entity_ref=entity_ref,
            resend_email_id=resend_email_id,
            event_created_at=event_created_at,
            payload_summary=payload_summary,
        )
        .on_conflict_do_nothing()
    )
    result = await db.execute(stmt)
    return int(cast(Any, result).rowcount) == 1


async def apply_resend_event_to_queue(
    db: AsyncSession,
    *,
    event_id: str,
    event_type: str,
    entity_ref: uuid.UUID,
    event_created_at: datetime | None,
    data: dict[str, Any],
) -> None:
    new_status = _RESEND_EVENT_STATUS.get(event_type)
    if new_status is None:
        return

    row = await db.scalar(
        select(EmailQueue).where(EmailQueue.email_id == entity_ref).with_for_update()
    )
    if row is None:
        return

    current_rank = _STATUS_PRECEDENCE.get(row.status, 0)
    new_rank = _STATUS_PRECEDENCE[new_status]
    event_time = event_created_at or datetime.now(UTC)
    last_event_time = row.last_provider_event_at
    is_newer_or_equal = last_event_time is None or event_time >= last_event_time
    is_terminal_suppression = new_status in {"bounced", "complained", "suppressed"}
    should_apply_terminal_suppression = is_terminal_suppression and (
        new_rank >= current_rank or current_rank < _STATUS_PRECEDENCE["suppressed"]
    )
    should_update = new_rank >= current_rank or should_apply_terminal_suppression
    if should_update and (is_newer_or_equal or is_terminal_suppression):
        row.status = new_status
        row.last_provider_event_id = event_id
        row.last_provider_event_at = event_time
        if new_status == "delivered":
            row.delivered_at = event_time
        elif new_status == "bounced":
            bounce = _as_dict(data.get("bounce"))
            row.bounced_at = event_time
            row.bounce_type = _as_str(bounce.get("type"))
        elif new_status in {"failed", "delivery_delayed", "suppressed"}:
            row.last_error = _provider_message(data)

    if should_apply_terminal_suppression:
        await _suppress_from_event(
            db,
            row=row,
            new_status=new_status,
            event_id=event_id,
            event_time=event_time,
        )


async def build_email_deliverability_summary(db: AsyncSession) -> AdminEmailDeliverability:
    now = datetime.now(UTC)
    from_email = settings.pinvi_resend_from_email
    from_domain = _extract_email_domain(from_email)
    resend_api_configured = bool(settings.pinvi_resend_api_key.strip())
    domain = await _build_domain_status(from_email=from_email, from_domain=from_domain)
    webhook = await _build_webhook_status(db, now=now)
    suppression = await _build_suppression_status(db)
    queue = await _build_queue_status(db)

    checks = _build_checks(
        resend_api_configured=resend_api_configured,
        from_domain=from_domain,
        domain=domain,
        webhook=webhook,
    )
    status_value = (
        "ok"
        if all(check.status == "ok" for check in checks if check.key != "dns_records")
        else "degraded"
    )
    return AdminEmailDeliverability(
        generated_at=now,
        status=status_value,
        resend_api_configured=resend_api_configured,
        console_mode=not resend_api_configured,
        domain=domain,
        webhook=webhook,
        suppression=suppression,
        queue=queue,
        checks=checks,
    )


async def _suppress_from_event(
    db: AsyncSession,
    *,
    row: EmailQueue,
    new_status: EmailQueueStatus,
    event_id: str,
    event_time: datetime,
) -> None:
    reason: Literal["hard_bounce", "complaint", "provider_suppressed"]
    user_status: str
    if new_status == "bounced":
        reason = "hard_bounce"
        user_status = "bounced"
    elif new_status == "complained":
        reason = "complaint"
        user_status = "complained"
    else:
        reason = "provider_suppressed"
        user_status = "suppressed"

    await upsert_email_suppression(
        db,
        email=row.to_email,
        reason=reason,
        provider_event_id=event_id,
        seen_at=event_time,
    )
    if row.user_id is not None:
        user = await db.scalar(select(User).where(User.user_id == row.user_id).with_for_update())
        if user is not None and user.email_status == "active":
            user.email_status = user_status


async def _build_domain_status(
    *,
    from_email: str,
    from_domain: str | None,
) -> AdminEmailDeliverabilityDomain:
    if not settings.pinvi_resend_api_key.strip():
        return AdminEmailDeliverabilityDomain(
            from_email=from_email,
            from_domain=from_domain,
            domain_matched=None,
        )

    try:
        async with create_resend_client() as client:
            domains = await client.list_domains()
    except Exception as exc:
        return AdminEmailDeliverabilityDomain(
            from_email=from_email,
            from_domain=from_domain,
            domain_matched=None,
            error_class=type(exc).__name__,
        )

    matched = next(
        (
            item
            for item in domains
            if from_domain is not None and _as_str(item.get("name")).lower() == from_domain
        ),
        None,
    )
    capabilities = _as_dict(matched.get("capabilities")) if matched is not None else {}
    sending = (
        _as_str(capabilities.get("sending")) or _as_str(matched.get("sending")) if matched else None
    )
    return AdminEmailDeliverabilityDomain(
        from_email=from_email,
        from_domain=from_domain,
        domain_status=_as_str(matched.get("status")) if matched else None,
        sending_capability=sending,
        domain_matched=matched is not None,
        domains_checked=len(domains),
    )


async def _build_webhook_status(
    db: AsyncSession,
    *,
    now: datetime,
) -> AdminEmailDeliverabilityWebhook:
    since = now - _RECENT_WEBHOOK_WINDOW
    latest_processed_at = await db.scalar(select(func.max(ResendWebhookEvent.processed_at)))
    result = await db.execute(
        select(ResendWebhookEvent.event_type, func.count())
        .where(ResendWebhookEvent.processed_at >= since)
        .group_by(ResendWebhookEvent.event_type)
    )
    return AdminEmailDeliverabilityWebhook(
        signature_configured=bool(settings.pinvi_resend_webhook_secret.strip()),
        unsigned_allowed=bool(settings.pinvi_resend_webhook_allow_unsigned),
        latest_processed_at=latest_processed_at,
        recent_events={event_type: int(count) for event_type, count in result.all()},
    )


async def _build_suppression_status(db: AsyncSession) -> AdminEmailDeliverabilitySuppression:
    active_suppressions = await db.scalar(
        select(func.count())
        .select_from(EmailSuppression)
        .where(EmailSuppression.released_at.is_(None))
    )
    released_suppressions = await db.scalar(
        select(func.count())
        .select_from(EmailSuppression)
        .where(EmailSuppression.released_at.is_not(None))
    )
    user_status_rows = await db.execute(
        select(User.email_status, func.count()).group_by(User.email_status)
    )
    return AdminEmailDeliverabilitySuppression(
        active_suppressions=int(active_suppressions or 0),
        released_suppressions=int(released_suppressions or 0),
        users_by_email_status={status: int(count) for status, count in user_status_rows.all()},
    )


async def _build_queue_status(db: AsyncSession) -> AdminEmailDeliverabilityQueue:
    row = (
        (
            await db.execute(
                text(
                    """
                SELECT
                  count(*) FILTER (WHERE status = 'pending')::int AS pending,
                  count(*) FILTER (WHERE status = 'sent')::int AS sent,
                  count(*) FILTER (WHERE status = 'delivered')::int AS delivered,
                  count(*) FILTER (WHERE status = 'delivery_delayed')::int AS delivery_delayed,
                  count(*) FILTER (WHERE status = 'bounced')::int AS bounced,
                  count(*) FILTER (WHERE status = 'complained')::int AS complained,
                  count(*) FILTER (WHERE status = 'suppressed')::int AS suppressed,
                  count(*) FILTER (WHERE status = 'failed')::int AS failed
                FROM app.email_queue
                """
                )
            )
        )
        .mappings()
        .one()
    )
    return AdminEmailDeliverabilityQueue(
        pending=int(row["pending"] or 0),
        sent=int(row["sent"] or 0),
        delivered=int(row["delivered"] or 0),
        delivery_delayed=int(row["delivery_delayed"] or 0),
        bounced=int(row["bounced"] or 0),
        complained=int(row["complained"] or 0),
        suppressed=int(row["suppressed"] or 0),
        failed=int(row["failed"] or 0),
    )


def _build_checks(
    *,
    resend_api_configured: bool,
    from_domain: str | None,
    domain: AdminEmailDeliverabilityDomain,
    webhook: AdminEmailDeliverabilityWebhook,
) -> list[AdminEmailDeliverabilityCheck]:
    domain_verified = domain.domain_status == "verified"
    sending_known_bad = domain.sending_capability not in {None, "", "enabled", "true", "active"}
    return [
        AdminEmailDeliverabilityCheck(
            key="resend_api",
            label="Resend API",
            status="ok" if resend_api_configured else "error",
            message=None if resend_api_configured else "console mode",
        ),
        AdminEmailDeliverabilityCheck(
            key="from_domain",
            label="FROM domain",
            status="ok" if from_domain else "error",
            message=from_domain,
        ),
        AdminEmailDeliverabilityCheck(
            key="domain_verified",
            label="Domain verified",
            status="ok" if domain_verified else "error",
            message=domain.domain_status or domain.error_class or "not found",
        ),
        AdminEmailDeliverabilityCheck(
            key="sending_capability",
            label="Sending",
            status="error" if sending_known_bad else "ok",
            message=domain.sending_capability,
        ),
        AdminEmailDeliverabilityCheck(
            key="dns_records",
            label="SPF/DKIM/DMARC",
            status="warn",
            message="manual check required",
        ),
        AdminEmailDeliverabilityCheck(
            key="webhook_signature",
            label="Webhook signature",
            status="ok" if webhook.signature_configured else "error",
            message=None if webhook.signature_configured else "missing secret",
        ),
        AdminEmailDeliverabilityCheck(
            key="webhook_unsigned",
            label="Unsigned webhook",
            status="ok" if not webhook.unsigned_allowed else "warn",
            message="allowed" if webhook.unsigned_allowed else "disabled",
        ),
    ]


def _extract_email_domain(value: str) -> str | None:
    _, addr = parseaddr(value)
    if "@" not in addr:
        return None
    return addr.rsplit("@", 1)[1].strip().lower() or None


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_str(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _provider_message(data: dict[str, Any]) -> str | None:
    for key in ("message", "reason"):
        value = data.get(key)
        if isinstance(value, str) and value:
            return value[:500]
    return None
