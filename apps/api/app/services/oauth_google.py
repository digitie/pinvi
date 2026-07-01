"""Social OAuth — Google/Naver/Kakao 안전 매칭 + state/PKCE 관리.

`docs/integrations/social-login.md` + `docs/api/auth.md` §6.

핵심 보안 정책:
- 기존 oauth identity(provider + provider_user_id)가 있으면 그 사용자로 로그인한다.
- 없고 같은 이메일의 로컬 계정이 있으면 자동 연결하지 않고 명시 연결을 요구한다.
- Google/Kakao처럼 provider가 verified email을 보증한 신규 이메일만 즉시 active 사용자로 만든다.
- Naver처럼 verified email 신호가 없는 provider는 pending_verification 사용자와 인증 메일을 만든다.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal
from urllib.parse import urlencode

import httpx
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.core.security import generate_opaque_token
from app.db import session as db_session
from app.middleware.api_call_logging import api_call_event_hooks
from app.models.oauth_identity import (
    OAuthLoginState,
    OAuthMobileExchange,
    UserOAuthIdentity,
)
from app.models.user import User
from app.models.user_email_verification import UserEmailVerification
from app.services.email_service import enqueue_verification_email
from app.services.user_registration import resend_verification_email

log = get_logger("oauth")

OAuthProviderName = Literal["google", "naver", "kakao"]

_GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"  # noqa: S105 - URL
_GOOGLE_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"
_GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"

_NAVER_TOKEN_URL = "https://nid.naver.com/oauth2.0/token"  # noqa: S105 - URL
_NAVER_USERINFO_URL = "https://openapi.naver.com/v1/nid/me"
_NAVER_AUTH_URL = "https://nid.naver.com/oauth2.0/authorize"

_KAKAO_TOKEN_URL = "https://kauth.kakao.com/oauth/token"  # noqa: S105 - URL
_KAKAO_USERINFO_URL = "https://kapi.kakao.com/v2/user/me"
_KAKAO_AUTH_URL = "https://kauth.kakao.com/oauth/authorize"

_SIGNUP_VERIFICATION_TTL_HOURS = 24
_VERIFIED_EMAIL_REQUIRED: set[OAuthProviderName] = {"google", "kakao"}
_PENDING_EMAIL_VERIFICATION_ALLOWED: set[OAuthProviderName] = {"naver"}
_PROVIDER_LABELS: dict[str, str] = {
    "google": "Google",
    "naver": "Naver",
    "kakao": "Kakao",
}


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


@dataclass(frozen=True)
class OAuthProviderConfig:
    provider: OAuthProviderName
    client_id: str
    client_secret: str
    auth_url: str
    token_url: str
    userinfo_url: str
    scope: str
    uses_pkce: bool
    include_nonce: bool


@dataclass
class OAuthClaims:
    """Provider userinfo에서 추출한 표준화 클레임."""

    provider_user_id: str
    email: str | None
    email_verified: bool
    display_name: str | None


GoogleClaims = OAuthClaims


@dataclass
class OAuthLoginResult:
    user: User
    created_user: bool
    linked_existing: bool


@dataclass
class ConsumedOAuthLoginState:
    provider: str
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


def provider_label(provider: str) -> str:
    return _PROVIDER_LABELS.get(provider, provider)


def get_provider_config(provider: OAuthProviderName) -> OAuthProviderConfig:
    if provider == "google":
        return OAuthProviderConfig(
            provider=provider,
            client_id=settings.pinvi_google_oauth_client_id,
            client_secret=settings.pinvi_google_oauth_client_secret,
            auth_url=_GOOGLE_AUTH_URL,
            token_url=_GOOGLE_TOKEN_URL,
            userinfo_url=_GOOGLE_USERINFO_URL,
            scope="openid email profile",
            uses_pkce=True,
            include_nonce=True,
        )
    if provider == "naver":
        return OAuthProviderConfig(
            provider=provider,
            client_id=settings.pinvi_naver_oauth_client_id,
            client_secret=settings.pinvi_naver_oauth_client_secret,
            auth_url=_NAVER_AUTH_URL,
            token_url=_NAVER_TOKEN_URL,
            userinfo_url=_NAVER_USERINFO_URL,
            scope="",
            uses_pkce=False,
            include_nonce=False,
        )
    return OAuthProviderConfig(
        provider=provider,
        client_id=settings.pinvi_kakao_oauth_rest_api_key,
        client_secret=settings.pinvi_kakao_oauth_client_secret,
        auth_url=_KAKAO_AUTH_URL,
        token_url=_KAKAO_TOKEN_URL,
        userinfo_url=_KAKAO_USERINFO_URL,
        scope="account_email profile_nickname",
        uses_pkce=False,
        include_nonce=False,
    )


def provider_configured(provider: OAuthProviderName) -> bool:
    config = get_provider_config(provider)
    if provider == "kakao":
        return bool(config.client_id)
    return bool(config.client_id and config.client_secret)


# ─────────────────────────────────────────────────────────────
# state 발급 / 소비 (CSRF + PKCE)
# ─────────────────────────────────────────────────────────────
async def issue_login_state(
    db: AsyncSession,
    *,
    provider: OAuthProviderName = "google",
    mode: str = "login",
    return_to: str = "/",
    user_id: uuid.UUID | None = None,
) -> tuple[str, str, str]:
    """state / nonce / PKCE verifier 반환 + hash만 DB 저장."""
    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(16)
    code_verifier = _derive_code_verifier(state)
    row = OAuthLoginState(
        state_hash=_hash(state),
        nonce_hash=_hash(nonce),
        pkce_code_verifier_hash=_hash(code_verifier),
        provider=provider,
        mode=mode,
        return_to_path=return_to,
        user_id=user_id,
        expires_at=datetime.now(UTC) + timedelta(seconds=settings.pinvi_oauth_state_ttl_seconds),
    )
    db.add(row)
    await db.commit()
    return state, nonce, code_verifier


async def consume_login_state(db: AsyncSession, *, state: str) -> ConsumedOAuthLoginState:
    state_hash = _hash(state)
    row = await db.scalar(select(OAuthLoginState).where(OAuthLoginState.state_hash == state_hash))
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
    now = datetime.now(UTC)
    consumed = await db.execute(
        update(OAuthLoginState)
        .where(
            OAuthLoginState.state_hash == state_hash,
            OAuthLoginState.consumed_at.is_(None),
        )
        .values(consumed_at=now)
        .returning(OAuthLoginState.state_hash)
        .execution_options(synchronize_session=False)
    )
    if consumed.scalar_one_or_none() is None:
        await db.rollback()
        raise OAuthStateInvalidError("이미 사용된 state 입니다.")
    await db.commit()
    return ConsumedOAuthLoginState(
        provider=row.provider,
        mode=row.mode,
        return_to_path=row.return_to_path,
        user_id=row.user_id,
        code_verifier=code_verifier,
    )


# ─────────────────────────────────────────────────────────────
# 모바일 1회용 교환 코드 (callback → 앱 딥링크 → exchange)
# ─────────────────────────────────────────────────────────────
async def mint_mobile_exchange(db: AsyncSession, *, user_id: uuid.UUID) -> str:
    """모바일 OAuth 성공 시 1회용 code 발급. plaintext code 반환, hash만 저장."""
    code = secrets.token_urlsafe(32)
    row = OAuthMobileExchange(
        code_hash=_hash(code),
        user_id=user_id,
        expires_at=datetime.now(UTC)
        + timedelta(seconds=settings.pinvi_mobile_oauth_exchange_ttl_seconds),
    )
    db.add(row)
    await db.commit()
    return code


async def consume_mobile_exchange(db: AsyncSession, *, code: str) -> uuid.UUID:
    """모바일 exchange code 소비 → user_id. 1회용 + TTL을 원자적 조건부 UPDATE로 보장."""
    now = datetime.now(UTC)
    code_hash = _hash(code)
    result = await db.execute(
        update(OAuthMobileExchange)
        .where(
            OAuthMobileExchange.code_hash == code_hash,
            OAuthMobileExchange.consumed_at.is_(None),
            OAuthMobileExchange.expires_at > now,
        )
        .values(consumed_at=now)
        .returning(OAuthMobileExchange.user_id)
        .execution_options(synchronize_session=False)
    )
    user_id = result.scalar_one_or_none()
    if user_id is not None:
        await db.commit()
        return user_id
    await db.rollback()
    row = await db.scalar(
        select(OAuthMobileExchange).where(OAuthMobileExchange.code_hash == code_hash)
    )
    if row is None:
        raise OAuthStateInvalidError("교환 코드가 존재하지 않습니다.")
    if row.consumed_at is not None:
        raise OAuthStateInvalidError("이미 사용된 교환 코드입니다.")
    raise OAuthStateInvalidError("교환 코드가 만료되었습니다.")


def build_authorize_url(
    *,
    state: str,
    nonce: str,
    code_verifier: str,
    provider: OAuthProviderName = "google",
) -> str:
    config = get_provider_config(provider)
    redirect_uri = f"{settings.pinvi_oauth_callback_base_url}/auth/oauth/{provider}/callback"
    params = {
        "client_id": config.client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "state": state,
    }
    if config.scope:
        params["scope"] = config.scope
    if config.include_nonce:
        params["nonce"] = nonce
    if config.uses_pkce:
        code_challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode()).digest())
            .decode()
            .rstrip("=")
        )
        params["code_challenge"] = code_challenge
        params["code_challenge_method"] = "S256"
        params["access_type"] = "offline"
    return f"{config.auth_url}?{urlencode(params)}"


def _token_request_data(
    *,
    provider: OAuthProviderName,
    code: str,
    state: str | None,
    code_verifier: str,
) -> dict[str, str]:
    config = get_provider_config(provider)
    redirect_uri = f"{settings.pinvi_oauth_callback_base_url}/auth/oauth/{provider}/callback"
    data = {
        "code": code,
        "client_id": config.client_id,
        "grant_type": "authorization_code",
    }
    if provider != "naver":
        data["redirect_uri"] = redirect_uri
    if config.client_secret:
        data["client_secret"] = config.client_secret
    if provider == "naver" and state:
        data["state"] = state
    if config.uses_pkce:
        data["code_verifier"] = code_verifier
    return data


def _claims_from_userinfo(provider: OAuthProviderName, info: dict[str, object]) -> OAuthClaims:
    if provider == "google":
        email = info.get("email")
        name = info.get("name")
        return OAuthClaims(
            provider_user_id=str(info["sub"]),
            email=email if isinstance(email, str) else None,
            email_verified=bool(info.get("email_verified", False)),
            display_name=name if isinstance(name, str) else None,
        )
    if provider == "naver":
        response = info.get("response")
        if not isinstance(response, dict) or not response.get("id"):
            raise OAuthProviderError("Naver userinfo id 누락")
        email = response.get("email")
        nickname = response.get("nickname") or response.get("name")
        return OAuthClaims(
            provider_user_id=str(response["id"]),
            email=email if isinstance(email, str) else None,
            email_verified=False,
            display_name=nickname if isinstance(nickname, str) else None,
        )
    account = info.get("kakao_account")
    account_data = account if isinstance(account, dict) else {}
    profile = account_data.get("profile")
    profile_data = profile if isinstance(profile, dict) else {}
    email_value = account_data.get("email")
    nickname_value = profile_data.get("nickname")
    email = email_value if isinstance(email_value, str) else None
    nickname = nickname_value if isinstance(nickname_value, str) else None
    if not info.get("id"):
        raise OAuthProviderError("Kakao userinfo id 누락")
    return OAuthClaims(
        provider_user_id=str(info["id"]),
        email=email,
        email_verified=bool(
            account_data.get("is_email_valid") and account_data.get("is_email_verified")
        ),
        display_name=nickname,
    )


# ─────────────────────────────────────────────────────────────
# HTTP 토큰 교환 + userinfo
# ─────────────────────────────────────────────────────────────
async def exchange_code_for_claims(
    *,
    code: str,
    code_verifier: str,
    state: str | None = None,
    provider: OAuthProviderName = "google",
    client: httpx.AsyncClient | None = None,
) -> OAuthClaims:
    config = get_provider_config(provider)
    owns_client = client is None
    http = client or httpx.AsyncClient(
        timeout=settings.pinvi_oauth_http_timeout_seconds,
        event_hooks=api_call_event_hooks(
            db_session.async_session_factory, provider=f"{provider}_oauth"
        ),
    )
    try:
        token_resp = await http.post(
            config.token_url,
            data=_token_request_data(
                provider=provider,
                code=code,
                state=state,
                code_verifier=code_verifier,
            ),
        )
        if token_resp.status_code != 200:
            raise OAuthProviderError(f"token exchange 실패: {token_resp.status_code}")
        access_token = token_resp.json().get("access_token")
        if not access_token:
            raise OAuthProviderError("access_token 누락")

        userinfo_resp = await http.get(
            config.userinfo_url,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if userinfo_resp.status_code != 200:
            raise OAuthProviderError(f"userinfo 실패: {userinfo_resp.status_code}")
        info = userinfo_resp.json()
    finally:
        if owns_client:
            await http.aclose()

    if not isinstance(info, dict):
        raise OAuthProviderError("userinfo 응답 형식이 올바르지 않습니다.")
    return _claims_from_userinfo(provider, info)


async def _enqueue_signup_verification(db: AsyncSession, *, user: User, now: datetime) -> bool:
    raw_token = generate_opaque_token(32)
    db.add(
        UserEmailVerification(
            user_id=user.user_id,
            token_hash=_hash(raw_token),
            purpose="signup",
            expires_at=now + timedelta(hours=_SIGNUP_VERIFICATION_TTL_HOURS),
        )
    )
    return await enqueue_verification_email(
        db,
        user_id=user.user_id,
        to_email=user.email,
        token=raw_token,
        expires_in_hours=_SIGNUP_VERIFICATION_TTL_HOURS,
    )


def _requires_verified_email(provider: OAuthProviderName) -> bool:
    return provider in _VERIFIED_EMAIL_REQUIRED


def _allows_pending_email_verification(provider: OAuthProviderName) -> bool:
    return provider in _PENDING_EMAIL_VERIFICATION_ALLOWED


# ─────────────────────────────────────────────────────────────
# 안전 매칭 (HTTP 없이 테스트 가능한 핵심)
# ─────────────────────────────────────────────────────────────
async def resolve_oauth_login(
    db: AsyncSession,
    *,
    provider: OAuthProviderName,
    claims: OAuthClaims,
) -> OAuthLoginResult:
    """Provider 클레임 → 로그인/연결/신규 결정."""
    now = datetime.now(UTC)
    label = provider_label(provider)

    identity = await db.scalar(
        select(UserOAuthIdentity).where(
            UserOAuthIdentity.provider == provider,
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
        if user.email_verified_at is None:
            await resend_verification_email(db, email=user.email)
            raise OAuthEmailUnverifiedError(
                "Pinvi 이메일 인증이 필요합니다. 인증 메일을 확인해 주세요."
            )
        await db.commit()
        await db.refresh(user)
        return OAuthLoginResult(user=user, created_user=False, linked_existing=False)

    if not claims.email:
        raise OAuthEmailUnverifiedError(f"{label} 계정의 이메일을 확인할 수 없습니다.")

    if _requires_verified_email(provider) and not claims.email_verified:
        raise OAuthEmailUnverifiedError(f"{label} 계정의 이메일 인증을 확인할 수 없습니다.")

    existing = await db.scalar(
        select(User).where(User.email == claims.email, User.deleted_at.is_(None))
    )
    if existing is not None:
        if existing.email_verified_at is None:
            raise OAuthEmailUnverifiedError("Pinvi 이메일 인증을 먼저 완료해 주세요.")
        raise OAuthAccountLinkRequiredError(
            "이미 같은 이메일의 Pinvi 계정이 있습니다. 이메일로 로그인한 뒤 "
            f"프로필에서 {label}을 연결해 주세요."
        )

    status = "active" if claims.email_verified else "pending_verification"
    user = User(
        email=claims.email,
        password_hash=None,
        nickname=claims.display_name,
        status=status,
        email_verified_at=now if claims.email_verified else None,
    )
    db.add(user)
    await db.flush()
    db.add(
        UserOAuthIdentity(
            user_id=user.user_id,
            provider=provider,
            provider_user_id=claims.provider_user_id,
            provider_email=claims.email,
            provider_email_verified=claims.email_verified,
            display_name_snapshot=claims.display_name,
            linked_at=now,
            last_login_at=now if claims.email_verified else None,
        )
    )
    if not claims.email_verified:
        if not _allows_pending_email_verification(provider):
            await db.rollback()
            raise OAuthEmailUnverifiedError(f"{label} 계정의 이메일 인증을 확인할 수 없습니다.")
        dispatched = await _enqueue_signup_verification(db, user=user, now=now)
        await db.commit()
        log.info(
            "oauth.created_pending_user",
            user_id=str(user.user_id),
            provider=provider,
            verification_email_dispatched=dispatched,
        )
        raise OAuthEmailUnverifiedError(
            "Pinvi 이메일 인증이 필요합니다. 인증 메일을 확인해 주세요."
        )
    await db.commit()
    await db.refresh(user)
    log.info("oauth.created_user", user_id=str(user.user_id), provider=provider)
    return OAuthLoginResult(user=user, created_user=True, linked_existing=False)


async def resolve_google_login(
    db: AsyncSession,
    *,
    claims: GoogleClaims,
) -> OAuthLoginResult:
    """Google 클레임 → 로그인/연결/신규 결정. 기존 호출자 호환 wrapper."""
    return await resolve_oauth_login(db, provider="google", claims=claims)


async def link_oauth_to_user(
    db: AsyncSession,
    *,
    provider: OAuthProviderName,
    user_id: uuid.UUID,
    claims: OAuthClaims,
) -> UserOAuthIdentity:
    """로그인된 사용자가 명시적으로 provider 계정을 연결."""
    label = provider_label(provider)
    if _requires_verified_email(provider) and (not claims.email or not claims.email_verified):
        raise OAuthEmailUnverifiedError(f"{label} 계정의 이메일 인증을 확인할 수 없습니다.")

    existing = await db.scalar(
        select(UserOAuthIdentity).where(
            UserOAuthIdentity.provider == provider,
            UserOAuthIdentity.provider_user_id == claims.provider_user_id,
        )
    )
    if existing is not None and existing.user_id != user_id:
        raise OAuthAccountLinkRequiredError(f"이 {label} 계정은 다른 사용자에 연결되어 있습니다.")
    now = datetime.now(UTC)
    if existing is not None:
        existing.last_login_at = now
        await db.commit()
        await db.refresh(existing)
        return existing

    linked_provider = await db.scalar(
        select(UserOAuthIdentity).where(
            UserOAuthIdentity.provider == provider,
            UserOAuthIdentity.user_id == user_id,
        )
    )
    if linked_provider is not None:
        raise OAuthAccountLinkRequiredError(f"이미 다른 {label} 계정이 연결되어 있습니다.")

    if claims.email:
        email_owner = await db.scalar(
            select(User).where(
                User.email == claims.email,
                User.user_id != user_id,
                User.deleted_at.is_(None),
            )
        )
        if email_owner is not None:
            raise OAuthAccountLinkRequiredError(
                f"이 {label} 이메일은 다른 Pinvi 계정과 일치합니다."
            )

    identity = UserOAuthIdentity(
        user_id=user_id,
        provider=provider,
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


async def link_google_to_user(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    claims: GoogleClaims,
) -> UserOAuthIdentity:
    """로그인된 사용자가 명시적으로 Google 계정을 연결. 기존 호출자 호환 wrapper."""
    return await link_oauth_to_user(db, provider="google", user_id=user_id, claims=claims)
