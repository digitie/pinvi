from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.models.mixins import kst_now
from app.models.user import User
from app.schemas.admin import (
    AdminDatasetListResponse,
    AdminDatasetRowsResponse,
    AdminLoginRequest,
    AdminLoginResponse,
    AdminManagedUserResponse,
    AdminUpdateUserRequest,
    AdminUserListResponse,
    AdminUserResponse,
)
from app.services.admin_auth import (
    authenticate_admin,
    create_session_token,
    get_admin_user_by_session_token,
    revoke_session_token,
)
from app.services.admin_data_browser import (
    DEFAULT_PAGE_SIZE,
    PAGE_SIZE_OPTIONS,
    list_admin_datasets,
    query_admin_dataset_rows,
)

router = APIRouter(prefix="/admin", tags=["admin"])


def require_admin_user(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> User:
    settings = get_settings()
    token = request.cookies.get(settings.session_cookie_name)
    user = get_admin_user_by_session_token(db, token)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="관리자 로그인이 필요하다.",
        )
    return user


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

    token, _ = create_session_token(
        db,
        user_id=user.id,
        expires_in_hours=settings.admin_session_hours,
    )
    db.commit()
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        max_age=settings.admin_session_hours * 60 * 60,
        httponly=True,
        secure=settings.environment == "production",
        samesite="lax",
        path="/",
    )
    return AdminLoginResponse(user=_to_admin_user_response(user))


@router.post("/auth/logout")
def logout_admin(
    request: Request,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, str]:
    settings = get_settings()
    revoke_session_token(db, request.cookies.get(settings.session_cookie_name))
    db.commit()
    response.delete_cookie(settings.session_cookie_name, path="/")
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
