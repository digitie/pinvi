/**
 * 16색 마커 팔레트 + 카테고리 매핑 — `docs/design/marker-palette.md`.
 *
 * 백엔드 feature 응답은 `marker_color`(P-01~P-16) + `marker_icon`(maki) 를 이미 해석해
 * 내려준다. 본 모듈은 (1) P-xx → hex 변환(마커 렌더 색), (2) 카테고리/kind fallback
 * 매핑(서버가 색/아이콘을 못 준 경우)을 제공한다.
 */

export const MARKER_PALETTE = {
  'P-01': { hex: '#E53935', name: '빨강', labelColor: '#FFFFFF' },
  'P-02': { hex: '#FB8C00', name: '주황', labelColor: '#FFFFFF' },
  'P-03': { hex: '#FDD835', name: '노랑', labelColor: '#222222' },
  'P-04': { hex: '#7CB342', name: '연두', labelColor: '#FFFFFF' },
  'P-05': { hex: '#43A047', name: '초록', labelColor: '#FFFFFF' },
  'P-06': { hex: '#00897B', name: '청록', labelColor: '#FFFFFF' },
  'P-07': { hex: '#00ACC1', name: '하늘색', labelColor: '#FFFFFF' },
  'P-08': { hex: '#1E88E5', name: '파랑', labelColor: '#FFFFFF' },
  'P-09': { hex: '#3949AB', name: '남색', labelColor: '#FFFFFF' },
  'P-10': { hex: '#8E24AA', name: '보라', labelColor: '#FFFFFF' },
  'P-11': { hex: '#D81B60', name: '자홍', labelColor: '#FFFFFF' },
  'P-12': { hex: '#6D4C41', name: '갈색', labelColor: '#FFFFFF' },
  'P-13': { hex: '#757575', name: '회색', labelColor: '#FFFFFF' },
  'P-14': { hex: '#212121', name: '검정', labelColor: '#FFFFFF' },
  'P-15': { hex: '#F4511E', name: '주홍', labelColor: '#FFFFFF' },
  'P-16': { hex: '#039BE5', name: '청색', labelColor: '#FFFFFF' },
} as const;

export type MarkerColorKey = keyof typeof MARKER_PALETTE;

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
    return MARKER_PALETTE[color].labelColor;
  }
  return MARKER_PALETTE[FALLBACK_COLOR].labelColor;
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
 * 카테고리 + kind 로 마커 스타일 결정. 카테고리 매핑 우선, 없으면 kind, 그래도 없으면
 * 회색 marker. (서버가 marker_color/marker_icon 을 주면 그 값을 우선 쓰고 본 함수는 fallback.)
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
