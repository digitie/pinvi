"""`/auth/oauth/*` — Social OAuth (Google/Naver/Kakao) 안전 매칭.

`docs/api/auth.md` §6 / `docs/integrations/social-login.md`.
"""

from __future__ import annotations

import uuid
from typing import Any, Literal, cast
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.deps import CurrentUserId, DbSession
from app.core.session_cookies import set_session_cookies
from app.models.oauth_identity import UserOAuthIdentity
from app.models.user import User
from app.schemas.auth import AuthUser
from app.schemas.envelope import Envelope
from app.schemas.oauth import (
    OAuthLinkRequest,
    OAuthProvider,
    OAuthProviderInfo,
    OAuthProvidersResponse,
    OAuthStartRequest,
    OAuthStartResponse,
)
from app.services.auth_session import IssuedAuthSession, issue_user_session
from app.services.oauth_google import (
    OAuthError,
    OAuthProviderName,
    OAuthStateInvalidError,
    build_authorize_url,
    consume_login_state,
    exchange_code_for_claims,
    issue_login_state,
    link_oauth_to_user,
    mint_mobile_exchange,
    provider_configured,
    provider_label,
    resolve_oauth_login,
)

router = APIRouter(prefix="/auth/oauth", tags=["oauth"])

_PROVIDERS: tuple[OAuthProviderName, ...] = ("google", "naver", "kakao")


def _request_user_agent(request: Request) -> str | None:
    return request.headers.get("user-agent")


def _request_ip_address(request: Request) -> str | None:
    return request.client.host if request.client is not None else None


def _set_issue_cookies(response: RedirectResponse, issue: IssuedAuthSession) -> None:
    set_session_cookies(
        response,
        access_token=issue.access_token,
        refresh_token=issue.refresh_token,
    )


def _oauth_error_redirect(
    *,
    code: str,
    message: str,
    path: str = "/login",
    provider: OAuthProvider | None = None,
) -> RedirectResponse:
    params = {"error": code, "error_description": message}
    if provider is not None:
        params["provider"] = provider
    query = urlencode(params)
    target_path = path if path.startswith("/") else "/login"
    separator = "&" if "?" in target_path else "?"
    return RedirectResponse(
        url=f"{settings.pinvi_web_base_url}{target_path}{separator}{query}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


def _is_mobile_return(return_to_path: str | None) -> bool:
    """모바일 OAuth 흐름인지 — start가 return_to를 앱 딥링크 스킴으로 발급한 경우."""
    return bool(return_to_path) and return_to_path == settings.pinvi_mobile_oauth_redirect


def _mobile_redirect(*, params: dict[str, str]) -> RedirectResponse:
    """앱 딥링크(`pinvi://oauth`)로 리다이렉트. 토큰은 싣지 않고 1회용 code/에러만."""
    base = settings.pinvi_mobile_oauth_redirect
    separator = "&" if "?" in base else "?"
    return RedirectResponse(
        url=f"{base}{separator}{urlencode(params)}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


async def _provider_error_redirect(
    db: AsyncSession,
    *,
    provider: OAuthProvider,
    state: str | None,
    error_description: str | None,
) -> RedirectResponse:
    """Provider가 callback에 error를 실어 보낸 경우 — state를 조회해 모바일/웹/연결 흐름에 맞게 라우팅."""
    code = "OAUTH_PROVIDER_DENIED"
    message = error_description or f"{provider_label(provider)} 인증이 취소되었습니다."
    login_state = None
    if state:
        try:
            login_state = await consume_login_state(db, state=state)
            if login_state.provider != provider:
                login_state = None
        except OAuthStateInvalidError:
            login_state = None
    if login_state is not None and _is_mobile_return(login_state.return_to_path):
        return _mobile_redirect(params={"error": code, "error_description": message})
    error_path = "/login"
    if login_state is not None and login_state.mode == "link":
        error_path = login_state.return_to_path or "/login"
    return _oauth_error_redirect(code=code, message=message, path=error_path, provider=provider)


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
    )


@router.get("/providers", response_model=Envelope[OAuthProvidersResponse])
async def list_providers() -> Envelope[OAuthProvidersResponse]:
    """현재 사용 중인 OAuth provider 목록."""
    providers = [
        OAuthProviderInfo(
            provider=provider,
            enabled=provider_configured(provider),
        )
        for provider in _PROVIDERS
    ]
    return Envelope.of(OAuthProvidersResponse(providers=providers))


@router.post("/{provider}/start", response_model=Envelope[OAuthStartResponse])
async def oauth_start(
    provider: OAuthProvider,
    body: OAuthStartRequest,
    db: DbSession,
) -> Envelope[OAuthStartResponse]:
    """authorize URL 발급. 프론트는 반환된 URL로 redirect."""
    label = provider_label(provider)
    if body.mode != "login":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "OAUTH_LINK_REQUIRES_AUTH",
                "message": f"계정 연결은 /auth/oauth/{provider}/link endpoint를 사용해야 합니다.",
            },
        )
    if not provider_configured(provider):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "OAUTH_NOT_CONFIGURED", "message": f"{label} OAuth 미설정."},
        )
    state, nonce, code_verifier = await issue_login_state(
        db, provider=provider, mode=body.mode, return_to=body.return_to
    )
    url = build_authorize_url(
        provider=provider,
        state=state,
        nonce=nonce,
        code_verifier=code_verifier,
    )
    return Envelope.of(OAuthStartResponse(authorize_url=url))


