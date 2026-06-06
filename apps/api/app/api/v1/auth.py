"""`/auth/*` — `docs/api/auth.md`."""

from __future__ import annotations

import uuid
from typing import Any, Literal, cast

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import select

from app.core.config import settings
from app.core.deps import CurrentUserId, DbSession
from app.core.security import create_access_token, generate_opaque_token
from app.models.oauth_identity import UserOAuthIdentity
from app.models.user import User
from app.schemas.auth import (
    AuthUser,
    AuthUserOAuthIdentity,
    LoginRequest,
    PasswordResetConfirmRequest,
    PasswordResetRequest,
    PasswordResetRequestResponse,
    RegisterRequest,
    RegisterResponse,
    UserResponse,
    VerifyEmailRequest,
)
from app.schemas.envelope import Envelope
from app.services.user_registration import (
    EmailAlreadyUsedError,
    EmailNotVerifiedError,
    InvalidCredentialsError,
    VerificationTokenInvalidError,
    authenticate,
    register_user,
    request_password_reset,
    reset_password,
    verify_email,
)

router = APIRouter(prefix="/auth", tags=["auth"])


async def _load_current_user(db: DbSession, current_user_id: str) -> User:
    try:
        user_uuid = uuid.UUID(current_user_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "TOKEN_INVALID", "message": "토큰 sub 클레임이 잘못되었습니다."},
        ) from exc

    user = await db.scalar(select(User).where(User.user_id == user_uuid, User.deleted_at.is_(None)))
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "TOKEN_INVALID", "message": "사용자를 찾을 수 없습니다."},
        )
    return user


async def _list_oauth_identities(
    db: DbSession,
    *,
    user_id: uuid.UUID,
) -> list[AuthUserOAuthIdentity]:
    rows = (
        (
            await db.execute(
                select(UserOAuthIdentity)
                .where(UserOAuthIdentity.user_id == user_id)
                .order_by(UserOAuthIdentity.provider.asc())
            )
        )
        .scalars()
        .all()
    )
    return [
        AuthUserOAuthIdentity(
            provider=cast(Literal["google", "naver", "kakao"], row.provider),
            provider_email=row.provider_email,
            provider_email_verified=row.provider_email_verified,
            display_name=row.display_name_snapshot,
            linked_at=row.linked_at,
            last_login_at=row.last_login_at,
        )
        for row in rows
    ]


def _set_session_cookies(response: Response, *, user_id: str) -> None:
    access = create_access_token(subject=user_id)
    refresh = generate_opaque_token(32)
    response.set_cookie(
        key="tripmate_access",
        value=access,
        httponly=True,
        secure=settings.tripmate_environment == "production",
        samesite="lax",
        max_age=settings.tripmate_access_token_minutes * 60,
    )
    response.set_cookie(
        key="tripmate_refresh",
        value=refresh,
        httponly=True,
        secure=settings.tripmate_environment == "production",
        samesite="lax",
        max_age=settings.tripmate_refresh_token_days * 24 * 60 * 60,
    )


def _clear_session_cookies(response: Response) -> None:
    response.delete_cookie("tripmate_access")
    response.delete_cookie("tripmate_refresh")


@router.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
    response_model=Envelope[RegisterResponse],
)
async def register(body: RegisterRequest, db: DbSession) -> Envelope[RegisterResponse]:
    try:
        result = await register_user(
            db,
            email=str(body.email),
            password=body.password,
            nickname=body.nickname,
            consents=body.consents,
        )
    except EmailAlreadyUsedError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc

    return Envelope.of(
        RegisterResponse(
            user=UserResponse(
                user_id=result.user.user_id,
                email=result.user.email,
                status=cast(
                    Literal["pending_verification", "pending_profile", "active", "disabled"],
                    result.user.status,
                ),
                email_verified_at=result.user.email_verified_at,
            ),
            verification_email_dispatched=result.verification_email_dispatched,
        )
    )


@router.post(
    "/verify-email",
    response_model=Envelope[AuthUser],
)
async def verify_email_endpoint(
    body: VerifyEmailRequest,
    response: Response,
    db: DbSession,
) -> Envelope[AuthUser]:
    try:
        user = await verify_email(db, token=body.token)
    except VerificationTokenInvalidError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": exc.code, "message": str(exc), "details": {"token": "invalid"}},
        ) from exc

    _set_session_cookies(response, user_id=str(user.user_id))
    return Envelope.of(_to_auth_user(user))


@router.post(
    "/password/reset-request",
    response_model=Envelope[PasswordResetRequestResponse],
)
async def password_reset_request(
    body: PasswordResetRequest,
    db: DbSession,
) -> Envelope[PasswordResetRequestResponse]:
    await request_password_reset(db, email=str(body.email))
    return Envelope.of(PasswordResetRequestResponse(accepted=True))


@router.post("/password/reset", response_model=Envelope[AuthUser])
async def password_reset(
    body: PasswordResetConfirmRequest,
    response: Response,
    db: DbSession,
) -> Envelope[AuthUser]:
    try:
        user = await reset_password(db, token=body.token, new_password=body.new_password)
    except VerificationTokenInvalidError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": exc.code, "message": str(exc), "details": {"token": "invalid"}},
        ) from exc

    _set_session_cookies(response, user_id=str(user.user_id))
    return Envelope.of(_to_auth_user(user))


@router.post("/login", response_model=Envelope[AuthUser])
async def login(
    body: LoginRequest,
    response: Response,
    db: DbSession,
) -> Envelope[AuthUser]:
    try:
        user = await authenticate(db, email=str(body.email), password=body.password)
    except EmailNotVerifiedError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": exc.code,
                "message": str(exc),
                "details": {"verification_email_dispatched": False},
            },
        ) from exc
    except InvalidCredentialsError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc

    _set_session_cookies(response, user_id=str(user.user_id))
    return Envelope.of(_to_auth_user(user))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(response: Response) -> Response:
    _clear_session_cookies(response)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me", response_model=Envelope[AuthUser])
async def me(current_user_id: CurrentUserId, db: DbSession) -> Envelope[AuthUser]:
    user = await _load_current_user(db, current_user_id)
    oauth_identities = await _list_oauth_identities(db, user_id=user.user_id)
    return Envelope.of(_to_auth_user(user, oauth_identities=oauth_identities))


def _to_auth_user(
    user: Any,
    *,
    oauth_identities: list[AuthUserOAuthIdentity] | None = None,
) -> AuthUser:
    return AuthUser(
        user_id=user.user_id,
        email=user.email,
        nickname=user.nickname,
        avatar_url=user.avatar_url,
        status=user.status,
        roles=cast(list[Literal["user", "admin", "operator", "cpo"]], user.roles),
        email_verified_at=user.email_verified_at,
        has_password=bool(user.password_hash),
        oauth_identities=oauth_identities or [],
    )
