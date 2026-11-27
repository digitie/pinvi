"""지도 장소 layer에서 transport 레이어가 소유한 항목을 뺀다 (ADR-076 보강, 2026-11-27).

주유소·교통 돌발은 지도에서 **transport 레이어**(`/transport/*`, Map 상태 저장소)가 그린다 — "주유소"·"교통 돌발"
토글이 켜져 있을 때만 보인다. 그런데 Map PG에는 같은 주유소가 일반 장소 feature(카테고리 `06020000`
`TRANSPORT_FUEL`, ADR-106 place job)로도 남아 있어, 토글을 꺼도 `/features/in-bounds`·`/features/nearby`가
평범한 장소 마커·주변 목록으로 돌려줬고, 켜면 같은 주유소가 두 번(주유소 마커 + 장소 마커) 보였다.

그래서 지도 장소 표면(in-bounds·nearby)에서는 이 항목을 **서버에서** 뺀다. 토글이 꺼지면 아무 데도 없고, 켜면
transport 마커 하나만 남는다(중복 제거). Map에는 제외 필터가 없어(포함 `category`만 있다) PinVi가 응답을 거른다.

- 주유소: 카테고리가 `0602`로 시작하는 장소(Map `PlaceCategoryCode.TRANSPORT_FUEL` 계층 — 원천 무관). 호출자가
  `category`로 주유소 계층을 **명시해** 고르면 그 뜻대로 돌려준다.
- 교통 돌발: Map krex 교통 notice(`TRAFFIC_NOTICE_CATEGORY` ``99000000`` + `TRAFFIC_NOTICE_MARKER_ICON`
  ``roadblock``). ``99000000``은 산림 안전 notice 등과 함께 쓰는 placeholder라 카테고리만으로는 가르지 않는다. Map은
  2026-10-24(migration 419) PG 교통 돌발을 퇴역했으므로 지금은 방어용이다.

남는 한계: Map 서버 클러스터(저배율 `clusters[]`)의 개수는 Map이 세므로 이 항목을 포함한다. 개별 마커가 보이는
배율에서는 빠진다. 통합 검색(`GET /search`)·여행 장소(POI)는 사용자가 명시한 선택이라 거르지 않는다.
"""

from __future__ import annotations

from typing import Final

from app.schemas.feature import FeatureSummary

#: Map `PlaceCategoryCode.TRANSPORT_FUEL`(`06020000`) 계층 접두.
FUEL_STATION_CATEGORY_PREFIX: Final[str] = "0602"
#: Map krex 교통 notice 식별자(`providers/krex.py` TRAFFIC_NOTICE_CATEGORY·TRAFFIC_NOTICE_MARKER_ICON).
TRAFFIC_NOTICE_CATEGORY: Final[str] = "99000000"
TRAFFIC_NOTICE_MARKER_ICON: Final[str] = "roadblock"


def is_fuel_station_category(category: str | None) -> bool:
    return bool(category) and str(category).startswith(FUEL_STATION_CATEGORY_PREFIX)


def is_transport_layer_feature(summary: FeatureSummary) -> bool:
    """이 feature를 transport 레이어가 그리는가(주유소 장소·교통 돌발 notice)."""
    if summary.kind == "place" and is_fuel_station_category(summary.category):
        return True
    return (
        summary.kind == "notice"
        and summary.category == TRAFFIC_NOTICE_CATEGORY
        and summary.marker_icon == TRAFFIC_NOTICE_MARKER_ICON
    )


def without_transport_layer_features(
    items: list[FeatureSummary], *, requested_category: str | None
) -> list[FeatureSummary]:
    """지도 장소 표면 응답에서 transport 레이어 항목을 뺀다. 주유소 카테고리를 명시해 고른 요청은 그대로."""
    if is_fuel_station_category(requested_category):
        return items
    return [item for item in items if not is_transport_layer_feature(item)]
