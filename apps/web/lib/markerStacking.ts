/**
 * 지도 마커 층(z-index) — #710.
 *
 * vworld-map-web `Marker`는 클릭한 마커를 전역 z-index(1001+)로 올리고, 그 값은 `zIndex` prop이 바뀔
 * 때만 풀린다. 층마다 고정 zIndex를 주고 선택 여부로 값을 바꾸면, 선택이 풀릴 때 원래 층으로 돌아가
 * 같은 자리의 교통 마커를 계속 덮지 않는다. 마커는 canvas container(독립 쌓임 맥락, #700) 안이라
 * 이 값은 popup 위로 올라가지 않는다.
 */
export const MARKER_Z = {
  feature: 1,
  featureSelected: 2,
  transport: 3,
  transportSelected: 4,
  tripPoi: 5,
  tripPoiSelected: 6,
} as const;

export type MarkerLayer = 'feature' | 'transport' | 'tripPoi';

export function markerZIndex(layer: MarkerLayer, selected: boolean): number {
  switch (layer) {
    case 'feature':
      return selected ? MARKER_Z.featureSelected : MARKER_Z.feature;
    case 'transport':
      return selected ? MARKER_Z.transportSelected : MARKER_Z.transport;
    case 'tripPoi':
      return selected ? MARKER_Z.tripPoiSelected : MARKER_Z.tripPoi;
  }
}
