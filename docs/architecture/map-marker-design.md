# 지도 마커 + 로그인 UI 디자인

지도 마커 (16색 + maki) + 로그인 / 가입 화면 디자인 — `DESIGN.md` (Airbnb 톤) +
`airbnb-marker-palette.html` (16색 reference) 기준. v1 `docs/architecture/map-marker-design.md` 정리.

## 1. 디자인 토큰 출처

- 저장소 루트 `DESIGN.md` — Airbnb 디자인 시스템 reference
- 저장소 루트 `airbnb-marker-palette.html` — 16색 시각 미리보기
- `docs/design/marker-palette.md` — 마커 운영 규칙

**마커 색상은 `airbnb-marker-palette.html`의 16색이 `DESIGN.md`보다 우선** (디자인
영역 분리).

## 2. 16색 마커 팔레트 (P-01 ~ P-16)

```ts
// packages/design-tokens/src/colors.ts
export const MARKER_PALETTE = {
  'P-01': { hex: '#E53935', name: '빨강' },       // 음식점
  'P-02': { hex: '#FB8C00', name: '주황' },       // 주유소
  'P-03': { hex: '#FDD835', name: '노랑' },       // 사찰/문화유산
  'P-04': { hex: '#7CB342', name: '연두' },       // 편의점/마트
  'P-05': { hex: '#43A047', name: '초록' },       // 골프장 / 휴양림 / 국립공원
  'P-06': { hex: '#00897B', name: '청록' },       // 트래킹 route
  'P-07': { hex: '#00ACC1', name: '하늘색' },     // 해수욕장
  'P-08': { hex: '#1E88E5', name: '파랑' },
  'P-09': { hex: '#3949AB', name: '남색' },       // 미술관/박물관
  'P-10': { hex: '#8E24AA', name: '보라' },       // 숙박
  'P-11': { hex: '#D81B60', name: '자홍' },       // 관광명소 / event(축제)
  'P-12': { hex: '#6D4C41', name: '갈색' },       // 카페
  'P-13': { hex: '#757575', name: '회색' },       // 주차장
  'P-14': { hex: '#212121', name: '검정' },       // notice(공지)
  'P-15': { hex: '#F4511E', name: '주홍' },       // 휴게소
  'P-16': { hex: '#039BE5', name: '청색' },       // 약국/병원
} as const;
```

자세한 카테고리 매핑은 `docs/design/marker-palette.md` §3.

## 3. Maki 아이콘 자체 호스팅

- 라이브러리: `@mapbox/maki@^8.2.0` (CC0-1.0, build-only)
- 위치: `apps/web/public/maki/<icon>.svg`
- 빌드 sync: `apps/web/scripts/sync-maki-icons.mjs` (Maki npm package에서 필요한 SVG만 복사)

```js
// apps/web/scripts/sync-maki-icons.mjs
import { copyFileSync, mkdirSync } from 'fs';
import { resolve } from 'path';

const ICONS_NEEDED = [
  'restaurant', 'fuel', 'religious-buddhist', 'grocery', 'golf',
  'swimming', 'museum', 'lodging', 'attraction', 'star',
  'cafe', 'parking', 'alert', 'car', 'hospital',
  'park-alt1', 'monument', 'walking', 'park',
];

const src = resolve('node_modules/@mapbox/maki/icons');
const dst = resolve('public/maki');
mkdirSync(dst, { recursive: true });

for (const icon of ICONS_NEEDED) {
  copyFileSync(`${src}/${icon}.svg`, `${dst}/${icon}.svg`);
}
console.log(`Synced ${ICONS_NEEDED.length} icons to public/maki/`);
```

`package.json`에 `"sync-maki": "node scripts/sync-maki-icons.mjs"` 추가.

규칙:

- runtime에서 raw GitHub / Mapbox CDN / 외부 URL 참조 X
- Maki 사용을 이유로 Mapbox token / tile provider 추가 X (지도 엔진은 `vworld-map-web`의 MapLibre GL JS, ADR-046)
- 새 아이콘 필요 시 `sync-maki-icons.mjs` 목록 갱신

## 4. 로그인 / 가입 화면 (DESIGN.md 톤)

### 4.1 레이아웃

