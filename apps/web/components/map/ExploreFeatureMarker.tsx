'use client';

import { CirclePlaceMarker } from '@/components/map/CirclePlaceMarker';
import { MakiIcon } from '@/components/map/MakiIcon';
import type { ExploreMapPoint } from '@/lib/exploreMapPoints';
import { markerZIndex } from '@/lib/markerStacking';

/** 여행 지도 장소 마커(`TripMapView` TRIP_MAP_MARKER_SIZE/ICON_SIZE)와 같은 원·아이콘 크기. */
export const EXPLORE_MARKER_SIZE = 22;
export const EXPLORE_ICON_SIZE = 13;
/** live e2e가 탐색 지도 장소 마커를 찾는 class(여행 지도의 `trip-map-marker`에 대응). */
export const EXPLORE_MARKER_CLASS = 'explore-map-marker';

/**
 * 탐색 지도 장소 마커 — 여행 지도 장소 마커와 **같은 컴포넌트**(`CirclePlaceMarker`)로 같은 모양을 그린다:
 * 흰 테두리 원 + 원 안 흰 아이콘 + 오른쪽에 상자 없는 이름(소유자 요청 2026-11-17 "탐색지도의 마커도 여행과
 * 동일하게"). 원 색·아이콘은 카테고리에서 온다(`toExplorePoints`).
 *
 * - 날씨 아이콘: 탐색 지도는 장소별 날씨를 받지 않는다 — 마커마다 날씨를 부르지 않으므로 그리지 않는다
 *   (날씨는 별도 weather marker 층이 보인다).
 * - 이름은 라벨로 늘 보이므로 hover 상자(title)는 두지 않는다(여행 지도와 같다).
 * - 마커 루트의 `role=button`·`aria-label`(이름)·`data-interaction-id="feature:<id>"`는 그대로다 — live e2e
 *   helper(`featureMarkerButtons`)가 이것으로 찾는다.
 */
export function ExploreFeatureMarker({
  point,
  selected,
  onSelect,
}: {
  point: ExploreMapPoint;
  selected: boolean;
  onSelect: (point: ExploreMapPoint) => void;
}) {
  return (
    <CirclePlaceMarker
      lngLat={point.lngLat}
      icon={<MakiIcon icon={point.icon} size={EXPLORE_ICON_SIZE} />}
      color={point.color}
      size={EXPLORE_MARKER_SIZE}
      label={point.title}
      className={EXPLORE_MARKER_CLASS}
      selected={selected}
      zIndex={markerZIndex(selected)}
      ariaLabel={point.title}
      interactionId={'feature:' + point.featureId}
      onClick={() => onSelect(point)}
    />
  );
}
