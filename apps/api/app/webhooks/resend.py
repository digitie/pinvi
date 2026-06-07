"""`/webhooks/resend` — Resend 이벤트 webhook."""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import time
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import update
from starlette.datastructures import Headers

from app.core.config import settings
from app.core.deps import DbSession
from app.core.logging import get_logger
from app.core.time import utc_now
from app.models.email_queue import EmailQueue

router = APIRouter(prefix="/webhooks/resend", tags=["webhooks"])
log = get_logger("resend_webhook")

_WEBHOOK_SIGNATURE_TOLERANCE_SECONDS = 300


class ResendWebhookSignatureError(Exception):
    """Resend/Svix webhook 서명 검증 실패."""


def _get_header(headers: Headers, *names: str) -> str | None:
    for name in names:
        value = headers.get(name)
        if value:
            return value
    return None


def _decode_svix_secret(secret: str) -> bytes:
    secret_value = secret.removeprefix("whsec_")
    padding = "=" * (-len(secret_value) % 4)
    try:
        return base64.b64decode(f"{secret_value}{padding}", altchars=b"-_", validate=False)
    except (binascii.Error, ValueError) as exc:
        raise ResendWebhookSignatureError("invalid webhook secret") from exc


def _iter_v1_signatures(signature_header: str) -> list[str]:
    signatures: list[str] = []
    for item in signature_header.split():
        version, separator, signature = item.partition(",")
        if version == "v1" and separator and signature:
            signatures.append(signature)
    return signatures


def _verify_resend_signature(
    payload: bytes,
    headers: Headers,
    secret: str,
    *,
    now_timestamp: int | None = None,
) -> None:
    message_id = _get_header(headers, "svix-id", "webhook-id")
    timestamp_raw = _get_header(headers, "svix-timestamp", "webhook-timestamp")
    signature_header = _get_header(
        headers,
        "svix-signature",
        "webhook-signature",
        "resend-signature",
        "Resend-Signature",
    )

    if not message_id or not timestamp_raw or not signature_header:
        raise ResendWebhookSignatureError("missing required signature headers")

    try:
        timestamp = int(timestamp_raw)
    except ValueError as exc:
        raise ResendWebhookSignatureError("invalid signature timestamp") from exc

    current_timestamp = int(time.time()) if now_timestamp is None else now_timestamp
    if abs(current_timestamp - timestamp) > _WEBHOOK_SIGNATURE_TOLERANCE_SECONDS:
        raise ResendWebhookSignatureError("signature timestamp outside tolerance")

    signatures = _iter_v1_signatures(signature_header)
    if not signatures:
        raise ResendWebhookSignatureError("missing v1 signature")

    signed_content = f"{message_id}.{timestamp}.".encode() + payload
    expected_signature = base64.b64encode(
        hmac.new(_decode_svix_secret(secret), signed_content, hashlib.sha256).digest()
    ).decode()

    if not any(hmac.compare_digest(expected_signature, signature) for signature in signatures):
        raise ResendWebhookSignatureError("signature mismatch")


@router.post("", status_code=status.HTTP_200_OK)
async def resend_webhook(request: Request, db: DbSession) -> dict[str, bool]:
    payload = await request.body()
    if settings.tripmate_resend_webhook_secret:
        try:
            _verify_resend_signature(
                payload,
                request.headers,
                settings.tripmate_resend_webhook_secret,
            )
        except ResendWebhookSignatureError as exc:
            log.warning("resend_webhook.invalid_signature", reason=str(exc))
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "code": "WEBHOOK_SIGNATURE_INVALID",
                    "message": "Resend webhook signature is invalid.",
                },
            ) from exc

    try:
        body_raw = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "VALIDATION_ERROR", "message": "Webhook payload JSON is invalid."},
        ) from exc

    body: dict[str, Any] = body_raw if isinstance(body_raw, dict) else {}

    event_type = body.get("type")
    data_raw = body.get("data", {})
    data: dict[str, Any] = data_raw if isinstance(data_raw, dict) else {}
    headers_raw = data.get("headers", {})
    data_headers: dict[str, Any] = headers_raw if isinstance(headers_raw, dict) else {}
    entity_ref = data_headers.get("X-Entity-Ref-ID")

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
        bounce_raw = data.get("bounce", {})
        bounce = bounce_raw if isinstance(bounce_raw, dict) else {}
        bounce_type = bounce.get("type")
        await db.execute(
            update(EmailQueue)
            .where(EmailQueue.email_id == entity_ref)
            .values(status="bounced", bounced_at=now, bounce_type=bounce_type)
        )
    elif event_type == "email.complained":
        await db.execute(
            update(EmailQueue).where(EmailQueue.email_id == entity_ref).values(status="complained")
        )

    await db.commit()
    log.info("resend_webhook.processed", event_type=event_type, entity_ref=entity_ref)
    return {"ok": True}
