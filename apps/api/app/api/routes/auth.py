from __future__ import annotations

from typing import Annotated
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import (
    AuthenticatedUserResponse,
    LoginRequest,
    LoginResponse,
    LogoutResponse,
    RefreshTokenResponse,
    RegisteredUserResponse,
    RegisterUserRequest,
    RegisterUserResponse,
    VerifyEmailRequest,
    VerifyEmailResponse,
)
from app.services.admin_auth import (
    authenticate_user,
    get_user_by_access_token,
    issue_auth_tokens,
    refresh_access_token,
    revoke_refresh_token,
)
from app.services.email_delivery import EmailVerificationMessage, send_verification_email
from app.services.user_registration import (
    DuplicateEmailError,
    EmailVerificationTokenInvalidError,
    RequiredConsentMissingError,
    ResidenceCodeNotFoundError,
    register_user,
    verify_email_token,
)

router = APIRouter(prefix="/auth", tags=["auth"])
OAUTH_PROVIDERS = ("google", "naver", "kakao")


def require_current_user(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> User:
    settings = get_settings()
    user = get_user_by_access_token(
        db,
        request.cookies.get(settings.access_token_cookie_name),
        secret_key=settings.jwt_secret_key,
        issuer=settings.jwt_issuer,
    )
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
        result = register_user(db, payload)
    except DuplicateEmailError as exc:
        raise HTTPException(status_code=409, detail="이미 가입된 이메일이다.") from exc
    except ResidenceCodeNotFoundError as exc:
        raise HTTPException(status_code=422, detail="거주지 시군구 코드를 찾을 수 없다.") from exc
    except RequiredConsentMissingError as exc:
        raise HTTPException(
            status_code=422,
            detail="Terms and privacy consent are required.",
        ) from exc

    settings = get_settings()
    try:
        email_dispatched = send_verification_email(
            EmailVerificationMessage(
                to_email=result.user.email,
                display_name=result.user.display_name or result.user.email,
                token=result.verification_token,
            ),
            settings=settings,
        )
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="이메일 인증 메일을 발송하지 못했다.",
        ) from exc

    db.commit()
    db.refresh(result.user)
    return RegisterUserResponse(
        user=_to_registered_user_response(
            result.user,
            verification_email_dispatched=email_dispatched,
        )
    )


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
    return LoginResponse(
        user=_to_authenticated_user_response(user),
        token_type="Bearer",
        access_token_expires_at=tokens.access_token_expires_at,
        refresh_token_expires_at=tokens.refresh_token_expires_at,
    )


@router.post("/refresh", response_model=RefreshTokenResponse)
def refresh_login(
    request: Request,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
) -> RefreshTokenResponse:
    settings = get_settings()
    result = refresh_access_token(
        db,
        request.cookies.get(settings.refresh_token_cookie_name),
        secret_key=settings.jwt_secret_key,
        issuer=settings.jwt_issuer,
        access_token_minutes=settings.access_token_minutes,
    )
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="다시 로그인이 필요하다."
        )

    db.commit()
    _set_access_cookie(response, result.access_token)
    return RefreshTokenResponse(
        user=_to_authenticated_user_response(result.user),
        token_type="Bearer",
        access_token_expires_at=result.access_token_expires_at,
    )


@router.post("/logout", response_model=LogoutResponse)
def logout(
    request: Request,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
) -> LogoutResponse:
    settings = get_settings()
    revoke_refresh_token(db, request.cookies.get(settings.refresh_token_cookie_name))
    db.commit()
    _delete_auth_cookies(response)
    return LogoutResponse(status="ok")


@router.post("/verify-email", response_model=VerifyEmailResponse)
def verify_email(
    payload: VerifyEmailRequest,
    db: Annotated[Session, Depends(get_db)],
) -> VerifyEmailResponse:
    try:
        user = verify_email_token(db, payload.token)
    except EmailVerificationTokenInvalidError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="이메일 인증 링크가 유효하지 않거나 만료됐다.",
        ) from exc

    db.commit()
    db.refresh(user)
    return VerifyEmailResponse(status="ok", user=_to_authenticated_user_response(user))


@router.get("/oauth/providers")
def list_oauth_providers() -> dict[str, list[dict[str, str | bool]]]:
    return {
        "providers": [
            {
                "provider": provider,
                "display_name": provider.title(),
                "enabled": False,
                "email_match_policy": "verified_email_requires_explicit_link",
            }
            for provider in OAUTH_PROVIDERS
        ]
    }


@router.get("/oauth/{provider}/start")
def start_oauth(provider: str) -> RedirectResponse:
    if provider not in OAUTH_PROVIDERS:
        raise HTTPException(status_code=404, detail="Unknown OAuth provider.")
    settings = get_settings()
    query = urlencode({"oauth_error": "temporary_failure", "provider": provider})
    return RedirectResponse(f"{settings.web_base_url}/login?{query}", status_code=303)


@router.get("/me", response_model=AuthenticatedUserResponse)
def get_me(
    user: Annotated[User, Depends(require_current_user)],
) -> AuthenticatedUserResponse:
    return _to_authenticated_user_response(user)


def _to_registered_user_response(
    user: User,
    *,
    verification_email_dispatched: bool = False,
) -> RegisteredUserResponse:
    return RegisteredUserResponse(
        id=user.id,
        email=user.email,
        nickname=user.nickname or user.display_name or user.email,
        name=user.name or user.display_name or user.email,
        account_status=user.account_status,
        status=user.status,
        system_role=user.system_role,
        email_verification_required=user.email_verified_at is None,
        verification_email_dispatched=verification_email_dispatched,
    )


def _to_authenticated_user_response(user: User) -> AuthenticatedUserResponse:
    return AuthenticatedUserResponse(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        nickname=user.nickname,
        name=user.name,
        account_status=user.account_status,
        status=user.status,
        system_role=user.system_role,
        email_verified_at=user.email_verified_at,
        is_admin=user.is_admin,
        is_privileged=user.is_privileged,
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
