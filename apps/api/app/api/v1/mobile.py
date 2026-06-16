"""모바일 전용 endpoint — `apps/mobile`(Expo Dev Client) 지원.

- VWorld 지도 키: 앱에 번들하지 않고 인증된 클라이언트에 server-issued로 발급(ADR-043).
- 모바일 인증(`/mobile/auth/*`): 웹은 httpOnly cookie를 쓰지만 모바일은 cookie를 못 쓰므로
  access/refresh 토큰을 **본문으로** 반환한다(expo-implementation-plan §5 #2). 같은 인증 서비스를
  재사용하며, 웹 `/auth/*`(cookie) 경로는 그대로 둔다.
"""

from __future__ import annotations

from typing import Any, Literal, cast

from fastapi import APIRouter, HTTPException, Request, status

from app.core.config import settings
from app.core.deps import CurrentUserId, DbSession
from app.schemas.auth import AuthUser, LoginRequest, VerifyEmailRequest
from app.schemas.envelope import Envelope
from app.schemas.mobile import (
    MobileAuthResponse,
    MobileRefreshRequest,
    MobileVWorldTokenResponse,
)
from app.services.auth_session import (
    RefreshTokenExpiredError,
    RefreshTokenInvalidError,
    issue_user_session,
    refresh_user_session,
    revoke_user_session,
)
from app.services.user_registration import (
    EmailNotVerifiedError,
    InvalidCredentialsError,
    VerificationTokenInvalidError,
    authenticate,
    verify_email,
)

router = APIRouter(prefix="/mobile", tags=["mobile"])


@router.get("/vworld/token", response_model=Envelope[MobileVWorldTokenResponse])
async def get_vworld_token(
    current_user_id: CurrentUserId,
) -> Envelope[MobileVWorldTokenResponse]:
    """인증된 모바일 클라이언트에 server-issued VWorld 키를 발급한다 (ADR-043).

    웹은 빌드타임 `NEXT_PUBLIC_VWORLD_API_KEY`를 쓰지만, 모바일 앱은 키를 번들하지 않고
    이 endpoint로 받는다(`apps/mobile/lib/config.ts`). 키 미설정 시 503.
    """
    if not settings.pinvi_vworld_api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "VWORLD_NOT_CONFIGURED",
                "message": "VWorld 지도 키가 설정되지 않았습니다.",
            },
        )
    return Envelope.of(
        MobileVWorldTokenResponse(
            api_key=settings.pinvi_vworld_api_key,
            ttl_seconds=settings.pinvi_vworld_token_ttl_seconds,
        )
    )


def _to_auth_user(user: Any) -> AuthUser:
    return AuthUser(
        user_id=user.user_id,
        email=user.email,
        nickname=user.nickname,
        avatar_url=user.avatar_url,
        status=user.status,
        roles=cast(list[Literal["user", "admin", "operator", "cpo"]], user.roles),
        email_verified_at=user.email_verified_at,
        has_password=bool(user.password_hash),
        oauth_identities=[],
    )


def _client_meta(request: Request) -> tuple[str | None, str | None]:
    user_agent = request.headers.get("user-agent")
    ip_address = request.client.host if request.client is not None else None
    return user_agent, ip_address


def _mobile_auth_response(user: Any, issue: Any) -> Envelope[MobileAuthResponse]:
    return Envelope.of(
        MobileAuthResponse(
            user=_to_auth_user(user),
            access_token=issue.access_token,
            refresh_token=issue.refresh_token,
            expires_at=issue.expires_at,
        )
    )


@router.post("/auth/login", response_model=Envelope[MobileAuthResponse])
async def mobile_login(
    body: LoginRequest, request: Request, db: DbSession
) -> Envelope[MobileAuthResponse]:
    """모바일 로그인 — access/refresh 토큰을 본문으로 반환(SecureStore 보관용)."""
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

    user_agent, ip_address = _client_meta(request)
    issue = await issue_user_session(
        db, user_id=user.user_id, user_agent=user_agent, ip_address=ip_address
    )
    return _mobile_auth_response(user, issue)


@router.post("/auth/verify-email", response_model=Envelope[MobileAuthResponse])
async def mobile_verify_email(
    body: VerifyEmailRequest, request: Request, db: DbSession
) -> Envelope[MobileAuthResponse]:
    """모바일 이메일 verify — 성공 시 로그인 상태로 토큰을 본문 반환."""
    try:
        user = await verify_email(db, token=body.token)
    except VerificationTokenInvalidError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": exc.code, "message": str(exc), "details": {"token": "invalid"}},
        ) from exc

    user_agent, ip_address = _client_meta(request)
    issue = await issue_user_session(
        db, user_id=user.user_id, user_agent=user_agent, ip_address=ip_address
    )
    return _mobile_auth_response(user, issue)


@router.post("/auth/refresh", response_model=Envelope[MobileAuthResponse])
async def mobile_refresh(
    body: MobileRefreshRequest, request: Request, db: DbSession
) -> Envelope[MobileAuthResponse]:
    """모바일 refresh — 본문 refresh token으로 새 access/refresh 토큰을 회전 발급."""
    user_agent, ip_address = _client_meta(request)
    try:
        refreshed = await refresh_user_session(
            db,
            refresh_token=body.refresh_token,
            user_agent=user_agent,
            ip_address=ip_address,
        )
    except (RefreshTokenExpiredError, RefreshTokenInvalidError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc

    return _mobile_auth_response(refreshed.user, refreshed.issue)


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
async def mobile_logout(body: MobileRefreshRequest, db: DbSession) -> None:
    """모바일 logout — 본문 refresh token으로 세션 폐기."""
    await revoke_user_session(db, refresh_token=body.refresh_token)
