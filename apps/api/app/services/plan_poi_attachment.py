from __future__ import annotations

from collections.abc import Iterable
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from app.models.mixins import kst_now
from app.models.trip import NoticePlan, NoticePoi, PlanPoiAttachment, Trip, TripPoi
from app.models.user import User
from app.schemas.attachment import (
    PlanPoiAttachmentCreateRequest,
    PlanPoiAttachmentResponse,
)


class AttachmentError(Exception):
    pass


class AttachmentNotFoundError(AttachmentError):
    pass


class AttachmentAccessDeniedError(AttachmentError):
    pass


def list_trip_attachments(
    db: Session,
    *,
    current_user: User,
    trip_id: UUID,
) -> list[PlanPoiAttachment]:
    trip = _trip_for_user(db, current_user=current_user, trip_id=trip_id)
    return _list_attachments(db, PlanPoiAttachment.trip_id == trip.id)


def create_trip_attachment(
    db: Session,
    *,
    current_user: User,
    trip_id: UUID,
    payload: PlanPoiAttachmentCreateRequest,
) -> PlanPoiAttachment:
    trip = _trip_for_user(db, current_user=current_user, trip_id=trip_id)
    attachment = _attachment_from_payload(
        payload,
        uploaded_by_user_id=current_user.id,
        trip_id=trip.id,
    )
    db.add(attachment)
    db.flush()
    return attachment


def delete_trip_attachment(
    db: Session,
    *,
    current_user: User,
    trip_id: UUID,
    attachment_id: UUID,
) -> None:
    trip = _trip_for_user(db, current_user=current_user, trip_id=trip_id)
    attachment = _attachment_or_not_found(
        db,
        attachment_id=attachment_id,
        trip_id=trip.id,
    )
    _soft_delete(attachment)


def list_trip_poi_attachments(
    db: Session,
    *,
    current_user: User,
    trip_id: UUID,
    poi_id: UUID,
) -> list[PlanPoiAttachment]:
    poi = _trip_poi_for_user(db, current_user=current_user, trip_id=trip_id, poi_id=poi_id)
    return _list_attachments(db, PlanPoiAttachment.trip_poi_id == poi.id)


def create_trip_poi_attachment(
    db: Session,
    *,
    current_user: User,
    trip_id: UUID,
    poi_id: UUID,
    payload: PlanPoiAttachmentCreateRequest,
) -> PlanPoiAttachment:
    poi = _trip_poi_for_user(db, current_user=current_user, trip_id=trip_id, poi_id=poi_id)
    attachment = _attachment_from_payload(
        payload,
        uploaded_by_user_id=current_user.id,
        trip_poi_id=poi.id,
    )
    db.add(attachment)
    db.flush()
    return attachment


def delete_trip_poi_attachment(
    db: Session,
    *,
    current_user: User,
    trip_id: UUID,
    poi_id: UUID,
    attachment_id: UUID,
) -> None:
    poi = _trip_poi_for_user(db, current_user=current_user, trip_id=trip_id, poi_id=poi_id)
    attachment = _attachment_or_not_found(
        db,
        attachment_id=attachment_id,
        trip_poi_id=poi.id,
    )
    _soft_delete(attachment)


def list_notice_plan_attachments(db: Session, *, plan_id: UUID) -> list[PlanPoiAttachment]:
    plan = _notice_plan_or_not_found(db, plan_id)
    return _list_attachments(db, PlanPoiAttachment.notice_plan_id == plan.id)


def create_notice_plan_attachment(
    db: Session,
    *,
    current_user: User,
    plan_id: UUID,
    payload: PlanPoiAttachmentCreateRequest,
) -> PlanPoiAttachment:
    plan = _notice_plan_or_not_found(db, plan_id)
    attachment = _attachment_from_payload(
        payload,
        uploaded_by_user_id=current_user.id,
        notice_plan_id=plan.id,
    )
    db.add(attachment)
    db.flush()
    return attachment


def delete_notice_plan_attachment(
    db: Session,
    *,
    plan_id: UUID,
    attachment_id: UUID,
) -> None:
    plan = _notice_plan_or_not_found(db, plan_id)
    attachment = _attachment_or_not_found(
        db,
        attachment_id=attachment_id,
        notice_plan_id=plan.id,
    )
    _soft_delete(attachment)


def list_notice_poi_attachments(
    db: Session,
    *,
    plan_id: UUID,
    poi_id: UUID,
) -> list[PlanPoiAttachment]:
    poi = _notice_poi_or_not_found(db, plan_id=plan_id, poi_id=poi_id)
    return _list_attachments(db, PlanPoiAttachment.notice_poi_id == poi.id)


