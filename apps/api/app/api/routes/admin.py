from __future__ import annotations

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.routes.notice import (
    _notice_pois,
    _pois_by_plan,
    _to_notice_plan_response,
    _to_notice_poi_response,
)
from app.core.config import get_settings
from app.db.session import get_db
from app.models.mixins import kst_now
from app.models.trip import NoticePlan, NoticePoi, PlanPoiAttachment
from app.models.user import User
from app.schemas.admin import (
    AdminDatasetListResponse,
    AdminDatasetRowsResponse,
    AdminEntityDeleteResponse,
    AdminEntityDetailResponse,
    AdminEntityKind,
    AdminEntityListResponse,
    AdminEntityUpsertRequest,
    AdminLoginRequest,
    AdminLoginResponse,
    AdminManagedUserResponse,
    AdminRefreshTokenResponse,
    AdminUpdateUserRequest,
    AdminUserListResponse,
    AdminUserResponse,
)
from app.schemas.attachment import (
    PlanPoiAttachmentCreateRequest,
    PlanPoiAttachmentListResponse,
    PlanPoiAttachmentResponse,
)
from app.schemas.notice import (
    AdminNoticePlanCreate,
    AdminNoticePlanUpdate,
    AdminNoticePoiCreate,
    AdminNoticePoiUpdate,
    NoticePlanListResponse,
    NoticePlanResponse,
    NoticePoiResponse,
)
from app.schemas.storage import StorageObjectListResponse, StorageObjectResponse
from app.services.admin_auth import (
    authenticate_admin,
    get_user_by_access_token,
    issue_auth_tokens,
    refresh_access_token,
    revoke_refresh_token,
)
from app.services.admin_data_browser import (
    DEFAULT_PAGE_SIZE,
    PAGE_SIZE_OPTIONS,
    list_admin_datasets,
    query_admin_dataset_rows,
)
from app.services.admin_entity_crud import (
    AdminEntityNotFoundError,
    AdminEntityValidationError,
    create_admin_entity,
    delete_admin_entity,
    get_admin_entity_detail,
    list_admin_entities,
    update_admin_entity,
)
from app.services.file_storage import (
    FileStorageConfigurationError,
    FileStorageError,
    FileStorageHttpError,
    RustfsStorage,
)
from app.services.plan_poi_attachment import (
    AttachmentNotFoundError,
    create_notice_plan_attachment,
    create_notice_poi_attachment,
    delete_notice_plan_attachment,
    delete_notice_poi_attachment,
    list_notice_plan_attachments,
    list_notice_poi_attachments,
    to_attachment_response,
)

router = APIRouter(prefix="/admin", tags=["admin"])

ENTITY_QUERY_PARAM_NAMES = {"page", "limit", "search"}


def require_admin_user(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> User:
    settings = get_settings()
    user = get_user_by_access_token(
        db,
        request.cookies.get(settings.access_token_cookie_name),
        secret_key=settings.jwt_secret_key,
        issuer=settings.jwt_issuer,
        require_admin=True,
    )
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="관리자 로그인이 필요하다.",
        )
    return user


@router.get("/notice-plans", response_model=NoticePlanListResponse)
def list_admin_notice_plans(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(require_admin_user)],
    category: str | None = Query(default=None, max_length=80),
    published: bool | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> NoticePlanListResponse:
    query = select(NoticePlan).where(NoticePlan.deleted_at.is_(None))
    if category:
        query = query.where(NoticePlan.category == category)
    if published is not None:
        query = query.where(NoticePlan.is_published.is_(published))

    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    plans = db.scalars(
        query.order_by(NoticePlan.updated_at.desc())
        .offset((page - 1) * limit)
        .limit(limit)
    ).all()
    pois_by_plan = _pois_by_plan(db, [plan.id for plan in plans])
    return NoticePlanListResponse(
        items=[_to_notice_plan_response(plan, pois_by_plan.get(plan.id, [])) for plan in plans],
        total=total,
        page=page,
        limit=limit,
    )


