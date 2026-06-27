"""`/users/me/*` — `docs/api/users.md`."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.core.deps import CurrentUserId, DbSession
from app.models.user import User
from app.schemas.consent import (
    ConsentItem,
    ConsentResponse,
    ConsentType,
    ConsentWithdrawRequest,
    ProfileCompleteRequest,
)
from app.schemas.envelope import Envelope
from app.schemas.mcp import McpTokenIssueRequest, McpTokenIssueResponse, McpTokenResponse
from app.schemas.storage import (
    AVATAR_CONTENT_TYPES,
    AvatarApplyRequest,
    AvatarInfo,
    AvatarUploadUrlRequest,
    DownloadUrlResponse,
    UploadUrlResponse,
)
from app.services.avatar_storage import (
    apply_avatar,
    avatar_info,
    clear_avatar,
    get_storage_settings,
    validate_avatar_apply,
)
from app.services.consent import (
    ConsentNotFoundError,
    list_user_consents,
    record_consents,
    withdraw_consent,
)
from app.services.mcp_tokens import (
    McpTokenNotFoundError,
    default_mcp_expires_at,
    issue_mcp_token,
    list_user_mcp_tokens,
    mask_mcp_token,
    revoke_mcp_token,
)
from app.services.rustfs_admin import delete_object
from app.services.rustfs_storage import (
    FileTooLargeError,
    InvalidStorageRefError,
    MimeNotAllowedError,
    make_download_url,
    make_upload_url,
)

router = APIRouter(prefix="/users/me", tags=["users"])


async def _get_current_user(db: DbSession, current_user_id: CurrentUserId) -> User:
    user = await db.scalar(
        select(User).where(User.user_id == uuid.UUID(current_user_id), User.deleted_at.is_(None))
    )
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "Not found."},
        )
    return user


def _storage_error(exc: Exception) -> HTTPException:
    if isinstance(exc, (FileTooLargeError, MimeNotAllowedError, InvalidStorageRefError)):
        return HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": exc.code, "message": str(exc)},
        )
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail={"code": "STORAGE_UNAVAILABLE", "message": "객체 저장소 요청에 실패했습니다."},
    )


def _effective_expires_at(body: McpTokenIssueRequest) -> datetime | None:
    if "expires_at" in body.model_fields_set:
        return body.expires_at
    return default_mcp_expires_at()


def _mcp_token_response(row) -> McpTokenResponse:  # type: ignore[no-untyped-def]
    return McpTokenResponse(
        token_id=row.token_id,
        name=row.name,
        scopes=row.scopes,
        masked_token=mask_mcp_token(row),
        expires_at=row.expires_at,
        last_used_at=row.last_used_at,
        revoked_at=row.revoked_at,
        created_at=row.created_at,
    )


@router.post("/avatar/upload-url", response_model=Envelope[UploadUrlResponse])
async def create_my_avatar_upload_url(
    body: AvatarUploadUrlRequest,
    current_user_id: CurrentUserId,
    db: DbSession,
) -> Envelope[UploadUrlResponse]:
    await _get_current_user(db, current_user_id)
    settings_row = await get_storage_settings(db)
    try:
        response = make_upload_url(
            purpose="avatar",
            user_id=uuid.UUID(current_user_id),
            filename=body.filename,
            content_type=body.content_type,
            content_length=body.content_length,
            max_upload_bytes=settings_row.avatar_max_upload_bytes,
            allowed_content_types=AVATAR_CONTENT_TYPES,
        )
    except (FileTooLargeError, MimeNotAllowedError) as exc:
        raise _storage_error(exc) from exc
    return Envelope.of(response)


@router.put("/avatar", response_model=Envelope[AvatarInfo])
async def update_my_avatar(
    body: AvatarApplyRequest,
    current_user_id: CurrentUserId,
    db: DbSession,
) -> Envelope[AvatarInfo]:
    user = await _get_current_user(db, current_user_id)
    settings_row = await get_storage_settings(db)
    try:
        validate_avatar_apply(
            body,
            user_id=user.user_id,
            max_upload_bytes=settings_row.avatar_max_upload_bytes,
        )
    except (FileTooLargeError, MimeNotAllowedError, InvalidStorageRefError) as exc:
        raise _storage_error(exc) from exc
    apply_avatar(user, body)
    await db.commit()
    await db.refresh(user)
    return Envelope.of(avatar_info(user))


@router.get("/avatar/download-url", response_model=Envelope[DownloadUrlResponse])
async def get_my_avatar_download_url(
    current_user_id: CurrentUserId,
    db: DbSession,
) -> Envelope[DownloadUrlResponse]:
    user = await _get_current_user(db, current_user_id)
    if not user.avatar_bucket or not user.avatar_storage_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "아바타가 없습니다."},
        )
    try:
        response = make_download_url(
            bucket=user.avatar_bucket,
            storage_key=user.avatar_storage_key,
            public_url=user.avatar_url,
        )
    except Exception as exc:
        raise _storage_error(exc) from exc
    return Envelope.of(response)


@router.delete("/avatar", response_model=Envelope[AvatarInfo])
async def delete_my_avatar(
    current_user_id: CurrentUserId,
    db: DbSession,
) -> Envelope[AvatarInfo]:
    user = await _get_current_user(db, current_user_id)
    if user.avatar_storage_key:
        try:
            await delete_object(key=user.avatar_storage_key)
        except Exception as exc:
            raise _storage_error(exc) from exc
    clear_avatar(user)
    await db.commit()
    await db.refresh(user)
    return Envelope.of(avatar_info(user))


@router.post(
    "/profile/complete",
    response_model=Envelope[list[ConsentResponse]],
)
async def complete_profile(
    body: ProfileCompleteRequest,
    current_user_id: CurrentUserId,
    db: DbSession,
) -> Envelope[list[ConsentResponse]]:
    # 사용자 모델 갱신은 별 service에서 (Sprint 2 후속 — 본 endpoint는 동의 + 닉네임만)
    rows = await record_consents(db, user_id=uuid.UUID(current_user_id), consents=body.consents)
    return Envelope.of(
        [
            ConsentResponse(
                consent_type=row.consent_type,
                version=row.version,
                agreed_at=row.agreed_at,
                withdrawn_at=row.withdrawn_at,
            )
            for row in rows
        ]
    )


def _to_consent_responses(rows: list) -> list[ConsentResponse]:  # type: ignore[type-arg]
    return [
        ConsentResponse(
            consent_type=row.consent_type,
            version=row.version,
            agreed_at=row.agreed_at,
            withdrawn_at=row.withdrawn_at,
        )
        for row in rows
    ]


@router.put("/consents", response_model=Envelope[list[ConsentResponse]])
async def put_consents(
    body: list[ConsentItem],
    current_user_id: CurrentUserId,
    db: DbSession,
) -> Envelope[list[ConsentResponse]]:
    """동의 항목 기록 (idempotent). `docs/api/users.md` §3."""
    rows = await record_consents(db, user_id=uuid.UUID(current_user_id), consents=body)
    return Envelope.of(_to_consent_responses(rows))


@router.delete("/consents/{consent_type}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_consent(
    consent_type: ConsentType,
    current_user_id: CurrentUserId,
    db: DbSession,
) -> None:
    """동의 철회 + 부작용 (demographic_use → 인구통계 컬럼 NULL)."""
    try:
        await withdraw_consent(db, user_id=uuid.UUID(current_user_id), consent_type=consent_type)
    except ConsentNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc


@router.get("/consents", response_model=Envelope[list[ConsentResponse]])
async def get_consents(
    current_user_id: CurrentUserId, db: DbSession
) -> Envelope[list[ConsentResponse]]:
    rows = await list_user_consents(db, user_id=uuid.UUID(current_user_id))
    return Envelope.of(
        [
            ConsentResponse(
                consent_type=row.consent_type,
                version=row.version,
                agreed_at=row.agreed_at,
                withdrawn_at=row.withdrawn_at,
            )
            for row in rows
        ]
    )


@router.get("/mcp-tokens", response_model=Envelope[list[McpTokenResponse]])
async def list_mcp_tokens_endpoint(
    current_user_id: CurrentUserId,
    db: DbSession,
) -> Envelope[list[McpTokenResponse]]:
    rows = await list_user_mcp_tokens(db, user_id=uuid.UUID(current_user_id))
    return Envelope.of([_mcp_token_response(row) for row in rows])


@router.post("/mcp-tokens", response_model=Envelope[McpTokenIssueResponse], status_code=201)
async def issue_mcp_token_endpoint(
    body: McpTokenIssueRequest,
    current_user_id: CurrentUserId,
    db: DbSession,
) -> Envelope[McpTokenIssueResponse]:
    row, raw = await issue_mcp_token(
        db,
        user_id=uuid.UUID(current_user_id),
        name=body.name,
        expires_at=_effective_expires_at(body),
        scopes=body.scopes,
    )
    await db.commit()
    await db.refresh(row)
    base = _mcp_token_response(row)
    return Envelope.of(McpTokenIssueResponse(**base.model_dump(), token=raw))


@router.delete("/mcp-tokens/{token_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_mcp_token_endpoint(
    token_id: uuid.UUID,
    current_user_id: CurrentUserId,
    db: DbSession,
) -> None:
    try:
        await revoke_mcp_token(db, token_id=token_id, user_id=uuid.UUID(current_user_id))
    except McpTokenNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc
    await db.commit()


@router.post(
    "/consents/withdraw",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def withdraw_consent_endpoint(
    body: ConsentWithdrawRequest, current_user_id: CurrentUserId, db: DbSession
) -> None:
    try:
        await withdraw_consent(
            db, user_id=uuid.UUID(current_user_id), consent_type=body.consent_type
        )
    except ConsentNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc
