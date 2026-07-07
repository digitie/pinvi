"""`/users/me/*` — `docs/api/users.md`."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from sqlalchemy import select

from app.api.request_url import public_api_base_url
from app.core.deps import CurrentUserId, DbSession
from app.core.session_cookies import clear_session_cookies
from app.models.attachment import CuratedPlanAttachment
from app.models.user import User
from app.schemas.consent import (
    ConsentItem,
    ConsentResponse,
    ConsentType,
    ConsentWithdrawRequest,
    ProfileCompleteRequest,
)
from app.schemas.dsr import (
    DsrRequestCreateRequest,
    DsrRequestListResponse,
    DsrRequestRecord,
    DsrRequestWithdrawRequest,
)
from app.schemas.envelope import Envelope
from app.schemas.mcp import McpTokenIssueRequest, McpTokenIssueResponse, McpTokenResponse
from app.schemas.moderation import (
    ContentReportAppealRequest,
    ContentReportCreateRequest,
    ContentReportListResponse,
    ContentReportRecord,
)
from app.schemas.storage import (
    AVATAR_CONTENT_TYPES,
    AttachmentLibraryItem,
    AttachmentLibraryPage,
    AvatarApplyRequest,
    AvatarInfo,
    AvatarUploadUrlRequest,
    DownloadUrlResponse,
    UploadUrlResponse,
)
from app.services.admin_user_lifecycle import self_delete_user
from app.services.admin_users import AdminUserPermissionError, AdminUserRoleTransitionError
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
from app.services.dsr_requests import (
    DsrRequestNotFoundError,
    DsrRequestTransitionError,
    create_dsr_request,
    list_user_dsr_requests,
    to_dsr_request_record,
    withdraw_dsr_request,
)
from app.services.mcp_tokens import (
    McpTokenNotFoundError,
    default_mcp_expires_at,
    issue_mcp_token,
    list_user_mcp_tokens,
    mask_mcp_token,
    revoke_mcp_token,
)
from app.services.moderation import (
    ContentReportNotFoundError,
    ContentReportPermissionError,
    ContentReportTransitionError,
    appeal_content_report,
    create_content_report,
    list_user_content_reports,
    to_content_report_record,
)
from app.services.rustfs_admin import delete_object
from app.services.rustfs_storage import (
    FileTooLargeError,
    InvalidStorageRefError,
    MimeNotAllowedError,
    make_download_url,
    make_upload_url,
)
from app.services.storage_policy import (
    attachment_scope,
    get_user_library_attachment,
    list_user_file_library,
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


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def delete_me(
    response: Response,
    current_user_id: CurrentUserId,
    db: DbSession,
) -> Response:
    try:
        await self_delete_user(db, user_id=uuid.UUID(current_user_id))
    except AdminUserPermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc
    except AdminUserRoleTransitionError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc
    await db.commit()
    clear_session_cookies(response)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


def _to_library_item(
    attachment: CuratedPlanAttachment,
    *,
    trip_title: str | None,
    poi_label: str | None,
) -> AttachmentLibraryItem:
    return AttachmentLibraryItem(
        attachment_id=attachment.attachment_id,
        trip_id=attachment.trip_id,
        trip_day_index=attachment.trip_day_index,
        trip_poi_id=attachment.trip_poi_id,
        curated_plan_id=attachment.curated_plan_id,
        curated_poi_id=attachment.curated_poi_id,
        notice_plan_id=attachment.notice_plan_id,
        notice_poi_id=attachment.notice_poi_id,
        source_attachment_id=attachment.source_attachment_id,
        bucket=attachment.bucket,
        storage_key=attachment.storage_key,
        original_filename=attachment.original_filename,
        content_type=attachment.content_type,
        byte_size=attachment.byte_size,
        public_url=attachment.public_url,
        role=attachment.role,
        description=attachment.description,
        sort_order=attachment.sort_order,
        created_at=attachment.created_at,
        updated_at=attachment.updated_at,
        target_scope=attachment_scope(attachment),
        uploaded_by_user_id=attachment.uploaded_by_user_id,
        trip_title=trip_title,
        poi_label=poi_label,
    )


@router.post("/avatar/upload-url", response_model=Envelope[UploadUrlResponse])
async def create_my_avatar_upload_url(
    body: AvatarUploadUrlRequest,
    request: Request,
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
            public_api_base_url=public_api_base_url(request),
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
    request: Request,
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
            public_api_base_url=public_api_base_url(request),
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


@router.get("/files", response_model=Envelope[AttachmentLibraryPage])
async def list_my_files(
    current_user_id: CurrentUserId,
    db: DbSession,
    page: int = 1,
    limit: int = 50,
) -> Envelope[AttachmentLibraryPage]:
    await _get_current_user(db, current_user_id)
    page = max(1, page)
    limit = min(100, max(1, limit))
    rows, total = await list_user_file_library(
        db,
        user_id=uuid.UUID(current_user_id),
        limit=limit,
        offset=(page - 1) * limit,
    )
    return Envelope.of(
        AttachmentLibraryPage(
            items=[
                _to_library_item(attachment, trip_title=trip_title, poi_label=poi_label)
                for attachment, trip_title, poi_label in rows
            ],
            total=total,
            page=page,
            limit=limit,
        )
    )


@router.get("/files/{attachment_id}/download-url", response_model=Envelope[DownloadUrlResponse])
async def get_my_file_download_url(
    attachment_id: uuid.UUID,
    request: Request,
    current_user_id: CurrentUserId,
    db: DbSession,
) -> Envelope[DownloadUrlResponse]:
    await _get_current_user(db, current_user_id)
    attachment = await get_user_library_attachment(
        db,
        user_id=uuid.UUID(current_user_id),
        attachment_id=attachment_id,
    )
    if attachment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "파일을 찾을 수 없습니다."},
        )
    try:
        response = make_download_url(
            bucket=attachment.bucket,
            storage_key=attachment.storage_key,
            public_url=attachment.public_url,
            public_api_base_url=public_api_base_url(request),
        )
    except Exception as exc:
        raise _storage_error(exc) from exc
    return Envelope.of(response)


@router.delete("/files/{attachment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_my_file(
    attachment_id: uuid.UUID,
    current_user_id: CurrentUserId,
    db: DbSession,
) -> None:
    await _get_current_user(db, current_user_id)
    attachment = await get_user_library_attachment(
        db,
        user_id=uuid.UUID(current_user_id),
        attachment_id=attachment_id,
    )
    if attachment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "파일을 찾을 수 없습니다."},
        )
    attachment.deleted_at = datetime.now(UTC)
    await db.commit()


@router.get("/dsr-requests", response_model=Envelope[DsrRequestListResponse])
async def list_my_dsr_requests(
    current_user_id: CurrentUserId,
    db: DbSession,
    page_size: int = Query(default=50, ge=1, le=100),
) -> Envelope[DsrRequestListResponse]:
    await _get_current_user(db, current_user_id)
    result = await list_user_dsr_requests(
        db,
        user_id=uuid.UUID(current_user_id),
        page_size=page_size,
    )
    return Envelope.of(result)


@router.post(
    "/dsr-requests",
    status_code=status.HTTP_201_CREATED,
    response_model=Envelope[DsrRequestRecord],
)
async def create_my_dsr_request(
    body: DsrRequestCreateRequest,
    current_user_id: CurrentUserId,
    db: DbSession,
) -> Envelope[DsrRequestRecord]:
    user = await _get_current_user(db, current_user_id)
    row = await create_dsr_request(db, user=user, body=body)
    await db.commit()
    return Envelope.of(to_dsr_request_record(row))


@router.post(
    "/dsr-requests/{request_id}/withdraw",
    response_model=Envelope[DsrRequestRecord],
)
async def withdraw_my_dsr_request(
    request_id: uuid.UUID,
    body: DsrRequestWithdrawRequest,
    current_user_id: CurrentUserId,
    db: DbSession,
) -> Envelope[DsrRequestRecord]:
    await _get_current_user(db, current_user_id)
    try:
        row = await withdraw_dsr_request(
            db,
            request_id=request_id,
            user_id=uuid.UUID(current_user_id),
            body=body,
        )
    except DsrRequestNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "DSR 요청을 찾을 수 없습니다."},
        ) from exc
    except DsrRequestTransitionError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "INVALID_STATE", "message": str(exc)},
        ) from exc
    await db.commit()
    return Envelope.of(to_dsr_request_record(row))


@router.get("/content-reports", response_model=Envelope[ContentReportListResponse])
async def list_my_content_reports(
    current_user_id: CurrentUserId,
    db: DbSession,
    page_size: int = Query(default=50, ge=1, le=100),
) -> Envelope[ContentReportListResponse]:
    await _get_current_user(db, current_user_id)
    result = await list_user_content_reports(
        db,
        user_id=uuid.UUID(current_user_id),
        page_size=page_size,
    )
    return Envelope.of(result)


@router.post(
    "/content-reports",
    status_code=status.HTTP_201_CREATED,
    response_model=Envelope[ContentReportRecord],
)
async def create_my_content_report(
    body: ContentReportCreateRequest,
    current_user_id: CurrentUserId,
    db: DbSession,
) -> Envelope[ContentReportRecord]:
    await _get_current_user(db, current_user_id)
    try:
        row = await create_content_report(
            db,
            reporter_user_id=uuid.UUID(current_user_id),
            body=body,
        )
    except ContentReportNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "신고 대상을 찾을 수 없습니다."},
        ) from exc
    except ContentReportPermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "PERMISSION_DENIED", "message": "신고 대상 접근 권한이 없습니다."},
        ) from exc
    await db.commit()
    return Envelope.of(to_content_report_record(row))


@router.post(
    "/content-reports/{report_id}/appeal",
    response_model=Envelope[ContentReportRecord],
)
async def appeal_my_content_report(
    report_id: uuid.UUID,
    body: ContentReportAppealRequest,
    current_user_id: CurrentUserId,
    db: DbSession,
) -> Envelope[ContentReportRecord]:
    await _get_current_user(db, current_user_id)
    try:
        row = await appeal_content_report(
            db,
            report_id=report_id,
            actor_user_id=uuid.UUID(current_user_id),
            body=body,
        )
    except ContentReportNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "신고를 찾을 수 없습니다."},
        ) from exc
    except ContentReportTransitionError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "INVALID_STATE", "message": str(exc)},
        ) from exc
    await db.commit()
    return Envelope.of(to_content_report_record(row))


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
