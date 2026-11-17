"""여행 장소(POI)의 시도·시군구 — 좌표만 있고 지역 코드가 없는 장소를 kor-travel-geo로 역지오코딩한다.

개인 홈의 '다녀온 지역'은 장소 snapshot의 지역 코드·주소에서 시도를 읽는다(`korea_regions`). 지도 검색으로
담은 장소는 snapshot에 좌표만 있어 시도를 정할 수 없었다. 그런 장소를 `POST /v2/reverse`로 한 번 조회해
snapshot의 `geo_region`에 남긴다.

- 장소 좌표다(사용자 위치가 아니다) — 위치정보 동의·확인자료 경로를 타지 않는다(소유자 결정 2026-11-17).
- 기존 snapshot 키는 건드리지 않는다. 결과는 별도 키 `geo_region`에만 쓴다:
  - 찾음: `{"status": "found", "sido_code", "sig_cd", "sido", "sigungu", "source", "resolved_at"}`
  - 행정구역 밖(바다 등): `{"status": "not_found", "source", "resolved_at"}` — 다시 묻지 않는다.
- geo 장애·4xx면 아무것도 쓰지 않는다. 다음 백필(`app.commands.poi_region_backfill`)이 다시 시도한다.
- 쓰기는 조회한 좌표가 그대로이고 `geo_region`이 아직 없을 때만 한다(그 사이 장소가 옮겨졌거나 다른 쓰기가
  먼저 끝났으면 버린다). 버전은 올리지 않는다 — 사용자의 편집(If-Match)과 다투지 않는 파생 값이다.
"""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal, Protocol, cast

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.kor_travel_geo import KorTravelGeoError
from app.db import session as db_session
from app.models.poi import TripDayPoi
from app.services.korea_regions import sido_from_code, sido_from_snapshot

logger = logging.getLogger(__name__)

GEO_REGION_KEY = "geo_region"
GEO_REGION_SOURCE = "kor-travel-geo"
# 배경 조회는 한 번만 짧게 묻는다 — 장애면 백필이 다시 한다.
BACKGROUND_ATTEMPT_TIMEOUT_SECONDS = 3.0

RegionOutcome = Literal["found", "not_found", "skipped", "unavailable"]


class ReverseGeocoder(Protocol):
    async def reverse(
        self,
        *,
        lon: float,
        lat: float,
        radius_m: int | None = None,
        include_region: bool = True,
        include_zipcode: bool = True,
        max_attempts: int | None = None,
        attempt_timeout_seconds: float | None = None,
    ) -> dict[str, Any]: ...


@dataclass(frozen=True)
class Coord:
    lon: float
    lat: float


def snapshot_coord(snapshot: object) -> Coord | None:
    """snapshot `coord`의 (lon, lat) — 한국 범위 밖이거나 숫자가 아니면 None."""
    if not isinstance(snapshot, Mapping):
        return None
    coord = snapshot.get("coord")
    if not isinstance(coord, Mapping):
        return None
    lon, lat = coord.get("lon"), coord.get("lat")
    if isinstance(lon, bool) or isinstance(lat, bool):
        return None
    if not isinstance(lon, int | float) or not isinstance(lat, int | float):
        return None
    if not (124.0 <= lon <= 132.0 and 33.0 <= lat <= 43.0):
        return None
    return Coord(lon=float(lon), lat=float(lat))


def needs_region_lookup(snapshot: object) -> bool:
    """좌표가 있고, 시도를 아직 정할 수 없고, 조회한 적도 없는 snapshot."""
    if not isinstance(snapshot, Mapping) or GEO_REGION_KEY in snapshot:
        return False
    return snapshot_coord(snapshot) is not None and sido_from_snapshot(snapshot) is None


def region_from_reverse(payload: Mapping[str, Any]) -> dict[str, str] | None:
    """`/v2/reverse` 응답의 첫 후보 region → 시도·시군구. 시도 코드를 정할 수 없으면 None."""
    candidates = payload.get("candidates")
    if not isinstance(candidates, list):
        return None
    for candidate in candidates:
        region = candidate.get("region") if isinstance(candidate, Mapping) else None
        if not isinstance(region, Mapping):
            continue
        sig_cd = region.get("sig_cd")
        bjd_cd = region.get("bjd_cd")
        code = sig_cd if isinstance(sig_cd, str) and sig_cd else bjd_cd
        sido_code = sido_from_code(code)
        if sido_code is None:
            continue
        result = {"status": "found", "sido_code": sido_code}
        if isinstance(sig_cd, str) and len(sig_cd) == 5 and sig_cd.isdigit():
            result["sig_cd"] = sig_cd
        for key in ("sido", "sigungu"):
            value = region.get(key)
            if isinstance(value, str) and value.strip():
                result[key] = value.strip()
        return result
    return None