@router.post(
    "/notice-plans",
    response_model=NoticePlanResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_admin_notice_plan(
    payload: AdminNoticePlanCreate,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(require_admin_user)],
) -> NoticePlanResponse:
    _ensure_notice_slug_available(db, payload.slug)
    plan = NoticePlan(
        slug=payload.slug,
        title=payload.title,
        category=payload.category,
        summary=payload.summary,
        source_name=payload.source_name,
        destination=payload.destination,
        starts_on=payload.starts_on,
        ends_on=payload.ends_on,
        is_published=payload.is_published,
        created_by_admin_id=current_user.id,
        updated_by_admin_id=current_user.id,
        version=1,
    )
    db.add(plan)
    db.flush()
    pois = [_notice_poi_from_payload(plan.id, poi) for poi in payload.pois]
    for poi in pois:
        db.add(poi)
    db.commit()
    return _to_notice_plan_response(plan, pois)


@router.get("/notice-plans/{plan_id}", response_model=NoticePlanResponse)
def get_admin_notice_plan(
    plan_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(require_admin_user)],
) -> NoticePlanResponse:
    plan = _admin_notice_plan_or_404(db, plan_id)
    return _to_notice_plan_response(plan, _notice_pois(db, plan.id))


@router.patch("/notice-plans/{plan_id}", response_model=NoticePlanResponse)
def update_admin_notice_plan(
    plan_id: UUID,
    payload: AdminNoticePlanUpdate,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(require_admin_user)],
) -> NoticePlanResponse:
    plan = _admin_notice_plan_or_404(db, plan_id)
    fields = payload.model_fields_set
    starts_on = payload.starts_on if "starts_on" in fields else plan.starts_on
    ends_on = payload.ends_on if "ends_on" in fields else plan.ends_on
    _validate_notice_period(starts_on, ends_on)

    changed = False
    for field in (
        "slug",
        "title",
        "category",
        "summary",
        "source_name",
        "destination",
        "starts_on",
        "ends_on",
        "is_published",
    ):
        if field not in fields:
            continue
        value = getattr(payload, field)
        if field == "slug" and value is not None:
            _ensure_notice_slug_available(db, value, exclude_plan_id=plan.id)
        if getattr(plan, field) != value:
            setattr(plan, field, value)
            changed = True
    if changed:
        _touch_notice_plan(plan, current_user.id)

    db.commit()
    return _to_notice_plan_response(plan, _notice_pois(db, plan.id))


@router.delete("/notice-plans/{plan_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_admin_notice_plan(
    plan_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(require_admin_user)],
) -> None:
    plan = _admin_notice_plan_or_404(db, plan_id)
    now = kst_now()
    plan.deleted_at = now
    plan.updated_at = now
    plan.updated_by_admin_id = current_user.id
    plan.version += 1
    db.commit()


@router.get(
    "/notice-plans/{plan_id}/attachments",
    response_model=PlanPoiAttachmentListResponse,
)
def get_admin_notice_plan_attachments(
    plan_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(require_admin_user)],
) -> PlanPoiAttachmentListResponse:
    try:
        attachments = list_notice_plan_attachments(db, plan_id=plan_id)
    except AttachmentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _attachment_list_response(attachments)


@router.post(
    "/notice-plans/{plan_id}/attachments",
    response_model=PlanPoiAttachmentResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_admin_notice_plan_attachment(
    plan_id: UUID,
    payload: PlanPoiAttachmentCreateRequest,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(require_admin_user)],
) -> PlanPoiAttachmentResponse:
    try:
        attachment = create_notice_plan_attachment(
            db,
            current_user=current_user,
            plan_id=plan_id,
            payload=payload,
        )
    except AttachmentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    plan = db.get(NoticePlan, plan_id)
    if plan is not None:
        _touch_notice_plan(plan, current_user.id)
    db.commit()
    db.refresh(attachment)
    return to_attachment_response(attachment)


