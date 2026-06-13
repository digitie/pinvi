"""추천 여행(curated trip plan) 도메인 — listing + 상세 + trip 으로 copy.

외부 `/notice-plans` API 이름은 호환 유지한다. 내부 schema는 ADR-029에 따라
`curated_trip_plans` / `curated_plan_pois` / `curated_plan_attachments`를 쓴다.
"""

from __future__ import annotations

import hashlib
import re
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any, Protocol, cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.attachment import CuratedPlanAttachment
from app.models.curated_plan import CuratedPlanPoi, CuratedTripPlan
from app.models.poi import TripDayPoi
from app.models.trip import Trip
from app.models.trip_day import TripDay
from app.services import lexorank


class NoticePlanError(Exception):
    code: str = "INTERNAL_ERROR"


class NoticePlanNotFoundError(NoticePlanError):
    code = "RESOURCE_NOT_FOUND"


class NoticePlanCopyError(NoticePlanError):
    code = "NOTICE_PLAN_COPY_ERROR"


class NoticePlanPolicyError(NoticePlanError):
    code = "CURATED_PLAN_POI_POLICY_ERROR"


class KorTravelMapCuratedCopyClient(Protocol):
    async def get_curated_pinvi_copy(self, curated_feature_id: str) -> dict[str, Any]:
        """kor-travel-map Pinvi copy snapshot 조회."""
        ...


@dataclass(frozen=True)
class KorTravelMapCuratedImportResult:
    plan: CuratedTripPlan
    created_plan: bool
    copied_poi_count: int
    reused_feature_backed_poi_count: int
    source_system: str
    source_curated_feature_id: str
    source_version: int | None
    source_etag: str | None


_KOR_TRAVEL_MAP_SOURCE_SYSTEM = "kor-travel-map"
_SLUG_TOKEN_RE = re.compile(r"[^a-z0-9]+")


