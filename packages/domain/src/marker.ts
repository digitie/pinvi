/**
 * 16색 마커 팔레트 스타일 로직 — `docs/design/marker-palette.md`.
 *
 * 팔레트 데이터(P-01~P-16)는 `@pinvi/design-tokens`가 단일 진실로 소유한다.
 * 본 모듈은 (1) P-xx → hex 변환(마커 렌더 색), (2) 카테고리/kind fallback 매핑을
 * 제공한다. 백엔드 feature 응답이 marker_color/marker_icon 을 주면 그 값을 우선
 * 쓰고, 본 모듈 함수는 누락 시 fallback 으로만 쓴다. (Next.js 웹 / Expo 공용.)
 */

import { MARKER_PALETTE, type MarkerColorKey } from '@pinvi/design-tokens';

export { MARKER_PALETTE };
export type { MarkerColorKey };

/** 미상 색상 fallback — P-13 회색. */
export const FALLBACK_COLOR: MarkerColorKey = 'P-13';

function isMarkerColorKey(value: string): value is MarkerColorKey {
  return value in MARKER_PALETTE;
}

/** P-xx 코드를 hex 로. 미상/누락 시 회색(P-13). */
export function paletteHex(color: string | null | undefined): string {
  if (color && isMarkerColorKey(color)) {
    return MARKER_PALETTE[color].hex;
  }
  return MARKER_PALETTE[FALLBACK_COLOR].hex;
}

/** 마커 라벨(텍스트) 대비 색 — 노랑(P-03)만 어두운 글자. */
export function paletteLabelColor(color: string | null | undefined): string {
  if (color && isMarkerColorKey(color)) {
    return MARKER_PALETTE[color].label_color;
  }
  return MARKER_PALETTE[FALLBACK_COLOR].label_color;
}

interface MarkerStyle {
  icon: string;
  color: MarkerColorKey;
}

/** 카테고리 → maki 아이콘 + 기본 색 (`docs/design/marker-palette.md` §3). */
export const CATEGORY_MARKER: Record<string, MarkerStyle> = {
  주유소: { icon: 'fuel', color: 'P-02' },
  휴게소: { icon: 'car', color: 'P-15' },
  해수욕장: { icon: 'swimming', color: 'P-07' },
  골프장: { icon: 'golf', color: 'P-05' },
  숙박: { icon: 'lodging', color: 'P-10' },
  카페: { icon: 'cafe', color: 'P-12' },
  음식점: { icon: 'restaurant', color: 'P-01' },
  '미술관/박물관': { icon: 'museum', color: 'P-09' },
  관광명소: { icon: 'attraction', color: 'P-11' },
  '사찰/문화유산': { icon: 'religious-buddhist', color: 'P-03' },
  '편의점/마트': { icon: 'grocery', color: 'P-04' },
  '약국/병원': { icon: 'hospital', color: 'P-16' },
  '휴양림/수목원': { icon: 'park-alt1', color: 'P-05' },
  국가유산: { icon: 'monument', color: 'P-03' },
  주차장: { icon: 'parking', color: 'P-13' },
};

/** kind → 기본 마커 스타일 (카테고리 매핑이 없을 때 최종 fallback). */
export const KIND_MARKER: Record<string, MarkerStyle> = {
  place: { icon: 'marker', color: 'P-08' },
  event: { icon: 'star', color: 'P-11' },
  notice: { icon: 'alert', color: 'P-14' },
  price: { icon: 'fuel', color: 'P-02' },
  weather: { icon: 'marker', color: 'P-07' },
  route: { icon: 'walking', color: 'P-06' },
  area: { icon: 'park', color: 'P-05' },
};

/**
 * 카테고리 + kind 로 마커 스타일 결정. 카테고리 매핑 우선, 없으면 kind, 그래도
 * 없으면 회색 marker.
 */
export function markerStyleFor(
  category: string | null | undefined,
  kind: string | null | undefined
): MarkerStyle {
  if (category && category in CATEGORY_MARKER) {
    return CATEGORY_MARKER[category]!;
  }
  if (kind && kind in KIND_MARKER) {
    return KIND_MARKER[kind]!;
  }
  return { icon: 'marker', color: FALLBACK_COLOR };
}