@router.delete(
    "/notice-plans/{plan_id}/attachments/{attachment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def remove_admin_notice_plan_attachment(
    plan_id: UUID,
    attachment_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(require_admin_user)],
) -> None:
    try:
        delete_notice_plan_attachment(db, plan_id=plan_id, attachment_id=attachment_id)
    except AttachmentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    plan = db.get(NoticePlan, plan_id)
    if plan is not None:
        _touch_notice_plan(plan, current_user.id)
    db.commit()


@router.post(
    "/notice-plans/{plan_id}/pois",
    response_model=NoticePoiResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_admin_notice_poi(
    plan_id: UUID,
    payload: AdminNoticePoiCreate,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(require_admin_user)],
) -> NoticePoiResponse:
    plan = _admin_notice_plan_or_404(db, plan_id)
    poi = _notice_poi_from_payload(plan.id, payload)
    db.add(poi)
    _touch_notice_plan(plan, current_user.id)
    db.commit()
    return _to_notice_poi_response(poi)


@router.patch("/notice-plans/{plan_id}/pois/{poi_id}", response_model=NoticePoiResponse)
def update_admin_notice_poi(
    plan_id: UUID,
    poi_id: UUID,
    payload: AdminNoticePoiUpdate,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(require_admin_user)],
) -> NoticePoiResponse:
    plan = _admin_notice_plan_or_404(db, plan_id)
    poi = _admin_notice_poi_or_404(db, plan.id, poi_id)
    changed = False
    for field in (
        "day_index",
        "sort_order",
        "feature_id",
        "map_feature_id",
        "snapshot",
        "memo",
        "budget",
        "currency",
        "user_url",
        "custom_marker_color",
        "custom_marker_icon",
    ):
        if field not in payload.model_fields_set:
            continue
        value = getattr(payload, field)
        if getattr(poi, field) != value:
            setattr(poi, field, value)
            changed = True
    if changed:
        poi.version += 1
        poi.updated_at = kst_now()
        _touch_notice_plan(plan, current_user.id)
    db.commit()
    return _to_notice_poi_response(poi)


@router.delete("/notice-plans/{plan_id}/pois/{poi_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_admin_notice_poi(
    plan_id: UUID,
    poi_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(require_admin_user)],
) -> None:
    plan = _admin_notice_plan_or_404(db, plan_id)
    poi = _admin_notice_poi_or_404(db, plan.id, poi_id)
    now = kst_now()
    poi.deleted_at = now
    poi.updated_at = now
    poi.version += 1
    _touch_notice_plan(plan, current_user.id)
    db.commit()


@router.get(
    "/notice-plans/{plan_id}/pois/{poi_id}/attachments",
    response_model=PlanPoiAttachmentListResponse,
)
def get_admin_notice_poi_attachments(
    plan_id: UUID,
    poi_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(require_admin_user)],
) -> PlanPoiAttachmentListResponse:
    try:
        attachments = list_notice_poi_attachments(db, plan_id=plan_id, poi_id=poi_id)
    except AttachmentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _attachment_list_response(attachments)


@router.post(
    "/notice-plans/{plan_id}/pois/{poi_id}/attachments",
    response_model=PlanPoiAttachmentResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_admin_notice_poi_attachment(
    plan_id: UUID,
    poi_id: UUID,
    payload: PlanPoiAttachmentCreateRequest,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(require_admin_user)],
) -> PlanPoiAttachmentResponse:
    try:
        attachment = create_notice_poi_attachment(
            db,
            current_user=current_user,
            plan_id=plan_id,
            poi_id=poi_id,
            payload=payload,
        )
    except AttachmentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    plan = db.get(NoticePlan, plan_id)
    poi = db.get(NoticePoi, poi_id)
    if poi is not None:
        poi.version += 1
        poi.updated_at = kst_now()
    if plan is not None:
        _touch_notice_plan(plan, current_user.id)
    db.commit()
    db.refresh(attachment)
    return to_attachment_response(attachment)


