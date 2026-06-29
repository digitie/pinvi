"""Admin request timeline builder for `/admin/debug/request/{request_id}`."""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime
from typing import Any, Literal
from urllib.parse import parse_qsl, urlencode, urlsplit

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.kor_travel_map import KorTravelMapError
from app.clients.kor_travel_map_admin import KorTravelMapAdminClient
from app.models.api_call_log import ApiCallLog
from app.models.audit import AdminAuditLog, LocationAccessLog, LocationAuditOutbox
from app.models.email_queue import EmailQueue
from app.schemas.admin import (
    AdminRequestTimelineEvent,
    AdminRequestTimelineResponse,
    AdminRequestTimelineSource,
    AdminUpstreamApiCallLogRecord,
    AdminUpstreamSystemLogRecord,
)

_SENSITIVE_KEY_RE = re.compile(
    r"(authorization|cookie|set-cookie|token|secret|password|passwd|api[_-]?key|email|ip|host|domain)",
    re.IGNORECASE,
)
_SENSITIVE_PAIR_RE = re.compile(
    r"(?i)(authorization|cookie|token|secret|password|passwd|api[_-]?key|email)=([^&\s]+)"
)


async def build_request_timeline(
    db: AsyncSession,
    *,
    request_id: uuid.UUID,
    admin_client: KorTravelMapAdminClient,
) -> AdminRequestTimelineResponse:
    """Collect local Pinvi events and attach upstream sanitized logs as auxiliary sources."""
    generated_at = datetime.now(UTC)
    events: list[AdminRequestTimelineEvent] = []
    sources: list[AdminRequestTimelineSource] = []

    local_api_events = await _api_call_events(db, request_id)
    events.extend(local_api_events)
    sources.append(_source("pinvi_api_call_log", local_api_events))

    audit_events = await _admin_audit_events(db, request_id)
    events.extend(audit_events)
    sources.append(_source("pinvi_admin_audit_log", audit_events))

    location_events = await _location_events(db, request_id)
    events.extend(location_events)
    sources.append(_source("pinvi_location_audit", location_events))

    email_events = await _email_events(db, request_id)
    events.extend(email_events)
    sources.append(_source("pinvi_email_queue", email_events))

    upstream_system, system_source = await _upstream_system_events(admin_client, request_id)
    events.extend(upstream_system)
    sources.append(system_source)

    upstream_api, upstream_api_source = await _upstream_api_events(admin_client, request_id)
    events.extend(upstream_api)
    sources.append(upstream_api_source)

    events.sort(key=lambda item: (item.occurred_at, item.event_id))
    partial = any(source.status == "degraded" for source in sources)
    started_at = events[0].occurred_at if events else None
    finished_at = events[-1].occurred_at if events else None
    duration_ms = (
        int((finished_at - started_at).total_seconds() * 1000)
        if started_at is not None and finished_at is not None
        else None
    )

    return AdminRequestTimelineResponse(
        request_id=request_id,
        generated_at=generated_at,
        status="partial" if partial else "ok",
        started_at=started_at,
        finished_at=finished_at,
        duration_ms=duration_ms,
        sources=sources,
        events=events,
    )


def has_timeline_events(response: AdminRequestTimelineResponse) -> bool:
    return bool(response.events)


def has_degraded_source(response: AdminRequestTimelineResponse) -> bool:
    return any(source.status == "degraded" for source in response.sources)


async def _api_call_events(
    db: AsyncSession, request_id: uuid.UUID
) -> list[AdminRequestTimelineEvent]:
    rows = (
        await db.execute(
            select(ApiCallLog)
            .where(ApiCallLog.request_id == request_id)
            .order_by(ApiCallLog.occurred_at, ApiCallLog.log_id)
        )
    ).scalars()
    return [
        AdminRequestTimelineEvent(
            event_id=f"pinvi_api_call:{row.log_id}",
            occurred_at=row.occurred_at,
            source="pinvi_api_call_log",
            title=f"{row.provider} API call",
            status=str(row.status_code) if row.status_code is not None else None,
            duration_ms=row.latency_ms,
            error_code=row.error_class,
            detail={
                "provider": row.provider,
                "endpoint": _sanitize_url(row.endpoint),
                "has_error_message": bool(row.error_message),
            },
        )
        for row in rows
    ]


