"""Content moderation report, takedown, restore, appeal workflow."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal, cast

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.attachment import CuratedPlanAttachment
from app.models.comment import TripComment
from app.models.companion import TripCompanion
from app.models.moderation import ContentModerationAction, ContentReport
from app.models.poi import TripDayPoi
from app.models.share_link import TripShareLink
from app.models.trip import Trip
from app.schemas.moderation import (
    ContentModerationActionRecord,
    ContentModerationActionRequest,
    ContentReportAppealRequest,
    ContentReportCreateRequest,
    ContentReportListResponse,
    ContentReportRecord,
)

ContentModerationActionName = Literal["review", "hide", "takedown", "restore", "reject"]
OPEN_REVIEW_STATUSES = {"received", "reviewing", "appealed"}
APPEALABLE_STATUSES = {"hidden", "taken_down", "rejected"}


class ContentReportNotFoundError(Exception):
    """Report or target does not exist in the caller scope."""


class ContentReportPermissionError(Exception):
    """Caller cannot report or appeal the requested target."""


class ContentReportTransitionError(Exception):
    """Requested moderation transition is not allowed."""


@dataclass(frozen=True)
class ResolvedTarget:
    target_type: str
    target_id: uuid.UUID
    target_trip_id: uuid.UUID | None
    target_owner_user_id: uuid.UUID | None
    snapshot: dict[str, Any]


async def create_content_report(
    db: AsyncSession,
    *,
    reporter_user_id: uuid.UUID,
    body: ContentReportCreateRequest,
) -> ContentReport:
    target = await resolve_reportable_target(
        db,
        target_type=body.target_type,
        target_id=body.target_id,
        actor_user_id=reporter_user_id,
    )
    row = ContentReport(
        target_type=target.target_type,
        target_id=target.target_id,
        target_trip_id=target.target_trip_id,
        target_owner_user_id=target.target_owner_user_id,
        reporter_user_id=reporter_user_id,
        reason_code=body.reason_code,
        reason_text=body.reason_text.strip(),
        status="received",
        target_snapshot=target.snapshot,
        evidence=body.evidence,
    )
    db.add(row)
    await db.flush()
    await db.refresh(row)
    return row


async def list_user_content_reports(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    page_size: int,
) -> ContentReportListResponse:
    conditions = [
        or_(
            ContentReport.reporter_user_id == user_id, ContentReport.target_owner_user_id == user_id
        )
    ]
    stmt = (
        select(ContentReport)
        .where(*conditions)
        .order_by(ContentReport.created_at.desc())
        .limit(page_size)
    )
    count_stmt = select(func.count()).select_from(ContentReport).where(*conditions)
    rows = list((await db.scalars(stmt)).all())
    actions = await _load_actions_for_reports(db, rows)
    return ContentReportListResponse(
        items=[
            to_content_report_record(row, actions=actions.get(row.report_id, [])) for row in rows
        ],
        page_size=page_size,
        total=int(await db.scalar(count_stmt) or 0),
    )


async def list_content_reports(
    db: AsyncSession,
    *,
    status_filter: str | None,
    target_type: str | None,
    page_size: int,
) -> ContentReportListResponse:
    conditions: list[Any] = []
    if status_filter:
        conditions.append(ContentReport.status == status_filter)
    if target_type:
        conditions.append(ContentReport.target_type == target_type)
    stmt = (
        select(ContentReport)
        .where(*conditions)
        .order_by(ContentReport.created_at.desc())
        .limit(page_size)
    )
    count_stmt = select(func.count()).select_from(ContentReport).where(*conditions)
    rows = list((await db.scalars(stmt)).all())
    actions = await _load_actions_for_reports(db, rows)
    return ContentReportListResponse(
        items=[
            to_content_report_record(row, actions=actions.get(row.report_id, [])) for row in rows
        ],
        page_size=page_size,
        total=int(await db.scalar(count_stmt) or 0),
    )


async def get_content_report(db: AsyncSession, *, report_id: uuid.UUID) -> ContentReport:
    row = await db.get(ContentReport, report_id)
    if row is None:
        raise ContentReportNotFoundError
    return row


async def appeal_content_report(
    db: AsyncSession,
    *,
    report_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    body: ContentReportAppealRequest,
) -> ContentReport:
    row = await get_content_report(db, report_id=report_id)
    if actor_user_id not in {row.reporter_user_id, row.target_owner_user_id}:
        raise ContentReportNotFoundError
    if row.status not in APPEALABLE_STATUSES:
        raise ContentReportTransitionError(
            "hidden/taken_down/rejected 상태에서만 appeal 가능합니다."
        )
    before = _report_state(row)
    now = datetime.now(UTC)
    row.status = "appealed"
    row.appeal_summary = body.appeal_reason.strip()
    row.appealed_at = now
    await db.flush()
    await _add_action(
        db,
        row=row,
        actor_user_id=actor_user_id,
        action="appeal",
        reason=row.appeal_summary,
        before_state=before,
        after_state=_report_state(row),
    )
    await db.refresh(row)
    return row


async def moderate_content_report(
    db: AsyncSession,
    *,
    report_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    action: ContentModerationActionName,
    body: ContentModerationActionRequest,
) -> ContentReport:
    row = await get_content_report(db, report_id=report_id)
    _require_action_allowed(row, action)
    before_state = await _load_current_target_state(db, row)
    now = datetime.now(UTC)
    row.reviewer_user_id = actor_user_id
    row.resolution_summary = body.resolution_summary.strip()
    if action == "review":
        row.status = "reviewing"
        row.reviewed_at = now
    elif action == "hide":
        await _hide_target(db, row, taken_down=False, now=now)
        row.status = "hidden"
        row.actioned_at = now
    elif action == "takedown":
        await _hide_target(db, row, taken_down=True, now=now)
        row.status = "taken_down"
        row.actioned_at = now
    elif action == "restore":
        await _restore_target(db, row)
        row.status = "restored"
        row.restored_at = now
    elif action == "reject":
        row.status = "rejected"
        row.actioned_at = now
    await db.flush()
    await _add_action(
        db,
        row=row,
        actor_user_id=actor_user_id,
        action=action,
        reason=body.resolution_summary,
        before_state=before_state,
        after_state=await _load_current_target_state(db, row, allow_missing=True),
    )
    await db.refresh(row)
    return row


async def resolve_reportable_target(
    db: AsyncSession,
    *,
    target_type: str,
    target_id: uuid.UUID,
    actor_user_id: uuid.UUID,
) -> ResolvedTarget:
    if target_type == "trip":
        trip = await db.scalar(
            select(Trip).where(Trip.trip_id == target_id, Trip.deleted_at.is_(None))
        )
        if trip is None:
            raise ContentReportNotFoundError
        if not await _can_access_trip(db, trip=trip, user_id=actor_user_id):
            raise ContentReportPermissionError
        return ResolvedTarget(
            target_type=target_type,
            target_id=trip.trip_id,
            target_trip_id=trip.trip_id,
            target_owner_user_id=trip.owner_user_id,
            snapshot=_trip_state(trip),
        )

    if target_type == "comment":
        comment = await db.scalar(
            select(TripComment).where(
                TripComment.comment_id == target_id,
                TripComment.deleted_at.is_(None),
            )
        )
        if comment is None:
            raise ContentReportNotFoundError
        trip = await _get_active_trip(db, comment.trip_id)
        if not await _can_access_trip(db, trip=trip, user_id=actor_user_id):
            raise ContentReportPermissionError
        return ResolvedTarget(
            target_type=target_type,
            target_id=comment.comment_id,
            target_trip_id=comment.trip_id,
            target_owner_user_id=comment.author_user_id or trip.owner_user_id,
            snapshot=_comment_state(comment),
        )

    if target_type == "attachment":
        attachment = await db.scalar(
            select(CuratedPlanAttachment).where(
                CuratedPlanAttachment.attachment_id == target_id,
                CuratedPlanAttachment.deleted_at.is_(None),
            )
        )
        if attachment is None:
            raise ContentReportNotFoundError
        trip = await _trip_for_attachment(db, attachment)
        if trip is None:
            if attachment.uploaded_by_user_id != actor_user_id:
                raise ContentReportPermissionError
        elif not await _can_access_trip(db, trip=trip, user_id=actor_user_id):
            raise ContentReportPermissionError
        return ResolvedTarget(
            target_type=target_type,
            target_id=attachment.attachment_id,
            target_trip_id=None if trip is None else trip.trip_id,
            target_owner_user_id=attachment.uploaded_by_user_id,
            snapshot=_attachment_state(attachment),
        )

    if target_type == "share_link":
        share = await db.get(TripShareLink, target_id)
        if share is None or share.revoked_at is not None:
            raise ContentReportNotFoundError
        trip = await _get_active_trip(db, share.trip_id)
        if not await _can_manage_trip(db, trip=trip, user_id=actor_user_id):
            raise ContentReportPermissionError
        return ResolvedTarget(
            target_type=target_type,
            target_id=share.share_id,
            target_trip_id=share.trip_id,
            target_owner_user_id=share.created_by_user_id,
            snapshot=_share_link_state(share),
        )

    raise ContentReportNotFoundError


def to_content_report_record(
    row: ContentReport,
    *,
    actions: list[ContentModerationAction] | None = None,
) -> ContentReportRecord:
    return ContentReportRecord(
        report_id=row.report_id,
        target_type=row.target_type,
        target_id=row.target_id,
        target_trip_id=row.target_trip_id,
        target_owner_user_id=row.target_owner_user_id,
        reporter_user_id=row.reporter_user_id,
        reason_code=row.reason_code,
        reason_text=row.reason_text,
        status=row.status,
        target_snapshot=row.target_snapshot or {},
        evidence=row.evidence or {},
        reviewer_user_id=row.reviewer_user_id,
        resolution_summary=row.resolution_summary,
        appeal_summary=row.appeal_summary,
        reviewed_at=row.reviewed_at,
        actioned_at=row.actioned_at,
        appealed_at=row.appealed_at,
        restored_at=row.restored_at,
        next_actions=_next_actions(row),
        actions=[_to_action_record(action) for action in actions or []],
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _to_action_record(row: ContentModerationAction) -> ContentModerationActionRecord:
    return ContentModerationActionRecord(
        action_id=row.action_id,
        report_id=row.report_id,
        actor_user_id=row.actor_user_id,
        action=row.action,
        action_reason=row.action_reason,
        before_state=row.before_state or {},
        after_state=row.after_state or {},
        created_at=row.created_at,
    )


def _next_actions(row: ContentReport) -> list[str]:
    if row.status == "received":
        return ["review", "hide", "takedown", "reject"]
    if row.status == "reviewing":
        return ["hide", "takedown", "reject"]
    if row.status == "appealed":
        return ["restore", "takedown", "reject"]
    if row.status in {"hidden", "taken_down"}:
        return ["restore"]
    return []


async def _load_actions_for_reports(
    db: AsyncSession, rows: list[ContentReport]
) -> dict[uuid.UUID, list[ContentModerationAction]]:
    if not rows:
        return {}
    report_ids = [row.report_id for row in rows]
    result = await db.execute(
        select(ContentModerationAction)
        .where(ContentModerationAction.report_id.in_(report_ids))
        .order_by(ContentModerationAction.created_at.asc(), ContentModerationAction.action_id.asc())
    )
    grouped: dict[uuid.UUID, list[ContentModerationAction]] = {
        report_id: [] for report_id in report_ids
    }
    for action in result.scalars():
        grouped.setdefault(action.report_id, []).append(action)
    return grouped


async def _add_action(
    db: AsyncSession,
    *,
    row: ContentReport,
    actor_user_id: uuid.UUID | None,
    action: str,
    reason: str,
    before_state: dict[str, Any],
    after_state: dict[str, Any],
) -> None:
    db.add(
        ContentModerationAction(
            report_id=row.report_id,
            actor_user_id=actor_user_id,
            action=action,
            action_reason=reason.strip(),
            before_state=before_state,
            after_state=after_state,
        )
    )
    await db.flush()


def _require_action_allowed(row: ContentReport, action: ContentModerationActionName) -> None:
    if action == "review" and row.status in {"received", "appealed"}:
        return
    if action in {"hide", "takedown"} and row.status in OPEN_REVIEW_STATUSES | {"restored"}:
        return
    if action == "restore" and row.status in {"hidden", "taken_down", "appealed"}:
        return
    if action == "reject" and row.status in OPEN_REVIEW_STATUSES:
        return
    raise ContentReportTransitionError(f"{row.status} 상태에서는 {action} 조치를 할 수 없습니다.")


async def _get_active_trip(db: AsyncSession, trip_id: uuid.UUID) -> Trip:
    trip = await db.scalar(select(Trip).where(Trip.trip_id == trip_id, Trip.deleted_at.is_(None)))
    if trip is None:
        raise ContentReportNotFoundError
    return trip


async def _can_access_trip(db: AsyncSession, *, trip: Trip, user_id: uuid.UUID) -> bool:
    if trip.owner_user_id == user_id or trip.visibility == "public":
        return True
    role = await db.scalar(
        select(TripCompanion.role).where(
            TripCompanion.trip_id == trip.trip_id,
            TripCompanion.user_id == user_id,
        )
    )
    return role in {"co_owner", "editor", "viewer"}


async def _can_manage_trip(db: AsyncSession, *, trip: Trip, user_id: uuid.UUID) -> bool:
    if trip.owner_user_id == user_id:
        return True
    role = await db.scalar(
        select(TripCompanion.role).where(
            TripCompanion.trip_id == trip.trip_id,
            TripCompanion.user_id == user_id,
        )
    )
    return role == "co_owner"


async def _trip_for_attachment(db: AsyncSession, attachment: CuratedPlanAttachment) -> Trip | None:
    if attachment.trip_id is not None:
        trip = await db.scalar(
            select(Trip).where(Trip.trip_id == attachment.trip_id, Trip.deleted_at.is_(None))
        )
        return trip
    if attachment.trip_poi_id is not None:
        poi_trip_id = await db.scalar(
            select(TripDayPoi.trip_id).where(
                TripDayPoi.attachment_id == attachment.trip_poi_id,
                TripDayPoi.deleted_at.is_(None),
            )
        )
        if poi_trip_id is not None:
            trip = await db.scalar(
                select(Trip).where(Trip.trip_id == poi_trip_id, Trip.deleted_at.is_(None))
            )
            return cast(Trip | None, trip)
    return None


async def _load_current_target_state(
    db: AsyncSession,
    row: ContentReport,
    *,
    allow_missing: bool = False,
) -> dict[str, Any]:
    target = await _load_target_model(db, row)
    if target is None:
        if allow_missing:
            return {
                "target_type": row.target_type,
                "target_id": str(row.target_id),
                "missing": True,
            }
        raise ContentReportNotFoundError
    if isinstance(target, Trip):
        return _trip_state(target)
    if isinstance(target, TripComment):
        return _comment_state(target)
    if isinstance(target, CuratedPlanAttachment):
        return _attachment_state(target)
    if isinstance(target, TripShareLink):
        return _share_link_state(target)
    raise ContentReportNotFoundError


async def _load_target_model(
    db: AsyncSession,
    row: ContentReport,
) -> Trip | TripComment | CuratedPlanAttachment | TripShareLink | None:
    if row.target_type == "trip":
        return await db.get(Trip, row.target_id)
    if row.target_type == "comment":
        return await db.get(TripComment, row.target_id)
    if row.target_type == "attachment":
        return await db.get(CuratedPlanAttachment, row.target_id)
    if row.target_type == "share_link":
        return await db.get(TripShareLink, row.target_id)
    return None


async def _hide_target(
    db: AsyncSession,
    row: ContentReport,
    *,
    taken_down: bool,
    now: datetime,
) -> None:
    target = await _load_target_model(db, row)
    if target is None:
        raise ContentReportNotFoundError
    if isinstance(target, Trip):
        if taken_down:
            target.status = "archived"
            target.deleted_at = now
        target.visibility = "private"
        target.version += 1
    elif isinstance(target, TripComment):
        target.deleted_at = target.deleted_at or now
    elif isinstance(target, CuratedPlanAttachment):
        target.deleted_at = target.deleted_at or now
    elif isinstance(target, TripShareLink):
        target.revoked_at = target.revoked_at or now
    else:
        raise ContentReportNotFoundError
    await db.flush()


async def _restore_target(db: AsyncSession, row: ContentReport) -> None:
    target = await _load_target_model(db, row)
    if target is None:
        raise ContentReportNotFoundError
    snapshot = row.target_snapshot or {}
    if isinstance(target, Trip):
        target.deleted_at = None
        target.status = str(snapshot.get("status") or target.status or "draft")
        target.visibility = str(snapshot.get("visibility") or target.visibility or "private")
        target.version += 1
    elif isinstance(target, TripComment):
        target.deleted_at = None
    elif isinstance(target, CuratedPlanAttachment):
        target.deleted_at = None
    elif isinstance(target, TripShareLink):
        target.revoked_at = None
    else:
        raise ContentReportNotFoundError
    await db.flush()


def _report_state(row: ContentReport) -> dict[str, Any]:
    return {
        "report_id": str(row.report_id),
        "status": row.status,
        "target_type": row.target_type,
        "target_id": str(row.target_id),
        "target_owner_user_id": (
            str(row.target_owner_user_id) if row.target_owner_user_id else None
        ),
        "reporter_user_id": str(row.reporter_user_id) if row.reporter_user_id else None,
        "resolution_summary": row.resolution_summary,
        "appeal_summary": row.appeal_summary,
    }


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _trip_state(trip: Trip) -> dict[str, Any]:
    return {
        "target_type": "trip",
        "target_id": str(trip.trip_id),
        "owner_user_id": str(trip.owner_user_id),
        "title": trip.title,
        "visibility": trip.visibility,
        "status": trip.status,
        "version": trip.version,
        "deleted_at": _iso(trip.deleted_at),
    }


def _comment_state(comment: TripComment) -> dict[str, Any]:
    return {
        "target_type": "comment",
        "target_id": str(comment.comment_id),
        "trip_id": str(comment.trip_id),
        "author_user_id": str(comment.author_user_id) if comment.author_user_id else None,
        "body": comment.body[:500],
        "comment_target_type": comment.target_type,
        "comment_target_id": str(comment.target_id) if comment.target_id else None,
        "day_index": comment.day_index,
        "deleted_at": _iso(comment.deleted_at),
    }


def _attachment_state(attachment: CuratedPlanAttachment) -> dict[str, Any]:
    return {
        "target_type": "attachment",
        "target_id": str(attachment.attachment_id),
        "trip_id": str(attachment.trip_id) if attachment.trip_id else None,
        "trip_day_index": attachment.trip_day_index,
        "trip_poi_id": str(attachment.trip_poi_id) if attachment.trip_poi_id else None,
        "uploaded_by_user_id": str(attachment.uploaded_by_user_id),
        "original_filename": attachment.original_filename,
        "content_type": attachment.content_type,
        "byte_size": attachment.byte_size,
        "role": attachment.role,
        "deleted_at": _iso(attachment.deleted_at),
    }


def _share_link_state(share: TripShareLink) -> dict[str, Any]:
    return {
        "target_type": "share_link",
        "target_id": str(share.share_id),
        "trip_id": str(share.trip_id),
        "created_by_user_id": str(share.created_by_user_id),
        "visibility": share.visibility,
        "expires_at": _iso(share.expires_at),
        "revoked_at": _iso(share.revoked_at),
        "last_used_at": _iso(share.last_used_at),
    }
