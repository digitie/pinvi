"""`/storage/upload-urls` — `docs/api/storage.md`."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status

from app.core.deps import CurrentUserId
from app.schemas.envelope import Envelope
from app.schemas.storage import UploadUrlRequest, UploadUrlResponse
from app.services.rustfs_storage import (
    FileTooLargeError,
    MimeNotAllowedError,
    make_upload_url,
)

router = APIRouter(prefix="/storage", tags=["storage"])


@router.post("/upload-urls", response_model=Envelope[UploadUrlResponse])
async def upload_urls(
    body: UploadUrlRequest, current_user_id: CurrentUserId
) -> Envelope[UploadUrlResponse]:
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