async def _admin_audit_events(
    db: AsyncSession, request_id: uuid.UUID
) -> list[AdminRequestTimelineEvent]:
    rows = (
        await db.execute(
            select(AdminAuditLog)
            .where(AdminAuditLog.request_id == request_id)
            .order_by(AdminAuditLog.occurred_at, AdminAuditLog.log_id)
        )
    ).scalars()
    return [
        AdminRequestTimelineEvent(
            event_id=f"pinvi_admin_audit:{row.log_id}",
            occurred_at=row.occurred_at,
            source="pinvi_admin_audit_log",
            title=row.action,
            status=row.resource_type,
            detail={
                "resource_type": row.resource_type,
                "resource_id": row.resource_id,
                "has_access_reason": bool(row.access_reason),
                "target_pii_fields": row.target_pii_fields or [],
                "has_before_state": row.before_state is not None,
                "has_after_state": row.after_state is not None,
            },
        )
        for row in rows
    ]


async def _location_events(
    db: AsyncSession, request_id: uuid.UUID
) -> list[AdminRequestTimelineEvent]:
    location_rows = (
        await db.execute(
            select(LocationAccessLog)
            .where(LocationAccessLog.request_id == request_id)
            .order_by(LocationAccessLog.occurred_at, LocationAccessLog.log_id)
        )
    ).scalars()
    outbox_rows = (
        await db.execute(
            select(LocationAuditOutbox)
            .where(LocationAuditOutbox.request_id == request_id)
            .order_by(LocationAuditOutbox.occurred_at, LocationAuditOutbox.outbox_id)
        )
    ).scalars()
    events = [
        AdminRequestTimelineEvent(
            event_id=f"pinvi_location_access:{row.log_id}",
            occurred_at=row.occurred_at,
            source="pinvi_location_audit",
            title="location access audit",
            status=row.purpose,
            detail={"endpoint": _sanitize_url(row.endpoint), "purpose": row.purpose},
        )
        for row in location_rows
    ]
    events.extend(
        AdminRequestTimelineEvent(
            event_id=f"pinvi_location_outbox:{row.outbox_id}",
            occurred_at=row.occurred_at,
            source="pinvi_location_audit",
            title="location audit outbox",
            status="processed" if row.processed_at else "pending",
            detail={
                "endpoint": _sanitize_url(row.endpoint),
                "purpose": row.purpose,
                "processed": row.processed_at is not None,
            },
        )
        for row in outbox_rows
    )
    return events


async def _email_events(db: AsyncSession, request_id: uuid.UUID) -> list[AdminRequestTimelineEvent]:
    rows = (
        await db.execute(
            select(EmailQueue)
            .where(EmailQueue.payload.contains({"request_id": str(request_id)}))
            .order_by(EmailQueue.created_at, EmailQueue.email_id)
        )
    ).scalars()
    return [
        AdminRequestTimelineEvent(
            event_id=f"pinvi_email_queue:{row.email_id}",
            occurred_at=row.created_at,
            source="pinvi_email_queue",
            title=f"email queued: {row.template}",
            status=row.status,
            detail={
                "email_id": str(row.email_id),
                "template": row.template,
                "attempts": row.attempts,
                "scheduled_at": row.scheduled_at.isoformat(),
                "sent_at": row.sent_at.isoformat() if row.sent_at else None,
                "delivered_at": row.delivered_at.isoformat() if row.delivered_at else None,
                "bounced_at": row.bounced_at.isoformat() if row.bounced_at else None,
                "has_last_error": bool(row.last_error),
            },
        )
        for row in rows
    ]


