/**
 * 지도 마커 z-index — #710.
 *
 * vworld-map-web `Marker`는 클릭한 마커를 전역 z-index(1001+)로 올리고, 그 값은 `zIndex` prop이 바뀔
 * 때만 풀린다. 그래서 선택 여부로 prop을 바꾼다 — 선택이 풀리면 승격도 풀려 같은 자리의 교통 마커를 계속
 * 덮지 않는다.
 *
 * 비선택은 0이다. z-index 0과 auto(묶음 거품·내 위치처럼 값을 주지 않은 마커)는 같은 층이라 지금처럼 DOM
 * 순서로 쌓인다 — 층 순서를 새로 정하지 않는다. 선택은 1로 그 위에 둔다. 마커는 canvas container(독립 쌓임
 * 맥락, #700) 안이라 popup 위로 올라가지 않는다. 이미 선택된 마커를 다시 누르면 prop이 그대로라 선택이
 * 풀릴 때까지 승격이 남는다(허용).
 */
export const MARKER_Z_BASE = 0;
export const MARKER_Z_SELECTED = 1;

export function markerZIndex(selected: boolean): number {
  return selected ? MARKER_Z_SELECTED : MARKER_Z_BASE;
}
