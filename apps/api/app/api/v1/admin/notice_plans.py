"""`/admin/notice-plans/*` — 큐레이션(curated) 플랜/POI 첨부 관리 (T-105 #1·#2).

`docs/api/storage.md` §5.3(plan 첨부) / §5.4(POI 첨부). API path/field 는 `/notice-plans`
호환을 유지하고 내부 DB 는 curated-trip 정본(ADR-029)을 쓴다. mutate(POST/DELETE)는
admin_audit chain 에 기록한다. DELETE 는 soft delete 만 — RustFS object 는 보존(§5.6).
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any, NoReturn

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import DbSession
from app.core.rbac import require_role
from app.models.user import User
from app.schemas.envelope import Envelope
from app.schemas.storage import AttachmentCreate, AttachmentResponse
from app.services.admin_audit import append_admin_audit
from app.services.admin_curated_attachment import (
    CuratedAttachmentLimitError,
    CuratedAttachmentNotFoundError,
    CuratedPlanNotFoundError,
    create_curated_attachment,
    delete_curated_attachment,
    ensure_plan,
    ensure_poi,
    list_curated_attachments,
)

router = APIRouter(prefix="/admin/notice-plans", tags=["admin"])

AdminDep = Annotated[User, Depends(require_role("admin"))]


def _to_response(attachment) -> AttachmentResponse:  # type: ignore[no-untyped-def]
    return AttachmentResponse(
        attachment_id=attachment.attachment_id,
        trip_id=attachment.trip_id,
        trip_poi_id=attachment.trip_poi_id,
        curated_plan_id=attachment.curated_plan_id,
        curated_poi_id=attachment.curated_poi_id,
        notice_plan_id=attachment.notice_plan_id,
        notice_poi_id=attachment.notice_poi_id,
        source_attachment_id=attachment.source_attachment_id,
        bucket=attachment.bucket,
        storage_key=attachment.storage_key,
        original_filename=attachment.original_filename,
        content_type=attachment.content_type,
        byte_size=attachment.byte_size,
        public_url=attachment.public_url,
        role=attachment.role,
        description=attachment.description,
        sort_order=attachment.sort_order,
        created_at=attachment.created_at,
        updated_at=attachment.updated_at,
    )


def _parse_request_id(value: str | None) -> uuid.UUID:
    if value is None:
        return uuid.uuid4()
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "VALIDATION_ERROR",
                "message": "X-Request-Id 형식이 올바르지 않습니다.",
            },
        ) from exc


def _raise_not_found(
    exc: CuratedPlanNotFoundError | CuratedAttachmentNotFoundError,
) -> NoReturn:
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={"code": exc.code, "message": str(exc)},
    ) from exc


def _raise_limit(exc: CuratedAttachmentLimitError) -> NoReturn:
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={"code": exc.code, "message": str(exc)},
    ) from exc


async def _audit(
    db: AsyncSession,
    admin: User,
    request: Request,
    x_request_id: str | None,
    *,
    action: str,
    resource_id: str,
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
) -> None:
    await append_admin_audit(
        db,
        actor_user_id=admin.user_id,
        action=action,
        resource_type="curated_plan_attachment",
        resource_id=resource_id,
        before_state=before,
        after_state=after,
        access_reason=None,
        target_pii_fields=None,
        ip_hash_input=request.client.host if request.client else "",
        user_agent=request.headers.get("user-agent"),
        request_id=_parse_request_id(x_request_id),
    )


# ── §5.3 curated plan 첨부 ─────────────────────────────────────────────────


@router.get("/{plan_id}/attachments", response_model=Envelope[list[AttachmentResponse]])
async def list_plan_attachments(
    plan_id: uuid.UUID, _admin: AdminDep, db: DbSession
) -> Envelope[list[AttachmentResponse]]:
    try:
        await ensure_plan(db, curated_plan_id=plan_id)
    except CuratedPlanNotFoundError as exc:
        _raise_not_found(exc)
    rows = await list_curated_attachments(db, curated_plan_id=plan_id)
    return Envelope.of([_to_response(r) for r in rows])


@router.post(
    "/{plan_id}/attachments",
    status_code=status.HTTP_201_CREATED,
    response_model=Envelope[AttachmentResponse],
)
async def create_plan_attachment(
    plan_id: uuid.UUID,
    body: AttachmentCreate,
    admin: AdminDep,
    db: DbSession,
    request: Request,
    x_request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
) -> Envelope[AttachmentResponse]:
    try:
        await ensure_plan(db, curated_plan_id=plan_id)
        attachment = await create_curated_attachment(
            db,
            uploaded_by_user_id=admin.user_id,
            curated_plan_id=plan_id,
            payload=body.model_dump(),
        )
    except CuratedPlanNotFoundError as exc:
        _raise_not_found(exc)
    except CuratedAttachmentLimitError as exc:
        _raise_limit(exc)
    await _audit(
        db,
        admin,
        request,
        x_request_id,
        action="curated_plan.attachment_added",
        resource_id=str(attachment.attachment_id),
        before=None,
        after={"curated_plan_id": str(plan_id), "storage_key": attachment.storage_key},
    )
    await db.commit()
    return Envelope.of(_to_response(attachment))


@router.delete("/{plan_id}/attachments/{attachment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_plan_attachment(
    plan_id: uuid.UUID,
    attachment_id: uuid.UUID,
    admin: AdminDep,
    db: DbSession,
    request: Request,
    x_request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
) -> None:
    try:
        attachment = await delete_curated_attachment(
            db, attachment_id=attachment_id, curated_plan_id=plan_id
        )
    except CuratedAttachmentNotFoundError as exc:
        _raise_not_found(exc)
    await _audit(
        db,
        admin,
        request,
        x_request_id,
        action="curated_plan.attachment_deleted",
        resource_id=str(attachment_id),
        before={"curated_plan_id": str(plan_id), "storage_key": attachment.storage_key},
        after=None,
    )
    await db.commit()


# ── §5.4 curated POI 첨부 ──────────────────────────────────────────────────


@router.get(
    "/{plan_id}/pois/{poi_id}/attachments",
    response_model=Envelope[list[AttachmentResponse]],
)
async def list_poi_attachments(
    plan_id: uuid.UUID, poi_id: uuid.UUID, _admin: AdminDep, db: DbSession
) -> Envelope[list[AttachmentResponse]]:
    try:
        await ensure_poi(db, curated_plan_id=plan_id, curated_poi_id=poi_id)
    except CuratedPlanNotFoundError as exc:
        _raise_not_found(exc)
    rows = await list_curated_attachments(db, curated_poi_id=poi_id)
    return Envelope.of([_to_response(r) for r in rows])


@router.post(
    "/{plan_id}/pois/{poi_id}/attachments",
    status_code=status.HTTP_201_CREATED,
    response_model=Envelope[AttachmentResponse],
)
async def create_poi_attachment(
    plan_id: uuid.UUID,
    poi_id: uuid.UUID,
    body: AttachmentCreate,
    admin: AdminDep,
    db: DbSession,
    request: Request,
    x_request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
) -> Envelope[AttachmentResponse]:
    try:
        await ensure_poi(db, curated_plan_id=plan_id, curated_poi_id=poi_id)
        attachment = await create_curated_attachment(
            db,
            uploaded_by_user_id=admin.user_id,
            curated_poi_id=poi_id,
            payload=body.model_dump(),
        )
    except CuratedPlanNotFoundError as exc:
        _raise_not_found(exc)
    except CuratedAttachmentLimitError as exc:
        _raise_limit(exc)
    await _audit(
        db,
        admin,
        request,
        x_request_id,
        action="curated_poi.attachment_added",
        resource_id=str(attachment.attachment_id),
        before=None,
        after={"curated_poi_id": str(poi_id), "storage_key": attachment.storage_key},
    )
    await db.commit()
    return Envelope.of(_to_response(attachment))


@router.delete(
    "/{plan_id}/pois/{poi_id}/attachments/{attachment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_poi_attachment(
    plan_id: uuid.UUID,
    poi_id: uuid.UUID,
    attachment_id: uuid.UUID,
    admin: AdminDep,
    db: DbSession,
    request: Request,
    x_request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
) -> None:
    try:
        attachment = await delete_curated_attachment(
            db, attachment_id=attachment_id, curated_poi_id=poi_id
        )
    except CuratedAttachmentNotFoundError as exc:
        _raise_not_found(exc)
    await _audit(
        db,
        admin,
        request,
        x_request_id,
        action="curated_poi.attachment_deleted",
        resource_id=str(attachment_id),
        before={"curated_poi_id": str(poi_id), "storage_key": attachment.storage_key},
        after=None,
    )
    await db.commit()
