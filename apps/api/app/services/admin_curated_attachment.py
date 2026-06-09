"""Admin 큐레이션(curated/notice) 첨부 서비스 — `docs/api/storage.md` §5.3/5.4.

`app.curated_plan_attachments` 중 `curated_plan_id` 또는 `curated_poi_id` 로 묶인 행을
관리한다(trip / trip_poi 도메인은 `app.services.trip` 소관). DELETE 는 soft delete 만 —
RustFS object 는 notice→trip copy 시 `storage_key` 를 공유하므로 함께 지우지 않는다(§5.6).

라우터가 audit append 와 같은 트랜잭션에 묶으므로 mutate 함수는 commit 하지 않고 flush 만 한다.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.attachment import CuratedPlanAttachment
from app.models.curated_plan import CuratedPlanPoi, CuratedTripPlan


class CuratedAttachmentError(Exception):
    """Base."""

    code = "CURATED_ATTACHMENT_ERROR"


class CuratedPlanNotFoundError(CuratedAttachmentError):
    code = "NOT_FOUND"


class CuratedAttachmentNotFoundError(CuratedAttachmentError):
    code = "ATTACHMENT_NOT_FOUND"


class CuratedAttachmentLimitError(CuratedAttachmentError):
    code = "ATTACHMENT_LIMIT_EXCEEDED"


async def ensure_plan(db: AsyncSession, *, curated_plan_id: uuid.UUID) -> None:
    """curated plan 존재 확인(soft-delete 제외). 없으면 NotFound."""
    found = await db.scalar(
        select(CuratedTripPlan.curated_plan_id).where(
            CuratedTripPlan.curated_plan_id == curated_plan_id,
            CuratedTripPlan.deleted_at.is_(None),
        )
    )
    if found is None:
        raise CuratedPlanNotFoundError("큐레이션 플랜을 찾을 수 없습니다.")


async def ensure_poi(
    db: AsyncSession, *, curated_plan_id: uuid.UUID, curated_poi_id: uuid.UUID
) -> None:
    """curated POI 가 해당 plan 소속인지 확인(soft-delete 제외). 없으면 NotFound."""
    found = await db.scalar(
        select(CuratedPlanPoi.curated_poi_id).where(
            CuratedPlanPoi.curated_poi_id == curated_poi_id,
            CuratedPlanPoi.curated_plan_id == curated_plan_id,
            CuratedPlanPoi.deleted_at.is_(None),
        )
    )
    if found is None:
        raise CuratedPlanNotFoundError("큐레이션 POI 를 찾을 수 없습니다.")


def _scope_filters(
    *, curated_plan_id: uuid.UUID | None, curated_poi_id: uuid.UUID | None
) -> list[Any]:
    filters: list[Any] = [CuratedPlanAttachment.deleted_at.is_(None)]
    if curated_plan_id is not None:
        filters.append(CuratedPlanAttachment.curated_plan_id == curated_plan_id)
    if curated_poi_id is not None:
        filters.append(CuratedPlanAttachment.curated_poi_id == curated_poi_id)
    return filters


async def list_curated_attachments(
    db: AsyncSession,
    *,
    curated_plan_id: uuid.UUID | None = None,
    curated_poi_id: uuid.UUID | None = None,
) -> list[CuratedPlanAttachment]:
    result = await db.execute(
        select(CuratedPlanAttachment)
        .where(*_scope_filters(curated_plan_id=curated_plan_id, curated_poi_id=curated_poi_id))
        .order_by(CuratedPlanAttachment.sort_order.asc(), CuratedPlanAttachment.created_at.asc())
    )
    return list(result.scalars())


async def _count(
    db: AsyncSession, *, curated_plan_id: uuid.UUID | None, curated_poi_id: uuid.UUID | None
) -> int:
    return int(
        await db.scalar(
            select(func.count(CuratedPlanAttachment.attachment_id)).where(
                *_scope_filters(curated_plan_id=curated_plan_id, curated_poi_id=curated_poi_id)
            )
        )
        or 0
    )


async def create_curated_attachment(
    db: AsyncSession,
    *,
    uploaded_by_user_id: uuid.UUID,
    curated_plan_id: uuid.UUID | None = None,
    curated_poi_id: uuid.UUID | None = None,
    payload: dict[str, Any],
) -> CuratedPlanAttachment:
    """첨부 1건 생성(flush 까지). 대상당 개수 상한은 trip 첨부와 동일 설정 공유."""
    limit = settings.tripmate_max_attachments_per_target
    if await _count(db, curated_plan_id=curated_plan_id, curated_poi_id=curated_poi_id) >= limit:
        raise CuratedAttachmentLimitError(f"첨부는 대상당 최대 {limit}개까지 등록할 수 있습니다.")
    attachment = CuratedPlanAttachment(
        curated_plan_id=curated_plan_id,
        curated_poi_id=curated_poi_id,
        uploaded_by_user_id=uploaded_by_user_id,
        **payload,
    )
    db.add(attachment)
    await db.flush()
    await db.refresh(attachment)
    return attachment


async def get_curated_attachment(
    db: AsyncSession,
    *,
    attachment_id: uuid.UUID,
    curated_plan_id: uuid.UUID | None = None,
    curated_poi_id: uuid.UUID | None = None,
) -> CuratedPlanAttachment:
    filters = [
        CuratedPlanAttachment.attachment_id == attachment_id,
        *_scope_filters(curated_plan_id=curated_plan_id, curated_poi_id=curated_poi_id),
    ]
    attachment = await db.scalar(select(CuratedPlanAttachment).where(*filters))
    if attachment is None:
        raise CuratedAttachmentNotFoundError("첨부를 찾을 수 없습니다.")
    return attachment


async def delete_curated_attachment(
    db: AsyncSession,
    *,
    attachment_id: uuid.UUID,
    curated_plan_id: uuid.UUID | None = None,
    curated_poi_id: uuid.UUID | None = None,
) -> CuratedPlanAttachment:
    """soft delete(`deleted_at=now()`). RustFS object 는 보존(§5.6). flush 까지만."""
    attachment = await get_curated_attachment(
        db,
        attachment_id=attachment_id,
        curated_plan_id=curated_plan_id,
        curated_poi_id=curated_poi_id,
    )
    attachment.deleted_at = datetime.now(UTC)
    await db.flush()
    return attachment