@router.delete(
    "/notice-plans/{plan_id}/pois/{poi_id}/attachments/{attachment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def remove_admin_notice_poi_attachment(
    plan_id: UUID,
    poi_id: UUID,
    attachment_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(require_admin_user)],
) -> None:
    try:
        delete_notice_poi_attachment(
            db,
            plan_id=plan_id,
            poi_id=poi_id,
            attachment_id=attachment_id,
        )
    except AttachmentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    plan = db.get(NoticePlan, plan_id)
    poi = db.get(NoticePoi, poi_id)
    if poi is not None:
        poi.version += 1
        poi.updated_at = kst_now()
    if plan is not None:
        _touch_notice_plan(plan, current_user.id)
    db.commit()


@router.get("/rustfs/objects", response_model=StorageObjectListResponse)
def get_admin_rustfs_objects(
    _: Annotated[User, Depends(require_admin_user)],
    prefix: Annotated[str, Query(max_length=1024)] = "",
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
    continuation_token: Annotated[str | None, Query(max_length=2048)] = None,
) -> StorageObjectListResponse:
    storage = RustfsStorage.from_settings(get_settings())
    try:
        listing = storage.list_objects(
            prefix=prefix,
            max_keys=limit,
            continuation_token=continuation_token,
        )
    except FileStorageConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except FileStorageError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except FileStorageHttpError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return StorageObjectListResponse(
        bucket=listing.bucket,
        prefix=listing.prefix,
        objects=[
            StorageObjectResponse(
                key=item.key,
                size=item.size,
                last_modified=item.last_modified,
                etag=item.etag,
                storage_class=item.storage_class,
                public_url=storage.public_object_url(item.key),
            )
            for item in listing.objects
        ],
        is_truncated=listing.is_truncated,
        next_continuation_token=listing.next_continuation_token,
    )


@router.delete("/rustfs/objects", status_code=status.HTTP_204_NO_CONTENT)
def remove_admin_rustfs_object(
    _: Annotated[User, Depends(require_admin_user)],
    key: Annotated[str, Query(min_length=1, max_length=1024)],
) -> None:
    storage = RustfsStorage.from_settings(get_settings())
    try:
        storage.delete_object(key)
    except FileStorageConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except FileStorageError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except FileStorageHttpError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/auth/login", response_model=AdminLoginResponse)
def login_admin(
    payload: AdminLoginRequest,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
) -> AdminLoginResponse:
    settings = get_settings()
    user = authenticate_admin(db, email=payload.email, password=payload.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="관리자 계정 또는 비밀번호가 올바르지 않다.",
        )

    tokens = issue_auth_tokens(
        db,
        user_id=user.id,
        secret_key=settings.jwt_secret_key,
        issuer=settings.jwt_issuer,
        access_token_minutes=settings.access_token_minutes,
        refresh_token_days=settings.refresh_token_days,
    )
    db.commit()
    _set_auth_cookies(response, tokens.access_token, tokens.refresh_token)
    return AdminLoginResponse(
        user=_to_admin_user_response(user),
        token_type="Bearer",
        access_token_expires_at=tokens.access_token_expires_at,
        refresh_token_expires_at=tokens.refresh_token_expires_at,
    )


@router.post("/auth/refresh", response_model=AdminRefreshTokenResponse)
def refresh_admin_login(
    request: Request,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
) -> AdminRefreshTokenResponse:
    settings = get_settings()
    result = refresh_access_token(
        db,
        request.cookies.get(settings.refresh_token_cookie_name),
        secret_key=settings.jwt_secret_key,
        issuer=settings.jwt_issuer,
        access_token_minutes=settings.access_token_minutes,
        require_admin=True,
    )
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="다시 로그인이 필요하다."
        )

    db.commit()
    _set_access_cookie(response, result.access_token)
    return AdminRefreshTokenResponse(
        user=_to_admin_user_response(result.user),
        token_type="Bearer",
        access_token_expires_at=result.access_token_expires_at,
    )


