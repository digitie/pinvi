"""`/storage/upload-urls` — `docs/api/storage.md`."""

from __future__ import annotations

import uuid

from botocore.exceptions import ClientError
from fastapi import APIRouter, HTTPException, Request, Response, status
from sqlalchemy import select

from app.api.request_url import public_api_base_url
from app.core.deps import CurrentUserId, DbSession
from app.models.user import User
from app.schemas.envelope import Envelope
from app.schemas.storage import UploadUrlRequest, UploadUrlResponse
from app.services.rustfs_storage import (
    FileTooLargeError,
    InvalidStorageProxyTokenError,
    MimeNotAllowedError,
    get_storage_object,
    make_upload_url,
    parse_storage_proxy_token,
    put_storage_object,
)
from app.services.storage_policy import effective_attachment_quota, get_storage_settings

router = APIRouter(prefix="/storage", tags=["storage"])
_ADMIN_ONLY_PURPOSES = {"curated_plan_attachment", "curated_poi_attachment"}


def _storage_http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, InvalidStorageProxyTokenError):
        return HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": exc.code, "message": str(exc)},
        )
    if isinstance(exc, (FileTooLargeError, MimeNotAllowedError)):
        return HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": exc.code, "message": str(exc)},
        )
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail={"code": "STORAGE_UNAVAILABLE", "message": "파일 저장소에 연결할 수 없습니다."},
    )


@router.post("/upload-urls", response_model=Envelope[UploadUrlResponse])
async def upload_urls(
    body: UploadUrlRequest,
    request: Request,
    current_user_id: CurrentUserId,
    db: DbSession,
) -> Envelope[UploadUrlResponse]:
    user = await db.scalar(select(User).where(User.user_id == uuid.UUID(current_user_id)))
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "Not found."},
        )
    if body.purpose in _ADMIN_ONLY_PURPOSES:
        if "admin" not in set(user.roles or []):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "RESOURCE_NOT_FOUND", "message": "Not found."},
            )
    max_upload_bytes: int | None = None
    if body.purpose in {"trip_attachment", "trip_day_attachment", "poi_attachment"}:
        settings_row = await get_storage_settings(db)
        max_upload_bytes = effective_attachment_quota(settings_row, user).max_upload_bytes
    try:
        response = make_upload_url(
            purpose=body.purpose,
            user_id=uuid.UUID(current_user_id),
            filename=body.filename,
            content_type=body.content_type,
            content_length=body.content_length,
            max_upload_bytes=max_upload_bytes,
            public_api_base_url=public_api_base_url(request),
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


@router.put("/uploads/{token}", status_code=status.HTTP_204_NO_CONTENT)
async def storage_upload_proxy(token: str, request: Request) -> Response:
    try:
        ref = parse_storage_proxy_token(token, expected_op="put")
        body = await request.body()
        put_storage_object(ref=ref, body=body, content_type=request.headers.get("content-type"))
    except Exception as exc:
        raise _storage_http_error(exc) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/downloads/{token}")
async def storage_download_proxy(token: str) -> Response:
    try:
        ref = parse_storage_proxy_token(token, expected_op="get")
        body, content_type = get_storage_object(ref=ref)
    except ClientError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "파일을 찾을 수 없습니다."},
        ) from exc
    except Exception as exc:
        raise _storage_http_error(exc) from exc
    return Response(content=body, media_type=content_type)