async def _upstream_system_events(
    admin_client: KorTravelMapAdminClient, request_id: uuid.UUID
) -> tuple[list[AdminRequestTimelineEvent], AdminRequestTimelineSource]:
    try:
        payload = await admin_client.list_system_logs(
            request_id=str(request_id),
            page_size=50,
        )
        records = _validate_upstream_items(payload, AdminUpstreamSystemLogRecord)
    except (KorTravelMapError, ValueError):
        return [], _source(
            "kor_travel_map_system_logs",
            [],
            status="degraded",
            message="kor_travel_map system log 조회 실패",
        )
    events = [
        AdminRequestTimelineEvent(
            event_id=f"kor_travel_map_system:{record.log_id}",
            occurred_at=record.created_at,
            source="kor_travel_map_system_logs",
            title=record.event,
            status=record.level,
            detail={
                "source": record.source,
                "message": _sanitize_text(record.message),
                "detail": _sanitize_detail(record.detail),
            },
        )
        for record in records
        if record.request_id == str(request_id)
    ]
    return events, _source("kor_travel_map_system_logs", events)


async def _upstream_api_events(
    admin_client: KorTravelMapAdminClient, request_id: uuid.UUID
) -> tuple[list[AdminRequestTimelineEvent], AdminRequestTimelineSource]:
    try:
        payload = await admin_client.list_ops_api_call_logs(
            request_id=str(request_id),
            page_size=50,
        )
        records = _validate_upstream_items(payload, AdminUpstreamApiCallLogRecord)
    except (KorTravelMapError, ValueError):
        return [], _source(
            "kor_travel_map_api_call_logs",
            [],
            status="degraded",
            message="kor_travel_map api call log 조회 실패",
        )
    events = [
        AdminRequestTimelineEvent(
            event_id=f"kor_travel_map_api:{record.log_id}",
            occurred_at=record.created_at,
            source="kor_travel_map_api_call_logs",
            title=f"{record.method} {record.path}",
            status=str(record.status_code),
            duration_ms=record.duration_ms,
            error_code=record.error_code,
            detail={"method": record.method, "path": _sanitize_url(record.path)},
        )
        for record in records
        if record.request_id == str(request_id)
    ]
    return events, _source("kor_travel_map_api_call_logs", events)


def _validate_upstream_items[T: (AdminUpstreamSystemLogRecord, AdminUpstreamApiCallLogRecord)](
    payload: dict[str, Any],
    model: type[T],
) -> list[T]:
    data = payload.get("data")
    if not isinstance(data, dict):
        raise ValueError("missing data")
    items = data.get("items")
    if not isinstance(items, list):
        raise ValueError("missing items")
    return [model.model_validate(item) for item in items]


def _source(
    name: str,
    events: list[AdminRequestTimelineEvent],
    *,
    status: Literal["ok", "degraded"] = "ok",
    message: str | None = None,
) -> AdminRequestTimelineSource:
    return AdminRequestTimelineSource(
        source=name,
        status=status,
        event_count=len(events),
        message=message,
    )


def _sanitize_url(value: str) -> str:
    value = _sanitize_text(value)
    parts = urlsplit(value)
    path = parts.path or value.split("?", 1)[0]
    query = parse_qsl(parts.query, keep_blank_values=True)
    if not query:
        return path
    masked = [
        (key, "[masked]" if _SENSITIVE_KEY_RE.search(key) else _sanitize_text(val))
        for key, val in query
    ]
    return f"{path}?{urlencode(masked)}"


def _sanitize_detail(value: Any) -> Any:
    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        for key, nested in value.items():
            key_string = str(key)
            cleaned[key_string] = (
                "[masked]" if _SENSITIVE_KEY_RE.search(key_string) else _sanitize_detail(nested)
            )
        return cleaned
    if isinstance(value, list):
        return [_sanitize_detail(item) for item in value[:20]]
    if isinstance(value, str):
        return _sanitize_text(value)
    if isinstance(value, int | float | bool) or value is None:
        return value
    return str(value)


def _sanitize_text(value: str) -> str:
    return _SENSITIVE_PAIR_RE.sub(lambda match: f"{match.group(1)}=[masked]", value)
