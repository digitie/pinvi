"""`/auth/oauth/google/*` — Google 소셜 로그인 (G-4 안전 매칭).

`docs/api/auth.md` §6 / `docs/integrations/social-login.md`.
"""

from __future__ import annotations

import uuid
from typing import Any, Literal, cast

from fastapi import APIRouter, HTTPException, Response, status
from fastapi.responses import RedirectResponse

from app.core.config import settings
from app.core.deps import CurrentUserId, DbSession
from app.core.security import create_access_token, generate_opaque_token
from app.schemas.auth import AuthUser
from app.schemas.envelope import Envelope
from app.schemas.oauth import (
    OAuthProviderInfo,
    OAuthProvidersResponse,
    OAuthStartRequest,
    OAuthStartResponse,
)
from app.services.oauth_google import (
    OAuthError,
    OAuthStateInvalidError,
    build_authorize_url,
    consume_login_state,
    exchange_code_for_claims,
    issue_login_state,
    link_google_to_user,
    resolve_google_login,
)

router = APIRouter(prefix="/auth/oauth", tags=["oauth"])


def _set_session_cookies(response: Response, *, user_id: str) -> None:
    access = create_access_token(subject=user_id)
    refresh = generate_opaque_token(32)
    secure = settings.tripmate_environment == "production"
    response.set_cookie(
        key="tripmate_access",
        value=access,
        httponly=True,
        secure=secure,
        samesite="lax",
        max_age=settings.tripmate_access_token_minutes * 60,
    )
    response.set_cookie(
        key="tripmate_refresh",
        value=refresh,
        httponly=True,
        secure=secure,
        samesite="lax",
        max_age=settings.tripmate_refresh_token_days * 24 * 60 * 60,
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
    )


@router.get("/providers", response_model=Envelope[OAuthProvidersResponse])
async def list_providers() -> Envelope[OAuthProvidersResponse]:
    """활성화된 OAuth provider 목록 (client id 가 설정된 것만 enabled)."""
    providers = [
        OAuthProviderInfo(
            provider="google",
            enabled=bool(settings.tripmate_google_oauth_client_id),
        ),
        OAuthProviderInfo(
            provider="naver",
            enabled=bool(settings.tripmate_naver_oauth_client_id),
        ),
        OAuthProviderInfo(
            provider="kakao",
            enabled=bool(settings.tripmate_kakao_oauth_rest_api_key),
        ),
    ]
    return Envelope.of(OAuthProvidersResponse(providers=providers))


@router.post("/google/start", response_model=Envelope[OAuthStartResponse])
async def google_start(body: OAuthStartRequest, db: DbSession) -> Envelope[OAuthStartResponse]:
    """authorize URL 발급. 프론트는 반환된 URL 로 redirect."""
    if not settings.tripmate_google_oauth_client_id:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "OAUTH_NOT_CONFIGURED", "message": "Google OAuth 미설정."},
        )
    state, nonce, code_verifier = await issue_login_state(
        db, mode=body.mode, return_to=body.return_to
    )
    url = build_authorize_url(state=state, nonce=nonce, code_verifier=code_verifier)
    return Envelope.of(OAuthStartResponse(authorize_url=url))


@router.get("/google/callback")
async def google_callback(
    code: str,
    state: str,
    response: Response,
    db: DbSession,
) -> RedirectResponse:
    """Google redirect 처리 — state 검증 → 토큰 교환 → 안전 매칭 → 세션 쿠키."""
    try:
        login_state = await consume_login_state(db, state=state)
    except OAuthStateInvalidError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc

    try:
        claims = await exchange_code_for_claims(
            code=code,
            code_verifier=login_state.code_verifier,
        )
    except OAuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc

    try:
        if login_state.mode == "link" and login_state.user_id is not None:
            await link_google_to_user(db, user_id=login_state.user_id, claims=claims)
            user_id = login_state.user_id
        else:
            result = await resolve_google_login(db, claims=claims)
            user_id = result.user.user_id
    except OAuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc

    return_to = login_state.return_to_path or "/"
    redirect = RedirectResponse(
        url=f"{settings.tripmate_web_base_url}{return_to}",
        status_code=status.HTTP_303_SEE_OTHER,
    )
    _set_session_cookies(redirect, user_id=str(user_id))
    return redirect


@router.delete("/google", status_code=status.HTTP_204_NO_CONTENT)
async def unlink_google(current_user_id: CurrentUserId, db: DbSession) -> None:
    """Google 연결 해제."""
    from sqlalchemy import delete

    from app.models.oauth_identity import UserOAuthIdentity

    await db.execute(
        delete(UserOAuthIdentity).where(
            UserOAuthIdentity.user_id == uuid.UUID(current_user_id),
            UserOAuthIdentity.provider == "google",
        )
    )
    await db.commit()
