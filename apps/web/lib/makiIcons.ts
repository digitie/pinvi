/**
 * 지도 마커 아이콘(maki) — 지도 마커와 아이콘 고르기(PoiEditor)가 같은 그림을 쓰도록 한곳에 둔다.
 *
 * 저장값은 maki 아이콘 이름(`custom_marker_icon`, `^[a-z0-9_-]{1,64}$`)이고, 서버·kor-travel-map이
 * 주는 카테고리 아이콘도 같은 이름 공간이다. 고르기 목록에 없는 이름(카테고리가 준 값)도 그대로
 * 그리며, 그림을 못 받으면 `marker`로 대신한다.
 */

export const MAKI_ICON_BASE_URL = 'https://unpkg.com/@mapbox/maki@8.0.0/icons';

/** 옛 저장값·카테고리 표가 쓰는, maki 8에 없는 이름 → 있는 이름. */
const MAKI_ICON_ALIASES: Record<string, string> = {
  alert: 'danger',
  camera: 'viewpoint',
  walking: 'mountain',
};

export function makiIconName(icon: string): string {
  return MAKI_ICON_ALIASES[icon] ?? icon;
}

export function makiIconUrl(icon: string): string {
  return `${MAKI_ICON_BASE_URL}/${encodeURIComponent(icon)}.svg`;
}

export interface MarkerIconOption {
  /** 저장하는 maki 이름. */
  icon: string;
  /** 고르기 버튼의 접근 이름. */
  label: string;
}

/**
 * 장소 마커 아이콘 고르기 목록 — 여행 장소에 흔한 종류 위주(구글·네이버 지도 카테고리 칩 참고).
 * 모든 이름은 maki 8.0.0에 있는 아이콘이고(2026-11-16 unpkg 200 확인), 화면에서는 앱에 묶인 lucide
 * 그림으로 그린다(`lib/markerIconGlyphs.ts` — 외부 요청 없음).
 */
export const MARKER_ICON_OPTIONS: readonly MarkerIconOption[] = [
  { icon: 'marker', label: '기본 핀' },
  { icon: 'star', label: '별' },
  { icon: 'heart', label: '하트' },
  { icon: 'home', label: '집' },
  { icon: 'lodging', label: '숙소' },
  { icon: 'campsite', label: '캠핑' },
  { icon: 'restaurant', label: '음식점' },
  { icon: 'cafe', label: '카페' },
  { icon: 'bakery', label: '빵집' },
  { icon: 'bar', label: '술집' },
  { icon: 'shop', label: '쇼핑' },
  { icon: 'grocery', label: '마트' },
  { icon: 'attraction', label: '명소' },
  { icon: 'viewpoint', label: '전망' },
  { icon: 'museum', label: '박물관' },
  { icon: 'monument', label: '유적' },
  { icon: 'castle', label: '성' },
  { icon: 'religious-buddhist', label: '사찰' },
  { icon: 'park', label: '공원' },
  { icon: 'mountain', label: '산' },
  { icon: 'beach', label: '해변' },
  { icon: 'swimming', label: '물놀이' },
  { icon: 'amusement-park', label: '놀이공원' },
  { icon: 'zoo', label: '동물원' },
  { icon: 'aquarium', label: '아쿠아리움' },
  { icon: 'theatre', label: '공연' },
  { icon: 'golf', label: '골프' },
  { icon: 'bicycle', label: '자전거' },
  { icon: 'parking', label: '주차' },
  { icon: 'fuel', label: '주유' },
  { icon: 'car', label: '자동차' },
  { icon: 'bus', label: '버스' },
  { icon: 'rail', label: '기차' },
  { icon: 'airport', label: '공항' },
  { icon: 'ferry', label: '배' },
  { icon: 'hospital', label: '병원' },
];
