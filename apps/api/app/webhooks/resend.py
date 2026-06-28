"""`/webhooks/resend` — Resend 이벤트 webhook."""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import time
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from starlette.datastructures import Headers

from app.core.config import settings
from app.core.deps import DbSession
from app.core.logging import get_logger
from app.services.email_deliverability import (
    apply_resend_event_to_queue,
    record_resend_webhook_event,
)

router = APIRouter(prefix="/webhooks/resend", tags=["webhooks"])
log = get_logger("resend_webhook")

_WEBHOOK_SIGNATURE_TOLERANCE_SECONDS = 300
_UNSIGNED_WEBHOOK_ENVIRONMENTS = {"development", "dev", "local", "test", "testing"}


class ResendWebhookSignatureError(Exception):
    """Resend/Svix webhook 서명 검증 실패."""


class ResendWebhookSecretError(Exception):
    """Resend/Svix webhook secret 설정 오류."""


def _allows_unsigned_resend_webhook() -> bool:
    return (
        settings.pinvi_resend_webhook_allow_unsigned
        and settings.pinvi_environment.lower() in _UNSIGNED_WEBHOOK_ENVIRONMENTS
    )


def _get_header(headers: Headers, *names: str) -> str | None:
    for name in names:
        value = headers.get(name)
        if value:
            return value
    return None


def _decode_svix_secret(secret: str) -> bytes:
    if not secret.startswith("whsec_"):
        raise ResendWebhookSecretError("webhook secret must start with whsec_")

    secret_value = secret.removeprefix("whsec_")
    padding = "=" * (-len(secret_value) % 4)
    try:
        return base64.b64decode(f"{secret_value}{padding}", validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ResendWebhookSecretError("invalid webhook secret") from exc


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


def _dict_get_case_insensitive(values: dict[str, Any], key: str) -> Any:
    for item_key, item_value in values.items():
        if item_key.lower() == key.lower():
            return item_value
    return None


def _as_str(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _parse_event_time(value: Any) -> datetime | None:
    if isinstance(value, int | float):
        return datetime.fromtimestamp(value, UTC)
    if not isinstance(value, str) or not value:
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


@router.post("", status_code=status.HTTP_200_OK)
async def resend_webhook(request: Request, db: DbSession) -> dict[str, bool]:
    payload = await request.body()
    webhook_secret = settings.pinvi_resend_webhook_secret.strip()
    if not webhook_secret and not _allows_unsigned_resend_webhook():
        log.error(
            "resend_webhook.missing_secret",
            environment=settings.pinvi_environment,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "WEBHOOK_SIGNATURE_NOT_CONFIGURED",
                "message": "Resend webhook signature secret is not configured.",
            },
        )

    if webhook_secret:
        try:
            _verify_resend_signature(
                payload,
                request.headers,
                webhook_secret,
            )
        except ResendWebhookSecretError as exc:
            log.error("resend_webhook.invalid_secret_config", reason=str(exc))
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "code": "WEBHOOK_SIGNATURE_NOT_CONFIGURED",
                    "message": "Resend webhook signature secret is invalid.",
                },
            ) from exc
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
    entity_ref_raw = _dict_get_case_insensitive(data_headers, "X-Entity-Ref-ID")
    entity_ref = entity_ref_raw if isinstance(entity_ref_raw, str) else None
    entity_uuid: uuid.UUID | None = None
    if entity_ref is not None:
        try:
            entity_uuid = uuid.UUID(entity_ref)
        except ValueError:
            entity_uuid = None

    svix_id = _get_header(request.headers, "svix-id", "webhook-id")
    event_created_at = (
        _parse_event_time(body.get("created_at"))
        or _parse_event_time(body.get("createdAt"))
        or _parse_event_time(data.get("created_at"))
        or _parse_event_time(data.get("createdAt"))
    )
    event_id = (
        _as_str(body.get("id"))
        or _as_str(data.get("event_id"))
        or _as_str(data.get("id"))
        or (svix_id or "")
    )
    if not event_id:
        fingerprint = hashlib.sha256(payload).hexdigest()[:32]
        event_id = f"{event_type or 'unknown'}:{entity_ref or 'none'}:{fingerprint}"

    resend_email_id = _as_str(data.get("email_id")) or _as_str(data.get("id")) or None
    bounce = _as_dict(data.get("bounce"))
    inserted = await record_resend_webhook_event(
        db,
        event_id=event_id,
        svix_id=svix_id,
        event_type=_as_str(event_type) or "unknown",
        entity_ref=entity_uuid,
        resend_email_id=resend_email_id,
        event_created_at=event_created_at,
        payload_summary={
            "has_entity_ref": entity_uuid is not None,
            "bounce_type": _as_str(bounce.get("type")) or None,
        },
    )
    if not inserted:
        await db.commit()
        log.info("resend_webhook.duplicate", event_type=event_type, event_id=event_id)
        return {"ok": True}

    if entity_uuid is None:
        log.info("resend_webhook.no_entity_ref", event_type=event_type)
        await db.commit()
        return {"ok": True}

    await apply_resend_event_to_queue(
        db,
        event_id=event_id,
        event_type=_as_str(event_type),
        entity_ref=entity_uuid,
        event_created_at=event_created_at,
        data=data,
    )

    await db.commit()
    log.info("resend_webhook.processed", event_type=event_type, entity_ref=entity_ref)
    return {"ok": True}
