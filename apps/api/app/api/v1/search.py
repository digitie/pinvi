"""`GET /search` — 통합 검색(feature + address + 내 POI). 감사 C-13 / `docs/api/features.md` §2.6.

feature는 krtour-map(httpx client), address는 kraddr-geo(v2 REST), my_pois는 TripMate DB.
외부 소스 한쪽이 불가해도 전체를 실패시키지 않고 해당 소스만 비우고 `degraded_sources`에 기록한다.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Query
from sqlalchemy import or_, select

from app.clients.kraddr_geo import KraddrGeoClientDep, KraddrGeoError
from app.clients.krtour_map import KrtourMapError, KrtourMapHttpClientDep
from app.core.deps import CurrentUserId, DbSession
from app.models.poi import TripDayPoi
from app.models.trip import Trip
from app.schemas.envelope import Envelope
from app.schemas.geo import UnifiedSearchResult

router = APIRouter(tags=["search"])

_MY_POI_LIMIT = 10


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


async def _search_my_pois(db: DbSession, *, user_id: uuid.UUID, q: str) -> list[dict[str, Any]]:
    """내 여행의 POI 중 이름/메모가 q에 매칭되는 것(소유 trip 한정)."""
    needle = f"%{_escape_like(q)}%"
    stmt = (
        select(TripDayPoi, Trip.title)
        .join(Trip, Trip.trip_id == TripDayPoi.trip_id)
        .where(
            Trip.owner_user_id == user_id,
            Trip.deleted_at.is_(None),
            TripDayPoi.deleted_at.is_(None),
            or_(
                TripDayPoi.feature_snapshot["name"].astext.ilike(needle, escape="\\"),
                TripDayPoi.user_note.ilike(needle, escape="\\"),
            ),
        )
        .order_by(TripDayPoi.updated_at.desc())
        .limit(_MY_POI_LIMIT)
    )
    rows = await db.execute(stmt)
    out: list[dict[str, Any]] = []
    for poi, trip_title in rows:
        snapshot = poi.feature_snapshot if isinstance(poi.feature_snapshot, dict) else {}
        out.append(
            {
                "poi_id": str(poi.attachment_id),
                "trip_id": str(poi.trip_id),
                "trip_title": trip_title,
                "feature_id": poi.feature_id,
                "name": snapshot.get("name"),
                "user_note": poi.user_note,
            }
        )
    return out


@router.get("/search", response_model=Envelope[UnifiedSearchResult])
async def unified_search(
    current_user_id: CurrentUserId,
    db: DbSession,
    krtour: KrtourMapHttpClientDep,
    kraddr: KraddrGeoClientDep,
    q: Annotated[str, Query(min_length=2, max_length=120)],
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
) -> Envelope[UnifiedSearchResult]:
    user_id = uuid.UUID(current_user_id)
    degraded: list[str] = []

    features: list[dict[str, Any]] = []
    try:
        feature_data = await krtour.search_features(q=q, page_size=limit)
        items = feature_data.get("items")
        if isinstance(items, list):
            features = [item for item in items if isinstance(item, dict)]
    except KrtourMapError:
        degraded.append("features")

    addresses: list[dict[str, Any]] = []
    try:
        address_data = await kraddr.search(query=q, kind="address", size=limit)
        candidates = address_data.get("candidates")
        if isinstance(candidates, list):
            addresses = [c for c in candidates if isinstance(c, dict)]
    except KraddrGeoError:
        degraded.append("addresses")

    my_pois = await _search_my_pois(db, user_id=user_id, q=q)

    return Envelope.of(
        UnifiedSearchResult(
            features=features,
            addresses=addresses,
            my_pois=my_pois,
            degraded_sources=degraded,
        )
    )
