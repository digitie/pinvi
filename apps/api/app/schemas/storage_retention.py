"""관리자 첨부 정리의 집계 계약. 객체 키/개인 식별자는 노출하지 않는다."""
from typing import Literal

from pydantic import BaseModel, Field


class StorageRetentionError(BaseModel):
    code: str
    count: int = Field(ge=0)


class StorageRetentionStatus(BaseModel):
    retention_days: int
    expired_trips: int
    eligible_attachments: int
    expired_uploads: int
    pending_objects: int
    in_progress_objects: int
    errors: list[StorageRetentionError]
    can_execute: bool = False


class StorageRetentionExecuteRequest(BaseModel):
    access_reason: str = Field(min_length=5, max_length=1000)
    confirm_phrase: Literal["DELETE EXPIRED FILES"]


class StorageRetentionResult(BaseModel):
    expired_trips_started: int
    retired_references: int
    objects_deleted: int
    objects_failed: int
    trips_deleted: int
    status: StorageRetentionStatus