async def lookup_region(
    client: ReverseGeocoder,
    coord: Coord,
    *,
    max_attempts: int | None = None,
    attempt_timeout_seconds: float | None = None,
) -> dict[str, str] | None:
    """좌표 → `geo_region` 값. 장애·4xx면 None(아무것도 쓰지 않는다)."""
    try:
        payload = await client.reverse(
            lon=coord.lon,
            lat=coord.lat,
            include_region=True,
            include_zipcode=False,
            max_attempts=max_attempts,
            attempt_timeout_seconds=attempt_timeout_seconds,
        )
    except KorTravelGeoError as exc:
        logger.info("poi_region.lookup_unavailable", extra={"error": type(exc).__name__})
        return None
    found = region_from_reverse(payload)
    return found if found is not None else {"status": "not_found"}


async def store_region(
    db: AsyncSession, *, poi_id: uuid.UUID, coord: Coord, region: Mapping[str, str]
) -> bool:
    """조회한 좌표가 그대로이고 `geo_region`이 없을 때만 snapshot에 합친다. 썼으면 True."""
    value = {
        **region,
        "source": GEO_REGION_SOURCE,
        "resolved_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    result = await db.execute(
        text(
            """
            UPDATE app.trip_day_pois
               SET feature_snapshot = feature_snapshot
                   || jsonb_build_object(:key, CAST(:value AS jsonb))
             WHERE attachment_id = :poi_id
               AND deleted_at IS NULL
               AND NOT (feature_snapshot ? :key)
               AND (feature_snapshot #>> '{coord,lon}')::double precision = :lon
               AND (feature_snapshot #>> '{coord,lat}')::double precision = :lat
            """
        ),
        {
            "key": GEO_REGION_KEY,
            "value": json.dumps(value, ensure_ascii=False),
            "poi_id": poi_id,
            "lon": coord.lon,
            "lat": coord.lat,
        },
    )
    return bool(getattr(result, "rowcount", 0))


async def resolve_poi_region(
    db: AsyncSession,
    client: ReverseGeocoder,
    poi_id: uuid.UUID,
    *,
    max_attempts: int | None = None,
    attempt_timeout_seconds: float | None = None,
) -> RegionOutcome:
    """한 장소의 시도를 정한다(필요할 때만 geo 호출). 호출부가 commit한다."""
    poi = await db.get(TripDayPoi, poi_id)
    if poi is None or poi.deleted_at is not None or not needs_region_lookup(poi.feature_snapshot):
        return "skipped"
    coord = snapshot_coord(poi.feature_snapshot)
    assert coord is not None  # needs_region_lookup가 확인했다
    region = await lookup_region(
        client,
        coord,
        max_attempts=max_attempts,
        attempt_timeout_seconds=attempt_timeout_seconds,
    )
    if region is None:
        return "unavailable"
    if not await store_region(db, poi_id=poi_id, coord=coord, region=region):
        return "skipped"
    return "found" if region.get("status") == "found" else "not_found"


def geo_client_from_app(app: object) -> ReverseGeocoder | None:
    """API lifespan이 만든 kor-travel-geo client(없으면 None — 조회를 건너뛴다)."""
    state = getattr(app, "state", None)
    client = getattr(state, "kor_travel_geo_client", None)
    if client is None or not hasattr(client, "reverse"):
        return None
    return cast("ReverseGeocoder", client)


async def resolve_poi_region_in_background(client: ReverseGeocoder, poi_id: uuid.UUID) -> None:
    """응답을 보낸 뒤 한 번 짧게 묻는다. 실패는 기록만 하고 백필에 맡긴다."""
    try:
        async with db_session.async_session_factory() as db:
            outcome = await resolve_poi_region(
                db,
                client,
                poi_id,
                max_attempts=1,
                attempt_timeout_seconds=BACKGROUND_ATTEMPT_TIMEOUT_SECONDS,
            )
            await db.commit()
    except Exception:  # 배경 작업 — 장소 저장은 이미 끝났다
        logger.warning("poi_region.background_failed", exc_info=True)
        return
    logger.info("poi_region.background", extra={"outcome": outcome})


def carry_geo_region(old: Mapping[str, Any], new: dict[str, Any]) -> dict[str, Any]:
    """PATCH로 snapshot이 바뀔 때 `geo_region`을 좌표에 맞춘다.

    좌표가 같으면 이전 조회 결과를 이어 쓰고(클라이언트가 키를 빠뜨려도 잃지 않는다), 좌표가 바뀌면
    지운다(옛 좌표의 시도가 남지 않게 — 새 좌표는 다시 조회한다).
    """
    same_place = snapshot_coord(new) == snapshot_coord(old)
    if not same_place:
        return {k: v for k, v in new.items() if k != GEO_REGION_KEY}
    if GEO_REGION_KEY not in new and GEO_REGION_KEY in old:
        return {**new, GEO_REGION_KEY: old[GEO_REGION_KEY]}
    return new