def create_notice_poi_attachment(
    db: Session,
    *,
    current_user: User,
    plan_id: UUID,
    poi_id: UUID,
    payload: PlanPoiAttachmentCreateRequest,
) -> PlanPoiAttachment:
    poi = _notice_poi_or_not_found(db, plan_id=plan_id, poi_id=poi_id)
    attachment = _attachment_from_payload(
        payload,
        uploaded_by_user_id=current_user.id,
        notice_poi_id=poi.id,
    )
    db.add(attachment)
    db.flush()
    return attachment


def delete_notice_poi_attachment(
    db: Session,
    *,
    plan_id: UUID,
    poi_id: UUID,
    attachment_id: UUID,
) -> None:
    poi = _notice_poi_or_not_found(db, plan_id=plan_id, poi_id=poi_id)
    attachment = _attachment_or_not_found(
        db,
        attachment_id=attachment_id,
        notice_poi_id=poi.id,
    )
    _soft_delete(attachment)


def attachments_by_notice_plan(
    db: Session,
    plan_ids: Iterable[UUID],
) -> dict[UUID, list[PlanPoiAttachment]]:
    ids = list(plan_ids)
    if not ids:
        return {}
    attachments = db.scalars(
        select(PlanPoiAttachment)
        .where(
            PlanPoiAttachment.notice_plan_id.in_(ids),
            PlanPoiAttachment.deleted_at.is_(None),
        )
        .order_by(PlanPoiAttachment.sort_order.asc(), PlanPoiAttachment.created_at.asc())
    ).all()
    grouped: dict[UUID, list[PlanPoiAttachment]] = {}
    for attachment in attachments:
        if attachment.notice_plan_id is not None:
            grouped.setdefault(attachment.notice_plan_id, []).append(attachment)
    return grouped


def attachments_by_notice_poi(
    db: Session,
    poi_ids: Iterable[UUID],
) -> dict[UUID, list[PlanPoiAttachment]]:
    ids = list(poi_ids)
    if not ids:
        return {}
    attachments = db.scalars(
        select(PlanPoiAttachment)
        .where(
            PlanPoiAttachment.notice_poi_id.in_(ids),
            PlanPoiAttachment.deleted_at.is_(None),
        )
        .order_by(PlanPoiAttachment.sort_order.asc(), PlanPoiAttachment.created_at.asc())
    ).all()
    grouped: dict[UUID, list[PlanPoiAttachment]] = {}
    for attachment in attachments:
        if attachment.notice_poi_id is not None:
            grouped.setdefault(attachment.notice_poi_id, []).append(attachment)
    return grouped


def copy_notice_attachments_to_trip(
    db: Session,
    *,
    current_user: User,
    notice_plan_id: UUID,
    target_trip_id: UUID,
    notice_poi_to_trip_poi: dict[UUID, UUID],
) -> None:
    plan_attachments = _list_attachments(
        db,
        PlanPoiAttachment.notice_plan_id == notice_plan_id,
    )
    for source in plan_attachments:
        db.add(
            _clone_attachment(
                source,
                uploaded_by_user_id=current_user.id,
                trip_id=target_trip_id,
            )
        )

    if not notice_poi_to_trip_poi:
        return
    poi_attachments = db.scalars(
        select(PlanPoiAttachment)
        .where(
            PlanPoiAttachment.notice_poi_id.in_(notice_poi_to_trip_poi.keys()),
            PlanPoiAttachment.deleted_at.is_(None),
        )
        .order_by(PlanPoiAttachment.notice_poi_id.asc(), PlanPoiAttachment.sort_order.asc())
    ).all()
    for source in poi_attachments:
        if source.notice_poi_id is None:
            continue
        target_poi_id = notice_poi_to_trip_poi.get(source.notice_poi_id)
        if target_poi_id is None:
            continue
        db.add(
            _clone_attachment(
                source,
                uploaded_by_user_id=current_user.id,
                trip_poi_id=target_poi_id,
            )
        )


def to_attachment_response(attachment: PlanPoiAttachment) -> PlanPoiAttachmentResponse:
    return PlanPoiAttachmentResponse(
        id=attachment.id,
        trip_id=attachment.trip_id,
        trip_poi_id=attachment.trip_poi_id,
        notice_plan_id=attachment.notice_plan_id,
        notice_poi_id=attachment.notice_poi_id,
        source_attachment_id=attachment.source_attachment_id,
        bucket=attachment.bucket,
        storage_key=attachment.storage_key,
        original_filename=attachment.original_filename,
        content_type=attachment.content_type,
        byte_size=attachment.byte_size,
        public_url=attachment.public_url,
        checksum_sha256=attachment.checksum_sha256,
        role=attachment.role,
        description=attachment.description,
        sort_order=attachment.sort_order,
        uploaded_by_user_id=attachment.uploaded_by_user_id,
        created_at=attachment.created_at,
        updated_at=attachment.updated_at,
    )


