import type { LngLatBounds } from 'maplibre-gl';
import { toBboxParam } from '@/lib/featureBounds';

/**
 * 장소 검색 지역 편향(2026-11-02 소유자 결정).
 *
 * "하회마을"을 검색하면 Map이 이름 정확 일치를 먼저 줘서 서울 식당 셋이 안동 마을보다 위에 왔다.
 * `/search`에 `bbox`를 주면 그 범위 안의 feature를 먼저, 밖의 결과는 뒤에 보여 준다(필터가 아니다).
 * 범위는 **여행 맥락 우선**(이 여행의 장소들), 없으면 지금 지도 화면이다.
 */

/** 여행 장소 경계에 붙이는 여백(도) — 약 25km. 하루 동선 주변의 이웃 명소까지 포함되게. */
export const TRIP_BIAS_PADDING_DEGREES = 0.25;

/**
 * 편향 bbox는 소수 2자리(≈1km)로 거칠게 보낸다 — 순서 편향에는 그만큼이면 충분하고, 탐색 지도 화면은 동의 후
 * 기기 위치로 자동 센터링될 수 있으므로 정밀한 화면 좌표를 PinVi API 요청(접근 로그)에 싣지 않는다. bbox는
 * PinVi API 밖(Map·Kakao·Naver)으로는 나가지 않는다.
 */
const BIAS_PRECISION = 2;

/** 지금 지도 화면 → 편향 bbox(거칠게). */
export function viewportSearchBias(bounds: LngLatBounds): string {
  return toBboxParam(
    bounds.getWest(),
    bounds.getSouth(),
    bounds.getEast(),
    bounds.getNorth(),
    BIAS_PRECISION,
  );
}

/** 여행 장소들의 경계를 여백만큼 넓힌 bbox(`lng_min,lat_min,lng_max,lat_max`). 좌표가 없으면 null. */
export function tripSearchBias(
  points: ReadonlyArray<{ lon: number; lat: number }>,
  padDegrees: number = TRIP_BIAS_PADDING_DEGREES,
): string | null {
  const valid = points.filter((p) => Number.isFinite(p.lon) && Number.isFinite(p.lat));
  if (valid.length === 0) return null;
  let west = Infinity;
  let south = Infinity;
  let east = -Infinity;
  let north = -Infinity;
  for (const { lon, lat } of valid) {
    west = Math.min(west, lon);
    east = Math.max(east, lon);
    south = Math.min(south, lat);
    north = Math.max(north, lat);
  }
  return toBboxParam(
    west - padDegrees,
    south - padDegrees,
    east + padDegrees,
    north + padDegrees,
    BIAS_PRECISION,
  );
}

/** 여행 맥락이 있으면 그것, 없으면 지도 화면. */
export function pickSearchBias(
  tripBias: string | null,
  viewportBias: string | null,
): string | null {
  return tripBias ?? viewportBias;
}
