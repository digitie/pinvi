/**
 * 지도 viewport → `/features/in-bounds` bbox 파라미터 변환.
 *
 * bbox 포맷은 api-client `featureApi.inBounds` 가 기대하는 `"lng_min,lat_min,lng_max,lat_max"`.
 * 백엔드 `BBox` 는 한국 범위(경도 124~132 / 위도 33~43, ADR-018)만 허용하므로, 바다·국경
 * 밖까지 늘어난 viewport 는 한국 범위로 clamp 해서 422 를 피한다.
 */

import type maplibregl from 'maplibre-gl';

export const KOREA_BOUNDS = {
  lngMin: 124,
  latMin: 33,
  lngMax: 132,
  latMax: 43,
} as const;

function clamp(value: number, min: number, max: number): number {
  if (value < min) return min;
  if (value > max) return max;
  return value;
}

/**
 * 순수 함수 — west/south/east/north 를 한국 범위로 clamp 한 bbox 문자열로.
 * 기본은 소수점 5자리(≈1m)로 고정한다. 낮은 줌에서 더 거친 precision을 넘기면
 * west/south는 floor, east/north는 ceil로 바깥쪽 확장해 캐시 키를 안정화한다.
 */
export function toBboxParam(
  west: number,
  south: number,
  east: number,
  north: number,
  precision = 5
): string {
  const p = Math.max(0, Math.min(5, Math.floor(precision)));
  const factor = 10 ** p;
  const w = clamp(Math.min(west, east), KOREA_BOUNDS.lngMin, KOREA_BOUNDS.lngMax);
  const e = clamp(Math.max(west, east), KOREA_BOUNDS.lngMin, KOREA_BOUNDS.lngMax);
  const s = clamp(Math.min(south, north), KOREA_BOUNDS.latMin, KOREA_BOUNDS.latMax);
  const n = clamp(Math.max(south, north), KOREA_BOUNDS.latMin, KOREA_BOUNDS.latMax);
  const qWest = Math.floor(w * factor) / factor;
  const qSouth = Math.floor(s * factor) / factor;
  const qEast = Math.ceil(e * factor) / factor;
  const qNorth = Math.ceil(n * factor) / factor;
  return `${qWest.toFixed(p)},${qSouth.toFixed(p)},${qEast.toFixed(p)},${qNorth.toFixed(p)}`;
}

/** 낮은 zoom일수록 더 거친 bbox 키를 써서 넓은 지도 이동 refetch churn을 줄인다. */
export function bboxPrecisionForZoom(zoom: number): number {
  const z = clampZoom(zoom);
  if (z <= 7) return 2;
  if (z <= 10) return 3;
  return 5;
}

/** maplibre 지도 경계 → bbox 파라미터. */
export function boundsToBbox(bounds: maplibregl.LngLatBounds, zoom?: number): string {
  const precision = zoom == null ? 5 : bboxPrecisionForZoom(zoom);
  return toBboxParam(
    bounds.getWest(),
    bounds.getSouth(),
    bounds.getEast(),
    bounds.getNorth(),
    precision
  );
}

/** 줌은 백엔드 스키마(5~19)로 clamp. */
export function clampZoom(zoom: number): number {
  return Math.round(clamp(zoom, 5, 19));
}