def _optional_feature_id(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _optional_text(value: object, *, max_length: int | None = None) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    if not normalized:
        return None
    if max_length is not None:
        return normalized[:max_length]
    return normalized


def _mapping(value: object) -> Mapping[str, Any]:
    return cast(Mapping[str, Any], value) if isinstance(value, Mapping) else {}


def _int_or_none(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return None
    return None


def _slug_for_kor_travel_map_curated_feature(curated_feature_id: str) -> str:
    token = _SLUG_TOKEN_RE.sub("-", curated_feature_id.lower()).strip("-")
    digest = hashlib.sha256(curated_feature_id.encode("utf-8")).hexdigest()[:10]
    if not token:
        return f"kor_travel_map-{digest}"
    token = token[:140].strip("-")
    return f"kor_travel_map-{token}-{digest}"


def _snapshot_items(snapshot: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    raw_items = snapshot.get("items")
    if not isinstance(raw_items, list):
        return []
    return [cast(Mapping[str, Any], item) for item in raw_items if isinstance(item, Mapping)]


async def list_published_plans(
    db: AsyncSession,
    *,
    category: str | None = None,
    limit: int = 50,
) -> list[CuratedTripPlan]:
    stmt = select(CuratedTripPlan).where(
        CuratedTripPlan.is_published.is_(True), CuratedTripPlan.deleted_at.is_(None)
    )
    if category is not None:
        stmt = stmt.where(CuratedTripPlan.category == category)
    stmt = stmt.order_by(CuratedTripPlan.created_at.desc()).limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars())


async def get_published_plan(db: AsyncSession, *, notice_plan_id: uuid.UUID) -> CuratedTripPlan:
    plan = await db.scalar(
        select(CuratedTripPlan).where(
            CuratedTripPlan.curated_plan_id == notice_plan_id,
            CuratedTripPlan.is_published.is_(True),
            CuratedTripPlan.deleted_at.is_(None),
        )
    )
    if plan is None:
        raise NoticePlanNotFoundError("추천 여행을 찾을 수 없습니다.")
    return plan


async def list_plan_pois(db: AsyncSession, *, notice_plan_id: uuid.UUID) -> list[CuratedPlanPoi]:
    result = await db.execute(
        select(CuratedPlanPoi)
        .where(
            CuratedPlanPoi.curated_plan_id == notice_plan_id,
            CuratedPlanPoi.deleted_at.is_(None),
        )
        .order_by(CuratedPlanPoi.day_index, CuratedPlanPoi.sort_order)
    )
    return list(result.scalars())


async def copy_plan_to_trip(
    db: AsyncSession,
    *,
    notice_plan_id: uuid.UUID,
    user_id: uuid.UUID,
    target_trip_id: uuid.UUID | None,
    trip_title: str | None,
    trip_start_date: date | None,
    trip_end_date: date | None,
    poi_ids: list[uuid.UUID],
) -> tuple[Trip, bool, list[uuid.UUID], int]:
    """notice plan 의 POI 를 사용자 trip 으로 복사.

    - target_trip_id 가 있으면 그 trip(소유자 검증)에 추가, 없으면 새 trip 생성.
    - poi_ids 가 비어 있으면 plan 전체 POI 복사, 있으면 해당 POI 만.
    - curated_poi 의 curated_plan_attachments 도 새 trip_poi 로 복제.
    반환: (trip, created_trip, copied_poi_ids, copied_attachment_count)
    """
    plan = await get_published_plan(db, notice_plan_id=notice_plan_id)
    source_pois = await list_plan_pois(db, notice_plan_id=notice_plan_id)
    if poi_ids:
        wanted = set(poi_ids)
        source_pois = [p for p in source_pois if p.curated_poi_id in wanted]
        if len(source_pois) != len(wanted):
            raise NoticePlanCopyError("일부 POI 가 추천 여행에 없습니다.")
    if not source_pois:
        raise NoticePlanCopyError("복사할 POI 가 없습니다.")

    # 대상 trip 결정
    created_trip = False
    if target_trip_id is not None:
        trip = await db.scalar(
            select(Trip).where(Trip.trip_id == target_trip_id, Trip.deleted_at.is_(None))
        )
        if trip is None:
            raise NoticePlanNotFoundError("대상 여행을 찾을 수 없습니다.")
        if trip.owner_user_id != user_id:
            raise NoticePlanCopyError("대상 여행에 대한 권한이 없습니다.")
    else:
        trip = Trip(
            owner_user_id=user_id,
            title=trip_title or plan.title,
            description=plan.summary,
            region_hint=plan.destination,
            start_date=trip_start_date,
            end_date=trip_end_date,
            visibility="private",
        )
        db.add(trip)
        await db.flush()
        created_trip = True

    copied_poi_ids: list[uuid.UUID] = []
    copied_attachment_count = 0

    # day_index 별 마지막 sort_order 추적 (LexoRank append)
    last_sort: dict[int, str | None] = {}

    for src in source_pois:
        day_index = src.day_index
        # trip_day 보장
        day = await db.scalar(
            select(TripDay).where(TripDay.trip_id == trip.trip_id, TripDay.day_index == day_index)
        )
        if day is None:
            db.add(TripDay(trip_id=trip.trip_id, day_index=day_index))
            await db.flush()

        if day_index not in last_sort:
            last_sort[day_index] = await _max_sort_order(db, trip.trip_id, day_index)
        new_sort = lexorank.between(last_sort[day_index], None)
        last_sort[day_index] = new_sort

        new_poi = TripDayPoi(
            trip_id=trip.trip_id,
            day_index=day_index,
            sort_order=new_sort,
            feature_id=src.feature_id,
            feature_snapshot=src.feature_snapshot,
            custom_marker_color=src.custom_marker_color,
            custom_marker_icon=src.custom_marker_icon,
            user_note=src.memo,
            budget_amount=src.budget_amount,
            currency=src.currency,
            user_url=src.user_url,
            added_by_user_id=user_id,
        )
        db.add(new_poi)
        await db.flush()
        copied_poi_ids.append(new_poi.attachment_id)

        # 첨부 복제 (curated_poi → 새 trip_poi)
        attachments = await db.execute(
            select(CuratedPlanAttachment).where(
                CuratedPlanAttachment.curated_poi_id == src.curated_poi_id,
                CuratedPlanAttachment.deleted_at.is_(None),
            )
        )
        for att in attachments.scalars():
            db.add(
                CuratedPlanAttachment(
                    trip_poi_id=new_poi.attachment_id,
                    source_attachment_id=att.attachment_id,
                    bucket=att.bucket,
                    storage_key=att.storage_key,
                    original_filename=att.original_filename,
                    content_type=att.content_type,
                    byte_size=att.byte_size,
                    public_url=att.public_url,
                    checksum_sha256=att.checksum_sha256,
                    role=att.role,
                    description=att.description,
                    sort_order=att.sort_order,
                    uploaded_by_user_id=user_id,
                )
            )
            copied_attachment_count += 1

    await db.commit()
    await db.refresh(trip)
    return trip, created_trip, copied_poi_ids, copied_attachment_count


async def _max_sort_order(db: AsyncSession, trip_id: uuid.UUID, day_index: int) -> str | None:
    result = await db.execute(
        select(TripDayPoi.sort_order)
        .where(
            TripDayPoi.trip_id == trip_id,
            TripDayPoi.day_index == day_index,
            TripDayPoi.deleted_at.is_(None),
        )
        .order_by(TripDayPoi.sort_order.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def ensure_plan_poi_for_feature(
    db: AsyncSession,
    *,
    curated_plan_id: uuid.UUID,
    feature_id: str,
    day_index: int,
    sort_order: str,
    feature_snapshot: dict[str, Any] | None = None,
    memo: str | None = None,
    budget_amount: Any | None = None,
    currency: str = "KRW",
    user_url: str | None = None,
    custom_marker_color: str | None = None,
    custom_marker_icon: str | None = None,
) -> CuratedPlanPoi:
    """외부 연계에서 feature-backed curated POI를 보장.

    POI 자체는 `feature_id` 없이도 존재할 수 있다. 다만 kor-travel-map import처럼
    feature를 알고 들어오는 경우, 같은 plan에 해당 feature POI가 이미 있으면 재사용하고
    없으면 새 `curated_plan_pois` row를 만든다.
    """
    normalized_feature_id = _optional_feature_id(feature_id)
    if normalized_feature_id is None:
        raise NoticePlanPolicyError("feature 연계 POI 생성에는 feature_id가 필요합니다.")
    existing = await db.scalar(
        select(CuratedPlanPoi).where(
            CuratedPlanPoi.curated_plan_id == curated_plan_id,
            CuratedPlanPoi.feature_id == normalized_feature_id,
            CuratedPlanPoi.deleted_at.is_(None),
        )
    )
    if existing is not None:
        return existing

    poi = CuratedPlanPoi(
        curated_plan_id=curated_plan_id,
        day_index=day_index,
        sort_order=sort_order,
        feature_id=normalized_feature_id,
        feature_snapshot=feature_snapshot or {},
        memo=memo,
        budget_amount=budget_amount,
        currency=currency,
        user_url=user_url,
        custom_marker_color=custom_marker_color,
        custom_marker_icon=custom_marker_icon,
    )
    db.add(poi)
    await db.flush()
    return poi


async def import_kor_travel_map_curated_feature(
    db: AsyncSession,
    *,
    admin_id: uuid.UUID,
    kor_travel_map_client: KorTravelMapCuratedCopyClient,
    curated_feature_id: str,
    mode: str = "create",
    is_published: bool | None = None,
) -> KorTravelMapCuratedImportResult:
    """kor-travel-map curated feature snapshot을 Pinvi curated plan으로 복사."""
    if mode not in {"create", "upsert", "refresh"}:
        raise NoticePlanPolicyError("지원하지 않는 import mode 입니다.")

    snapshot = _mapping(await kor_travel_map_client.get_curated_pinvi_copy(curated_feature_id))
    source_curated_feature_id = _optional_text(snapshot.get("curated_feature_id"))
    if source_curated_feature_id is None:
        raise NoticePlanCopyError("kor-travel-map copy snapshot에 curated_feature_id가 없습니다.")
    plan_payload = _mapping(snapshot.get("plan"))
    source_payload = _mapping(snapshot.get("source"))
    theme_payload = _mapping(snapshot.get("theme"))
    items = _snapshot_items(snapshot)
    if not items:
        raise NoticePlanCopyError("kor-travel-map copy snapshot에 복사할 item이 없습니다.")

    existing = await _get_kor_travel_map_imported_plan(
        db, source_curated_feature_id=source_curated_feature_id
    )
    if existing is not None and mode == "create":
        raise NoticePlanCopyError("이미 가져온 kor_travel_map curated feature 입니다.")
    if existing is None and mode == "refresh":
        raise NoticePlanNotFoundError("refresh할 kor_travel_map curated feature import가 없습니다.")

    created_plan = existing is None
    plan = existing or CuratedTripPlan(
        slug=_slug_for_kor_travel_map_curated_feature(source_curated_feature_id),
        title=_optional_text(plan_payload.get("title"), max_length=200)
        or source_curated_feature_id,
        category=_category_from_snapshot(plan_payload, theme_payload),
        created_by_admin_id=admin_id,
        updated_by_admin_id=admin_id,
    )
    if created_plan:
        db.add(plan)

    _apply_kor_travel_map_plan_snapshot(
        plan,
        admin_id=admin_id,
        plan_payload=plan_payload,
        source_payload=source_payload,
        theme_payload=theme_payload,
        snapshot=snapshot,
        source_curated_feature_id=source_curated_feature_id,
        is_published=is_published
        if is_published is not None
        else (False if created_plan else plan.is_published),
    )
    await db.flush()

    copied_count = 0
    reused_count = 0
    last_sort_by_day: dict[int, str | None] = {}
    ordered_items = sorted(
        items,
        key=lambda item: (
            _int_or_none(item.get("day_index")) or 1,
            _int_or_none(item.get("sort_order")) or 0,
            _optional_text(item.get("curated_feature_item_id")) or "",
        ),
    )
    for item in ordered_items:
        poi, reused = await _ensure_kor_travel_map_import_poi(
            db,
            plan=plan,
            source_curated_feature_id=source_curated_feature_id,
            item=item,
            last_sort_by_day=last_sort_by_day,
        )
        _apply_kor_travel_map_poi_snapshot(
            poi,
            source_curated_feature_id=source_curated_feature_id,
            item=item,
        )
        copied_count += 1
        if reused and poi.feature_id is not None:
            reused_count += 1

    await db.commit()
    await db.refresh(plan)
    return KorTravelMapCuratedImportResult(
        plan=plan,
        created_plan=created_plan,
        copied_poi_count=copied_count,
        reused_feature_backed_poi_count=reused_count,
        source_system=_KOR_TRAVEL_MAP_SOURCE_SYSTEM,
        source_curated_feature_id=source_curated_feature_id,
        source_version=_int_or_none(snapshot.get("version")),
        source_etag=_optional_text(snapshot.get("etag"), max_length=128),
    )


async def _get_kor_travel_map_imported_plan(
    db: AsyncSession, *, source_curated_feature_id: str
) -> CuratedTripPlan | None:
    return cast(
        CuratedTripPlan | None,
        await db.scalar(
            select(CuratedTripPlan).where(
                CuratedTripPlan.source_system == _KOR_TRAVEL_MAP_SOURCE_SYSTEM,
                CuratedTripPlan.source_curated_feature_id == source_curated_feature_id,
                CuratedTripPlan.deleted_at.is_(None),
            )
        ),
    )


def _category_from_snapshot(
    plan_payload: Mapping[str, Any], theme_payload: Mapping[str, Any]
) -> str:
    return (
        _optional_text(plan_payload.get("category"), max_length=80)
        or _optional_text(theme_payload.get("theme_slug"), max_length=80)
        or "recommended"
    )


def _apply_kor_travel_map_plan_snapshot(
    plan: CuratedTripPlan,
    *,
    admin_id: uuid.UUID,
    plan_payload: Mapping[str, Any],
    source_payload: Mapping[str, Any],
    theme_payload: Mapping[str, Any],
    snapshot: Mapping[str, Any],
    source_curated_feature_id: str,
    is_published: bool,
) -> None:
    plan.title = _optional_text(plan_payload.get("title"), max_length=200) or plan.title
    plan.category = _category_from_snapshot(plan_payload, theme_payload)
    plan.summary = _optional_text(plan_payload.get("summary"))
    plan.source_name = (
        _optional_text(source_payload.get("source_name"), max_length=200)
        or _optional_text(source_payload.get("provider"), max_length=200)
        or _KOR_TRAVEL_MAP_SOURCE_SYSTEM
    )
    plan.destination = _optional_text(
        plan_payload.get("destination_name"), max_length=120
    ) or _optional_text(plan_payload.get("region_code"), max_length=120)
    plan.is_published = is_published
    plan.updated_by_admin_id = admin_id
    plan.source_system = _KOR_TRAVEL_MAP_SOURCE_SYSTEM
    plan.source_curated_feature_id = source_curated_feature_id
    plan.source_curated_feature_version = _int_or_none(snapshot.get("version"))
    plan.source_etag = _optional_text(snapshot.get("etag"), max_length=128)
    plan.source_imported_at = datetime.now(UTC)


async def _ensure_kor_travel_map_import_poi(
    db: AsyncSession,
    *,
    plan: CuratedTripPlan,
    source_curated_feature_id: str,
    item: Mapping[str, Any],
    last_sort_by_day: dict[int, str | None],
) -> tuple[CuratedPlanPoi, bool]:
    source_item_id = _optional_text(item.get("curated_feature_item_id"))
    if source_item_id is not None:
        existing_by_item = await db.scalar(
            select(CuratedPlanPoi).where(
                CuratedPlanPoi.curated_plan_id == plan.curated_plan_id,
                CuratedPlanPoi.source_curated_feature_id == source_curated_feature_id,
                CuratedPlanPoi.source_curated_feature_item_id == source_item_id,
                CuratedPlanPoi.deleted_at.is_(None),
            )
        )
        if existing_by_item is not None:
            return existing_by_item, True

    day_index = _int_or_none(item.get("day_index")) or 1
    feature_id = _optional_feature_id(item.get("feature_id"))
    if feature_id is not None:
        existing_by_feature = await db.scalar(
            select(CuratedPlanPoi).where(
                CuratedPlanPoi.curated_plan_id == plan.curated_plan_id,
                CuratedPlanPoi.feature_id == feature_id,
                CuratedPlanPoi.deleted_at.is_(None),
            )
        )
        sort_order = existing_by_feature.sort_order if existing_by_feature else None
        if sort_order is None:
            sort_order = await _next_curated_sort_order(
                db, plan.curated_plan_id, day_index, last_sort_by_day
            )
        poi = await ensure_plan_poi_for_feature(
            db,
            curated_plan_id=plan.curated_plan_id,
            feature_id=feature_id,
            day_index=day_index,
            sort_order=sort_order,
        )
        return poi, existing_by_feature is not None

    sort_order = await _next_curated_sort_order(
        db, plan.curated_plan_id, day_index, last_sort_by_day
    )
    poi = CuratedPlanPoi(
        curated_plan_id=plan.curated_plan_id,
        day_index=day_index,
        sort_order=sort_order,
        feature_id=None,
    )
    db.add(poi)
    await db.flush()
    return poi, False


async def _next_curated_sort_order(
    db: AsyncSession,
    curated_plan_id: uuid.UUID,
    day_index: int,
    last_sort_by_day: dict[int, str | None],
) -> str:
    if day_index not in last_sort_by_day:
        last_sort_by_day[day_index] = await _max_curated_sort_order(db, curated_plan_id, day_index)
    sort_order = lexorank.between(last_sort_by_day[day_index], None)
    last_sort_by_day[day_index] = sort_order
    return sort_order


async def _max_curated_sort_order(
    db: AsyncSession, curated_plan_id: uuid.UUID, day_index: int
) -> str | None:
    result = await db.execute(
        select(CuratedPlanPoi.sort_order)
        .where(
            CuratedPlanPoi.curated_plan_id == curated_plan_id,
            CuratedPlanPoi.day_index == day_index,
            CuratedPlanPoi.deleted_at.is_(None),
        )
        .order_by(CuratedPlanPoi.sort_order.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


def _apply_kor_travel_map_poi_snapshot(
    poi: CuratedPlanPoi,
    *,
    source_curated_feature_id: str,
    item: Mapping[str, Any],
) -> None:
    day_index = _int_or_none(item.get("day_index"))
    if day_index is not None:
        poi.day_index = day_index
    poi.feature_id = _optional_feature_id(item.get("feature_id"))
    snapshot = item.get("feature_snapshot")
    poi.feature_snapshot = dict(_mapping(snapshot))
    poi.memo = _optional_text(item.get("memo"))
    poi.source_curated_feature_id = source_curated_feature_id
    poi.source_curated_feature_item_id = _optional_text(item.get("curated_feature_item_id"))


# Admin 용 생성 helper (Sprint 3 admin UI 보강 전 최소 — seed/테스트용)
async def create_plan_with_pois(
    db: AsyncSession,
    *,
    admin_id: uuid.UUID,
    slug: str,
    title: str,
    category: str = "recommended",
    summary: str | None = None,
    destination: str | None = None,
    is_published: bool = True,
    pois: list[dict[str, Any]] | None = None,
) -> CuratedTripPlan:
    plan = CuratedTripPlan(
        slug=slug,
        title=title,
        category=category,
        summary=summary,
        destination=destination,
        is_published=is_published,
        created_by_admin_id=admin_id,
        updated_by_admin_id=admin_id,
    )
    db.add(plan)
    await db.flush()
    for item in pois or []:
        feature_id = _optional_feature_id(item.get("feature_id"))
        if feature_id is not None:
            await ensure_plan_poi_for_feature(
                db,
                curated_plan_id=plan.curated_plan_id,
                day_index=item.get("day_index", 1),
                sort_order=item["sort_order"],
                feature_id=feature_id,
                feature_snapshot=item.get("feature_snapshot", {}),
                memo=item.get("memo"),
                budget_amount=item.get("budget_amount"),
                currency=item.get("currency", "KRW"),
                user_url=item.get("user_url"),
                custom_marker_color=item.get("custom_marker_color"),
                custom_marker_icon=item.get("custom_marker_icon"),
            )
            continue
        db.add(
            CuratedPlanPoi(
                curated_plan_id=plan.curated_plan_id,
                day_index=item.get("day_index", 1),
                sort_order=item["sort_order"],
                feature_id=None,
                feature_snapshot=item.get("feature_snapshot", {}),
                memo=item.get("memo"),
                budget_amount=item.get("budget_amount"),
                currency=item.get("currency", "KRW"),
                user_url=item.get("user_url"),
                custom_marker_color=item.get("custom_marker_color"),
                custom_marker_icon=item.get("custom_marker_icon"),
            )
        )
    await db.commit()
    await db.refresh(plan)
    return plan
