"""`/admin/notice-plans/*` — 큐레이션(curated) 플랜/POI 첨부 관리 (T-105 #1·#2).

`docs/api/storage.md` §5.3(plan 첨부) / §5.4(POI 첨부). API path/field 는 `/notice-plans`
호환을 유지하고 내부 DB 는 curated-trip 정본(ADR-029)을 쓴다. mutate(POST/DELETE)는
admin_audit chain 에 기록한다. DELETE 는 soft delete 만 — RustFS object 는 보존(§5.6).
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any, NoReturn

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.kor_travel_map import (
    KorTravelMapError,
    KorTravelMapFeatureNotFound,
)
from app.clients.kor_travel_map_admin import KorTravelMapAdminClientDep
from app.core.deps import DbSession
from app.core.rbac import require_role
from app.models.user import User
from app.schemas.envelope import Envelope
from app.schemas.notice import (
    KorTravelMapCuratedFeatureImportRequest,
    KorTravelMapCuratedFeatureImportResponse,
    NoticePlanCreate,
    NoticePlanResponse,
    NoticePlanUpdate,
    NoticePoiCreate,
    NoticePoiReorderRequest,
    NoticePoiResponse,
    NoticePoiUpdate,
)
from app.schemas.storage import AttachmentCreate, AttachmentResponse
from app.services.admin_audit import append_admin_audit
from app.services.admin_curated_attachment import (
    CuratedAttachmentLimitError,
    CuratedAttachmentNotFoundError,
    CuratedAttachmentStorageRefError,
    CuratedPlanNotFoundError,
    create_curated_attachment,
    delete_curated_attachment,
    ensure_plan,
    ensure_poi,
    list_curated_attachments,
)
from app.services.notice_plan import (
    NoticePlanCopyError,
    NoticePlanNotFoundError,
    NoticePlanPolicyError,
    NoticePlanVersionConflictError,
    create_admin_plan,
    create_admin_poi,
    get_admin_plan,
    get_admin_poi,
    import_kor_travel_map_curated_feature,
    list_admin_plans,
    list_plan_pois,
    reorder_admin_pois,
    soft_delete_admin_plan,
    soft_delete_admin_poi,
    update_admin_plan,
    update_admin_poi,
)

router = APIRouter(prefix="/admin/notice-plans", tags=["admin"])

AdminDep = Annotated[User, Depends(require_role("admin"))]


def _to_response(attachment) -> AttachmentResponse:  # type: ignore[no-untyped-def]
    return AttachmentResponse(
        attachment_id=attachment.attachment_id,
        trip_id=attachment.trip_id,
        trip_day_index=attachment.trip_day_index,
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


def _poi_to_response(poi) -> NoticePoiResponse:  # type: ignore[no-untyped-def]
    return NoticePoiResponse(
        notice_poi_id=poi.curated_poi_id,
        notice_plan_id=poi.curated_plan_id,
        day_index=poi.day_index,
        sort_order=poi.sort_order,
        feature_id=poi.feature_id,
        feature_snapshot=poi.feature_snapshot,
        memo=poi.memo,
        budget_amount=poi.budget_amount,
        currency=poi.currency,
        user_url=poi.user_url,
        custom_marker_color=poi.custom_marker_color,
        custom_marker_icon=poi.custom_marker_icon,
        version=poi.version,
        created_at=poi.created_at,
        updated_at=poi.updated_at,
    )


def _plan_to_response(plan, pois) -> NoticePlanResponse:  # type: ignore[no-untyped-def]
    return NoticePlanResponse(
        notice_plan_id=plan.curated_plan_id,
        slug=plan.slug,
        title=plan.title,
        category=plan.category,
        summary=plan.summary,
        source_name=plan.source_name,
        destination=plan.destination,
        starts_on=plan.starts_on,
        ends_on=plan.ends_on,
        is_published=plan.is_published,
        version=plan.version,
        created_at=plan.created_at,
        updated_at=plan.updated_at,
        pois=[_poi_to_response(p) for p in pois],
    )


def _snapshot_plan(plan) -> dict[str, Any]:  # type: ignore[no-untyped-def]
    return _plan_to_response(plan, []).model_dump(mode="json")


def _snapshot_poi(poi) -> dict[str, Any]:  # type: ignore[no-untyped-def]
    return _poi_to_response(poi).model_dump(mode="json")


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


def _parse_if_match(value: str | None) -> int | None:
    if value is None:
        return None
    token = value.strip().strip('"')
    try:
        parsed = int(token)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "VALIDATION_ERROR",
                "message": "If-Match는 정수 version이어야 합니다.",
            },
        ) from exc
    if parsed < 1:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "VALIDATION_ERROR", "message": "If-Match는 1 이상이어야 합니다."},
        )
    return parsed


def _raise_not_found(
    exc: CuratedPlanNotFoundError | CuratedAttachmentNotFoundError,
) -> NoReturn:
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={"code": exc.code, "message": str(exc)},
    ) from exc


def _raise_notice_not_found(exc: NoticePlanNotFoundError) -> NoReturn:
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={"code": exc.code, "message": str(exc)},
    ) from exc


def _raise_notice_policy(exc: NoticePlanPolicyError) -> NoReturn:
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail={"code": exc.code, "message": str(exc)},
    ) from exc


def _raise_version_conflict(exc: NoticePlanVersionConflictError) -> NoReturn:
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={"code": exc.code, "message": str(exc)},
    ) from exc


def _raise_limit(exc: CuratedAttachmentLimitError) -> NoReturn:
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={"code": exc.code, "message": str(exc)},
    ) from exc


def _raise_storage_ref(exc: CuratedAttachmentStorageRefError) -> NoReturn:
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
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
    resource_type: str = "curated_plan_attachment",
) -> None:
    await append_admin_audit(
        db,
        actor_user_id=admin.user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        before_state=before,
        after_state=after,
        access_reason=None,
        target_pii_fields=None,
        ip_hash_input=request.client.host if request.client else "",
        user_agent=request.headers.get("user-agent"),
        request_id=_parse_request_id(x_request_id),
    )


# ── kor-travel-map curated feature import (T-223d) ─────────────────────────────


@router.post(
    "/imports/kor-travel-map-curated-features",
    status_code=status.HTTP_201_CREATED,
    response_model=Envelope[KorTravelMapCuratedFeatureImportResponse],
)
async def import_kor_travel_map_curated_feature_route(
    body: KorTravelMapCuratedFeatureImportRequest,
    admin: AdminDep,
    db: DbSession,
    kor_travel_map_client: KorTravelMapAdminClientDep,
    request: Request,
    x_request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
) -> Envelope[KorTravelMapCuratedFeatureImportResponse]:
    try:
        result = await import_kor_travel_map_curated_feature(
            db,
            admin_id=admin.user_id,
            kor_travel_map_client=kor_travel_map_client,
            curated_feature_id=body.curated_feature_id,
            mode=body.mode,
            is_published=body.is_published,
        )
    except KorTravelMapFeatureNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "KOR_TRAVEL_MAP_CURATED_FEATURE_NOT_FOUND", "message": str(exc)},
        ) from exc
    except KorTravelMapError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "KOR_TRAVEL_MAP_UNAVAILABLE", "message": str(exc)},
        ) from exc
    except NoticePlanNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc
    except NoticePlanPolicyError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc
    except NoticePlanCopyError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc

    await _audit(
        db,
        admin,
        request,
        x_request_id,
        action="curated_plan.kor_travel_map_imported",
        resource_type="curated_plan",
        resource_id=str(result.plan.curated_plan_id),
        before=None,
        after={
            "source_system": result.source_system,
            "source_curated_feature_id": result.source_curated_feature_id,
            "source_version": result.source_version,
            "source_etag": result.source_etag,
            "copied_poi_count": result.copied_poi_count,
            "created_plan": result.created_plan,
        },
    )
    await db.commit()
    return Envelope.of(
        KorTravelMapCuratedFeatureImportResponse(
            notice_plan_id=result.plan.curated_plan_id,
            created_plan=result.created_plan,
            source_system=result.source_system,
            source_curated_feature_id=result.source_curated_feature_id,
            source_version=result.source_version,
            source_etag=result.source_etag,
            copied_poi_count=result.copied_poi_count,
            reused_feature_backed_poi_count=result.reused_feature_backed_poi_count,
        )
    )


# ── Admin curated plan CRUD ─────────────────────────────────────────────────


@router.get("", response_model=Envelope[list[NoticePlanResponse]])
async def list_notice_plans(
    _admin: AdminDep,
    db: DbSession,
    q: str | None = None,
    category: str | None = None,
    is_published: bool | None = None,
    limit: int = Query(default=100, ge=1, le=200),
) -> Envelope[list[NoticePlanResponse]]:
    rows = await list_admin_plans(
        db, q=q, category=category, is_published=is_published, limit=limit
    )
    return Envelope.of([_plan_to_response(plan, []) for plan in rows])


@router.post("", status_code=status.HTTP_201_CREATED, response_model=Envelope[NoticePlanResponse])
async def create_notice_plan(
    body: NoticePlanCreate,
    admin: AdminDep,
    db: DbSession,
    request: Request,
    x_request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
) -> Envelope[NoticePlanResponse]:
    try:
        plan = await create_admin_plan(
            db,
            admin_id=admin.user_id,
            values=body.model_dump(exclude_unset=True),
        )
    except NoticePlanPolicyError as exc:
        _raise_notice_policy(exc)
    await _audit(
        db,
        admin,
        request,
        x_request_id,
        action="curated_plan.created",
        resource_type="curated_plan",
        resource_id=str(plan.curated_plan_id),
        before=None,
        after=_snapshot_plan(plan),
    )
    await db.commit()
    return Envelope.of(_plan_to_response(plan, []))


@router.get("/{plan_id}", response_model=Envelope[NoticePlanResponse])
async def get_notice_plan(
    plan_id: uuid.UUID, _admin: AdminDep, db: DbSession
) -> Envelope[NoticePlanResponse]:
    try:
        plan = await get_admin_plan(db, notice_plan_id=plan_id)
    except NoticePlanNotFoundError as exc:
        _raise_notice_not_found(exc)
    pois = await list_plan_pois(db, notice_plan_id=plan_id)
    return Envelope.of(_plan_to_response(plan, pois))


@router.patch("/{plan_id}", response_model=Envelope[NoticePlanResponse])
async def update_notice_plan(
    plan_id: uuid.UUID,
    body: NoticePlanUpdate,
    admin: AdminDep,
    db: DbSession,
    request: Request,
    x_request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
    if_match: Annotated[str | None, Header(alias="If-Match")] = None,
) -> Envelope[NoticePlanResponse]:
    try:
        plan = await get_admin_plan(db, notice_plan_id=plan_id)
        before = _snapshot_plan(plan)
        plan = await update_admin_plan(
            db,
            plan=plan,
            admin_id=admin.user_id,
            values=body.model_dump(exclude_unset=True),
            expected_version=_parse_if_match(if_match),
        )
    except NoticePlanNotFoundError as exc:
        _raise_notice_not_found(exc)
    except NoticePlanVersionConflictError as exc:
        _raise_version_conflict(exc)
    except NoticePlanPolicyError as exc:
        _raise_notice_policy(exc)
    await _audit(
        db,
        admin,
        request,
        x_request_id,
        action="curated_plan.updated",
        resource_type="curated_plan",
        resource_id=str(plan.curated_plan_id),
        before=before,
        after=_snapshot_plan(plan),
    )
    await db.commit()
    pois = await list_plan_pois(db, notice_plan_id=plan_id)
    return Envelope.of(_plan_to_response(plan, pois))


@router.delete("/{plan_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_notice_plan(
    plan_id: uuid.UUID,
    admin: AdminDep,
    db: DbSession,
    request: Request,
    x_request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
    if_match: Annotated[str | None, Header(alias="If-Match")] = None,
) -> None:
    try:
        plan = await get_admin_plan(db, notice_plan_id=plan_id)
        before = _snapshot_plan(plan)
        await soft_delete_admin_plan(
            db,
            plan=plan,
            admin_id=admin.user_id,
            expected_version=_parse_if_match(if_match),
        )
    except NoticePlanNotFoundError as exc:
        _raise_notice_not_found(exc)
    except NoticePlanVersionConflictError as exc:
        _raise_version_conflict(exc)
    await _audit(
        db,
        admin,
        request,
        x_request_id,
        action="curated_plan.deleted",
        resource_type="curated_plan",
        resource_id=str(plan_id),
        before=before,
        after=None,
    )
    await db.commit()


@router.post(
    "/{plan_id}/pois",
    status_code=status.HTTP_201_CREATED,
    response_model=Envelope[NoticePoiResponse],
)
async def create_notice_poi(
    plan_id: uuid.UUID,
    body: NoticePoiCreate,
    admin: AdminDep,
    db: DbSession,
    request: Request,
    x_request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
) -> Envelope[NoticePoiResponse]:
    try:
        plan = await get_admin_plan(db, notice_plan_id=plan_id)
        poi = await create_admin_poi(
            db,
            plan=plan,
            admin_id=admin.user_id,
            values=body.model_dump(exclude_unset=True),
        )
    except NoticePlanNotFoundError as exc:
        _raise_notice_not_found(exc)
    await _audit(
        db,
        admin,
        request,
        x_request_id,
        action="curated_poi.created",
        resource_type="curated_poi",
        resource_id=str(poi.curated_poi_id),
        before=None,
        after=_snapshot_poi(poi),
    )
    await db.commit()
    return Envelope.of(_poi_to_response(poi))


@router.post("/{plan_id}/pois/reorder", response_model=Envelope[list[NoticePoiResponse]])
async def reorder_notice_pois(
    plan_id: uuid.UUID,
    body: NoticePoiReorderRequest,
    admin: AdminDep,
    db: DbSession,
    request: Request,
    x_request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
) -> Envelope[list[NoticePoiResponse]]:
    try:
        plan = await get_admin_plan(db, notice_plan_id=plan_id)
        before = [_snapshot_poi(p) for p in await list_plan_pois(db, notice_plan_id=plan_id)]
        rows = await reorder_admin_pois(
            db,
            plan=plan,
            admin_id=admin.user_id,
            items=[item.model_dump() for item in body.items],
        )
    except NoticePlanNotFoundError as exc:
        _raise_notice_not_found(exc)
    except NoticePlanPolicyError as exc:
        _raise_notice_policy(exc)
    await _audit(
        db,
        admin,
        request,
        x_request_id,
        action="curated_poi.reordered",
        resource_type="curated_plan",
        resource_id=str(plan_id),
        before={"pois": before},
        after={"pois": [_snapshot_poi(p) for p in rows]},
    )
    await db.commit()
    return Envelope.of([_poi_to_response(p) for p in rows])


@router.patch("/{plan_id}/pois/{poi_id}", response_model=Envelope[NoticePoiResponse])
async def update_notice_poi(
    plan_id: uuid.UUID,
    poi_id: uuid.UUID,
    body: NoticePoiUpdate,
    admin: AdminDep,
    db: DbSession,
    request: Request,
    x_request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
    if_match: Annotated[str | None, Header(alias="If-Match")] = None,
) -> Envelope[NoticePoiResponse]:
    try:
        plan = await get_admin_plan(db, notice_plan_id=plan_id)
        poi = await get_admin_poi(db, notice_plan_id=plan_id, notice_poi_id=poi_id)
        before = _snapshot_poi(poi)
        poi = await update_admin_poi(
            db,
            plan=plan,
            poi=poi,
            values=body.model_dump(exclude_unset=True),
            expected_version=_parse_if_match(if_match),
        )
    except NoticePlanNotFoundError as exc:
        _raise_notice_not_found(exc)
    except NoticePlanVersionConflictError as exc:
        _raise_version_conflict(exc)
    except NoticePlanPolicyError as exc:
        _raise_notice_policy(exc)
    await _audit(
        db,
        admin,
        request,
        x_request_id,
        action="curated_poi.updated",
        resource_type="curated_poi",
        resource_id=str(poi.curated_poi_id),
        before=before,
        after=_snapshot_poi(poi),
    )
    await db.commit()
    return Envelope.of(_poi_to_response(poi))


@router.delete("/{plan_id}/pois/{poi_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_notice_poi(
    plan_id: uuid.UUID,
    poi_id: uuid.UUID,
    admin: AdminDep,
    db: DbSession,
    request: Request,
    x_request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
    if_match: Annotated[str | None, Header(alias="If-Match")] = None,
) -> None:
    try:
        plan = await get_admin_plan(db, notice_plan_id=plan_id)
        poi = await get_admin_poi(db, notice_plan_id=plan_id, notice_poi_id=poi_id)
        before = _snapshot_poi(poi)
        await soft_delete_admin_poi(
            db,
            plan=plan,
            poi=poi,
            expected_version=_parse_if_match(if_match),
        )
    except NoticePlanNotFoundError as exc:
        _raise_notice_not_found(exc)
    except NoticePlanVersionConflictError as exc:
        _raise_version_conflict(exc)
    await _audit(
        db,
        admin,
        request,
        x_request_id,
        action="curated_poi.deleted",
        resource_type="curated_poi",
        resource_id=str(poi_id),
        before=before,
        after=None,
    )
    await db.commit()


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
    except CuratedAttachmentStorageRefError as exc:
        _raise_storage_ref(exc)
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
    except CuratedAttachmentStorageRefError as exc:
        _raise_storage_ref(exc)
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
