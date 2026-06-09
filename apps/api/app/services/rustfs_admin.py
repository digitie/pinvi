"""RustFS(S3 호환) Admin 객체 관리 — ListObjectsV2 / DeleteObject (T-105 #3).

boto3 동기 client를 `asyncio.to_thread`로 감싸 비동기 경로에서 호출한다. 객체 본문은
RustFS가 소유하므로 TripMate는 메타만 다룬다. RBAC는 라우터에서 강제.
"""

from __future__ import annotations

import asyncio
from typing import Any

import boto3

from app.core.config import settings


def _client() -> Any:
    return boto3.client(
        "s3",
        endpoint_url=settings.tripmate_rustfs_endpoint_url,
        aws_access_key_id=settings.tripmate_rustfs_access_key_id,
        aws_secret_access_key=settings.tripmate_rustfs_secret_access_key,
        region_name="us-east-1",
    )


def _list_objects_sync(prefix: str, limit: int, token: str | None) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "Bucket": settings.tripmate_rustfs_bucket,
        "Prefix": prefix,
        "MaxKeys": limit,
    }
    if token:
        kwargs["ContinuationToken"] = token
    resp = _client().list_objects_v2(**kwargs)
    objects = [
        {
            "key": obj["Key"],
            "size": int(obj.get("Size", 0)),
            "last_modified": obj["LastModified"].isoformat() if obj.get("LastModified") else None,
            "etag": obj.get("ETag"),
            "storage_class": obj.get("StorageClass"),
        }
        for obj in resp.get("Contents", [])
    ]
    return {
        "objects": objects,
        "is_truncated": bool(resp.get("IsTruncated", False)),
        "next_continuation_token": resp.get("NextContinuationToken"),
    }


async def list_objects(
    *, prefix: str = "", limit: int = 100, continuation_token: str | None = None
) -> dict[str, Any]:
    return await asyncio.to_thread(_list_objects_sync, prefix, limit, continuation_token)


def _delete_object_sync(key: str) -> None:
    _client().delete_object(Bucket=settings.tripmate_rustfs_bucket, Key=key)


async def delete_object(*, key: str) -> None:
    await asyncio.to_thread(_delete_object_sync, key)
