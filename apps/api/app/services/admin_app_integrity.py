"""Pinvi app-owned `/admin/integrity` issue source."""

from __future__ import annotations

from typing import Any

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.attachment import CuratedPlanAttachment
from app.models.curated_plan import CuratedPlanPoi, CuratedTripPlan
from app.models.data_integrity import DataIntegrityViolation
from app.models.poi import TripDayPoi
from app.models.trip import Trip
from app.schemas.admin import AdminIntegrityIssueRecord

APP_INTEGRITY_SOURCE = "pinvi_app"
MARKER_COLOR_RE = r"^P-(0[1-9]|1[0-6])$"


async def list_pinvi_app_integrity_issues(
    db: AsyncSession,
    *,
    status_filter: str | None,
    severity: str | None,
    violation_type: str | None,
    provider: str | None,
    dataset_key: str | None,
    feature_id: str | None,
    page_size: int,
) -> list[AdminIntegrityIssueRecord]:
    """Return persisted and computed Pinvi integrity issues.

    `provider`/`dataset_key` are kor-travel-map dimensions, so a request scoped by
    either one intentionally excludes Pinvi app-owned rows.
    """

    if provider or dataset_key:
        return []

    issues: list[AdminIntegrityIssueRecord] = []
    issues.extend(
        await _persisted_violations(
            db,
            status_filter=status_filter,
            severity=severity,
            violation_type=violation_type,
            feature_id=feature_id,
            limit=page_size,
        )
    )
    remaining = max(page_size - len(issues), 0)
    if remaining == 0:
        return issues

    computed = await _computed_known_violations(
        db,
        status_filter=status_filter,
        severity=severity,
        violation_type=violation_type,
        feature_id=feature_id,
        limit=remaining,
    )
    issues.extend(computed)
    issues.sort(key=lambda item: item.detected_at, reverse=True)
    return issues[:page_size]


async def _persisted_violations(
    db: AsyncSession,
    *,
    status_filter: str | None,
    severity: str | None,
    violation_type: str | None,
    feature_id: str | None,
    limit: int,
) -> list[AdminIntegrityIssueRecord]:
    if limit <= 0:
        return []

    stmt = select(DataIntegrityViolation)
    if status_filter:
        stmt = stmt.where(DataIntegrityViolation.status == status_filter)
    if severity:
        stmt = stmt.where(DataIntegrityViolation.severity == severity)
    if violation_type:
        stmt = stmt.where(DataIntegrityViolation.rule_key == violation_type)
    if feature_id:
        stmt = stmt.where(
            or_(
                DataIntegrityViolation.entity_id == feature_id,
                DataIntegrityViolation.details["feature_id"].astext == feature_id,
            )
        )
    stmt = stmt.order_by(DataIntegrityViolation.detected_at.desc()).limit(limit)
    rows = (await db.scalars(stmt)).all()
    return [_stored_violation_to_issue(row) for row in rows]


async def _computed_known_violations(
    db: AsyncSession,
    *,
    status_filter: str | None,
    severity: str | None,
    violation_type: str | None,
    feature_id: str | None,
    limit: int,
) -> list[AdminIntegrityIssueRecord]:
    if status_filter not in (None, "open") or limit <= 0:
        return []

    rules = [
        _broken_poi_feature_links,
        _duplicate_trip_day_poi_sort_orders,
        _invalid_trip_day_poi_marker_colors,
        _curated_import_source_drift,
        _active_attachment_soft_deleted_targets,
    ]
    issues: list[AdminIntegrityIssueRecord] = []
    for rule in rules:
        if len(issues) >= limit:
            break
        next_issues = await rule(
            db,
            severity=severity,
            violation_type=violation_type,
            feature_id=feature_id,
            limit=limit - len(issues),
        )
        issues.extend(next_issues)
    return issues