def _trip_for_user(db: Session, *, current_user: User, trip_id: UUID) -> Trip:
    trip = db.get(Trip, trip_id)
    if trip is None or trip.deleted_at is not None:
        raise AttachmentNotFoundError("여행을 찾을 수 없다.")
    if (
        trip.user_id != current_user.id
        and trip.leader_id != current_user.id
        and not current_user.is_admin
    ):
        raise AttachmentAccessDeniedError("해당 여행의 첨부 파일을 수정할 권한이 없다.")
    return trip


def _trip_poi_for_user(
    db: Session,
    *,
    current_user: User,
    trip_id: UUID,
    poi_id: UUID,
) -> TripPoi:
    _trip_for_user(db, current_user=current_user, trip_id=trip_id)
    poi = db.get(TripPoi, poi_id)
    if poi is None or poi.trip_id != trip_id:
        raise AttachmentNotFoundError("여행 POI를 찾을 수 없다.")
    return poi


def _notice_plan_or_not_found(db: Session, plan_id: UUID) -> NoticePlan:
    plan = db.get(NoticePlan, plan_id)
    if plan is None or plan.deleted_at is not None:
        raise AttachmentNotFoundError("공지 계획을 찾을 수 없다.")
    return plan


def _notice_poi_or_not_found(db: Session, *, plan_id: UUID, poi_id: UUID) -> NoticePoi:
    _notice_plan_or_not_found(db, plan_id)
    poi = db.get(NoticePoi, poi_id)
    if poi is None or poi.notice_plan_id != plan_id or poi.deleted_at is not None:
        raise AttachmentNotFoundError("공지 POI를 찾을 수 없다.")
    return poi


def _list_attachments(
    db: Session,
    *criteria: ColumnElement[bool],
) -> list[PlanPoiAttachment]:
    return list(
        db.scalars(
            select(PlanPoiAttachment)
            .where(*criteria, PlanPoiAttachment.deleted_at.is_(None))
            .order_by(PlanPoiAttachment.sort_order.asc(), PlanPoiAttachment.created_at.asc())
        ).all()
    )


def _attachment_or_not_found(
    db: Session,
    *,
    attachment_id: UUID,
    **criteria: UUID,
) -> PlanPoiAttachment:
    query = select(PlanPoiAttachment).where(
        PlanPoiAttachment.id == attachment_id,
        PlanPoiAttachment.deleted_at.is_(None),
    )
    for field_name, expected_value in criteria.items():
        query = query.where(getattr(PlanPoiAttachment, field_name) == expected_value)
    attachment = db.scalar(query)
    if attachment is None:
        raise AttachmentNotFoundError("첨부 파일을 찾을 수 없다.")
    return attachment


def _attachment_from_payload(
    payload: PlanPoiAttachmentCreateRequest,
    *,
    uploaded_by_user_id: UUID,
    trip_id: UUID | None = None,
    trip_poi_id: UUID | None = None,
    notice_plan_id: UUID | None = None,
    notice_poi_id: UUID | None = None,
) -> PlanPoiAttachment:
    return PlanPoiAttachment(
        trip_id=trip_id,
        trip_poi_id=trip_poi_id,
        notice_plan_id=notice_plan_id,
        notice_poi_id=notice_poi_id,
        bucket=payload.bucket,
        storage_key=payload.storage_key,
        original_filename=payload.original_filename,
        content_type=payload.content_type,
        byte_size=payload.byte_size,
        public_url=payload.public_url,
        checksum_sha256=payload.checksum_sha256,
        role=payload.role,
        description=payload.description,
        sort_order=payload.sort_order,
        uploaded_by_user_id=uploaded_by_user_id,
    )


def _clone_attachment(
    source: PlanPoiAttachment,
    *,
    uploaded_by_user_id: UUID,
    trip_id: UUID | None = None,
    trip_poi_id: UUID | None = None,
) -> PlanPoiAttachment:
    return PlanPoiAttachment(
        trip_id=trip_id,
        trip_poi_id=trip_poi_id,
        source_attachment_id=source.id,
        bucket=source.bucket,
        storage_key=source.storage_key,
        original_filename=source.original_filename,
        content_type=source.content_type,
        byte_size=source.byte_size,
        public_url=source.public_url,
        checksum_sha256=source.checksum_sha256,
        role=source.role,
        description=source.description,
        sort_order=source.sort_order,
        uploaded_by_user_id=uploaded_by_user_id,
    )


def _soft_delete(attachment: PlanPoiAttachment) -> None:
    now = kst_now()
    attachment.deleted_at = now
    attachment.updated_at = now