@router.post("/auth/logout")
def logout_admin(
    request: Request,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, str]:
    settings = get_settings()
    revoke_refresh_token(db, request.cookies.get(settings.refresh_token_cookie_name))
    db.commit()
    _delete_auth_cookies(response)
    return {"status": "ok"}


@router.get("/auth/me", response_model=AdminUserResponse)
def get_admin_me(
    user: Annotated[User, Depends(require_admin_user)],
) -> AdminUserResponse:
    return _to_admin_user_response(user)


@router.get("/users", response_model=AdminUserListResponse)
def get_admin_users(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(require_admin_user)],
    page: Annotated[int, Query(ge=1)] = 1,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    search: str | None = None,
    account_status: str | None = None,
    system_role: str | None = None,
) -> AdminUserListResponse:
    query = select(User)
    if search and search.strip():
        pattern = f"%{search.strip().lower()}%"
        query = query.where(
            or_(
                func.lower(User.email).like(pattern),
                func.lower(func.coalesce(User.nickname, "")).like(pattern),
                func.lower(func.coalesce(User.name, "")).like(pattern),
                func.lower(func.coalesce(User.display_name, "")).like(pattern),
            )
        )
    if account_status:
        query = query.where(User.account_status == account_status)
    if system_role:
        query = query.where(User.system_role == system_role)

    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    users = db.scalars(
        query.order_by(User.created_at.desc(), User.email.asc())
        .offset((page - 1) * limit)
        .limit(limit)
    ).all()
    return AdminUserListResponse(
        users=[_to_managed_user_response(user) for user in users],
        page=page,
        limit=limit,
        total=total,
    )


@router.patch("/users/{user_id}", response_model=AdminManagedUserResponse)
def update_admin_user(
    user_id: UUID,
    payload: AdminUpdateUserRequest,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(require_admin_user)],
) -> AdminManagedUserResponse:
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없다.")

    if target.id == current_user.id:
        if payload.account_status in {"disabled", "deleted"}:
            raise HTTPException(
                status_code=400,
                detail="자기 자신의 관리자 계정을 비활성화할 수 없다.",
            )
        if payload.system_role is not None and payload.system_role != "admin":
            raise HTTPException(status_code=400, detail="자기 자신의 관리자 권한을 제거할 수 없다.")

    if payload.account_status is not None:
        target.account_status = payload.account_status
        target.is_active = payload.account_status not in {"disabled", "deleted"}
    if payload.system_role is not None:
        target.system_role = payload.system_role
        target.is_admin = payload.system_role == "admin"
        target.is_privileged = payload.system_role == "admin"
    if payload.nickname is not None:
        target.nickname = payload.nickname.strip()
        target.display_name = target.nickname
    if payload.name is not None:
        target.name = payload.name.strip()
    if payload.email_verified is True and target.email_verified_at is None:
        target.email_verified_at = kst_now()
    if payload.email_verified is False:
        target.email_verified_at = None

    db.commit()
    db.refresh(target)
    return _to_managed_user_response(target)


@router.get("/entities/{entity}", response_model=AdminEntityListResponse)
def get_admin_entity_list(
    entity: AdminEntityKind,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(require_admin_user)],
    page: Annotated[int, Query(ge=1)] = 1,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    search: str | None = None,
) -> AdminEntityListResponse:
    filters = {
        key: value
        for key, value in request.query_params.multi_items()
        if key not in ENTITY_QUERY_PARAM_NAMES and value
    }
    try:
        result = list_admin_entities(
            db,
            entity=entity,
            page=page,
            limit=limit,
            search=search,
            filters=filters,
        )
    except AdminEntityValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return AdminEntityListResponse.model_validate(result)


@router.get("/entities/{entity}/{item_id}", response_model=AdminEntityDetailResponse)
def get_admin_entity_item(
    entity: AdminEntityKind,
    item_id: str,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(require_admin_user)],
) -> AdminEntityDetailResponse:
    try:
        result = get_admin_entity_detail(db, entity=entity, item_id=item_id)
    except AdminEntityValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except AdminEntityNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return AdminEntityDetailResponse.model_validate(result)


