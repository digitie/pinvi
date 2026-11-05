"""HTTP rate-limit middleware.

Production/staging uses a PostgreSQL fixed-window bucket so multiple Uvicorn
workers and deployment nodes share the same counters. Development/test defaults
to process-local memory to keep unit tests and local shells lightweight.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import re
import uuid
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from math import ceil
from typing import Final, Literal, Protocol, cast

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.config import settings
from app.core.errors import build_error
from app.core.security import InvalidTokenError, decode_access_token
from app.db import session as db_session

logger = logging.getLogger(__name__)

IdentityKind = Literal["ip", "ip_email", "user", "shared_token"]
BackendName = Literal["memory", "postgres"]

USER_LIMIT_NAMES: Final[tuple[str, ...]] = (
    "authenticated_default",
    "feature_search",
    "storage_upload_urls",
    "trip_exports",
)


def _configured_user_limit(policy_name: str, raw_key: str) -> int | None:
    """_identity_key의 검증된 user prefix만 설정 membership으로 사용한다."""
    if policy_name not in USER_LIMIT_NAMES or not raw_key.startswith("user:"):
        return None
    subject = raw_key[len("user:") :]
    try:
        if str(uuid.UUID(subject)) != subject:
            return None
    except ValueError:
        return None
    return settings.pinvi_rate_limit_user_limit_overrides.get(subject)


def configured_user_bucket_limits() -> dict[tuple[str, str], int]:
    """관리자 관측에도 같은 기존 HMAC identity의 유효 상한을 적용한다. UUID는 응답하지 않는다."""
    return {
        (name, _bucket_hash(name, "user:" + subject)): cap
        for subject, cap in settings.pinvi_rate_limit_user_limit_overrides.items()
        for name in USER_LIMIT_NAMES
    }


AUTH_LOW_PATHS: Final[set[str]] = {
    "/auth/login",
    "/auth/register",
    "/auth/verify-email",
    "/auth/password/reset-request",
    "/auth/password/reset",
}
OAUTH_LIMIT_PATH_RE: Final[re.Pattern[str]] = re.compile(
    r"^/auth/oauth/(providers|[^/]+/(start|callback))$"
)
TRIP_EXPORT_PATH_RE: Final[re.Pattern[str]] = re.compile(r"^/trips/[^/]+/exports/")
SHARED_TRIP_PATH_RE: Final[re.Pattern[str]] = re.compile(
    r"^/trips/[^/]+/shared/([^/]+)(?:/comments(?:/[^/]+)?)?$"
)


@dataclass(frozen=True)
class RateLimitPolicy:
    name: str
    limit_per_minute: int
    identity_kind: IdentityKind


@dataclass(frozen=True)
class RateLimitOverrideDecision:
    override_id: uuid.UUID
    action: Literal["blocked", "allowed"]
    expires_at: datetime


@dataclass(frozen=True)
class RateLimitStoreResult:
    count: int
    override: RateLimitOverrideDecision | None = None


class RateLimitBackend(Protocol):
    async def hit(
        self,
        *,
        bucket_hash: str,
        limit_name: str,
        window_start: datetime,
        expires_at: datetime,
    ) -> int:
        """Increment a bucket and return the new count."""


class MemoryRateLimitBackend:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._counts: dict[tuple[str, datetime], tuple[int, datetime]] = {}

    def reset(self) -> None:
        """누적 카운트를 비운다 — 테스트 격리(모듈 싱글톤이 테스트 간 누적되지 않게)."""
        self._counts.clear()

    async def hit(
        self,
        *,
        bucket_hash: str,
        limit_name: str,
        window_start: datetime,
        expires_at: datetime,
    ) -> int:
        del limit_name
        now = datetime.now(UTC)
        async with self._lock:
            expired_keys = [
                key
                for key, (_, bucket_expires_at) in self._counts.items()
                if bucket_expires_at < now
            ]
            for key in expired_keys:
                self._counts.pop(key, None)

            key = (bucket_hash, window_start)
            count = self._counts.get(key, (0, expires_at))[0] + 1
            self._counts[key] = (count, expires_at)
            return count


class PostgresRateLimitBackend:
    _UPSERT_SQL: Final = text(
        """
        INSERT INTO app.rate_limit_buckets (
          bucket_hash, window_start, limit_name, count, expires_at
        )
        VALUES (:bucket_hash, :window_start, :limit_name, 1, :expires_at)
        ON CONFLICT (bucket_hash, window_start)
        DO UPDATE SET
          count = app.rate_limit_buckets.count + 1,
          limit_name = EXCLUDED.limit_name,
          expires_at = GREATEST(app.rate_limit_buckets.expires_at, EXCLUDED.expires_at),
          updated_at = now()
        RETURNING count
        """
    )
    # override와 증가는 같은 statement snapshot에서 결정한다. configured cap이 있으면
    # 과거 allowed는 우회가 아니며 blocked는 생성 순서와 무관하게 우선한다.
    _CHECK_SQL: Final = text(
        """
        WITH active_override AS MATERIALIZED (
          SELECT override_id, action, expires_at
          FROM app.rate_limit_overrides
          WHERE bucket_hash = :bucket_hash AND limit_name = :limit_name
            AND revoked_at IS NULL AND expires_at > :now
          ORDER BY CASE WHEN :prefer_blocked THEN action = 'blocked' ELSE false END DESC,
                   created_at DESC
          LIMIT 1
        ), incremented AS (
          INSERT INTO app.rate_limit_buckets (
            bucket_hash, window_start, limit_name, count, expires_at
          )
          SELECT :bucket_hash, :window_start, :limit_name, 1, :expires_at
          WHERE NOT EXISTS (
            SELECT 1 FROM active_override
            WHERE action = 'blocked' OR NOT :prefer_blocked
          )
          ON CONFLICT (bucket_hash, window_start)
          DO UPDATE SET
            count = app.rate_limit_buckets.count + 1,
            limit_name = EXCLUDED.limit_name,
            expires_at = GREATEST(app.rate_limit_buckets.expires_at, EXCLUDED.expires_at),
            updated_at = now()
          RETURNING count
        )
        SELECT COALESCE((SELECT count FROM incremented), 0) AS count,
               active_override.override_id, active_override.action, active_override.expires_at
        FROM (VALUES (1)) AS one_row(value)
        LEFT JOIN active_override ON true
        """
    )

    async def check(
        self,
        *,
        bucket_hash: str,
        limit_name: str,
        window_start: datetime,
        expires_at: datetime,
        now: datetime,
        prefer_blocked: bool = False,
    ) -> RateLimitStoreResult:
        async with db_session.async_session_factory() as session:
            row = (
                await session.execute(
                    self._CHECK_SQL,
                    {
                        "bucket_hash": bucket_hash,
                        "limit_name": limit_name,
                        "window_start": window_start,
                        "expires_at": expires_at,
                        "now": now,
                        "prefer_blocked": prefer_blocked,
                    },
                )
            ).one()
            decision = (
                RateLimitOverrideDecision(
                    override_id=row.override_id,
                    action=cast(Literal["blocked", "allowed"], row.action),
                    expires_at=row.expires_at,
                )
                if row.override_id is not None
                else None
            )
            await session.commit()
            return RateLimitStoreResult(count=int(row._mapping["count"]), override=decision)

    async def hit(
        self,
        *,
        bucket_hash: str,
        limit_name: str,
        window_start: datetime,
        expires_at: datetime,
    ) -> int:
        async with db_session.async_session_factory() as session:
            result = await session.execute(
                self._UPSERT_SQL,
                {
                    "bucket_hash": bucket_hash,
                    "window_start": window_start,
                    "limit_name": limit_name,
                    "expires_at": expires_at,
                },
            )
            count = int(result.scalar_one())
            await session.commit()
            return count


_MEMORY_BACKEND = MemoryRateLimitBackend()
_POSTGRES_BACKEND = PostgresRateLimitBackend()


class RateLimitMiddleware:
    def __init__(self, app: ASGIApp, backend: RateLimitBackend | None = None) -> None:
        self.app = app
        self._backend = backend

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not settings.pinvi_rate_limit_enabled:
            await self.app(scope, receive, send)
            return

        request = Request(scope)
        path = request.url.path
        method = request.method.upper()
        if method == "OPTIONS" or _is_bypass_path(path):
            await self.app(scope, receive, send)
            return

        policy = _policy_for_request(path)
        body_messages: list[Message] | None = None
        email: str | None = None
        if policy.identity_kind == "ip_email" and _can_peek_body(request):
            body_messages = await _collect_body(receive)
            receive = _replay_receive(body_messages)
            email = _email_from_body(request, _body_bytes(body_messages))

        now = datetime.now(UTC)
        window_seconds = max(1, settings.pinvi_rate_limit_window_seconds)
        window_start = _window_start(now, window_seconds)
        expires_at = window_start + timedelta(seconds=window_seconds * 2)
        raw_key = _identity_key(request, path=path, policy=policy, email=email)
        bucket_hash = _bucket_hash(policy.name, raw_key)
        configured_limit = _configured_user_limit(policy.name, raw_key)
        effective_limit = (
            configured_limit if configured_limit is not None else policy.limit_per_minute
        )

        override_decision = None
        count = 0
        store_unavailable = False
        # 이 경계에는 저장소 I/O만 둔다. 응답 전송이나 핸들러 오류를 한도 오류로
        # 재분류하면 fail-open에서 이미 실행한 사용자 mutation을 다시 실행할 수 있다.
        try:
            if self._uses_postgres_store():
                result = await _POSTGRES_BACKEND.check(
                    bucket_hash=bucket_hash,
                    limit_name=policy.name,
                    window_start=window_start,
                    expires_at=expires_at,
                    now=now,
                    prefer_blocked=configured_limit is not None,
                )
                override_decision, count = result.override, result.count
            else:
                count = await self._backend_for_settings().hit(
                    bucket_hash=bucket_hash,
                    limit_name=policy.name,
                    window_start=window_start,
                    expires_at=expires_at,
                )
        except SQLAlchemyError as exc:
            store_unavailable = True
            logger.warning(
                "rate_limit.store_unavailable",
                extra={"error_type": type(exc).__name__, "limit_name": policy.name},
            )

        if store_unavailable and not settings.pinvi_rate_limit_fail_open:
            response = JSONResponse(
                status_code=503,
                content=build_error(
                    "SERVICE_UNAVAILABLE",
                    "요청 한도 확인 저장소를 사용할 수 없습니다.",
                ),
            )
            await response(scope, receive, send)
            return

        if override_decision is not None and override_decision.action == "blocked":
            retry_after = max(
                1,
                min(3600, ceil((override_decision.expires_at - now).total_seconds())),
            )
            response = JSONResponse(
                status_code=429,
                content=build_error(
                    "RATE_LIMIT_BLOCKED",
                    "운영 정책에 따라 요청이 일시 차단되었습니다.",
                    {
                        "limit_name": policy.name,
                        "override_id": str(override_decision.override_id),
                        "expires_at": override_decision.expires_at.isoformat(),
                    },
                ),
                headers={"Retry-After": str(retry_after)},
            )
            await response(scope, receive, send)
            return

        if count > effective_limit:
            retry_after = _retry_after_seconds(now, window_start, window_seconds)
            response = JSONResponse(
                status_code=429,
                content=build_error(
                    "RATE_LIMITED",
                    "요청 한도를 초과했습니다. 잠시 후 다시 시도해 주세요.",
                    {"limit": effective_limit, "window_seconds": window_seconds},
                ),
                headers={"Retry-After": str(retry_after)},
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)

    def _uses_postgres_store(self) -> bool:
        return self._backend is None and _effective_backend_name() == "postgres"

    def _backend_for_settings(self) -> RateLimitBackend:
        if self._backend is not None:
            return self._backend
        backend = _effective_backend_name()
        if backend == "postgres":
            return _POSTGRES_BACKEND
        return _MEMORY_BACKEND


def _effective_backend_name() -> BackendName:
    configured = settings.pinvi_rate_limit_backend.lower().strip()
    if configured == "auto":
        return "postgres" if settings.pinvi_environment in {"production", "staging"} else "memory"
    if configured == "postgres":
        return "postgres"
    return "memory"


def effective_rate_limit_backend_name() -> BackendName:
    return _effective_backend_name()


def rate_limit_policy_for_name(name: str) -> RateLimitPolicy:
    if name == "public":
        return RateLimitPolicy(
            "public",
            settings.pinvi_rate_limit_public_per_minute,
            "ip",
        )
    if name == "auth_low":
        return RateLimitPolicy(
            "auth_low",
            settings.pinvi_rate_limit_auth_per_minute,
            "ip_email",
        )
    if name == "oauth":
        return RateLimitPolicy(
            "oauth",
            settings.pinvi_rate_limit_oauth_per_minute,
            "ip",
        )
    if name == "storage_upload_urls":
        return RateLimitPolicy(
            "storage_upload_urls",
            settings.pinvi_rate_limit_storage_upload_per_minute,
            "user",
        )
    if name == "feature_search":
        return RateLimitPolicy(
            "feature_search",
            settings.pinvi_rate_limit_feature_search_per_minute,
            "user",
        )
    if name == "trip_exports":
        return RateLimitPolicy(
            "trip_exports",
            settings.pinvi_rate_limit_trip_export_per_minute,
            "user",
        )
    if name == "shared_trip":
        return RateLimitPolicy(
            "shared_trip",
            settings.pinvi_rate_limit_shared_token_per_minute,
            "shared_token",
        )
    if name == "authenticated_default":
        return RateLimitPolicy(
            "authenticated_default",
            settings.pinvi_rate_limit_authenticated_per_minute,
            "user",
        )
    raise KeyError(name)


def rate_limit_policies() -> list[RateLimitPolicy]:
    return [
        rate_limit_policy_for_name(name)
        for name in [
            "public",
            "auth_low",
            "oauth",
            "storage_upload_urls",
            "feature_search",
            "trip_exports",
            "shared_trip",
            "authenticated_default",
        ]
    ]


def _policy_for_request(path: str) -> RateLimitPolicy:
    normalized_path = _normalize_path(path)
    if normalized_path.startswith("/public/"):
        return rate_limit_policy_for_name("public")
    if normalized_path in AUTH_LOW_PATHS:
        return rate_limit_policy_for_name("auth_low")
    if OAUTH_LIMIT_PATH_RE.match(normalized_path):
        return rate_limit_policy_for_name("oauth")
    if normalized_path == "/storage/upload-urls":
        return rate_limit_policy_for_name("storage_upload_urls")
    if normalized_path in {"/features/in-bounds", "/search", "/weather/markers-in-bounds"}:
        # T-368: weather marker는 /features/in-bounds와 같은 pan/zoom 이벤트로
        # 병렬 호출되므로 같은 버킷이어야 한다 — 다르면 빠른 팬 중 weather marker만
        # 조용히 사라진다.
        return rate_limit_policy_for_name("feature_search")
    if TRIP_EXPORT_PATH_RE.match(normalized_path):
        return rate_limit_policy_for_name("trip_exports")
    if SHARED_TRIP_PATH_RE.match(normalized_path):
        return rate_limit_policy_for_name("shared_trip")
    return rate_limit_policy_for_name("authenticated_default")


def _normalize_path(path: str) -> str:
    if path.startswith("/v1/"):
        return path[3:]
    return path


def _is_bypass_path(path: str) -> bool:
    return any(
        path == bypass or path.startswith(f"{bypass}/")
        for bypass in settings.pinvi_rate_limit_bypass_paths
    )


def _identity_key(
    request: Request,
    *,
    path: str,
    policy: RateLimitPolicy,
    email: str | None,
) -> str:
    if policy.identity_kind == "ip":
        return f"ip:{_client_ip(request)}"
    if policy.identity_kind == "ip_email":
        email_part = email or "unknown"
        return f"ip:{_client_ip(request)}:email:{email_part}"
    if policy.identity_kind == "shared_token":
        match = SHARED_TRIP_PATH_RE.match(_normalize_path(path))
        token = match.group(1) if match is not None else "unknown"
        return f"shared:{token}"

    subject = _access_token_subject(request)
    if subject is not None:
        return f"user:{subject}"
    bearer_token = _bearer_token(request)
    if bearer_token:
        return f"bearer:{bearer_token}"
    return f"ip:{_client_ip(request)}"


def rate_limit_identity_key(
    identity_kind: IdentityKind,
    *,
    ip: str | None = None,
    email: str | None = None,
    user_id: str | None = None,
    shared_token: str | None = None,
) -> str:
    if identity_kind == "ip":
        return f"ip:{ip or 'unknown'}"
    if identity_kind == "ip_email":
        email_part = (email or "unknown").strip().lower() or "unknown"
        return f"ip:{ip or 'unknown'}:email:{email_part}"
    if identity_kind == "shared_token":
        return f"shared:{shared_token or 'unknown'}"
    return f"user:{user_id or 'unknown'}"


def _client_ip(request: Request) -> str:
    header_name = settings.pinvi_rate_limit_client_ip_header.strip()
    if header_name:
        header_value = request.headers.get(header_name)
        if header_value:
            return header_value.split(",", 1)[0].strip()
    if request.client is None:
        return "unknown"
    return request.client.host


def _can_peek_body(request: Request) -> bool:
    content_type = request.headers.get("content-type", "")
    if "application/json" not in content_type.lower():
        return False
    content_length = request.headers.get("content-length")
    if content_length is None:
        return False
    try:
        length = int(content_length)
    except ValueError:
        return False
    return 0 <= length <= settings.pinvi_rate_limit_body_peek_max_bytes


def _access_token_subject(request: Request) -> str | None:
    token = request.cookies.get("pinvi_access")
    if token is None:
        token = _bearer_token(request)
    if token is None:
        return None
    try:
        payload = decode_access_token(token)
    except InvalidTokenError:
        return None
    subject = payload.get("sub")
    return subject if isinstance(subject, str) else None


def _bearer_token(request: Request) -> str | None:
    authorization = request.headers.get("authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    return token


def _bucket_hash(policy_name: str, raw_key: str) -> str:
    digest = hmac.new(
        settings.pinvi_jwt_secret_key.encode("utf-8"),
        f"{policy_name}:{raw_key}".encode(),
        hashlib.sha256,
    )
    return digest.hexdigest()


def rate_limit_bucket_hash(policy_name: str, raw_key: str) -> str:
    return _bucket_hash(policy_name, raw_key)


_CLEANUP_SQL: Final = text(
    """
    WITH expired AS (
      SELECT bucket_hash, window_start
      FROM app.rate_limit_buckets
      WHERE expires_at < :cutoff
      ORDER BY expires_at
      LIMIT :batch_size
      FOR UPDATE SKIP LOCKED
    )
    DELETE FROM app.rate_limit_buckets AS bucket
    USING expired
    WHERE bucket.bucket_hash = expired.bucket_hash
      AND bucket.window_start = expired.window_start
    RETURNING 1
    """
)


async def cleanup_expired_rate_limit_buckets(*, batch_size: int = 1000) -> int:
    """요청과 독립된 짧은 transaction에서 만료 bucket만 제한 수량 정리한다."""
    if batch_size < 1:
        raise ValueError("batch_size는 양수여야 합니다.")
    async with db_session.async_session_factory() as session:
        result = await session.execute(
            _CLEANUP_SQL, {"cutoff": datetime.now(UTC), "batch_size": batch_size}
        )
        count = len(result.all())
        await session.commit()
        return count


class RateLimitBucketCleanup:
    """API lifespan 소유 task. 한도 요청은 이 task나 청소를 기다리지 않는다."""

    def __init__(self, *, interval_seconds: float = 60.0, timeout_seconds: float = 5.0) -> None:
        if interval_seconds <= 0 or timeout_seconds <= 0:
            raise ValueError("청소 주기와 timeout은 양수여야 합니다.")
        self._interval_seconds = interval_seconds
        self._timeout_seconds = timeout_seconds
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run(), name="rate-limit-bucket-cleanup")

    async def stop(self) -> None:
        if self._task is None:
            return
        task = self._task
        task.cancel()
        try:
            with suppress(asyncio.CancelledError):
                await task
        finally:
            self._task = None

    async def _run(self) -> None:
        while True:
            await asyncio.sleep(self._interval_seconds)
            try:
                async with asyncio.timeout(self._timeout_seconds):
                    await cleanup_expired_rate_limit_buckets()
            except (SQLAlchemyError, TimeoutError) as exc:
                logger.warning(
                    "rate_limit.cleanup_failed",
                    extra={"error_type": type(exc).__name__},
                )


async def _collect_body(receive: Receive) -> list[Message]:
    messages: list[Message] = []
    while True:
        message = await receive()
        messages.append(message)
        if message["type"] != "http.request" or not message.get("more_body", False):
            break
    return messages


def _replay_receive(messages: list[Message]) -> Receive:
    index = 0

    async def receive() -> Message:
        nonlocal index
        if index < len(messages):
            message = messages[index]
            index += 1
            return message
        return {"type": "http.request", "body": b"", "more_body": False}

    return receive


def _body_bytes(messages: list[Message]) -> bytes:
    body = b""
    for message in messages:
        if message["type"] == "http.request":
            body += cast(bytes, message.get("body", b""))
    return body


def _email_from_body(request: Request, body: bytes) -> str | None:
    if len(body) > settings.pinvi_rate_limit_body_peek_max_bytes:
        return None
    content_type = request.headers.get("content-type", "")
    if "application/json" not in content_type.lower():
        return None
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    email = payload.get("email")
    if not isinstance(email, str):
        return None
    normalized = email.strip().lower()
    return normalized or None


def _window_start(now: datetime, window_seconds: int) -> datetime:
    epoch_seconds = int(now.timestamp())
    window_epoch = epoch_seconds - (epoch_seconds % window_seconds)
    return datetime.fromtimestamp(window_epoch, UTC)


def _retry_after_seconds(now: datetime, window_start: datetime, window_seconds: int) -> int:
    reset_at = window_start + timedelta(seconds=window_seconds)
    return max(1, ceil((reset_at - now).total_seconds()))
