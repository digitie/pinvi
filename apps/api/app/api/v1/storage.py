"""`/storage/upload-urls` — `docs/api/storage.md`."""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime

from botocore.exceptions import ClientError
from fastapi import APIRouter, HTTPException, Request, Response, status
from sqlalchemy import select

from app.api.request_url import public_api_base_url
from app.core.deps import CurrentUserId, DbSession
from app.models.storage_lifecycle import AttachmentUploadIntent
from app.models.user import User
from app.schemas.envelope import Envelope
from app.schemas.storage import UploadUrlRequest, UploadUrlResponse
from app.services.rustfs_storage import (
    FileTooLargeError,
    InvalidStorageProxyTokenError,
    InvalidStorageRefError,
    MimeNotAllowedError,
    UploadAlreadyStartedError,
    get_storage_object,
    make_upload_url,
    parse_storage_proxy_token,
    put_storage_object,
)
from app.services.storage_lifecycle import (
    ATTACHMENT_PURPOSES,
    assert_objects_writable,
    reserve_attachment_upload,
)
from app.services.storage_policy import (
    AttachmentQuotaError,
    effective_attachment_quota,
    get_storage_settings,
)

router = APIRouter(prefix="/storage", tags=["storage"])
_ADMIN_ONLY_PURPOSES = {"curated_plan_attachment", "curated_poi_attachment"}


def _storage_http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, InvalidStorageRefError):
        return HTTPException(status_code=422, detail={"code": exc.code, "message": str(exc)})
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
    if body.purpose in ATTACHMENT_PURPOSES:
        try:
            await reserve_attachment_upload(
                db, user=user, bucket=response.bucket, key=response.storage_key,
                byte_size=body.content_length, expires_at=response.expires_at,
            )
            await db.commit()
        except AttachmentQuotaError as exc:
            raise HTTPException(status_code=409, detail={"code": exc.code, "message": str(exc)}) from exc
    return Envelope.of(response)


@router.put("/uploads/{token}", status_code=status.HTTP_204_NO_CONTENT)
async def storage_upload_proxy(token: str, request: Request, db: DbSession) -> Response:
    try:
        ref = parse_storage_proxy_token(token, expected_op="put")
        body = await request.body()
        ref = parse_storage_proxy_token(token, expected_op="put")
        tracked = len(ref.storage_key.split("/")) > 1 and ref.storage_key.split("/")[1] in ATTACHMENT_PURPOSES
        await assert_objects_writable(db, [(ref.bucket, ref.storage_key)])
        intent: AttachmentUploadIntent | None = None
        if tracked:
            intent = await db.get(AttachmentUploadIntent, (ref.bucket, ref.storage_key), populate_existing=True)
            if intent is None or intent.purged_at is not None or intent.expires_at <= datetime.now(UTC):
                raise InvalidStorageRefError("만료되거나 정리된 업로드입니다. 다시 업로드해 주세요.")
            if intent.registered_at is not None or intent.write_started_at is not None:
                raise UploadAlreadyStartedError("이미 시도한 업로드입니다. 새 업로드 URL로 다시 선택해 주세요.")
            if intent.byte_size != len(body):
                raise InvalidStorageRefError("업로드 크기가 발급된 정보와 일치하지 않습니다.")
            write_token = uuid.uuid4()
            intent.write_token = write_token
            intent.write_started_at = datetime.now(UTC)
            await db.commit()  # 네트워크 쓰기 전에 one-shot 시작을 영속화한다.
            await assert_objects_writable(db, [(ref.bucket, ref.storage_key)])
            intent = await db.get(AttachmentUploadIntent, (ref.bucket, ref.storage_key), populate_existing=True)
            if intent is None or intent.write_token != write_token or intent.registered_at is not None or intent.purged_at is not None or intent.expires_at <= datetime.now(UTC):
                raise InvalidStorageRefError("업로드 대상이 변경되었습니다. 다시 업로드해 주세요.")
            parse_storage_proxy_token(token, expected_op="put")
        write = asyncio.create_task(asyncio.to_thread(
            put_storage_object, ref=ref, body=body, content_type=request.headers.get("content-type")
        ))
        try:
            await asyncio.shield(write)
        except asyncio.CancelledError:
            while not write.done():
                try:
                    await asyncio.shield(write)
                except asyncio.CancelledError:
                    continue
                except Exception:
                    break
            if not write.cancelled():
                write.exception()
            raise
        if tracked:
            await assert_objects_writable(db, [(ref.bucket, ref.storage_key)])
            intent = await db.get(AttachmentUploadIntent, (ref.bucket, ref.storage_key), populate_existing=True)
            if intent is None or intent.write_token != write_token or intent.purged_at is not None:
                raise InvalidStorageRefError("업로드 결과를 확정하지 못했습니다. 새 URL로 다시 업로드해 주세요.")
            intent.uploaded_bytes = len(body)
        await db.commit()
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
