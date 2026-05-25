/**
 * 디자인 토큰 — Airbnb 톤 reference (저장소 루트 DESIGN.md + airbnb-marker-palette.html 기준).
 * `docs/architecture/frontend.md` §3.2 / `docs/architecture/map-marker-design.md` mirror.
 */

export const colors = {
  // 브랜드 / accent
  primary: '#ff385c', // Rausch — 모든 primary CTA / 검색 orb / heart save
  'primary-active': '#e00b41',
  'primary-disabled': '#ffd1da',
  luxe: '#460479',
  plus: '#92174d',

  // 표면
  canvas: '#ffffff',
  'surface-soft': '#f7f7f7',
  'surface-strong': '#f2f2f2',

  // 헤어라인 / 보더
  hairline: '#dddddd',
  'hairline-soft': '#ebebeb',
  'border-strong': '#c1c1c1',

  // 텍스트
  ink: '#222222',
  body: '#3f3f3f',
  muted: '#6a6a6a',
  'muted-soft': '#929292',
  'star-rating': '#222222',
  'on-primary': '#ffffff',

  // 시맨틱
  'error-text': '#c13515',
  'error-text-hover': '#b32505',
  'legal-link': '#428bff',

  // 스크림
  scrim: '#000000',
} as const;

/**
 * 16색 마커 팔레트 P-01 ~ P-16
 * `docs/design/marker-palette.md` + `airbnb-marker-palette.html` 기준.
 * WCAG AA 통과. 카테고리 매핑은 `app.category_mappings` DB + 라이브러리 default.
 */
export const MARKER_PALETTE = {
  'P-01': { hex: '#E53935', name: '빨강', label_color: '#FFFFFF' }, // 음식점
  'P-02': { hex: '#FB8C00', name: '주황', label_color: '#FFFFFF' }, // 주유소
  'P-03': { hex: '#FDD835', name: '노랑', label_color: '#222222' }, // 사찰/문화유산
  'P-04': { hex: '#7CB342', name: '연두', label_color: '#FFFFFF' }, // 편의점/마트
  'P-05': { hex: '#43A047', name: '초록', label_color: '#FFFFFF' }, // 골프장/휴양림/공원
  'P-06': { hex: '#00897B', name: '청록', label_color: '#FFFFFF' }, // 트래킹 route
  'P-07': { hex: '#00ACC1', name: '하늘색', label_color: '#FFFFFF' }, // 해수욕장
  'P-08': { hex: '#1E88E5', name: '파랑', label_color: '#FFFFFF' },
  'P-09': { hex: '#3949AB', name: '남색', label_color: '#FFFFFF' }, // 미술관/박물관
  'P-10': { hex: '#8E24AA', name: '보라', label_color: '#FFFFFF' }, // 숙박
  'P-11': { hex: '#D81B60', name: '자홍', label_color: '#FFFFFF' }, // 관광명소 / event
  'P-12': { hex: '#6D4C41', name: '갈색', label_color: '#FFFFFF' }, // 카페
  'P-13': { hex: '#757575', name: '회색', label_color: '#FFFFFF' }, // 주차장
  'P-14': { hex: '#212121', name: '검정', label_color: '#FFFFFF' }, // notice
  'P-15': { hex: '#F4511E', name: '주홍', label_color: '#FFFFFF' }, // 휴게소
  'P-16': { hex: '#039BE5', name: '청색', label_color: '#FFFFFF' }, // 약국/병원
} as const;

export type MarkerColorKey = keyof typeof MARKER_PALETTE;
export type MarkerColor = (typeof MARKER_PALETTE)[MarkerColorKey];