async def _broken_poi_feature_links(
    db: AsyncSession,
    *,
    severity: str | None,
    violation_type: str | None,
    feature_id: str | None,
    limit: int,
) -> list[AdminIntegrityIssueRecord]:
    rule_key = "broken_poi_feature_link"
    if not _computed_rule_matches(rule_key, "warning", severity, violation_type) or limit <= 0:
        return []

    stmt = (
        select(TripDayPoi)
        .where(
            TripDayPoi.deleted_at.is_(None),
            TripDayPoi.feature_id.is_not(None),
            TripDayPoi.feature_link_broken_at.is_not(None),
        )
        .order_by(TripDayPoi.feature_link_broken_at.desc())
        .limit(limit)
    )
    if feature_id:
        stmt = stmt.where(TripDayPoi.feature_id == feature_id)
    rows = (await db.scalars(stmt)).all()
    return [
        AdminIntegrityIssueRecord(
            issue_id=f"pinvi_app:{rule_key}:{row.attachment_id}",
            source=APP_INTEGRITY_SOURCE,
            violation_type=rule_key,
            severity="warning",
            message="여행 POI의 feature 링크가 끊어진 상태입니다.",
            payload={
                "trip_id": str(row.trip_id),
                "day_index": row.day_index,
                "poi_id": str(row.attachment_id),
                "feature_id": row.feature_id,
            },
            status="open",
            detected_at=row.feature_link_broken_at or row.updated_at,
            feature_id=row.feature_id,
            source_record_key=f"trip_day_pois:{row.attachment_id}",
        )
        for row in rows
    ]


async def _duplicate_trip_day_poi_sort_orders(
    db: AsyncSession,
    *,
    severity: str | None,
    violation_type: str | None,
    feature_id: str | None,
    limit: int,
) -> list[AdminIntegrityIssueRecord]:
    rule_key = "trip_day_poi_sort_order_duplicate"
    if (
        feature_id
        or not _computed_rule_matches(rule_key, "error", severity, violation_type)
        or limit <= 0
    ):
        return []

    stmt = (
        select(
            TripDayPoi.trip_id,
            TripDayPoi.day_index,
            TripDayPoi.sort_order,
            func.count(TripDayPoi.attachment_id).label("count"),
            func.max(TripDayPoi.updated_at).label("detected_at"),
        )
        .where(TripDayPoi.deleted_at.is_(None))
        .group_by(TripDayPoi.trip_id, TripDayPoi.day_index, TripDayPoi.sort_order)
        .having(func.count(TripDayPoi.attachment_id) > 1)
        .order_by(func.max(TripDayPoi.updated_at).desc())
        .limit(limit)
    )
    rows = (await db.execute(stmt)).all()
    return [
        AdminIntegrityIssueRecord(
            issue_id=(f"pinvi_app:{rule_key}:{row.trip_id}:{row.day_index}:{row.sort_order}"),
            source=APP_INTEGRITY_SOURCE,
            violation_type=rule_key,
            severity="error",
            message="같은 여행 날짜 안에서 POI sort_order가 중복되었습니다.",
            payload={
                "trip_id": str(row.trip_id),
                "day_index": row.day_index,
                "sort_order": row.sort_order,
                "count": row.count,
            },
            status="open",
            detected_at=row.detected_at,
            source_record_key=f"trip_day_pois:{row.trip_id}:{row.day_index}",
        )
        for row in rows
    ]