@router.post(
    "/entities/{entity}",
    response_model=AdminEntityDetailResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_admin_entity_item(
    entity: AdminEntityKind,
    payload: AdminEntityUpsertRequest,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(require_admin_user)],
) -> AdminEntityDetailResponse:
    try:
        item_id = create_admin_entity(db, entity=entity, values=payload.values)
        db.commit()
        result = get_admin_entity_detail(db, entity=entity, item_id=item_id)
    except AdminEntityValidationError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except AdminEntityNotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="관리자 CRUD 저장 중 제약 조건이 충돌했다.",
        ) from exc
    return AdminEntityDetailResponse.model_validate(result)


@router.patch("/entities/{entity}/{item_id}", response_model=AdminEntityDetailResponse)
def update_admin_entity_item(
    entity: AdminEntityKind,
    item_id: str,
    payload: AdminEntityUpsertRequest,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(require_admin_user)],
) -> AdminEntityDetailResponse:
    try:
        updated_id = update_admin_entity(
            db,
            entity=entity,
            item_id=item_id,
            values=payload.values,
            current_user=current_user,
        )
        db.commit()
        result = get_admin_entity_detail(db, entity=entity, item_id=updated_id)
    except AdminEntityValidationError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except AdminEntityNotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="관리자 CRUD 저장 중 제약 조건이 충돌했다.",
        ) from exc
    return AdminEntityDetailResponse.model_validate(result)


@router.delete("/entities/{entity}/{item_id}", response_model=AdminEntityDeleteResponse)
def delete_admin_entity_item(
    entity: AdminEntityKind,
    item_id: str,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(require_admin_user)],
) -> AdminEntityDeleteResponse:
    try:
        deleted_id = delete_admin_entity(
            db,
            entity=entity,
            item_id=item_id,
            current_user=current_user,
        )
        db.commit()
    except AdminEntityValidationError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except AdminEntityNotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="관리자 CRUD 삭제 중 제약 조건이 충돌했다.",
        ) from exc
    return AdminEntityDeleteResponse(entity=entity, id=deleted_id, status="deleted")


@router.get("/datasets", response_model=AdminDatasetListResponse)
def get_admin_datasets(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(require_admin_user)],
) -> AdminDatasetListResponse:
    return AdminDatasetListResponse.model_validate(
        {
            "datasets": list_admin_datasets(db),
            "page_size_options": sorted(PAGE_SIZE_OPTIONS),
            "default_page_size": DEFAULT_PAGE_SIZE,
        }
    )


@router.get("/datasets/{table_name}/rows", response_model=AdminDatasetRowsResponse)
def get_admin_dataset_rows(
    table_name: str,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(require_admin_user)],
    page: Annotated[int, Query(ge=1)] = 1,
    limit: Annotated[int, Query()] = DEFAULT_PAGE_SIZE,
    search: str | None = None,
    sort_by: str | None = None,
    sort_dir: str = "desc",
) -> AdminDatasetRowsResponse:
    filters = {
        key.removeprefix("filter."): value
        for key, value in request.query_params.multi_items()
        if key.startswith("filter.")
    }
    try:
        result = query_admin_dataset_rows(
            db,
            table_name=table_name,
            page=page,
            limit=limit,
            search=search,
            sort_by=sort_by,
            sort_dir="asc" if sort_dir == "asc" else "desc",
            filters=filters,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="조회할 수 없는 관리자 데이터셋이다.") from exc

    return AdminDatasetRowsResponse.model_validate(result)


def _to_admin_user_response(user: User) -> AdminUserResponse:
    return AdminUserResponse(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        is_admin=user.is_admin,
        is_privileged=user.is_privileged,
    )


def _attachment_list_response(
    attachments: list[PlanPoiAttachment],
) -> PlanPoiAttachmentListResponse:
    return PlanPoiAttachmentListResponse(
        items=[to_attachment_response(attachment) for attachment in attachments],
        total=len(attachments),
    )


