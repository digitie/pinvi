"""Google OAuth — 안전 매칭 (G-4) + state/PKCE 관리.

`docs/integrations/social-login.md` + `docs/api/auth.md` §6.

핵심 보안 정책 (G-4 안전 매칭):
- 기존 oauth identity (provider + provider_user_id) 가 있으면 그 사용자로 로그인.
- 없고, 같은 이메일의 로컬 계정이 있으면 → 자동 연결하지 않고 명시 연결을 요구한다
  (계정 탈취 방지).
- Google이 email_verified=true 로 보증한 신규 이메일만 provider-only 사용자로 만든다.

HTTP 토큰 교환 / userinfo 조회는 `exchange_code_for_claims` 로 분리 — 통합
테스트에서 claims 를 직접 주입(`resolve_google_login`)해 HTTP 없이 매칭 로직만
검증한다.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.models.oauth_identity import OAuthLoginState, UserOAuthIdentity
from app.models.user import User

log = get_logger("oauth_google")

_GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"  # noqa: S105 — URL, not a secret
_GOOGLE_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"
_GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"


class OAuthError(Exception):
    code: str = "OAUTH_ERROR"


class OAuthStateInvalidError(OAuthError):
    code = "OAUTH_STATE_INVALID"


class OAuthProviderError(OAuthError):
    code = "OAUTH_PROVIDER_ERROR"


class OAuthAccountLinkRequiredError(OAuthError):
    code = "OAUTH_ACCOUNT_LINK_REQUIRED"


class OAuthEmailUnverifiedError(OAuthError):
    code = "OAUTH_EMAIL_UNVERIFIED"


@dataclass
class GoogleClaims:
    """검증된 Google 사용자 클레임 (id_token / userinfo 에서 추출)."""

    provider_user_id: str
    email: str | None
    email_verified: bool
    display_name: str | None


@dataclass
class OAuthLoginResult:
    user: User
    created_user: bool
    linked_existing: bool


@dataclass
class ConsumedOAuthLoginState:
    mode: str
    return_to_path: str | None
    user_id: uuid.UUID | None
    code_verifier: str


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _derive_code_verifier(state: str) -> str:
    digest = hmac.new(
        settings.pinvi_jwt_secret_key.encode("utf-8"),
        f"pinvi-oauth-pkce:{state}".encode(),
        hashlib.sha256,
    ).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")


# ─────────────────────────────────────────────────────────────
# state 발급 / 소비 (CSRF + PKCE)
# ─────────────────────────────────────────────────────────────
async def issue_login_state(
    db: AsyncSession,
    *,
    mode: str = "login",
    return_to: str = "/",
    user_id: uuid.UUID | None = None,
) -> tuple[str, str, str]:
    """state / nonce / PKCE verifier 반환 + hash 만 DB 저장."""
    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(16)
    code_verifier = _derive_code_verifier(state)
    row = OAuthLoginState(
        state_hash=_hash(state),
        nonce_hash=_hash(nonce),
        pkce_code_verifier_hash=_hash(code_verifier),
        provider="google",
        mode=mode,
        return_to_path=return_to,
        user_id=user_id,
        expires_at=datetime.now(UTC) + timedelta(seconds=settings.pinvi_oauth_state_ttl_seconds),
    )
    db.add(row)
    await db.commit()
    return state, nonce, code_verifier


async def consume_login_state(db: AsyncSession, *, state: str) -> ConsumedOAuthLoginState:
    row = await db.scalar(select(OAuthLoginState).where(OAuthLoginState.state_hash == _hash(state)))
    if row is None:
        raise OAuthStateInvalidError("state 가 존재하지 않습니다.")
    if row.consumed_at is not None:
        raise OAuthStateInvalidError("이미 사용된 state 입니다.")
    if row.expires_at < datetime.now(UTC):
        raise OAuthStateInvalidError("state 가 만료되었습니다.")
    code_verifier = _derive_code_verifier(state)
    if row.pkce_code_verifier_hash and not hmac.compare_digest(
        row.pkce_code_verifier_hash,
        _hash(code_verifier),
    ):
        raise OAuthStateInvalidError("PKCE verifier 검증에 실패했습니다.")
    row.consumed_at = datetime.now(UTC)
    await db.commit()
    return ConsumedOAuthLoginState(
        mode=row.mode,
        return_to_path=row.return_to_path,
        user_id=row.user_id,
        code_verifier=code_verifier,
    )


def build_authorize_url(*, state: str, nonce: str, code_verifier: str) -> str:
    code_challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode()).digest())
        .decode()
        .rstrip("=")
    )
    redirect_uri = f"{settings.pinvi_oauth_callback_base_url}/auth/oauth/google/callback"
    params = {
        "client_id": settings.pinvi_google_oauth_client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "nonce": nonce,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "access_type": "offline",
    }
    return f"{_GOOGLE_AUTH_URL}?{urlencode(params)}"


# ─────────────────────────────────────────────────────────────
# HTTP 토큰 교환 + userinfo (실제 흐름)
# ─────────────────────────────────────────────────────────────
async def exchange_code_for_claims(
    *,
    code: str,
    code_verifier: str,
    client: httpx.AsyncClient | None = None,
) -> GoogleClaims:
    redirect_uri = f"{settings.pinvi_oauth_callback_base_url}/auth/oauth/google/callback"
    owns_client = client is None
    http = client or httpx.AsyncClient(timeout=settings.pinvi_oauth_http_timeout_seconds)
    try:
        token_resp = await http.post(
            _GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": settings.pinvi_google_oauth_client_id,
                "client_secret": settings.pinvi_google_oauth_client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
                "code_verifier": code_verifier,
            },
        )
        if token_resp.status_code != 200:
            raise OAuthProviderError(f"token exchange 실패: {token_resp.status_code}")
        access_token = token_resp.json().get("access_token")
        if not access_token:
            raise OAuthProviderError("access_token 누락")

        userinfo_resp = await http.get(
            _GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if userinfo_resp.status_code != 200:
            raise OAuthProviderError(f"userinfo 실패: {userinfo_resp.status_code}")
        info = userinfo_resp.json()
    finally:
        if owns_client:
            await http.aclose()

    return GoogleClaims(
        provider_user_id=str(info["sub"]),
        email=info.get("email"),
        email_verified=bool(info.get("email_verified", False)),
        display_name=info.get("name"),
    )


# ─────────────────────────────────────────────────────────────
# G-4 안전 매칭 (HTTP 없이 테스트 가능한 핵심)
# ─────────────────────────────────────────────────────────────
async def resolve_google_login(
    db: AsyncSession,
    *,
    claims: GoogleClaims,
) -> OAuthLoginResult:
    """Google 클레임 → 로그인/연결/신규 결정. G-4 안전 매칭."""
    now = datetime.now(UTC)

    # 1) 기존 identity → 그 사용자로 로그인
    identity = await db.scalar(
        select(UserOAuthIdentity).where(
            UserOAuthIdentity.provider == "google",
            UserOAuthIdentity.provider_user_id == claims.provider_user_id,
        )
    )
    if identity is not None:
        user = await db.scalar(select(User).where(User.user_id == identity.user_id))
        if user is None:
            raise OAuthError("identity 는 있으나 사용자가 없습니다.")
        identity.last_login_at = now
        identity.provider_email = claims.email
        identity.provider_email_verified = claims.email_verified
        await db.commit()
        await db.refresh(user)
        return OAuthLoginResult(user=user, created_user=False, linked_existing=False)

    if not claims.email or not claims.email_verified:
        raise OAuthEmailUnverifiedError("Google 계정의 이메일 인증을 확인할 수 없습니다.")

    # 2) 같은 이메일 로컬 계정 → 자동 연결 금지, 사용자가 로그인 후 profile에서 명시 연결.
    existing = await db.scalar(
        select(User).where(User.email == claims.email, User.deleted_at.is_(None))
    )
    if existing is not None:
        if existing.email_verified_at is None:
            raise OAuthEmailUnverifiedError("Pinvi 이메일 인증을 먼저 완료해 주세요.")
        raise OAuthAccountLinkRequiredError(
            "이미 같은 이메일의 Pinvi 계정이 있습니다. 이메일로 로그인한 뒤 "
            "프로필에서 Google을 연결해 주세요."
        )

    # 3) 신규 사용자 생성. Google이 email_verified=true 로 보증한 이메일만 계정 식별자로 쓴다.
    user = User(
        email=claims.email,
        password_hash=None,
        nickname=claims.display_name,
        status="active",
        email_verified_at=now,
    )
    db.add(user)
    await db.flush()
    db.add(
        UserOAuthIdentity(
            user_id=user.user_id,
            provider="google",
            provider_user_id=claims.provider_user_id,
            provider_email=claims.email,
            provider_email_verified=claims.email_verified,
            display_name_snapshot=claims.display_name,
            linked_at=now,
            last_login_at=now,
        )
    )
    await db.commit()
    await db.refresh(user)
    log.info("oauth.created_user", user_id=str(user.user_id), provider="google")
    return OAuthLoginResult(user=user, created_user=True, linked_existing=False)


async def link_google_to_user(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    claims: GoogleClaims,
) -> UserOAuthIdentity:
    """로그인된 사용자가 명시적으로 Google 계정 연결 (mode=link)."""
    if not claims.email or not claims.email_verified:
        raise OAuthEmailUnverifiedError("Google 계정의 이메일 인증을 확인할 수 없습니다.")

    existing = await db.scalar(
        select(UserOAuthIdentity).where(
            UserOAuthIdentity.provider == "google",
            UserOAuthIdentity.provider_user_id == claims.provider_user_id,
        )
    )
    if existing is not None and existing.user_id != user_id:
        raise OAuthAccountLinkRequiredError("이 Google 계정은 다른 사용자에 연결되어 있습니다.")
    now = datetime.now(UTC)
    if existing is not None:
        existing.last_login_at = now
        await db.commit()
        await db.refresh(existing)
        return existing

    linked_google = await db.scalar(
        select(UserOAuthIdentity).where(
            UserOAuthIdentity.provider == "google",
            UserOAuthIdentity.user_id == user_id,
        )
    )
    if linked_google is not None:
        raise OAuthAccountLinkRequiredError("이미 다른 Google 계정이 연결되어 있습니다.")

    email_owner = await db.scalar(
        select(User).where(
            User.email == claims.email,
            User.user_id != user_id,
            User.deleted_at.is_(None),
        )
    )
    if email_owner is not None:
        raise OAuthAccountLinkRequiredError("이 Google 이메일은 다른 Pinvi 계정과 일치합니다.")

    identity = UserOAuthIdentity(
        user_id=user_id,
        provider="google",
        provider_user_id=claims.provider_user_id,
        provider_email=claims.email,
        provider_email_verified=claims.email_verified,
        display_name_snapshot=claims.display_name,
        linked_at=now,
        last_login_at=now,
    )
    db.add(identity)
    await db.commit()
    await db.refresh(identity)
    return identity
