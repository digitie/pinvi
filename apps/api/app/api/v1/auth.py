"""`/auth/*` — `docs/api/auth.md`."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.core.config import settings
from app.core.deps import DbSession
from app.core.security import create_access_token, generate_opaque_token
from app.schemas.auth import (
    AuthUser,
    LoginRequest,
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
    verify_email,
)

router = APIRouter(prefix="/auth", tags=["auth"])


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
async def register(
    body: RegisterRequest, db: DbSession
) -> Envelope[RegisterResponse]:
    try:
        result = await register_user(
            db,
            email=str(body.email),
            password=body.password,
            nickname=body.nickname,
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
                status=result.user.status,  # type: ignore[arg-type]
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


def _to_auth_user(user) -> AuthUser:  # type: ignore[no-untyped-def]
    return AuthUser(
        user_id=user.user_id,
        email=user.email,
        nickname=user.nickname,
        avatar_url=user.avatar_url,
        status=user.status,
        roles=user.roles,
        email_verified_at=user.email_verified_at,
    )