**데스크탑 (≥ 768px)**:
- 좌측 50% — 축제 / 추천 plan / 마커 미리보기 카드 grid
- 우측 50% — 로그인 폼

**모바일 (< 768px)**:
- 상단 — 로그인 폼 (full-width)
- 하단 — 축제 / 추천 plan (스크롤)

### 4.2 컴포넌트

```tsx
// apps/web/app/(auth)/login/page.tsx
export default async function LoginPage() {
  const featuredFestivals = await apiServer.public.festivalsMonthly();
  return (
    <div className="grid min-h-screen md:grid-cols-2">
      <FeaturedFestivalsPanel festivals={featuredFestivals} />
      <LoginFormPanel />
    </div>
  );
}
```

### 4.3 디자인 토큰 적용

- 배경: `canvas` (`#ffffff`)
- CTA: `primary` Rausch (`#FF385C`) + 흰 텍스트
- 입력: `surface-soft` (`#f7f7f7`) + `hairline` border
- 텍스트: `ink` (`#222`), 보조: `muted` (`#6a6a6a`)
- radius: `rounded.sm` 8px (버튼), `rounded.md` 14px (카드), `rounded.full` (검색 orb)
- shadow: 단일 tier (`shadows.card`)

### 4.4 소셜 로그인 버튼

자세히는 `docs/integrations/social-login.md` §8.1. 현재 Web UI에 노출하는 OAuth
버튼은 Google 하나다. Naver/Kakao 버튼은 T-122 provider 구현 전까지 만들지 않는다.

```tsx
<div className="space-y-3 mt-6">
  <SocialButton provider="google" />
</div>
```

- 너비: full
- min-height 48px
- radius 8px
- top-level navigation (`fetch` 금지)

### 4.5 Admin 로그인 (`/admin/login`)

- 소셜 버튼 X (이메일 + 비밀번호만)
- Admin 전용 톤 — 약간 더 sobér
- bootstrap admin은 운영 런북의 임시 credential로만 최초 진입한다. 공개 문서에는
  이메일/비밀번호 조합을 고정하지 않는다.

## 5. 지도 화면 (Trip Workspace)

자세히는 `docs/spec/v8/03-frontend.md` §2 + `docs/architecture/frontend.md` §2.

레이아웃 변수 (CSS vars):

```css
:root {
  --tm-nav-h: 56px;
  --tm-trip-tab-h: 44px;
  --tm-panel-w-left: 340px;
  --tm-panel-w-right: 320px;
  --tm-panel-min-w: 280px;
  --tm-panel-max-w: 460px;
  --tm-marker-surface: #ffffff;
  --tm-marker-icon-on-color: #ffffff;
  --tm-marker-border: rgba(0, 0, 0, 0.1);
}
```

브레이크포인트:

- mobile-narrow ≤374px
- mobile 375~767px
- tablet 768~1023px
- desktop 1024~1279px
- wide ≥1280px

Tailwind: `md=768px` (desktop nav), `lg=1024px` (both panels), `xl=1280px` (sticky widgets).

## 6. TREK 패턴 채택 / 비채택

### 6.1 채택

- 고정 top nav + breadcrumb
- 보조 pill tab bar
- 지도 = primary surface
- 좌측 day-plan + 우측 place-pool
- 패널 collapse + desktop resize
- 모바일 pill → bottom sheet
- 마커 + 리스트 통합 selection state
- compact rows
- spotlight + grid dashboard
- `data-testid`로 e2e 안정성

### 6.2 비채택

- TREK assets / brand
- AGPL 코드
- Leaflet / Mapbox abstractions
- 3D map / terrain
- Vacay / Atlas / Journey / Addons / MCP (TREK 영역)

## 7. AI agent 체크리스트

새 UI 추가:

- [ ] `apps/web/components/ui/*` shadcn/ui 위에 Airbnb 톤 wrapper
- [ ] CSS var / Tailwind 디자인 토큰만 사용 (`packages/design-tokens`)
- [ ] 마커는 16색 + maki — 다른 색 X
- [ ] Maki 아이콘은 self-host (`public/maki/`)
- [ ] 소셜 버튼은 top-level navigation
- [ ] Admin 화면에 소셜 버튼 X
- [ ] data-testid로 e2e 식별자 부여
- [ ] DESIGN.md / palette HTML 톤 준수
