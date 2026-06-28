"""Admin rate-limit / abuse operations for T-282."""

from __future__ import annotations

import ipaddress
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Literal, cast

from sqlalchemy import func, literal, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.middleware.rate_limit import (
    IdentityKind,
    effective_rate_limit_backend_name,
    rate_limit_bucket_hash,
    rate_limit_identity_key,
    rate_limit_policies,
    rate_limit_policy_for_name,
)
from app.models.rate_limit import RateLimitBucket, RateLimitOverride
from app.schemas.admin import (
    AdminRateLimitAbuseSummary,
    AdminRateLimitBackendStatus,
    AdminRateLimitBucketRecord,
    AdminRateLimitOverrideCreateRequest,
    AdminRateLimitOverrideRecord,
    AdminRateLimitOverrideRollbackRequest,
    AdminRateLimitPolicyRecord,
    AdminRateLimitSuspiciousActivityRecord,
)
from app.services.hash_chain import sha256_hex

SUSPICIOUS_LIMIT_NAMES: tuple[str, ...] = (
    "auth_low",
    "shared_trip",
    "storage_upload_urls",
)


class RateLimitAbuseError(Exception):
    code = "RATE_LIMIT_ABUSE_ERROR"


class RateLimitOverrideNotFoundError(RateLimitAbuseError):
    code = "RATE_LIMIT_OVERRIDE_NOT_FOUND"


class RateLimitOverrideValidationError(RateLimitAbuseError):
    code = "INVALID_RATE_LIMIT_OVERRIDE"


class RateLimitOverrideTransitionError(RateLimitAbuseError):
    code = "INVALID_RATE_LIMIT_OVERRIDE_STATE"


async def build_rate_limit_abuse_summary(
    db: AsyncSession,
    *,
    limit_name: str | None,
    page_size: int,
) -> AdminRateLimitAbuseSummary:
    now = datetime.now(UTC)
    policies = [_policy_record(policy) for policy in rate_limit_policies()]
    backend = await _backend_status(db)
    if backend.store_status == "degraded":
        return AdminRateLimitAbuseSummary(
            generated_at=now,
            backend=backend,
            policies=policies,
        )

    buckets = await _list_bucket_records(db, now=now, limit_name=limit_name, page_size=page_size)
    overrides = await _list_override_records(
        db, now=now, limit_name=limit_name, page_size=page_size
    )
    suspicious = await _list_suspicious_records(db, now=now, page_size=page_size)
    rate_limited_bucket_count = await _rate_limited_bucket_count(db, now=now)
    active_override_count = int(
        await db.scalar(
            select(func.count(RateLimitOverride.override_id)).where(
                RateLimitOverride.revoked_at.is_(None),
                RateLimitOverride.expires_at > now,
            )
        )
        or 0
    )
    return AdminRateLimitAbuseSummary(
        generated_at=now,
        backend=backend,
        policies=policies,
        buckets=buckets,
        overrides=overrides,
        suspicious=suspicious,
        rate_limited_bucket_count=rate_limited_bucket_count,
        active_override_count=active_override_count,
        suspicious_count=len(suspicious),
    )


async def create_rate_limit_override(
    db: AsyncSession,
    *,
    body: AdminRateLimitOverrideCreateRequest,
    actor_user_id: uuid.UUID,
) -> RateLimitOverride:
    policy = _policy_or_error(body.limit_name)
    if policy.identity_kind != body.identity_kind:
        raise RateLimitOverrideValidationError(
            f"{body.limit_name} 정책은 {policy.identity_kind} identity만 지원합니다."
        )
    identity = _normalized_identity(body)
    raw_key = rate_limit_identity_key(body.identity_kind, **identity.raw_key_kwargs)
    bucket_hash = rate_limit_bucket_hash(policy.name, raw_key)
    now = datetime.now(UTC)
    row = RateLimitOverride(
        limit_name=policy.name,
        bucket_hash=bucket_hash,
        identity_kind=body.identity_kind,
        identity_fingerprint=identity.fingerprint,
        identity_label=identity.label,
        action=body.action,
        reason=body.access_reason,
        created_by_user_id=actor_user_id,
        expires_at=now + timedelta(minutes=body.ttl_minutes),
    )
    db.add(row)
    await db.flush()
    await db.refresh(row)
    return row


