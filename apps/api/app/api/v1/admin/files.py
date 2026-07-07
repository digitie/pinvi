"""`/admin/files/*` — 여행/날짜/POI 첨부 파일 운영."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy import select

from app.api.request_url import public_api_base_url
from app.core.deps import DbSession
from app.core.rbac import require_role
from app.models.attachment import CuratedPlanAttachment
from app.models.user import User
from app.schemas.admin import AdminActionRequest
from app.schemas.envelope import Envelope
from app.schemas.storage import (
    AttachmentLibraryItem,
    AttachmentLibraryPage,
    DownloadUrlResponse,
)
from app.services.admin_audit import append_admin_audit
from app.services.admin_users import mask_email
from app.services.rustfs_storage import make_download_url
from app.services.storage_policy import (
    AttachmentScope,
    attachment_scope,
    attachment_state,
    list_admin_file_library,
)

router = APIRouter(prefix="/admin/files", tags=["admin"])


def _parse_request_id(value: str | None) -> uuid.UUID:
    if value is None:
        return uuid.uuid4()
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "VALIDATION_ERROR",
                "message": "X-Request-Id 형식이 올바르지 않습니다.",
            },
        ) from exc


def _to_library_item(
    attachment: CuratedPlanAttachment,
    *,
    trip_title: str | None,
    poi_label: str | None,
    uploaded_by_email: str,
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
        uploaded_by_email_masked=mask_email(uploaded_by_email),
        trip_title=trip_title,
        poi_label=poi_label,
    )


async def _get_attachment(db: DbSession, attachment_id: uuid.UUID) -> CuratedPlanAttachment:
    attachment = await db.scalar(
        select(CuratedPlanAttachment).where(
            CuratedPlanAttachment.attachment_id == attachment_id,
            CuratedPlanAttachment.deleted_at.is_(None),
        )
    )
    if attachment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "파일을 찾을 수 없습니다."},
        )
    return attachment


@router.get("", response_model=Envelope[AttachmentLibraryPage])
async def list_files_endpoint(
    _admin: Annotated[User, Depends(require_role("admin", "operator"))],
    db: DbSession,
    page: int = 1,
    limit: int = 50,
    q: str | None = None,
    scope: AttachmentScope | None = None,
    user_id: uuid.UUID | None = None,
    trip_id: uuid.UUID | None = None,
) -> Envelope[AttachmentLibraryPage]:
    page = max(1, page)
    limit = min(100, max(1, limit))
    rows, total = await list_admin_file_library(
        db,
        q=q,
        scope=scope,
        user_id=user_id,
        trip_id=trip_id,
        limit=limit,
        offset=(page - 1) * limit,
    )
    return Envelope.of(
        AttachmentLibraryPage(
            items=[
                _to_library_item(
                    attachment,
                    trip_title=trip_title,
                    poi_label=poi_label,
                    uploaded_by_email=uploaded_by_email,
                )
                for attachment, trip_title, poi_label, uploaded_by_email in rows
            ],
            total=total,
            page=page,
            limit=limit,
        )
    )


@router.get("/{attachment_id}/download-url", response_model=Envelope[DownloadUrlResponse])
async def get_file_download_url_endpoint(
    attachment_id: uuid.UUID,
    request: Request,
    _admin: Annotated[User, Depends(require_role("admin", "operator"))],
    db: DbSession,
) -> Envelope[DownloadUrlResponse]:
    attachment = await _get_attachment(db, attachment_id)
    return Envelope.of(
        make_download_url(
            bucket=attachment.bucket,
            storage_key=attachment.storage_key,
            public_url=attachment.public_url,
            public_api_base_url=public_api_base_url(request),
        )
    )


@router.delete("/{attachment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_file_endpoint(
    attachment_id: uuid.UUID,
    body: AdminActionRequest,
    request: Request,
    admin: Annotated[User, Depends(require_role("admin"))],
    db: DbSession,
    x_request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
) -> None:
    attachment = await _get_attachment(db, attachment_id)
    before_state = attachment_state(attachment)
    attachment.deleted_at = datetime.now(UTC)
    await append_admin_audit(
        db,
        actor_user_id=admin.user_id,
        action="attachment.delete",
        resource_type="attachment",
        resource_id=str(attachment.attachment_id),
        before_state=before_state,
        after_state=attachment_state(attachment),
        access_reason=body.access_reason,
        target_pii_fields=None,
        ip_hash_input=request.client.host if request.client else "",
        user_agent=request.headers.get("user-agent"),
        request_id=_parse_request_id(x_request_id),
    )
    await db.commit()
