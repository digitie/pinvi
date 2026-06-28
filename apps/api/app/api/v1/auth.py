"""`/auth/*` — `docs/api/auth.md`."""

from __future__ import annotations

import uuid
from typing import Annotated, Any, Literal, cast

from fastapi import APIRouter, Cookie, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy import select

from app.core.deps import CurrentUserId, DbSession
from app.core.errors import build_error
from app.core.session_cookies import clear_session_cookies, set_session_cookies
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
    VerifyEmailResendRequest,
    VerifyEmailResendResponse,
)
from app.schemas.envelope import Envelope
from app.services.auth_session import (
    IssuedAuthSession,
    RefreshTokenExpiredError,
    RefreshTokenInvalidError,
    issue_user_session,
    refresh_user_session,
    revoke_user_session,
)
from app.services.user_registration import (
    EmailAlreadyUsedError,
    EmailNotVerifiedError,
    InvalidCredentialsError,
    VerificationTokenInvalidError,
    authenticate,
    register_user,
    request_password_reset,
    resend_verification_email,
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


def _request_user_agent(request: Request) -> str | None:
    return request.headers.get("user-agent")


def _request_ip_address(request: Request) -> str | None:
    return request.client.host if request.client is not None else None


def _set_issue_cookies(response: Response, issue: IssuedAuthSession) -> None:
    set_session_cookies(
        response,
        access_token=issue.access_token,
        refresh_token=issue.refresh_token,
    )


async def _issue_session_and_set_cookies(
    response: Response,
    *,
    db: DbSession,
    request: Request,
    user_id: uuid.UUID,
) -> None:
    issue = await issue_user_session(
        db,
        user_id=user_id,
        user_agent=_request_user_agent(request),
        ip_address=_request_ip_address(request),
    )
    _set_issue_cookies(response, issue)


def _auth_error_with_cleared_cookies(
    *,
    status_code: int,
    code: str,
    message: str,
) -> JSONResponse:
    response = JSONResponse(status_code=status_code, content=build_error(code, message))
    clear_session_cookies(response)
    return response


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
                    Literal[
                        "pending_verification",
                        "pending_profile",
                        "active",
                        "disabled",
                        "pending_delete",
                        "deleted",
                    ],
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
    request: Request,
    db: DbSession,
) -> Envelope[AuthUser]:
    try:
        user = await verify_email(db, token=body.token)
    except VerificationTokenInvalidError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": exc.code, "message": str(exc), "details": {"token": "invalid"}},
        ) from exc

    await _issue_session_and_set_cookies(response, db=db, request=request, user_id=user.user_id)
    return Envelope.of(_to_auth_user(user))


@router.post(
    "/verify-email/resend",
    response_model=Envelope[VerifyEmailResendResponse],
)
async def verify_email_resend(
    body: VerifyEmailResendRequest,
    db: DbSession,
) -> Envelope[VerifyEmailResendResponse]:
    """미인증 계정의 가입 인증 메일 재발송 요청.

    user enumeration을 막기 위해 대상 존재/발송 여부와 무관하게 항상 `accepted=true`를
    반환한다(비밀번호 재설정 요청과 동일 정책). 실제 발송은 cooldown/적격 여부를 서비스가 판단.
    """
    await resend_verification_email(db, email=str(body.email))
    return Envelope.of(VerifyEmailResendResponse(accepted=True))


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
    request: Request,
    db: DbSession,
) -> Envelope[AuthUser]:
    try:
        user = await reset_password(db, token=body.token, new_password=body.new_password)
    except VerificationTokenInvalidError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": exc.code, "message": str(exc), "details": {"token": "invalid"}},
        ) from exc

    await _issue_session_and_set_cookies(response, db=db, request=request, user_id=user.user_id)
    return Envelope.of(_to_auth_user(user))


@router.post("/login", response_model=Envelope[AuthUser])
async def login(
    body: LoginRequest,
    response: Response,
    request: Request,
    db: DbSession,
) -> Envelope[AuthUser]:
    try:
        user = await authenticate(db, email=str(body.email), password=body.password)
    except EmailNotVerifiedError as exc:
        # 비밀번호 검증을 통과한 미인증 계정 — 재인증(가입 인증) 링크를 재발송한다.
        # 올바른 비밀번호로 소유가 증명됐으므로 dispatched 결과 노출은 enumeration 위험이 없다.
        resend = await resend_verification_email(db, email=str(body.email))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": exc.code,
                "message": str(exc),
                "details": {"verification_email_dispatched": resend.verification_email_dispatched},
            },
        ) from exc
    except InvalidCredentialsError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc

    await _issue_session_and_set_cookies(response, db=db, request=request, user_id=user.user_id)
    return Envelope.of(_to_auth_user(user))


@router.post("/refresh", response_model=Envelope[AuthUser])
async def refresh_session(
    response: Response,
    request: Request,
    db: DbSession,
    pinvi_refresh: Annotated[str | None, Cookie(alias="pinvi_refresh")] = None,
) -> Envelope[AuthUser] | JSONResponse:
    if not pinvi_refresh:
        return _auth_error_with_cleared_cookies(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="TOKEN_INVALID",
            message="refresh cookie가 없습니다.",
        )

    try:
        refreshed = await refresh_user_session(
            db,
            refresh_token=pinvi_refresh,
            user_agent=_request_user_agent(request),
            ip_address=_request_ip_address(request),
        )
    except RefreshTokenExpiredError as exc:
        return _auth_error_with_cleared_cookies(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code=exc.code,
            message=str(exc),
        )
    except RefreshTokenInvalidError as exc:
        return _auth_error_with_cleared_cookies(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code=exc.code,
            message=str(exc),
        )

    _set_issue_cookies(response, refreshed.issue)
    return Envelope.of(_to_auth_user(refreshed.user))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    response: Response,
    db: DbSession,
    pinvi_refresh: Annotated[str | None, Cookie(alias="pinvi_refresh")] = None,
) -> Response:
    await revoke_user_session(db, refresh_token=pinvi_refresh)
    clear_session_cookies(response)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


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
        avatar_kind=user.avatar_kind,
        avatar_content_type=user.avatar_content_type,
        avatar_byte_size=user.avatar_byte_size,
        avatar_updated_at=user.avatar_updated_at,
        has_avatar=bool(user.avatar_bucket and user.avatar_storage_key),
        status=user.status,
        roles=cast(list[Literal["user", "admin", "operator", "cpo"]], user.roles),
        email_verified_at=user.email_verified_at,
        has_password=bool(user.password_hash),
        oauth_identities=oauth_identities or [],
    )