async def rollback_rate_limit_override(
    db: AsyncSession,
    *,
    override_id: uuid.UUID,
    body: AdminRateLimitOverrideRollbackRequest,
    actor_user_id: uuid.UUID,
) -> RateLimitOverride:
    now = datetime.now(UTC)
    row = await db.get(RateLimitOverride, override_id)
    if row is None:
        raise RateLimitOverrideNotFoundError("rate-limit override를 찾을 수 없습니다.")
    if row.revoked_at is not None:
        raise RateLimitOverrideTransitionError("이미 rollback된 override입니다.")
    if row.expires_at <= now:
        raise RateLimitOverrideTransitionError("이미 만료된 override입니다.")
    row.revoked_at = now
    row.revoked_by_user_id = actor_user_id
    row.revoked_reason = body.rollback_reason or body.access_reason
    await db.flush()
    await db.refresh(row)
    return row


def to_rate_limit_override_record(
    row: RateLimitOverride,
    *,
    now: datetime | None = None,
) -> AdminRateLimitOverrideRecord:
    current = now or datetime.now(UTC)
    return AdminRateLimitOverrideRecord(
        override_id=row.override_id,
        limit_name=row.limit_name,
        bucket_hash_prefix=_hash_prefix(row.bucket_hash),
        identity_kind=cast(Any, row.identity_kind),
        identity_label=row.identity_label,
        action=cast(Any, row.action),
        status=_override_status(row, now=current),
        reason=row.reason,
        created_by_user_id=row.created_by_user_id,
        expires_at=row.expires_at,
        revoked_at=row.revoked_at,
        revoked_by_user_id=row.revoked_by_user_id,
        revoked_reason=row.revoked_reason,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


async def _backend_status(db: AsyncSession) -> AdminRateLimitBackendStatus:
    effective_backend = effective_rate_limit_backend_name()
    store_status: Literal["ok", "degraded", "not_applicable"] = (
        "ok" if effective_backend == "postgres" else "not_applicable"
    )
    store_error_class: str | None = None
    store_error_message: str | None = None
    if effective_backend == "postgres":
        try:
            await db.execute(select(literal(1)).select_from(RateLimitBucket).limit(1))
        except SQLAlchemyError as exc:
            await db.rollback()
            store_status = "degraded"
            store_error_class = exc.__class__.__name__
            store_error_message = str(exc)

    return AdminRateLimitBackendStatus(
        enabled=settings.pinvi_rate_limit_enabled,
        configured_backend=settings.pinvi_rate_limit_backend,
        effective_backend=effective_backend,
        window_seconds=max(1, settings.pinvi_rate_limit_window_seconds),
        fail_open=settings.pinvi_rate_limit_fail_open,
        fail_closed=not settings.pinvi_rate_limit_fail_open,
        store_status=store_status,
        store_error_class=store_error_class,
        store_error_message=store_error_message,
    )


async def _list_bucket_records(
    db: AsyncSession,
    *,
    now: datetime,
    limit_name: str | None,
    page_size: int,
) -> list[AdminRateLimitBucketRecord]:
    conditions: list[Any] = [RateLimitBucket.expires_at >= now]
    if limit_name:
        _policy_or_error(limit_name)
        conditions.append(RateLimitBucket.limit_name == limit_name)
    rows = list(
        (
            await db.scalars(
                select(RateLimitBucket)
                .where(*conditions)
                .order_by(RateLimitBucket.count.desc(), RateLimitBucket.updated_at.desc())
                .limit(page_size)
            )
        ).all()
    )
    override_map = await _active_override_map(db, rows=rows, now=now)
    return [_bucket_record(row, override_map.get(row.bucket_hash), now=now) for row in rows]


async def _list_override_records(
    db: AsyncSession,
    *,
    now: datetime,
    limit_name: str | None,
    page_size: int,
) -> list[AdminRateLimitOverrideRecord]:
    conditions: list[Any] = []
    if limit_name:
        _policy_or_error(limit_name)
        conditions.append(RateLimitOverride.limit_name == limit_name)
    rows = list(
        (
            await db.scalars(
                select(RateLimitOverride)
                .where(*conditions)
                .order_by(RateLimitOverride.created_at.desc())
                .limit(page_size)
            )
        ).all()
    )
    return [to_rate_limit_override_record(row, now=now) for row in rows]


async def _list_suspicious_records(
    db: AsyncSession,
    *,
    now: datetime,
    page_size: int,
) -> list[AdminRateLimitSuspiciousActivityRecord]:
    rows = list(
        (
            await db.scalars(
                select(RateLimitBucket)
                .where(
                    RateLimitBucket.expires_at >= now,
                    RateLimitBucket.limit_name.in_(SUSPICIOUS_LIMIT_NAMES),
                )
                .order_by(RateLimitBucket.count.desc(), RateLimitBucket.updated_at.desc())
                .limit(page_size)
            )
        ).all()
    )
    override_map = await _active_override_map(db, rows=rows, now=now)
    records: list[AdminRateLimitSuspiciousActivityRecord] = []
    for row in rows:
        signal = _signal_for_limit_name(row.limit_name)
        if signal is None:
            continue
        records.append(
            AdminRateLimitSuspiciousActivityRecord(
                signal=signal,
                bucket=_bucket_record(row, override_map.get(row.bucket_hash), now=now),
            )
        )
    return records


async def _active_override_map(
    db: AsyncSession,
    *,
    rows: list[RateLimitBucket],
    now: datetime,
) -> dict[str, RateLimitOverride]:
    bucket_hashes = {row.bucket_hash for row in rows}
    if not bucket_hashes:
        return {}
    overrides = list(
        (
            await db.scalars(
                select(RateLimitOverride)
                .where(
                    RateLimitOverride.bucket_hash.in_(bucket_hashes),
                    RateLimitOverride.revoked_at.is_(None),
                    RateLimitOverride.expires_at > now,
                )
                .order_by(RateLimitOverride.created_at.desc())
            )
        ).all()
    )
    result: dict[str, RateLimitOverride] = {}
    for override in overrides:
        result.setdefault(override.bucket_hash, override)
    return result


async def _rate_limited_bucket_count(db: AsyncSession, *, now: datetime) -> int:
    rows = (
        await db.execute(
            select(RateLimitBucket.limit_name, RateLimitBucket.count).where(
                RateLimitBucket.expires_at >= now
            )
        )
    ).all()
    total = 0
    for limit_name, count in rows:
        try:
            limit = rate_limit_policy_for_name(limit_name).limit_per_minute
        except KeyError:
            continue
        if count > limit:
            total += 1
    return total


def _bucket_record(
    row: RateLimitBucket,
    override: RateLimitOverride | None,
    *,
    now: datetime,
) -> AdminRateLimitBucketRecord:
    identity_kind: IdentityKind
    try:
        policy = rate_limit_policy_for_name(row.limit_name)
        limit = policy.limit_per_minute
        identity_kind = policy.identity_kind
    except KeyError:
        limit = 0
        identity_kind = "ip"
    status: Literal["observed", "blocked", "allowed", "expired"] = "observed"
    if row.expires_at <= now:
        status = "expired"
    elif override is not None:
        status = cast(Literal["blocked", "allowed"], override.action)
    return AdminRateLimitBucketRecord(
        bucket_hash_prefix=_hash_prefix(row.bucket_hash),
        limit_name=row.limit_name,
        identity_kind=identity_kind,
        count=row.count,
        limit=limit,
        remaining=max(0, limit - row.count),
        rate_limited=limit > 0 and row.count > limit,
        window_start=row.window_start,
        expires_at=row.expires_at,
        updated_at=row.updated_at,
        status=status,
        active_override_id=override.override_id if override is not None else None,
        active_override_action=cast(Any, override.action) if override is not None else None,
    )


def _policy_record(policy: Any) -> AdminRateLimitPolicyRecord:
    return AdminRateLimitPolicyRecord(
        name=policy.name,
        limit_per_minute=policy.limit_per_minute,
        identity_kind=policy.identity_kind,
    )


def _policy_or_error(name: str) -> Any:
    try:
        return rate_limit_policy_for_name(name)
    except KeyError as exc:
        raise RateLimitOverrideValidationError(f"알 수 없는 rate-limit 정책입니다: {name}") from exc


def _override_status(
    row: RateLimitOverride,
    *,
    now: datetime,
) -> Literal["blocked", "allowed", "expired", "revoked"]:
    if row.revoked_at is not None:
        return "revoked"
    if row.expires_at <= now:
        return "expired"
    return cast(Literal["blocked", "allowed"], row.action)


class _Identity:
    def __init__(
        self,
        *,
        raw_key_kwargs: dict[str, str],
        fingerprint: str,
        label: str,
    ) -> None:
        self.raw_key_kwargs = raw_key_kwargs
        self.fingerprint = fingerprint
        self.label = label


def _normalized_identity(body: AdminRateLimitOverrideCreateRequest) -> _Identity:
    if body.identity_kind == "ip":
        ip = _normalize_ip(body.ip)
        digest = sha256_hex(f"ip:{ip}")
        return _Identity(
            raw_key_kwargs={"ip": ip},
            fingerprint=digest,
            label=f"ip_hash:{digest[:12]}",
        )
    if body.identity_kind == "ip_email":
        ip = _normalize_ip(body.ip)
        email = _normalize_email(body.email)
        digest = sha256_hex(f"ip_email:{ip}:{email}")
        return _Identity(
            raw_key_kwargs={"ip": ip, "email": email},
            fingerprint=digest,
            label=f"ip_email_hash:{digest[:12]}",
        )
    if body.identity_kind == "shared_token":
        token = (body.shared_token or "").strip()
        if len(token) < 8:
            raise RateLimitOverrideValidationError("shared_token은 최소 8자 이상이어야 합니다.")
        digest = sha256_hex(f"shared:{token}")
        return _Identity(
            raw_key_kwargs={"shared_token": token},
            fingerprint=digest,
            label=f"shared_token_hash:{digest[:12]}",
        )
    if body.user_id is None:
        raise RateLimitOverrideValidationError("user identity에는 user_id가 필요합니다.")
    user_id = str(body.user_id)
    digest = sha256_hex(f"user:{user_id}")
    return _Identity(
        raw_key_kwargs={"user_id": user_id},
        fingerprint=digest,
        label=f"user:{user_id}",
    )


def _normalize_ip(value: str | None) -> str:
    raw = (value or "").strip()
    try:
        return str(ipaddress.ip_address(raw))
    except ValueError as exc:
        raise RateLimitOverrideValidationError("ip 형식이 올바르지 않습니다.") from exc


def _normalize_email(value: str | None) -> str:
    email = (value or "").strip().lower()
    if "@" not in email:
        raise RateLimitOverrideValidationError("email 형식이 올바르지 않습니다.")
    return email


def _hash_prefix(value: str) -> str:
    return value[:16]


def _signal_for_limit_name(
    limit_name: str,
) -> (
    Literal["auth_low_repeated_attempt", "shared_token_pressure", "storage_upload_pressure"] | None
):
    if limit_name == "auth_low":
        return "auth_low_repeated_attempt"
    if limit_name == "shared_trip":
        return "shared_token_pressure"
    if limit_name == "storage_upload_urls":
        return "storage_upload_pressure"
    return None