@router.post("/{provider}/link", response_model=Envelope[OAuthStartResponse])
async def oauth_link(
    provider: OAuthProvider,
    body: OAuthLinkRequest,
    current_user_id: CurrentUserId,
    db: DbSession,
) -> Envelope[OAuthStartResponse]:
    """로그인된 사용자의 provider 연결 authorize URL 발급."""
    label = provider_label(provider)
    if not provider_configured(provider):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "OAUTH_NOT_CONFIGURED", "message": f"{label} OAuth 미설정."},
        )

    user_id = uuid.UUID(current_user_id)
    user_exists = await db.scalar(select(User.user_id).where(User.user_id == user_id))
    if user_exists is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "TOKEN_INVALID", "message": "사용자를 찾을 수 없습니다."},
        )

    state, nonce, code_verifier = await issue_login_state(
        db,
        provider=provider,
        mode="link",
        return_to=body.return_to,
        user_id=user_id,
    )
    url = build_authorize_url(
        provider=provider,
        state=state,
        nonce=nonce,
        code_verifier=code_verifier,
    )
    return Envelope.of(OAuthStartResponse(authorize_url=url))


@router.get("/{provider}/callback")
async def oauth_callback(
    provider: OAuthProvider,
    request: Request,
    db: DbSession,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    error_description: str | None = None,
) -> RedirectResponse:
    """Provider redirect 처리 — state 검증 → 토큰 교환 → 안전 매칭 → 세션 쿠키."""
    label = provider_label(provider)
    if error:
        return await _provider_error_redirect(
            db,
            provider=provider,
            state=state,
            error_description=error_description,
        )
    if not code or not state:
        return _oauth_error_redirect(
            code="OAUTH_CALLBACK_INVALID",
            message=f"{label} OAuth callback 파라미터가 올바르지 않습니다.",
            provider=provider,
        )

    try:
        login_state = await consume_login_state(db, state=state)
        if login_state.provider != provider:
            raise OAuthStateInvalidError("state provider가 callback provider와 일치하지 않습니다.")
    except OAuthStateInvalidError as exc:
        return _oauth_error_redirect(code=exc.code, message=str(exc), provider=provider)

    is_mobile = _is_mobile_return(login_state.return_to_path)

    def _flow_error(exc: OAuthError) -> RedirectResponse:
        if is_mobile:
            return _mobile_redirect(params={"error": exc.code, "error_description": str(exc)})
        error_path = login_state.return_to_path if login_state.mode == "link" else "/login"
        return _oauth_error_redirect(
            code=exc.code,
            message=str(exc),
            path=error_path or "/login",
            provider=provider,
        )

    try:
        claims = await exchange_code_for_claims(
            provider=provider,
            code=code,
            state=state,
            code_verifier=login_state.code_verifier,
        )
    except OAuthError as exc:
        return _flow_error(exc)

    try:
        if login_state.mode == "link" and login_state.user_id is not None:
            await link_oauth_to_user(
                db,
                provider=provider,
                user_id=login_state.user_id,
                claims=claims,
            )
            user_id = login_state.user_id
        else:
            result = await resolve_oauth_login(db, provider=provider, claims=claims)
            user_id = result.user.user_id
    except OAuthError as exc:
        return _flow_error(exc)

    if is_mobile:
        exchange_code = await mint_mobile_exchange(db, user_id=user_id)
        return _mobile_redirect(params={"code": exchange_code})

    return_to = login_state.return_to_path or "/"
    redirect = RedirectResponse(
        url=f"{settings.pinvi_web_base_url}{return_to}",
        status_code=status.HTTP_303_SEE_OTHER,
    )
    issue = await issue_user_session(
        db,
        user_id=user_id,
        user_agent=_request_user_agent(request),
        ip_address=_request_ip_address(request),
    )
    _set_issue_cookies(redirect, issue)
    return redirect


@router.delete("/{provider}", status_code=status.HTTP_204_NO_CONTENT)
async def unlink_oauth(
    provider: OAuthProvider, current_user_id: CurrentUserId, db: DbSession
) -> None:
    """Provider 연결 해제."""
    user_id = uuid.UUID(current_user_id)
    user = await db.scalar(select(User).where(User.user_id == user_id, User.deleted_at.is_(None)))
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "TOKEN_INVALID", "message": "사용자를 찾을 수 없습니다."},
        )
    if not user.password_hash:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "OAUTH_UNLINK_PASSWORD_REQUIRED",
                "message": "비밀번호가 없는 계정은 마지막 로그인 수단을 해제할 수 없습니다.",
            },
        )

    await db.execute(
        delete(UserOAuthIdentity).where(
            UserOAuthIdentity.user_id == user_id,
            UserOAuthIdentity.provider == provider,
        )
    )
    await db.commit()
