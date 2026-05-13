from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.routes.auth import require_current_user
from app.core.config import get_settings
from app.models.user import User
from app.schemas.storage import StorageUploadUrlRequest, StorageUploadUrlResponse
from app.services.file_storage import (
    FileStorageConfigurationError,
    FileStorageError,
    RustfsStorage,
)

router = APIRouter(prefix="/storage", tags=["storage"])


@router.post(
    "/upload-urls",
    response_model=StorageUploadUrlResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_upload_url(
    payload: StorageUploadUrlRequest,
    current_user: Annotated[User, Depends(require_current_user)],
) -> StorageUploadUrlResponse:
    settings = get_settings()
    storage = RustfsStorage.from_settings(settings)
    try:
        upload = storage.create_presigned_upload(
            user_id=current_user.id,
            filename=payload.filename,
            content_type=payload.content_type,
            content_length=payload.content_length,
            purpose=payload.purpose,
        )
    except FileStorageConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except FileStorageError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc

    return StorageUploadUrlResponse(
        method="PUT",
        bucket=upload.bucket,
        storage_key=upload.storage_key,
        upload_url=upload.upload_url,
        headers=upload.headers,
        expires_at=upload.expires_at,
        max_upload_bytes=settings.rustfs_max_upload_bytes,
        public_url=upload.public_url,
    )