async def _invalid_trip_day_poi_marker_colors(
    db: AsyncSession,
    *,
    severity: str | None,
    violation_type: str | None,
    feature_id: str | None,
    limit: int,
) -> list[AdminIntegrityIssueRecord]:
    rule_key = "invalid_trip_day_poi_marker_color"
    if not _computed_rule_matches(rule_key, "warning", severity, violation_type) or limit <= 0:
        return []

    stmt = (
        select(TripDayPoi)
        .where(
            TripDayPoi.deleted_at.is_(None),
            TripDayPoi.custom_marker_color.is_not(None),
            TripDayPoi.custom_marker_color.op("!~")(MARKER_COLOR_RE),
        )
        .order_by(TripDayPoi.updated_at.desc())
        .limit(limit)
    )
    if feature_id:
        stmt = stmt.where(TripDayPoi.feature_id == feature_id)
    rows = (await db.scalars(stmt)).all()
    return [
        AdminIntegrityIssueRecord(
            issue_id=f"pinvi_app:{rule_key}:{row.attachment_id}",
            source=APP_INTEGRITY_SOURCE,
            violation_type=rule_key,
            severity="warning",
            message="여행 POI marker color가 Pinvi 팔레트 범위를 벗어났습니다.",
            payload={
                "trip_id": str(row.trip_id),
                "day_index": row.day_index,
                "poi_id": str(row.attachment_id),
                "custom_marker_color": row.custom_marker_color,
            },
            status="open",
            detected_at=row.updated_at,
            feature_id=row.feature_id,
            source_record_key=f"trip_day_pois:{row.attachment_id}",
        )
        for row in rows
    ]


async def _curated_import_source_drift(
    db: AsyncSession,
    *,
    severity: str | None,
    violation_type: str | None,
    feature_id: str | None,
    limit: int,
) -> list[AdminIntegrityIssueRecord]:
    rule_key = "curated_import_source_drift"
    if not _computed_rule_matches(rule_key, "warning", severity, violation_type) or limit <= 0:
        return []

    stmt = (
        select(CuratedPlanPoi, CuratedTripPlan)
        .join(CuratedTripPlan, CuratedTripPlan.curated_plan_id == CuratedPlanPoi.curated_plan_id)
        .where(
            CuratedTripPlan.deleted_at.is_(None),
            CuratedPlanPoi.deleted_at.is_(None),
            CuratedTripPlan.source_curated_feature_id.is_not(None),
            CuratedPlanPoi.source_curated_feature_item_id.is_not(None),
            CuratedPlanPoi.source_curated_feature_id.is_distinct_from(
                CuratedTripPlan.source_curated_feature_id
            ),
        )
        .order_by(CuratedPlanPoi.updated_at.desc())
        .limit(limit)
    )
    if feature_id:
        stmt = stmt.where(CuratedPlanPoi.feature_id == feature_id)
    rows = (await db.execute(stmt)).all()
    return [
        AdminIntegrityIssueRecord(
            issue_id=f"pinvi_app:{rule_key}:{poi.curated_poi_id}",
            source=APP_INTEGRITY_SOURCE,
            violation_type=rule_key,
            severity="warning",
            message="curated import POI의 원본 curated_feature 참조가 plan과 다릅니다.",
            payload={
                "curated_plan_id": str(plan.curated_plan_id),
                "curated_poi_id": str(poi.curated_poi_id),
                "plan_source_curated_feature_id": plan.source_curated_feature_id,
                "poi_source_curated_feature_id": poi.source_curated_feature_id,
                "source_curated_feature_item_id": poi.source_curated_feature_item_id,
            },
            status="open",
            detected_at=poi.updated_at,
            feature_id=poi.feature_id,
            source_record_key=f"curated_plan_pois:{poi.curated_poi_id}",
        )
        for poi, plan in rows
    ]


