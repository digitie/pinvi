"""Resend 이메일 outbox + SKIP LOCKED worker.

자세히는 `docs/integrations/resend.md`. API 요청은 `app.email_queue`에 적재하고,
worker가 PostgreSQL `FOR UPDATE SKIP LOCKED`로 pending row를 가져가 발송한다.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from html import escape
from typing import Any, cast

from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.models.email_queue import EmailQueue

log = get_logger("email")

MAX_EMAIL_ATTEMPTS = 5
RETRY_BACKOFF_SECONDS = (30, 300, 1800, 3600, 14400)


@dataclass(frozen=True, slots=True)
class EmailBatchResult:
    claimed: int
    sent: int
    retried: int
    failed: int


async def enqueue_verification_email(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    to_email: str,
    token: str,
    expires_in_hours: int = 24,
) -> bool:
    """회원가입 인증 메일을 outbox에 적재합니다.

    반환값은 실제 provider 발송 가능 여부다. API key가 없는 개발 환경에서도 queue row는
    만들되 `verification_email_dispatched=false` 계약을 유지한다.
    """

    verify_url = _build_verify_url(token)
    db.add(
        EmailQueue(
            user_id=user_id,
            to_email=to_email,
            template="verify_email",
            subject="Pinvi 이메일 인증",
            payload={
                "verify_url": verify_url,
                "expires_in_hours": expires_in_hours,
                "user_id": str(user_id),
            },
            status="pending",
            scheduled_at=datetime.now(UTC),
        )
    )
    return bool(settings.pinvi_resend_api_key)


async def enqueue_password_reset_email(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    to_email: str,
    token: str,
    expires_in_minutes: int = 60,
) -> bool:
    """비밀번호 재설정 메일을 outbox에 적재합니다."""

    reset_url = _build_password_reset_url(token)
    db.add(
        EmailQueue(
            user_id=user_id,
            to_email=to_email,
            template="reset_password",
            subject="Pinvi 비밀번호 재설정",
            payload={
                "reset_url": reset_url,
                "expires_in_minutes": expires_in_minutes,
                "user_id": str(user_id),
            },
            status="pending",
            scheduled_at=datetime.now(UTC),
        )
    )
    return bool(settings.pinvi_resend_api_key)


async def enqueue_trip_invite_email(
    db: AsyncSession,
    *,
    to_email: str,
    trip_id: uuid.UUID,
    trip_title: str,
    companion_id: uuid.UUID,
    invited_by_user_id: uuid.UUID,
    target_user_id: uuid.UUID | None,
) -> bool:
    """동반자 초대 메일을 outbox에 적재합니다."""

    invite_url = _build_trip_invite_url(trip_id=trip_id, companion_id=companion_id)
    db.add(
        EmailQueue(
            user_id=target_user_id,
            to_email=to_email,
            template="trip_invite",
            subject=f"Pinvi 여행 초대: {trip_title}",
            payload={
                "invite_url": invite_url,
                "trip_id": str(trip_id),
                "trip_title": trip_title,
                "companion_id": str(companion_id),
                "invited_by_user_id": str(invited_by_user_id),
                "target_user_id": None if target_user_id is None else str(target_user_id),
            },
            status="pending",
            scheduled_at=datetime.now(UTC),
        )
    )
    return bool(settings.pinvi_resend_api_key)


async def process_pending_email_batch(
    db: AsyncSession,
    *,
    limit: int = 50,
    now: datetime | None = None,
) -> EmailBatchResult:
    """pending email을 `FOR UPDATE SKIP LOCKED`로 가져와 한 batch 발송합니다."""

    current = now or datetime.now(UTC)
    result = await db.execute(
        select(EmailQueue)
        .where(
            EmailQueue.status == "pending",
            EmailQueue.scheduled_at <= current,
        )
        .order_by(EmailQueue.scheduled_at, EmailQueue.created_at)
        .limit(limit)
        .with_for_update(skip_locked=True)
    )
    rows = list(result.scalars())
    sent = 0
    retried = 0
    failed = 0

    for row in rows:
        row.attempts += 1
        try:
            row.resend_id = await _send_email_row(row)
        except Exception as exc:
            if row.attempts >= MAX_EMAIL_ATTEMPTS:
                row.status = "failed"
                failed += 1
            else:
                row.status = "pending"
                row.scheduled_at = current + timedelta(seconds=_retry_delay(row.attempts))
                retried += 1
            row.last_error = str(exc)
            log.warning(
                "email.worker_failed",
                email_id=str(row.email_id),
                template=row.template,
                attempts=row.attempts,
                error=str(exc),
            )
            continue

        row.status = "sent"
        row.sent_at = current
        row.last_error = None
        sent += 1

    if rows:
        await db.commit()

    return EmailBatchResult(claimed=len(rows), sent=sent, retried=retried, failed=failed)


async def _drain_loop(interval: float, batch_size: int) -> None:
    from app.db.session import async_session_factory

    while True:
        try:
            async with async_session_factory() as session:
                result = await process_pending_email_batch(session, limit=batch_size)
            if result.claimed < batch_size:
                await asyncio.sleep(interval)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.warning("email.outbox_drain_failed", exc_info=True)
            await asyncio.sleep(interval)


@asynccontextmanager
async def email_outbox_worker_lifespan(app: FastAPI) -> AsyncIterator[None]:
    """FastAPI lifespan — email_queue drain worker를 시작/정리합니다."""

    if not settings.pinvi_email_outbox_worker_enabled:
        yield
        return

    task = asyncio.create_task(
        _drain_loop(
            settings.pinvi_email_outbox_drain_interval_seconds,
            settings.pinvi_email_outbox_batch_size,
        ),
        name="email-outbox-drain",
    )
    app.state.email_outbox_worker = task
    try:
        yield
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
        app.state.email_outbox_worker = None


async def send_verification_email(
    *,
    to_email: str,
    verify_url: str,
    expires_in_hours: int = 24,
) -> bool:
    """기존 즉시 발송 helper. 신규 flow는 `enqueue_verification_email`을 사용한다."""

    try:
        resend_id = await _send_email_payload(
            to_email=to_email,
            subject="Pinvi 이메일 인증",
            html=_render_verify_html(verify_url, expires_in_hours),
            template="verify_email",
            entity_ref=None,
        )
    except Exception as exc:
        log.error("email.send_failed", error=str(exc), to_email=to_email, template="verify_email")
        return False
    return resend_id is not None


async def _send_email_row(row: EmailQueue) -> str | None:
    payload = row.payload or {}
    return await _send_email_payload(
        to_email=row.to_email,
        subject=row.subject,
        html=_render_template(row.template, payload),
        template=row.template,
        entity_ref=row.email_id,
    )


async def _send_email_payload(
    *,
    to_email: str,
    subject: str,
    html: str,
    template: str,
    entity_ref: uuid.UUID | None,
) -> str | None:
    payload: dict[str, Any] = {
        "to_email": to_email,
        "subject": subject,
        "template": template,
        "entity_ref": None if entity_ref is None else str(entity_ref),
    }

    if not settings.pinvi_resend_api_key:
        log.info("email.console_mode", **payload)
        return None

    import resend

    resend.api_key = settings.pinvi_resend_api_key
    resend_payload: dict[str, Any] = {
        "from": settings.pinvi_resend_from_email,
        "to": [to_email],
        "subject": subject,
        "html": html,
        "tags": [
            {"name": "template", "value": template},
            {"name": "env", "value": settings.pinvi_environment},
        ],
    }
    if entity_ref is not None:
        resend_payload["headers"] = {"X-Entity-Ref-ID": str(entity_ref)}
    response = cast(Any, resend.Emails.send)(resend_payload)
    resend_id = response.get("id") if isinstance(response, dict) else None
    log.info("email.sent", resend_id=resend_id, **payload)
    return None if resend_id is None else str(resend_id)


def _render_template(template: str, payload: dict[str, Any]) -> str:
    if template == "verify_email":
        return _render_verify_html(
            verify_url=str(payload["verify_url"]),
            expires_in_hours=int(payload.get("expires_in_hours", 24)),
        )
    if template == "reset_password":
        return _render_reset_password_html(
            reset_url=str(payload["reset_url"]),
            expires_in_minutes=int(payload.get("expires_in_minutes", 60)),
        )
    if template == "trip_invite":
        return _render_trip_invite_html(
            invite_url=str(payload["invite_url"]),
            trip_title=str(payload["trip_title"]),
        )
    return _render_generic_html(template=template, payload=payload)


def _render_verify_html(verify_url: str, expires_in_hours: int) -> str:
    safe_url = json.dumps(verify_url)
    return f"""
    <html>
      <body style="font-family: sans-serif;">
        <h2>Pinvi 이메일 인증</h2>
        <p>아래 버튼을 클릭하여 이메일 주소를 인증하세요.</p>
        <p>
          <a href={safe_url}
             style="background:#FF385C;color:#fff;padding:12px 24px;
                    border-radius:6px;text-decoration:none;">
            이메일 인증하기
          </a>
        </p>
        <p style="color:#666;font-size:14px;margin-top:24px;">
          이 링크는 {expires_in_hours}시간 후 만료됩니다.<br />
          본인이 가입하지 않았다면 이 메일을 무시하세요.
        </p>
      </body>
    </html>
    """


def _render_reset_password_html(reset_url: str, expires_in_minutes: int) -> str:
    safe_url = json.dumps(reset_url)
    return f"""
    <html>
      <body style="font-family: sans-serif;">
        <h2>Pinvi 비밀번호 재설정</h2>
        <p>아래 버튼을 클릭하여 새 비밀번호를 설정하세요.</p>
        <p>
          <a href={safe_url}
             style="background:#FF385C;color:#fff;padding:12px 24px;
                    border-radius:6px;text-decoration:none;">
            비밀번호 재설정
          </a>
        </p>
        <p style="color:#666;font-size:14px;margin-top:24px;">
          이 링크는 {expires_in_minutes}분 후 만료됩니다.<br />
          본인이 요청하지 않았다면 이 메일을 무시하세요.
        </p>
      </body>
    </html>
    """


def _render_trip_invite_html(invite_url: str, trip_title: str) -> str:
    safe_url = json.dumps(invite_url)
    safe_title = escape(trip_title)
    return f"""
    <html>
      <body style="font-family: sans-serif;">
        <h2>Pinvi 여행 초대</h2>
        <p>{safe_title} 여행에 동반자로 초대되었습니다.</p>
        <p>
          <a href={safe_url}
             style="background:#FF385C;color:#fff;padding:12px 24px;
                    border-radius:6px;text-decoration:none;">
            여행 확인하기
          </a>
        </p>
      </body>
    </html>
    """


def _render_generic_html(*, template: str, payload: dict[str, Any]) -> str:
    safe_payload = json.dumps(payload, ensure_ascii=False, indent=2)
    return f"""
    <html>
      <body style="font-family: sans-serif;">
        <h2>Pinvi 알림</h2>
        <p>template: {template}</p>
        <pre>{safe_payload}</pre>
      </body>
    </html>
    """


def _build_verify_url(token: str) -> str:
    return f"{settings.pinvi_web_base_url}{settings.pinvi_email_verification_path}?token={token}"


def _build_password_reset_url(token: str) -> str:
    return f"{settings.pinvi_web_base_url}{settings.pinvi_auth_reset_path}?token={token}"


def _build_trip_invite_url(*, trip_id: uuid.UUID, companion_id: uuid.UUID) -> str:
    return f"{settings.pinvi_web_base_url}/trips/{trip_id}?invite={companion_id}"


def _retry_delay(attempts: int) -> int:
    index = max(0, min(attempts - 1, len(RETRY_BACKOFF_SECONDS) - 1))
    return RETRY_BACKOFF_SECONDS[index]
