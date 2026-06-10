"""`/storage/upload-urls` — `docs/api/storage.md`."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.core.deps import CurrentUserId, DbSession
from app.models.user import User
from app.schemas.envelope import Envelope
from app.schemas.storage import UploadUrlRequest, UploadUrlResponse
from app.services.rustfs_storage import (
    FileTooLargeError,
    MimeNotAllowedError,
    make_upload_url,
)

router = APIRouter(prefix="/storage", tags=["storage"])
_ADMIN_ONLY_PURPOSES = {"curated_plan_attachment", "curated_poi_attachment"}


@router.post("/upload-urls", response_model=Envelope[UploadUrlResponse])
async def upload_urls(
    body: UploadUrlRequest, current_user_id: CurrentUserId, db: DbSession
) -> Envelope[UploadUrlResponse]:
    if body.purpose in _ADMIN_ONLY_PURPOSES:
        user = await db.scalar(select(User).where(User.user_id == uuid.UUID(current_user_id)))
        if user is None or "admin" not in set(user.roles or []):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "RESOURCE_NOT_FOUND", "message": "Not found."},
            )
    try:
        response = make_upload_url(
            purpose=body.purpose,
            user_id=uuid.UUID(current_user_id),
            filename=body.filename,
            content_type=body.content_type,
            content_length=body.content_length,
        )
    except MimeNotAllowedError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc
    except FileTooLargeError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc
    return Envelope.of(response)