async def _active_attachment_soft_deleted_targets(
    db: AsyncSession,
    *,
    severity: str | None,
    violation_type: str | None,
    feature_id: str | None,
    limit: int,
) -> list[AdminIntegrityIssueRecord]:
    rule_key = "active_attachment_deleted_target"
    if (
        feature_id
        or not _computed_rule_matches(rule_key, "warning", severity, violation_type)
        or limit <= 0
    ):
        return []

    stmt = (
        select(
            CuratedPlanAttachment,
            Trip.deleted_at.label("trip_deleted_at"),
            TripDayPoi.deleted_at.label("trip_poi_deleted_at"),
            CuratedTripPlan.deleted_at.label("curated_plan_deleted_at"),
            CuratedPlanPoi.deleted_at.label("curated_poi_deleted_at"),
        )
        .outerjoin(Trip, CuratedPlanAttachment.trip_id == Trip.trip_id)
        .outerjoin(TripDayPoi, CuratedPlanAttachment.trip_poi_id == TripDayPoi.attachment_id)
        .outerjoin(
            CuratedTripPlan,
            CuratedPlanAttachment.curated_plan_id == CuratedTripPlan.curated_plan_id,
        )
        .outerjoin(
            CuratedPlanPoi,
            CuratedPlanAttachment.curated_poi_id == CuratedPlanPoi.curated_poi_id,
        )
        .where(
            CuratedPlanAttachment.deleted_at.is_(None),
            or_(
                and_(
                    CuratedPlanAttachment.trip_id.is_not(None),
                    CuratedPlanAttachment.trip_poi_id.is_(None),
                    CuratedPlanAttachment.curated_plan_id.is_(None),
                    CuratedPlanAttachment.curated_poi_id.is_(None),
                    Trip.deleted_at.is_not(None),
                ),
                and_(
                    CuratedPlanAttachment.trip_poi_id.is_not(None),
                    TripDayPoi.deleted_at.is_not(None),
                ),
                and_(
                    CuratedPlanAttachment.curated_plan_id.is_not(None),
                    CuratedTripPlan.deleted_at.is_not(None),
                ),
                and_(
                    CuratedPlanAttachment.curated_poi_id.is_not(None),
                    CuratedPlanPoi.deleted_at.is_not(None),
                ),
            ),
        )
        .order_by(CuratedPlanAttachment.updated_at.desc())
        .limit(limit)
    )
    rows = (await db.execute(stmt)).all()
    return [
        AdminIntegrityIssueRecord(
            issue_id=f"pinvi_app:{rule_key}:{attachment.attachment_id}",
            source=APP_INTEGRITY_SOURCE,
            violation_type=rule_key,
            severity="warning",
            message="활성 첨부가 soft-delete된 대상에 연결되어 있습니다.",
            payload={
                "attachment_id": str(attachment.attachment_id),
                "trip_id": _string_or_none(attachment.trip_id),
                "trip_poi_id": _string_or_none(attachment.trip_poi_id),
                "curated_plan_id": _string_or_none(attachment.curated_plan_id),
                "curated_poi_id": _string_or_none(attachment.curated_poi_id),
            },
            status="open",
            detected_at=attachment.updated_at,
            source_record_key=f"curated_plan_attachments:{attachment.attachment_id}",
        )
        for attachment, *_ in rows
    ]


def _stored_violation_to_issue(row: DataIntegrityViolation) -> AdminIntegrityIssueRecord:
    feature_id = _detail_string(row.details, "feature_id")
    return AdminIntegrityIssueRecord(
        issue_id=f"pinvi_app:data_integrity_violations:{row.id}",
        source=APP_INTEGRITY_SOURCE,
        violation_type=row.rule_key,
        severity=row.severity,
        message=row.message,
        payload={
            **row.details,
            "entity_kind": row.entity_kind,
            "entity_id": row.entity_id,
            "auto_fixable": row.auto_fixable,
        },
        status=row.status,
        detected_at=row.detected_at,
        feature_id=feature_id,
        source_record_key=f"{row.entity_kind}:{row.entity_id}",
        resolved_at=row.resolved_at,
    )


def _computed_rule_matches(
    rule_key: str,
    rule_severity: str,
    severity: str | None,
    violation_type: str | None,
) -> bool:
    return (severity is None or severity == rule_severity) and (
        violation_type is None or violation_type == rule_key
    )


def _detail_string(details: dict[str, Any], key: str) -> str | None:
    value = details.get(key)
    return value if isinstance(value, str) else None


def _string_or_none(value: object) -> str | None:
    return str(value) if value is not None else None
