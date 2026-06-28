# 16색 마커 팔레트 — Pinvi v2

SPEC V8 #3 (I-6) + v1의 색상 reference HTML(`airbnb-marker-palette.html`)을
Pinvi v2의 마커 표시 표준으로 박는다.

## 1. 위치 / 책임

- 색상 reference (사용자 시각 확인용): 저장소 루트 `airbnb-marker-palette.html`
  (브라우저로 직접 열어서 미리보기. v1 시점의 자산 그대로 보존)
- 디자인 시스템 가이드(브랜드/타이포/컴포넌트): 저장소 루트 `DESIGN.md`
  (v1 자산 — Airbnb 디자인 토큰 reference로 사용. Pinvi 브랜드 결정 전 임시
  기준)
- 본 문서: 마커 팔레트의 **운영 규칙** + 카테고리 매핑

## 2. 16색 코드

`apps/web/lib/markerPalette.ts`에 다음 상수를 박는다 (코드 작성 단계 진입 후):

```ts
export const MARKER_PALETTE = {
  'P-01': { hex: '#E53935', name: '빨강', label_color: '#FFFFFF' },
  'P-02': { hex: '#FB8C00', name: '주황', label_color: '#FFFFFF' },
  'P-03': { hex: '#FDD835', name: '노랑', label_color: '#222222' },
  'P-04': { hex: '#7CB342', name: '연두', label_color: '#FFFFFF' },
  'P-05': { hex: '#43A047', name: '초록', label_color: '#FFFFFF' },
  'P-06': { hex: '#00897B', name: '청록', label_color: '#FFFFFF' },
  'P-07': { hex: '#00ACC1', name: '하늘색', label_color: '#FFFFFF' },
  'P-08': { hex: '#1E88E5', name: '파랑', label_color: '#FFFFFF' },
  'P-09': { hex: '#3949AB', name: '남색', label_color: '#FFFFFF' },
  'P-10': { hex: '#8E24AA', name: '보라', label_color: '#FFFFFF' },
  'P-11': { hex: '#D81B60', name: '자홍', label_color: '#FFFFFF' },
  'P-12': { hex: '#6D4C41', name: '갈색', label_color: '#FFFFFF' },
  'P-13': { hex: '#757575', name: '회색', label_color: '#FFFFFF' },
  'P-14': { hex: '#212121', name: '검정', label_color: '#FFFFFF' },
  'P-15': { hex: '#F4511E', name: '주홍', label_color: '#FFFFFF' },
  'P-16': { hex: '#039BE5', name: '청색', label_color: '#FFFFFF' },
} as const;

export type MarkerColorKey = keyof typeof MARKER_PALETTE;
```

WCAG AA 대비 통과 기준으로 선정된 채도·명도. 브랜드 색상이 확정되면 별도 ADR로
교체.

## 3. 카테고리 ↔ maki 아이콘 ↔ 기본 색상 매핑

| 카테고리      | maki icon            | 기본 색상   | 비고                       |
| ------------- | -------------------- | ----------- | -------------------------- |
| 주유소        | `fuel`               | P-02 주황   | price feature: `fuel`      |
| 휴게소        | `car`                | P-15 주홍   | KREX 소스                  |
| 해수욕장      | `swimming`           | P-07 하늘색 | KHOA 해수욕지수와 함께     |
| 골프장        | `golf`               | P-05 초록   |                            |
| 숙박          | `lodging`            | P-10 보라   |                            |
| 카페          | `cafe`               | P-12 갈색   |                            |
| 음식점        | `restaurant`         | P-01 빨강   |                            |
| 미술관/박물관 | `museum`             | P-09 남색   |                            |
| 관광명소      | `attraction`         | P-11 자홍   |                            |
| 사찰/문화유산 | `religious-buddhist` | P-03 노랑   |                            |
| 편의점/마트   | `grocery`            | P-04 연두   |                            |
| 약국/병원     | `hospital`           | P-16 청색   |                            |
| 축제(event)   | `star`               | P-11 자홍   | 이벤트는 별표              |
| 공지(notice)  | `alert`              | P-14 검정   | 바다갈라짐/특보            |
| 휴양림/수목원 | `park-alt1`          | P-05 초록   | `python-krforest-api` 소스 |
| 국가유산      | `monument`           | P-03 노랑   | `python-krheritage-api`    |
| 트래킹 route  | `walking`            | P-06 청록   | 산림청 숲길 / 등산코스     |
| 국립공원 area | `park`               | P-05 초록   | KNPS / 산림청              |
| 주차장        | `parking`            | P-13 회색   | 표준데이터 15012896        |

`maki` 아이콘은 Mapbox Maki 8.0 (`https://github.com/mapbox/maki`). `apps/web/
public/maki/` 에 사용한 SVG를 vendoring (v1에서도 사용한 패턴).

## 4. 운영 정책

- 카테고리 taxonomy와 `maki_icon` 정본은 **`kor-travel-map` `/v1/categories`**다.
  Pinvi는 feature category를 직접 저장·정규화하지 않는다.
- Pinvi의 16색 팔레트와 `packages/domain`의 fallback 상수는 marker preview/누락 보정용이다.
  `/admin/category-mapping`은 read-only 운영 뷰로 upstream catalog와 Pinvi fallback drift를 보여준다.
- 클라이언트 표시 우선순위: 사용자 custom marker color/icon → 서버 resolved marker →
  upstream feature marker → feature snapshot marker → upstream category/kind fallback →
  Pinvi `P-13` 회색 fallback.
- 사용자가 POI별로 색/아이콘을 직접 변경하면 `app.trip_day_pois.custom_marker_color` /
  `custom_marker_icon`에 저장 — 카테고리 매핑과 무관
- 마커 표시는 항상 **불투명** (배경 색 + 흰 또는 검은 텍스트 1:1 매칭)
- 클러스터 마커는 별도 디자인 (숫자 강조)
- StyleSeed 적용 후에도 마커 16색은 **데이터 카테고리 표현 예외**로 유지한다.
  Primary CTA, nav, form 강조, 상태 메시지에는 마커 색을 재사용하지 않는다.

## 5. 색상 시각 확인

브라우저에서 `airbnb-marker-palette.html`을 직접 열면:

- 16색 칩 + Airbnb 스타일 카드 레이아웃
- Fraunces (display) + Manrope (body) + JetBrains Mono (code) 폰트로 색상 표시
- 색상 hex + 이름 + label color 미리보기

> 위 HTML은 Airbnb 디자인 가이드(저장소 루트 `DESIGN.md`)를 기준으로 만든 reference 데모다.
> Pinvi 자체 브랜드가 확정되면 별도 ADR로 본 팔레트를 교체하거나 확장한다.

## 6. SPEC V8 cross-reference

- SPEC V8 #3 I-6 (16색 팔레트 + maki 매핑)
- SPEC V8 #3 I-7 (마커 우클릭 색/아이콘 변경)
- SPEC V8 #4 M-2 (`/admin/category-mapping`)
- SPEC V8 #4 M-13 (Admin 시나리오 "feature 링크 broken 시뮬레이션")

## 7. 관련 문서

- `docs/architecture.md` §2.2 프론트
- `docs/spec/v8/03-frontend.md` (Next.js 스택)
- `docs/data-model.md` §2.3 POI 첨부
- `airbnb-marker-palette.html` (저장소 루트, 시각 미리보기)
- `DESIGN.md` (저장소 루트, Airbnb 디자인 토큰 reference)
