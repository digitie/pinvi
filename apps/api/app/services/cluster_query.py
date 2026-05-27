"""viewport feature 클러스터링 보조 — TripMate 측 PostGIS 쿼리.

라이브러리 측 클러스터링이 기본이지만 (라이브러리 `features_in_bounds(zoom=)`),
TripMate가 `app.trip_day_pois` 의 POI 마커를 viewport에 겹쳐 표시할 때 자체
클러스터링이 필요. 본 service 는 그것을 담당.

zoom별 클러스터링 단계:
- zoom < 7  : 시도 단위 (`bjd_lookup` sido 코드 group by)
- zoom < 11 : 시군구 단위 (`bjd_lookup` sigungu 코드 group by)
- zoom < 14 : `ST_ClusterDBSCAN` (PostGIS, eps=300m)
- zoom >= 14: 개별 마커 (클러스터 X)

SPEC V8 §H-4 + SPRINT-4 §클러스터링 + ADR 후보 viewport 클러스터링 전략.

데이터 모델 주의 (raw SQL):
- `app.trip_day_pois` PK = `attachment_id` (legacy 명명), FK = `(trip_id, day_index)`
- `app.trip_days` PK = composite `(trip_id, day_index)`
- 좌표는 `feature.feature` (`coord_4326` geography) — 라이브러리 schema (조회만)
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Literal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

ClusterMode = Literal["sido", "sigungu", "dbscan", "individual"]


def select_cluster_mode(zoom: int) -> ClusterMode:
    """zoom level → 클러스터 모드 결정.

    >>> select_cluster_mode(5)
    'sido'
    >>> select_cluster_mode(8)
    'sigungu'
    >>> select_cluster_mode(12)
    'dbscan'
    >>> select_cluster_mode(15)
    'individual'
    """
    if zoom < 7:
        return "sido"
    if zoom < 11:
        return "sigungu"
    if zoom < 14:
        return "dbscan"
    return "individual"


async def cluster_trip_pois(
    db: AsyncSession,
    *,
    trip_id: uuid.UUID,
    zoom: int,
    bbox: tuple[float, float, float, float],
) -> list[dict[str, Any]]:
    """trip의 POI 마커를 zoom별로 클러스터링 후 반환.

    `app.trip_day_pois` 는 좌표가 없고 `feature_id` 만 — 좌표는 `feature.feature` join
    필요. 본 함수는 join SQL을 raw text로 박는다 (`docs/conventions/geospatial.md`).
    """
    mode = select_cluster_mode(zoom)
    params: dict[str, Any] = {
        "trip_id": str(trip_id),
        "lng_min": bbox[0],
        "lat_min": bbox[1],
        "lng_max": bbox[2],
        "lat_max": bbox[3],
    }

    if mode == "individual":
        sql = text("""
            SELECT
                p.attachment_id::text AS poi_id,
                ST_X(f.coord_4326::geometry) AS lng,
                ST_Y(f.coord_4326::geometry) AS lat,
                p.custom_marker_color AS marker_color,
                p.custom_marker_icon AS marker_icon
            FROM app.trip_day_pois p
            JOIN feature.feature f ON f.feature_id::text = p.feature_id
            WHERE p.trip_id = :trip_id
              AND p.deleted_at IS NULL
              AND f.coord_4326 && ST_MakeEnvelope(
                  :lng_min, :lat_min, :lng_max, :lat_max, 4326
              )
        """)
        result = await db.execute(sql, params)
        return [dict(row._mapping) for row in result]

    if mode == "dbscan":
        # ST_ClusterDBSCAN — eps 300m (5179 meter CRS 기준 변환 후)
        sql = text("""
            WITH viewport AS (
                SELECT
                    p.attachment_id AS poi_id,
                    f.coord_4326,
                    f.kind,
                    ST_Transform(f.coord_4326::geometry, 5179) AS coord_5179
                FROM app.trip_day_pois p
                JOIN feature.feature f ON f.feature_id::text = p.feature_id
                WHERE p.trip_id = :trip_id
                  AND p.deleted_at IS NULL
                  AND f.coord_4326 && ST_MakeEnvelope(
                      :lng_min, :lat_min, :lng_max, :lat_max, 4326
                  )
            ),
            clustered AS (
                SELECT
                    ST_ClusterDBSCAN(coord_5179, eps := 300, minpoints := 2)
                        OVER () AS cluster_id,
                    poi_id, coord_4326, kind
                FROM viewport
            )
            SELECT
                COALESCE(cluster_id::text, 'solo-' || poi_id::text) AS cluster_id,
                AVG(ST_X(coord_4326::geometry)) AS lng_center,
                AVG(ST_Y(coord_4326::geometry)) AS lat_center,
                COUNT(*) AS count,
                ARRAY_AGG(DISTINCT kind) AS sample_kinds
            FROM clustered
            GROUP BY cluster_id, poi_id
        """)
        result = await db.execute(sql, params)
        return [dict(row._mapping) for row in result]

    # sido / sigungu — `feature.bjd_lookup` 으로 행정구역 매핑 group by
    bjd_column = "sido_code" if mode == "sido" else "sigungu_code"
    sql = text(f"""
        SELECT
            b.{bjd_column} AS cluster_id,
            AVG(ST_X(f.coord_4326::geometry)) AS lng_center,
            AVG(ST_Y(f.coord_4326::geometry)) AS lat_center,
            COUNT(*) AS count,
            ARRAY_AGG(DISTINCT f.kind) AS sample_kinds
        FROM app.trip_day_pois p
        JOIN feature.feature f ON f.feature_id::text = p.feature_id
        LEFT JOIN feature.bjd_lookup b ON b.bjd_code = f.bjd_code
        WHERE p.trip_id = :trip_id
          AND p.deleted_at IS NULL
          AND f.coord_4326 && ST_MakeEnvelope(
              :lng_min, :lat_min, :lng_max, :lat_max, 4326
          )
        GROUP BY b.{bjd_column}
        HAVING b.{bjd_column} IS NOT NULL
    """)  # noqa: S608 — bjd_column 은 Literal로 화이트리스트, SQL injection X
    result = await db.execute(sql, params)
    return [dict(row._mapping) for row in result]
