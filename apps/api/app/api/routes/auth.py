from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import (
    AuthenticatedUserResponse,
    LoginRequest,
    LoginResponse,
    LogoutResponse,
    RegisteredUserResponse,
    RegisterUserRequest,
    RegisterUserResponse,
)
from app.services.admin_auth import (
    authenticate_user,
    create_session_token,
    get_user_by_session_token,
    revoke_session_token,
)
from app.services.user_registration import (
    DuplicateEmailError,
    ResidenceCodeNotFoundError,
    register_user,
)

router = APIRouter(prefix="/auth", tags=["auth"])


def require_current_user(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> User:
    settings = get_settings()
    token = request.cookies.get(settings.session_cookie_name)
    user = get_user_by_session_token(db, token)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="로그인이 필요하다.",
        )
    return user


@router.post("/register", response_model=RegisterUserResponse, status_code=status.HTTP_201_CREATED)
def register(
    payload: RegisterUserRequest,
    db: Annotated[Session, Depends(get_db)],
) -> RegisterUserResponse:
    try:
        user = register_user(db, payload)
    except DuplicateEmailError as exc:
        raise HTTPException(status_code=409, detail="이미 가입된 이메일이다.") from exc
    except ResidenceCodeNotFoundError as exc:
        raise HTTPException(status_code=422, detail="거주지 시군구 코드를 찾을 수 없다.") from exc

    db.commit()
    db.refresh(user)
    return RegisterUserResponse(user=_to_registered_user_response(user))


@router.post("/login", response_model=LoginResponse)
def login(
    payload: LoginRequest,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
) -> LoginResponse:
    settings = get_settings()
    user = authenticate_user(db, email=payload.email, password=payload.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="이메일 또는 비밀번호가 올바르지 않거나 이메일 인증이 필요하다.",
        )

    token, _ = create_session_token(
        db,
        user_id=user.id,
        expires_in_hours=settings.user_session_hours,
    )
    db.commit()
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        max_age=settings.user_session_hours * 60 * 60,
        httponly=True,
        secure=settings.environment == "production",
        samesite="lax",
        path="/",
    )
    return LoginResponse(user=_to_authenticated_user_response(user))


@router.post("/logout", response_model=LogoutResponse)
def logout(
    request: Request,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
) -> LogoutResponse:
    settings = get_settings()
    revoke_session_token(db, request.cookies.get(settings.session_cookie_name))
    db.commit()
    response.delete_cookie(settings.session_cookie_name, path="/")
    return LogoutResponse(status="ok")


@router.get("/me", response_model=AuthenticatedUserResponse)
def get_me(
    user: Annotated[User, Depends(require_current_user)],
) -> AuthenticatedUserResponse:
    return _to_authenticated_user_response(user)


def _to_registered_user_response(user: User) -> RegisteredUserResponse:
    return RegisteredUserResponse(
        id=user.id,
        email=user.email,
        nickname=user.nickname or user.display_name or user.email,
        name=user.name or user.display_name or user.email,
        account_status=user.account_status,
        system_role=user.system_role,
        email_verification_required=user.email_verified_at is None,
        verification_email_dispatched=False,
    )


def _to_authenticated_user_response(user: User) -> AuthenticatedUserResponse:
    return AuthenticatedUserResponse(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        nickname=user.nickname,
        name=user.name,
        account_status=user.account_status,
        system_role=user.system_role,
        email_verified_at=user.email_verified_at,
        is_admin=user.is_admin,
        is_privileged=user.is_privileged,
    )
