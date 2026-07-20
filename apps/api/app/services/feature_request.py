"""외부 pick → feature-request 파이프라인(ADR-054 §7, T-303).

Kakao/Naver로 고른 장소를 POI로 추가하면, 서버가 **best-effort로 feature-request를 auto-fire**한다:
- 전역(GLOBAL) dedup — 같은 외부 장소(provider, external_id)에 active 제안이 이미 있으면 새로 만들지
  않는다. 이미 승인·반영(`added`)돼 feature_id가 있으면 방금 만든 POI를 즉시 그 feature에 연결한다.
- decoupled — POI 트랜잭션과 분리된 세션에서 수행하고, 실패해도 POI 생성을 되돌리지 않는다.
- 승인 시 reconciliation — admin이 제안을 승인해 feature가 생기면 그 external_ref를 참조하던 모든
  미연결 POI의 feature_id를 채운다.

provider 콘텐츠는 저장하지 않는다 — 저장·전달 대상은 user-authored name+coord+note + external_ref뿐.
"""

from __future__ import annotations

import logging
import uuid
from decimal import Decimal
from typing import Any, cast

from sqlalchemy import CursorResult, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.feature_suggestion import FeatureSuggestion
from app.models.poi import TripDayPoi

logger = logging.getLogger(__name__)

_ACTIVE_STATUSES = ("pending", "approved", "added")
_LON = Decimal("0.000001")


def _quantize(value: float, exp: Decimal = _LON) -> Decimal:
    return Decimal(str(value)).quantize(exp)


async def find_active_suggestion_by_external_ref(
    db: AsyncSession, *, provider: str, external_id: str
) -> FeatureSuggestion | None:
    """(provider, external_id)로 전역 active 제안 1건 조회(전역 dedup 키)."""
    row = await db.scalar(
        select(FeatureSuggestion)
        .where(
            FeatureSuggestion.external_ref["provider"].astext == provider,
            FeatureSuggestion.external_ref["external_id"].astext == external_id,
            FeatureSuggestion.status.in_(_ACTIVE_STATUSES),
        )
        .order_by(FeatureSuggestion.created_at.desc())
        .limit(1)
    )
    return row


def _ref_feature_id(suggestion: FeatureSuggestion) -> str | None:
    ref = suggestion.kor_travel_map_ref
    if isinstance(ref, dict):
        fid = ref.get("feature_id")
        if isinstance(fid, str) and fid:
            return fid
    return None


async def reconcile_pois_for_external_ref(
    db: AsyncSession, *, provider: str, external_id: str, feature_id: str
) -> int:
    """external_ref를 참조하는 미연결(feature_id NULL) POI를 새 feature_id에 연결한다. 갱신 건수 반환."""
    result = cast(
        CursorResult[Any],
        await db.execute(
            update(TripDayPoi)
            .where(
                TripDayPoi.external_ref["provider"].astext == provider,
                TripDayPoi.external_ref["external_id"].astext == external_id,
                TripDayPoi.feature_id.is_(None),
                TripDayPoi.deleted_at.is_(None),
            )
            .values(feature_id=feature_id)
        ),
    )
    return int(result.rowcount or 0)


async def auto_fire_external_feature_request(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    poi_id: uuid.UUID,
    requester_user_id: uuid.UUID,
    provider: str,
    external_id: str,
    deep_link_url: str | None,
    name: str,
    lon: float,
    lat: float,
    note: str | None,
) -> None:
    """외부 pick POI에 대한 feature-request를 best-effort로 auto-fire한다(decoupled, 예외 미전파)."""
    external_ref: dict[str, Any] = {"provider": provider, "external_id": external_id}
    if deep_link_url:
        external_ref["deep_link_url"] = deep_link_url
    try:
        async with session_factory() as db:
            existing = await find_active_suggestion_by_external_ref(
                db, provider=provider, external_id=external_id
            )
            if existing is not None:
                # 이미 반영된 feature면 방금 만든 POI를 즉시 연결. 그 외(pending/approved)는 dedup만.
                feature_id = _ref_feature_id(existing) if existing.status == "added" else None
                if feature_id is not None:
                    await db.execute(
                        update(TripDayPoi)
                        .where(TripDayPoi.attachment_id == poi_id, TripDayPoi.feature_id.is_(None))
                        .values(feature_id=feature_id)
                    )
                    await db.commit()
                return

            db.add(
                FeatureSuggestion(
                    requester_user_id=requester_user_id,
                    suggestion_type="new_place",
                    kind="place",
                    name=name[:200],
                    lng=_quantize(lon),
                    lat=_quantize(lat),
                    note=note,
                    source=provider,
                    external_ref=external_ref,
                )
            )
            try:
                await db.commit()
            except IntegrityError:
                # 전역 unique index 경합(동시 auto-fire) — 이미 만들어졌으므로 dedup으로 취급.
                await db.rollback()
    except Exception as exc:
        # best-effort: 어떤 실패도 POI 생성을 되돌리지 않는다(decoupled).
        logger.warning("feature_request.auto_fire_failed", extra={"error": str(exc)})