def _admin_notice_plan_or_404(db: Session, plan_id: UUID) -> NoticePlan:
    plan = db.get(NoticePlan, plan_id)
    if plan is None or plan.deleted_at is not None:
        raise HTTPException(status_code=404, detail="공지 계획을 찾을 수 없다.")
    return plan


def _admin_notice_poi_or_404(db: Session, plan_id: UUID, poi_id: UUID) -> NoticePoi:
    poi = db.get(NoticePoi, poi_id)
    if poi is None or poi.notice_plan_id != plan_id or poi.deleted_at is not None:
        raise HTTPException(status_code=404, detail="공지 POI를 찾을 수 없다.")
    return poi


def _ensure_notice_slug_available(
    db: Session,
    slug: str,
    *,
    exclude_plan_id: UUID | None = None,
) -> None:
    query = select(NoticePlan.id).where(
        NoticePlan.slug == slug,
        NoticePlan.deleted_at.is_(None),
    )
    if exclude_plan_id is not None:
        query = query.where(NoticePlan.id != exclude_plan_id)
    if db.scalar(query) is not None:
        raise HTTPException(status_code=409, detail="이미 사용 중인 공지 계획 slug다.")


def _notice_poi_from_payload(plan_id: UUID, payload: AdminNoticePoiCreate) -> NoticePoi:
    return NoticePoi(
        notice_plan_id=plan_id,
        day_index=payload.day_index,
        sort_order=payload.sort_order,
        feature_id=payload.feature_id,
        map_feature_id=payload.map_feature_id,
        snapshot=payload.snapshot,
        memo=payload.memo,
        budget=payload.budget,
        currency=payload.currency,
        user_url=payload.user_url,
        custom_marker_color=payload.custom_marker_color,
        custom_marker_icon=payload.custom_marker_icon,
        version=1,
    )


def _touch_notice_plan(plan: NoticePlan, admin_id: UUID) -> None:
    plan.updated_by_admin_id = admin_id
    plan.updated_at = kst_now()
    plan.version += 1


def _validate_notice_period(starts_on: date | None, ends_on: date | None) -> None:
    if (starts_on is None) != (ends_on is None):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="starts_on과 ends_on은 둘 다 있거나 둘 다 없어야 한다.",
        )
    if starts_on is not None and ends_on is not None and ends_on < starts_on:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="공지 계획 종료일은 시작일보다 빠를 수 없다.",
        )


def _set_auth_cookies(response: Response, access_token: str, refresh_token: str) -> None:
    _set_access_cookie(response, access_token)
    settings = get_settings()
    response.set_cookie(
        key=settings.refresh_token_cookie_name,
        value=refresh_token,
        max_age=settings.refresh_token_days * 24 * 60 * 60,
        httponly=True,
        secure=settings.environment == "production",
        samesite="lax",
        path="/",
    )


def _set_access_cookie(response: Response, access_token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        key=settings.access_token_cookie_name,
        value=access_token,
        max_age=settings.access_token_minutes * 60,
        httponly=True,
        secure=settings.environment == "production",
        samesite="lax",
        path="/",
    )


def _delete_auth_cookies(response: Response) -> None:
    settings = get_settings()
    response.delete_cookie(settings.access_token_cookie_name, path="/")
    response.delete_cookie(settings.refresh_token_cookie_name, path="/")


def _to_managed_user_response(user: User) -> AdminManagedUserResponse:
    return AdminManagedUserResponse(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        nickname=user.nickname,
        name=user.name,
        account_status=user.account_status,
        system_role=user.system_role,
        birth_year_month=user.birth_year_month,
        gender=user.gender,
        residence_sigungu_code=user.residence_sigungu_code,
        email_verified_at=user.email_verified_at,
        is_active=user.is_active,
        is_admin=user.is_admin,
        is_privileged=user.is_privileged,
        created_at=user.created_at,
        updated_at=user.updated_at,
    )
