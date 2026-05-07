# 로그인 후 TREK 차용 UI와 Kakao 지도 구현 계획

## 한 줄 결정

TripMate의 로그인 후 기본 UI는 TREK의 `My Trips` 대시보드와 `Trip Planner` 작업대 형태를 적극 차용한다. 구현은 Next.js App Router + TypeScript + Tailwind CSS + `react-kakao-maps-sdk`로 작성하며, 지도 표면은 Leaflet/Mapbox가 아니라 Kakao 지도를 사용한다.

이 문서는 Codex가 바로 구현 작업을 시작할 수 있도록 파일 경계, 타입, API 계약, UI 동작, 오류 상태, 테스트 기준을 최대한 명확하게 고정한다.

## 반드시 지킬 조건

- TREK의 코드, 로고, 이미지, 번역문, asset을 복사하지 않는다.
- TREK의 레이아웃 구조, 정보 밀도, 작업 흐름, panel 배치만 참고한다.
- 최종 룩앤필은 루트 `DESIGN.md`를 우선한다. TREK는 화면 구조 참고이고, 색상/타입/버튼/카드/그림자의 기준은 `DESIGN.md`다.
- 예외적으로 지도 marker 색상은 `airbnb-marker-palette.html`의 16색 팔레트가 `DESIGN.md`보다 우선한다. marker shape, shadow, radius는 `DESIGN.md`의 부드러운 Airbnb 계열 룩을 유지한다.
- 지도 marker glyph는 Mapbox Maki icon을 내려받아 self-host한 SVG asset을 사용한다. CDN hotlink, 임의 SVG 직접 제작, Mapbox GL 의존성 추가는 하지 않는다.
- TripMate는 대한민국 국내 여행 앱이다. 해외 여행/비회원 모드/외부 provider 원문 장기 저장을 기본 범위로 넣지 않는다.
- 일반 사용자 로그인 식별자는 이메일이고, 인증은 httpOnly cookie 기반 서버 세션을 사용한다.
- Kakao JavaScript app key는 브라우저 노출 가능 키로 `NEXT_PUBLIC_KAKAO_MAP_APP_KEY`를 쓴다.
- Kakao REST API key, Telegram bot token, Gemini API key, 비밀번호 원문은 브라우저 bundle, 일반 DB, 로그에 저장하지 않는다.
- 장소 추가는 Kakao 검색 결과 선택과 지도 클릭 입력을 모두 지원한다.
- Kakao가 기본 장소 후보 provider다. Naver/Google/일반 검색 확장은 정책 검토 후 별도 작업으로 둔다.
- “반경 nkm” 리포트는 행정구역 기반 근사일 수 있으며 UI와 문서에 근사라고 표시한다.
- Telegram 대상은 사용자 소유 리소스로 저장하고 여행별 최대 3개만 참조한다.
- Gemini Deep Research는 사용자 개인 API key 입력 구조이고 버튼 기반 수동 실행을 기본으로 한다.
- `youtube_place_mcp`, `address_code_lookup_mcp`는 설계/구현/스캐폴딩하지 않는다.

## 분석 기준

- TREK GitHub 저장소: `https://github.com/mauriceboe/TREK`
- TREK 데모 페이지: `https://demo-nomad.pakulat.org/`
- 분석한 TREK commit: `de3152e`
- TripMate 시각 기준: `DESIGN.md`
- TripMate marker 색상 기준: `airbnb-marker-palette.html`
- TREK 화면 근거:
  - `docs/screenshots/dashboard.png`
  - `docs/screenshots/trip-planner.png`
  - `docs/screenshots/trip-iceland.png`
- 분석한 TREK 핵심 구조:
  - `client/src/pages/DashboardPage.tsx`
  - `client/src/pages/TripPlannerPage.tsx`
  - `client/src/components/Layout/Navbar.tsx`
  - `client/src/components/Layout/BottomNav.tsx`
  - `client/src/components/Planner/DayPlanSidebar.tsx`
  - `client/src/components/Planner/PlacesSidebar.tsx`
  - `client/src/components/Planner/PlaceInspector.tsx`
  - `client/src/components/Map/MapViewAuto.tsx`
  - `client/src/components/Map/MapView.tsx`
  - `client/src/components/Map/MapViewGL.tsx`
- Kakao React 지도 라이브러리:
  - npm package: `react-kakao-maps-sdk`
  - 2026-05-07 확인 버전: `1.2.1`
  - docs: `https://react-kakao-maps-sdk.jaeseokim.dev/docs/intro/`
- Kakao 지도 TypeScript type package:
  - npm package: `kakao.maps.d.ts`
  - 2026-05-07 확인 버전: `0.1.40`
- 지도 marker icon set:
  - npm package: `@mapbox/maki`
  - 2026-05-07 확인 버전: `8.2.0`
  - source repo: `https://github.com/mapbox/maki`
  - license: `CC0-1.0`
  - 형식: 15px x 15px SVG source icon

## 기존 문서와의 관계

구현 전에 아래 문서를 읽고 충돌이 있으면 이 문서보다 상위 기준을 우선한다.

- 공통 작업 규칙: `AGENTS.md`, `docs/runbooks/agent-working-rules.md`
- 룩앤필 기준: `DESIGN.md`
- 전체 계획: `docs/execplan/korea-tripmate-implementation-plan.md`
- 아키텍처: `docs/architecture.md`
- 사용자/여행 스키마: `docs/architecture/user-trip-schema.md`
- 장소 스키마: `docs/architecture/place-schema.md`
- 지도 feature 스키마: `docs/architecture/map-feature-schema.md`
- 지도 마커/화면 디자인: `docs/architecture/map-marker-design.md`
- 데이터 출처/저장 정책: `docs/data-sources.md`
- 여행 API: `docs/api/trips.md`
- 공개 데이터 API: `docs/api/public.md`
- 행정경계 API: `docs/api/regions.md`
- Telegram: `docs/integrations/telegram.md`
- Gemini: `docs/integrations/gemini.md`
- 코딩 스타일: `skills/coding-style.ko.md`
- 테스트/QA: `skills/testing-and-qa.ko.md`

## 제품 범위

### 포함

- 로그인 성공 후 기본 진입 화면.
- 사용자 여행 목록 대시보드.
- 여행 상세 계획 작업대.
- Kakao 지도 기반 장소 marker, layer, 지도 클릭 custom place 추가.
- Kakao 장소 검색 후보 선택.
- 날짜별 일정 panel과 지도 marker 동기화.
- 공공/지역 데이터 layer 진입점.
- 행정구역 기반 지역 리포트 진입점.
- Telegram 알림 설정 panel 진입점.
- Gemini Deep Research panel 진입점.
- 모바일/PWA 작업 화면.

### 제외

- 관리자 UI.
- 로그인/회원가입 화면 재설계.
- TREK의 Vacay, Atlas, Journey, MCP 기능 복제.
- Leaflet/Mapbox GL/3D building/terrain 구현.
- 실제 길찾기 최적화 provider 연동.
- Naver/Google 장소 검색 구현.
- MCP 도구 구현.

## 최종 UI 목표

### 로그인 후 기본 진입

인증된 사용자가 `/login`에서 로그인하면 `/trips`로 이동한다. `/`도 인증 상태면 `/trips`로 redirect한다.

Desktop:

```text
┌──────────────────────────────────────────────────────────────────────────┐
│ Top nav: TripMate | 내 여행 | (후속 전역 메뉴)        알림  사용자 메뉴 │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│ ┌──────────────────────────────────────────────────────────────────────┐ │
│ │ 내 여행 | active/archived count              view/settings 새 여행   │ │
│ └──────────────────────────────────────────────────────────────────────┘ │
│                                                                          │
│ ┌──────────────────────────────────────────────────┐ ┌───────────────┐ │
│ │ 가장 가까운 여행 spotlight card                  │ │ 오늘 요약      │ │
│ │ 이미지/색상, 여행명, 기간, 남은 날, 장소 수       │ │ 축제/날씨      │ │
│ └──────────────────────────────────────────────────┘ │ Telegram      │ │
│ ┌───────────────┐ ┌───────────────┐                  │ Gemini        │ │
│ │ 작은 여행 card │ │ 작은 여행 card │                  └───────────────┘ │
│ └───────────────┘ └───────────────┘                                      │
└──────────────────────────────────────────────────────────────────────────┘
```

Mobile:

```text
┌─────────────────────────────┐
│ Top header: 내 여행  +       │
├─────────────────────────────┤
│ Spotlight trip card          │
│ Trip card list               │
│ Utility summary strip        │
├─────────────────────────────┤
│ Bottom nav / profile         │
└─────────────────────────────┘
```

### 여행 상세 작업대

TREK의 `Trip Planner` 화면처럼 full-screen 작업대를 만든다.

Desktop:

```text
┌──────────────────────────────────────────────────────────────────────────┐
│ Back TripMate / 여행명                              공유 알림 사용자 메뉴 │
├──────────────────────────────────────────────────────────────────────────┤
│            계획 | 지역 리포트 | 알림 | 리서치 | 파일/메모                │
├──────────────────────────────────────────────────────────────────────────┤
│ ┌───────────────┐                                      ┌───────────────┐ │
│ │ DayPlanPanel  │                                      │ PlacePoolPanel│ │
│ │ Day 1         │                                      │ + 장소 추가   │ │
│ │ - 장소 A      │             Kakao Map                │ 검색          │ │
│ │ - 장소 B      │        markers / layers              │ 전체/미배치   │ │
│ │ Day 2         │                                      │ 장소 rows     │ │
│ └───────────────┘                                      └───────────────┘ │
│                         PlaceInspector / DraftPopover                    │
└──────────────────────────────────────────────────────────────────────────┘
```

Mobile:

```text
┌─────────────────────────────┐
│ Back / 여행명                │
├─────────────────────────────┤
│ 계획 | 리포트 | 알림 | 리서치 │
├─────────────────────────────┤
│ Kakao Map full surface       │
│ [일정]              [장소]   │
│ marker click -> bottom sheet │
└─────────────────────────────┘
```

## TREK에서 차용할 구체 요소

### 차용한다

- 상단 fixed nav + 여행명 breadcrumb.
- 2차 pill tab bar.
- 중앙 map을 가장 큰 primary surface로 두는 방식.
- 좌측 날짜별 일정 panel, 우측 장소 pool panel.
- panel collapse button과 desktop resize handle.
- 모바일에서 지도 위 pill button으로 panel sheet를 여는 방식.
- marker와 list selection을 같은 state로 묶는 방식.
- 장소 row의 compact density.
- 여행 목록의 spotlight card + compact card list/grid.
- `data-testid`와 접근 가능한 button label을 달아 E2E가 안정적으로 잡을 수 있는 구조.

### 차용하지 않는다

- TREK 로고/브랜드/asset.
- TREK의 AGPL 코드 구현체.
- TREK의 Leaflet/Mapbox provider abstraction.
- TREK의 3D map/terrain.
- TREK의 Vacay/Atlas/Journey/Addons/MCP surface.
- TREK의 Google Places/OpenStreetMap/Naver import 구현.

## 프론트엔드 의존성

현재 `apps/web/package.json`은 Next.js, React, Tailwind 중심이다. 구현 시 아래 의존성을 추가한다.

권장 명령:

```bash
npm install --workspace apps/web react-kakao-maps-sdk lucide-react
npm install --workspace apps/web --save-dev kakao.maps.d.ts @mapbox/maki
```

권장 version:

```json
{
  "dependencies": {
    "react-kakao-maps-sdk": "^1.2.1",
    "lucide-react": "확인된 최신 호환 버전"
  },
  "devDependencies": {
    "kakao.maps.d.ts": "^0.1.40",
    "@mapbox/maki": "^8.2.0"
  }
}
```

`lucide-react`는 버튼 icon, tab icon, panel action icon에 사용한다. 지도 marker glyph는 `@mapbox/maki`에서 필요한 SVG만 내려받아 `apps/web/public/map-icons/maki/`에 복사한 asset을 사용한다.

Maki 사용 규칙:

- `@mapbox/maki`는 build/dev dependency로만 사용하고 runtime에서 외부 CDN을 호출하지 않는다.
- marker icon URL은 `/map-icons/maki/{iconName}.svg` 형태로 참조한다.
- Maki를 쓰기 위해 Mapbox GL, Mapbox token, Mapbox tile, Mapbox CSS를 추가하지 않는다.
- 필요한 SVG만 복사한다. 전체 icon set을 public에 무조건 노출하지 않는다.
- package를 갱신하면 `@mapbox/maki` 버전, license, 복사 대상 icon 목록을 이 문서 또는 관련 marker 디자인 문서에 갱신한다.

## 환경변수

프론트엔드:

| 이름 | 위치 | 필수 | 설명 |
| --- | --- | --- | --- |
| `NEXT_PUBLIC_KAKAO_MAP_APP_KEY` | `apps/web/.env.local` | Y | Kakao JavaScript 지도 app key. 브라우저 노출 가능 키 |
| `NEXT_PUBLIC_API_BASE_URL` 또는 기존 API base 설정 | `apps/web/.env.local` | Y | FastAPI base URL. 기존 `apps/web/app/shared/api-base.ts` 기준을 따른다 |

백엔드:

| 이름 | 위치 | 필수 | 설명 |
| --- | --- | --- | --- |
| `KAKAO_REST_API_KEY` | 서버 env/secret | 검색 구현 시 Y | Kakao Local REST API key. 브라우저로 보내지 않음 |
| `KAKAO_LOCAL_TIMEOUT_SECONDS` | 서버 env | N | 기본 3초 권장 |
| `KAKAO_LOCAL_CACHE_TTL_SECONDS` | 서버 env | N | 기본 86400초 권장. 최종 TTL은 `docs/data-sources.md`에 기록 |

secret 처리:

- `KAKAO_REST_API_KEY`는 `.env.example`에는 이름만 넣고 실제 값은 넣지 않는다.
- 로그에는 key, query 원문 전체, provider raw payload를 남기지 않는다. query는 필요 시 길이 제한 또는 hash만 남긴다.
- Kakao Local raw response는 TTL 캐시에만 저장하고 장기 보존 테이블에 복사하지 않는다.

## TypeScript 설정

`apps/web/tsconfig.json`에 `kakao.maps.d.ts` type을 추가한다. 기존 `types`가 있으면 병합하고, 없으면 추가한다.

```json
{
  "compilerOptions": {
    "types": ["kakao.maps.d.ts"]
  }
}
```

다른 type이 이미 있으면 지우지 말고 보존한다.

## 권장 파일 구조

구현 시작 시 실제 repository 상태를 먼저 확인한다. 아래 구조는 권장안이며, 기존 패턴이 있으면 기존 패턴을 우선한다.

```text
apps/web/app/trips/page.tsx
apps/web/app/trips/TripsDashboard.tsx
apps/web/app/trips/TripCard.tsx
apps/web/app/trips/TripFormDialog.tsx
apps/web/app/trips/[tripId]/page.tsx
apps/web/app/trips/[tripId]/TripWorkspace.tsx
apps/web/app/trips/[tripId]/TripWorkspace.types.ts
apps/web/app/trips/[tripId]/TripWorkspace.api.ts
apps/web/app/trips/[tripId]/TripWorkspace.responsive.ts
apps/web/app/trips/[tripId]/useResponsiveMode.ts
apps/web/app/trips/[tripId]/TripTopNav.tsx
apps/web/app/trips/[tripId]/TripTabs.tsx
apps/web/app/trips/[tripId]/TripKakaoMap.tsx
apps/web/app/trips/[tripId]/TripMapMarker.tsx
apps/web/app/trips/[tripId]/markerIconRegistry.ts
apps/web/app/trips/[tripId]/DayPlanPanel.tsx
apps/web/app/trips/[tripId]/PlacePoolPanel.tsx
apps/web/app/trips/[tripId]/PlaceInspector.tsx
apps/web/app/trips/[tripId]/DraftPlaceSheet.tsx
apps/web/app/trips/[tripId]/ResponsiveSheet.tsx
apps/web/app/trips/[tripId]/RegionalReportPanel.tsx
apps/web/app/trips/[tripId]/TelegramPanel.tsx
apps/web/app/trips/[tripId]/GeminiResearchPanel.tsx
apps/web/app/trips/[tripId]/workspaceParsers.ts
apps/web/app/trips/[tripId]/workspaceViewModels.ts
apps/web/scripts/sync-maki-icons.mjs
apps/web/public/map-icons/maki/marker.svg
apps/web/public/map-icons/maki/marker-stroked.svg
apps/web/public/map-icons/maki/star.svg
apps/web/public/map-icons/maki/attraction.svg
apps/web/public/map-icons/maki/beach.svg
apps/web/public/map-icons/maki/fuel.svg
apps/web/public/map-icons/maki/highway-rest-area.svg
apps/web/public/map-icons/maki/restaurant.svg
apps/web/public/map-icons/maki/cafe.svg
apps/web/public/map-icons/maki/lodging.svg
apps/web/public/map-icons/maki/town-hall.svg
apps/web/public/map-icons/maki/information.svg
```

백엔드 권장 구조:

```text
apps/api/app/api/routes/trips.py
apps/api/app/api/routes/places.py
apps/api/app/schemas/trip.py
apps/api/app/schemas/place_search.py
apps/api/app/services/trip_workspace.py
apps/api/app/services/trip_plan.py
apps/api/app/services/place_search.py
apps/api/app/services/kakao_local.py
apps/api/app/models/trip.py
apps/api/app/models/place.py
apps/api/tests/test_trip_workspace_api.py
apps/api/tests/test_place_search_api.py
apps/api/tests/test_kakao_local_adapter.py
```

새 route 파일을 추가하면 `apps/api/app/main.py`의 router 등록 패턴을 확인하고 기존 방식에 맞춘다.

## UI design token

기존 TripMate 디자인 기준과 TREK 작업대 느낌을 함께 맞춘다. 최종 시각 기준은 루트 `DESIGN.md`다. 즉, TREK에서는 정보 구조와 반응형 panel/sheet 패턴을 차용하고, 화면의 색상/타입/카드/버튼/그림자 스타일은 Airbnb 계열의 흰 캔버스, near-black ink, Rausch 포인트 컬러, 부드러운 radius, 낮은 elevation을 유지한다.

단, 지도 marker 색상은 예외다. marker 색상은 `airbnb-marker-palette.html`의 16색 팔레트가 `DESIGN.md`보다 우선한다. `DESIGN.md`는 marker의 표면감, radius, shadow, typography, panel 주변 룩앤필에 적용하고, marker category/source 구분 색은 16색 팔레트 안에서만 고른다.

룩앤필 우선순위:

1. `DESIGN.md`: 색상, type scale, radius, shadow, card density, CTA 스타일.
2. `airbnb-marker-palette.html`: 지도 marker category/source 색상. marker 색상에 한해 `DESIGN.md`보다 우선.
3. TripMate 기존 코드/문서: 국내 여행 도메인, 지도/일정 작업 밀도, 인증 기반 shell.
4. TREK: dashboard/planner 정보 배치, 좌우 panel, mobile sheet, tabbed workspace.

`DESIGN.md`에서 반드시 유지할 것:

- 기본 page canvas는 pure white `#ffffff`다.
- `#ff385c` Rausch는 primary CTA, 검색 orb, heart/save selected state, 선택 marker처럼 의미 있는 순간에만 쓴다.
- mainline 화면에서 Luxe purple, Plus magenta, 강한 blue/orange 계열을 brand color처럼 쓰지 않는다.
- type은 `Airbnb Cereal VF`가 있으면 우선하고, 없으면 `Circular`, `Inter`, system stack 순서로 둔다.
- display heading은 과하게 크거나 무겁게 만들지 않는다. 작업 화면 heading은 `20px-28px`, `500-700` 범위가 기준이다.
- button radius는 8px, card radius는 14px 안팎, search/filter pill은 full radius를 쓴다.
- shadow는 한 tier만 쓴다. 겹겹이 떠 있는 SaaS dashboard처럼 만들지 않는다.
- 여행 card는 photo-first 또는 지도/장소 정보를 보조로 둔 marketplace card 느낌을 유지한다.
- panel은 TREK처럼 지도 위에 떠도, 시각적으로는 white surface + hairline + 낮은 shadow다. dark glass, heavy blur, neon accent는 쓰지 않는다.

권장 CSS 변수:

```css
:root {
  --tm-nav-h: 56px;
  --tm-trip-tab-h: 44px;
  --tm-panel-w-left: 340px;
  --tm-panel-w-right: 320px;
  --tm-panel-min-w: 280px;
  --tm-panel-max-w: 460px;
  --tm-bg-page: #ffffff;
  --tm-bg-surface: #ffffff;
  --tm-bg-panel: rgba(255, 255, 255, 0.94);
  --tm-bg-soft: #f7f7f7;
  --tm-bg-strong: #f2f2f2;
  --tm-text-primary: #222222;
  --tm-text-body: #3f3f3f;
  --tm-text-secondary: #4b5563;
  --tm-text-muted: #6a6a6a;
  --tm-text-muted-soft: #929292;
  --tm-border: #dddddd;
  --tm-border-soft: #ebebeb;
  --tm-border-strong: #c1c1c1;
  --tm-accent: #ff385c;
  --tm-accent-active: #e00b41;
  --tm-accent-disabled: #ffd1da;
  --tm-accent-text: #ffffff;
  --tm-danger: #c13515;
  --tm-scrim: rgba(0, 0, 0, 0.5);
  --tm-shadow-card: rgba(0, 0, 0, 0.02) 0 0 0 1px,
    rgba(0, 0, 0, 0.04) 0 2px 6px 0,
    rgba(0, 0, 0, 0.1) 0 4px 8px 0;
  --tm-marker-rausch: #ff385c;
  --tm-marker-coral: #ff7e5f;
  --tm-marker-terracotta: #d2603a;
  --tm-marker-amber: #e89b3c;
  --tm-marker-saffron: #d9a441;
  --tm-marker-olive: #8b9d52;
  --tm-marker-sage: #7ba889;
  --tm-marker-forest: #2a9d7f;
  --tm-marker-teal: #3a8b96;
  --tm-marker-sky: #428bff;
  --tm-marker-indigo: #3d5a80;
  --tm-marker-lavender: #a78ac0;
  --tm-marker-luxe: #460479;
  --tm-marker-plus: #92174d;
  --tm-marker-berry: #b83a65;
  --tm-marker-charcoal: #3f3f3f;
  --tm-marker-surface: #ffffff;
  --tm-marker-icon-on-color: #ffffff;
  --tm-marker-border: rgba(0, 0, 0, 0.08);
}
```

스타일 규칙:

- 앱 작업 화면은 marketing hero가 아니라 dense work surface다.
- dense work surface라도 canvas, panel, sheet는 `DESIGN.md`처럼 white-first로 유지한다.
- 카드 반복 항목 외 page section을 card처럼 감싸지 않는다.
- panel 안에 또 큰 card panel을 중첩하지 않는다.
- 버튼과 input radius는 8px 기준이다.
- 반복 여행 card는 기존 TripMate 디자인 문서와 맞춰 14px 안팎까지 허용한다.
- letter spacing은 0을 기본으로 한다. badge의 uppercase metadata만 예외적으로 아주 작은 positive tracking을 허용한다.
- viewport width 기반 font-size scaling을 쓰지 않는다.
- desktop 지도는 full-bleed로 보이게 하고 decorative frame/card 안에 넣지 않는다.
- 모바일에서 텍스트가 버튼 밖으로 넘치면 숨김/줄바꿈/짧은 label을 우선한다.
- marker 색상은 `airbnb-marker-palette.html`의 16색만 사용한다. 16색 밖의 임의 category 색을 추가하지 않는다.
- marker glyph는 Maki icon을 사용하고, marker shape/radius/shadow는 `DESIGN.md`의 부드러운 Airbnb 계열 룩을 유지한다.

## 반응형 웹 구조

이 장은 Codex가 별도 해석 없이 레이아웃을 구현할 수 있도록 breakpoints, shell geometry, panel 전환, overflow 규칙을 고정한다. TREK의 반응형 구조는 그대로 복사하지 않고, TripMate의 Next.js, Tailwind CSS, Kakao Map, 로그인 기반 여행 작업대 요구사항에 맞게 변환한다.

### TREK 반응형 분석 결과

TREK에서 적극 차용할 반응형 패턴:

- desktop 기준점은 `768px`부터 시작한다. TREK는 Tailwind `md` 이상에서 상단 desktop nav와 desktop toolbar를 보여주고, 모바일에서는 별도 greeting, spotlight, quick action, bottom navigation을 쓴다.
- dashboard는 전체 viewport를 fixed root로 잡고, 실제 목록 영역만 내부 scroll container로 둔다. 이 방식은 모바일 브라우저 주소창 변화와 pull-to-refresh 흔들림을 줄인다.
- dashboard mobile은 상단 greeting, spotlight, quick action 3열 grid, trip list가 세로로 흐른다. desktop은 toolbar, trip grid/list, 우측 sticky widgets를 동시에 보여준다.
- desktop widgets는 `lg` 이상에서만 sticky sidebar로 고정한다. 그보다 좁은 화면에서는 widgets를 bottom sheet 또는 접힌 panel로 보여준다.
- planner는 상단 nav 아래 44px tab bar를 고정하고, 그 아래 workspace를 full-screen map surface로 둔다.
- planner desktop은 중앙 map 위에 좌우 panel을 translucent overlay로 띄운다. panel은 collapse와 resize affordance를 갖는다.
- planner mobile은 좌우 panel을 숨기고 `일정`, `장소` 같은 pill button으로 full-height sheet를 연다.
- mobile inspector는 marker를 누른 뒤 하단 bottom sheet로 열린다. desktop inspector는 우측 panel 또는 map 위 overlay로 열린다.
- mobile sheet, inspector, bottom nav는 `env(safe-area-inset-bottom)`을 고려한다.
- desktop은 scroll bar를 자연스럽게 표시하고, mobile은 작은 내부 scroll bar를 숨기되 scroll 자체는 유지한다.

TripMate에서 그대로 쓰지 않을 TREK 패턴:

- Leaflet/Mapbox GL 관련 viewport 계산은 쓰지 않는다. 지도는 `react-kakao-maps-sdk`의 `Map`, `CustomOverlayMap`, `MarkerClusterer`, `Polyline` 기준으로 다시 작성한다.
- TREK의 file/journal/AI layout을 MVP 기본 화면에 모두 노출하지 않는다. TripMate의 우선순위는 일정, 장소, 지도, 지역 리포트, Telegram, Gemini 수동 실행이다.
- 모바일에서 route를 복잡한 drag-and-drop 중심으로 만들지 않는다. 1차 구현은 선택, 추가, 순서 변경 버튼을 우선한다.

### TripMate breakpoint 정책

TripMate는 TREK의 `md=768px` 전환을 따르되, 태블릿에서 좌우 panel이 지도를 과도하게 가리지 않도록 한 단계를 더 둔다.

| 이름 | CSS 범위 | 용도 |
| --- | --- | --- |
| `mobile-narrow` | `0px` 이상 `374px` 이하 | 작은 Android, 좁은 in-app browser. 텍스트 label 축약, 1열 목록 고정 |
| `mobile` | `375px` 이상 `767px` 이하 | 휴대폰 기본. bottom nav, sheet, full-screen map |
| `tablet` | `768px` 이상 `1023px` 이하 | desktop nav는 사용하되 panel은 한 번에 하나만 overlay |
| `desktop` | `1024px` 이상 `1279px` 이하 | 좌우 panel 사용 가능. 우측 widgets는 조건부 |
| `wide` | `1280px` 이상 | dashboard 우측 sticky widgets, planner 좌우 panel 기본 표시 |

Tailwind 사용 기준:

- `md:`는 `768px` 이상에서 desktop navigation과 tab density를 켠다.
- `lg:`는 `1024px` 이상에서 planner 좌우 panel을 동시에 열 수 있는 기준이다.
- `xl:`는 `1280px` 이상에서 dashboard sticky sidebar와 planner 넓은 panel 기본값을 쓴다.
- `max-md:` 또는 custom CSS media query로 `767px` 이하 mobile sheet, bottom nav, touch-friendly spacing을 처리한다.

TypeScript 기준:

```ts
export type ResponsiveMode =
  | "mobile_narrow"
  | "mobile"
  | "tablet"
  | "desktop"
  | "wide"

export type PanelPresentation = "sheet" | "overlay" | "docked"

export function getResponsiveMode(width: number): ResponsiveMode {
  if (width <= 374) return "mobile_narrow"
  if (width <= 767) return "mobile"
  if (width <= 1023) return "tablet"
  if (width <= 1279) return "desktop"
  return "wide"
}
```

`getResponsiveMode`는 `apps/web/app/trips/[tripId]/TripWorkspace.responsive.ts`에 둔다. React hook은 `useResponsiveMode.ts`에 두고, SSR hydration mismatch를 피하기 위해 초기 render에서는 CSS만으로 숨김/표시가 가능한 상태를 우선한다. `window.innerWidth`를 render 중 직접 읽지 말고 `useEffect` 또는 `useSyncExternalStore`로 구독한다.

### Viewport shell 변수

전역 CSS 또는 trip workspace 전용 CSS module에 아래 변수를 둔다. 이름은 기존 design token과 충돌하지 않게 `--tm-*` prefix를 유지한다.

```css
:root {
  --tm-safe-top: env(safe-area-inset-top, 0px);
  --tm-safe-bottom: env(safe-area-inset-bottom, 0px);
  --tm-nav-h: calc(56px + var(--tm-safe-top));
  --tm-trip-tab-h: 44px;
  --tm-bottom-nav-h: 0px;
  --tm-workspace-top: calc(var(--tm-nav-h) + var(--tm-trip-tab-h));
  --tm-mobile-sheet-radius: 18px;
  --tm-mobile-sheet-max-h: min(86dvh, 720px);
}

@supports not (height: 100dvh) {
  :root {
    --tm-mobile-sheet-max-h: min(86vh, 720px);
  }
}

@media (max-width: 767px) {
  :root {
    --tm-nav-h: calc(52px + var(--tm-safe-top));
    --tm-bottom-nav-h: calc(72px + var(--tm-safe-bottom));
    --tm-workspace-top: calc(var(--tm-nav-h) + var(--tm-trip-tab-h));
  }
}

@media (min-width: 1024px) {
  :root {
    --tm-panel-w-left: 340px;
    --tm-panel-w-right: 320px;
  }
}

@media (min-width: 1280px) {
  :root {
    --tm-panel-w-left: 368px;
    --tm-panel-w-right: 344px;
  }
}
```

높이 기준:

- app root는 `min-height: 100dvh`를 우선 사용하고, fallback으로 `min-height: 100vh`를 둔다.
- planner workspace는 `position: fixed; inset: 0; overflow: hidden;`을 기본으로 한다.
- dashboard는 page scroll이 가능해야 하므로 fixed root 안의 content container만 `overflow: auto`로 둔다.
- mobile sheet 내부는 독립 scroll을 허용한다. page 전체 body가 sheet 뒤에서 같이 scroll되면 안 된다.
- Kakao map container는 항상 명시적 width/height가 있어야 한다. `height: 100%`를 쓰려면 모든 부모의 높이가 fixed 또는 계산되어 있어야 한다.

### Dashboard 반응형 구조

`/trips` dashboard는 TREK dashboard처럼 여행 목록을 빠르게 스캔하는 작업 화면이다.

Mobile `0px-767px`:

- 상단에는 compact app header를 둔다. greeting, 현재 사용자 email 일부, 새 여행 icon button을 한 줄에 배치한다.
- spotlight trip은 첫 화면에 보이되, hero처럼 과하게 크게 만들지 않는다. 권장 높이는 `160px-220px`다.
- quick action은 3열 grid다. 항목은 `새 여행`, `최근 여행`, `알림` 정도로 제한한다.
- trip card list는 1열이다. card 안 텍스트가 길면 title 2줄, description 2줄까지 허용하고 이후 말줄임한다.
- 여행이 많을 때 목록 영역만 자연스럽게 scroll된다. bottom nav와 겹치지 않게 마지막 padding은 `calc(var(--tm-bottom-nav-h) + 24px)` 이상 둔다.
- widgets, Telegram summary, Gemini key status는 기본 노출하지 않고 `더보기` sheet 또는 settings sheet에 넣는다.
- 새 여행 버튼은 상단 icon button과 empty state primary button 두 위치에만 둔다. floating action button은 MVP에서 쓰지 않는다.

Tablet `768px-1023px`:

- desktop nav를 사용한다.
- trip grid는 2열을 기본으로 한다.
- toolbar는 한 줄에 들어가지 않으면 search/filter를 다음 줄로 내려도 된다.
- widgets는 우측 sticky sidebar로 고정하지 않는다. trip grid 위 compact summary row 또는 접힘 section으로 둔다.
- page horizontal overflow가 생기면 grid column 폭을 줄이지 말고 1열로 내려간다.

Desktop `1024px-1279px`:

- trip grid는 2열 또는 3열이다. card 최소 폭은 `280px` 이상을 유지한다.
- list/grid toggle, search, filter, sort를 toolbar에 둔다.
- 우측 widgets는 화면 폭이 `1180px` 이상일 때만 표시한다. 그보다 좁으면 grid를 우선한다.

Wide `1280px+`:

- content max width는 `1300px-1440px` 사이로 둔다.
- 우측 sticky widgets는 폭 `280px-320px`, `top: calc(var(--tm-nav-h) + 24px)` 기준이다.
- trip grid는 3열을 기본으로 하고, 여행 title이 긴 한국어 문장을 포함해도 card 높이가 급격히 튀지 않게 line clamp를 둔다.

Dashboard CSS 골격:

```css
.trips-dashboard-shell {
  min-height: 100dvh;
  background: var(--tm-bg-page);
}

.trips-dashboard-scroll {
  min-height: 100dvh;
  overflow: auto;
  overscroll-behavior: contain;
  padding-top: var(--tm-nav-h);
  padding-bottom: calc(var(--tm-bottom-nav-h) + 24px);
}

.trips-dashboard-inner {
  width: min(100%, 1360px);
  margin: 0 auto;
  padding: 20px;
}

@media (max-width: 767px) {
  .trips-dashboard-inner {
    padding: 14px 14px calc(var(--tm-bottom-nav-h) + 24px);
  }
}
```

### Trip workspace 반응형 구조

`/trips/{tripId}`는 지도 중심 작업대다. desktop은 TREK planner처럼 좌우 panel과 중앙 지도를 동시에 보여주고, mobile은 지도 위에 필요한 panel을 sheet로 호출한다.

공통 shell:

```css
.trip-workspace {
  position: fixed;
  inset: 0;
  overflow: hidden;
  background: var(--tm-bg-page);
}

.trip-workspace-tabs {
  position: fixed;
  top: var(--tm-nav-h);
  left: 0;
  right: 0;
  height: var(--tm-trip-tab-h);
  z-index: 30;
}

.trip-workspace-body {
  position: fixed;
  top: var(--tm-workspace-top);
  left: 0;
  right: 0;
  bottom: 0;
  overflow: hidden;
}

.trip-map-surface {
  position: absolute;
  inset: 0;
}
```

Mobile `0px-767px`:

- 지도는 `trip-workspace-body` 전체를 채운다.
- 좌측 일정 panel과 우측 장소 panel은 DOM에는 있어도 visible 상태에서는 sheet로만 보여준다.
- 지도 위 상단에는 `일정`, `장소` pill button 2개를 둔다. 위치는 tab bar 아래 `12px`, 좌우 `12px` 기준이다.
- pill button container는 `pointer-events: none`, 실제 button만 `pointer-events: auto`로 둔다. 이렇게 해야 map drag가 막히지 않는다.
- `일정` sheet는 왼쪽 panel 내용을 그대로 재사용하되 header에 닫기 버튼과 선택 날짜 요약을 둔다.
- `장소` sheet는 검색 input이 열릴 때 mobile keyboard에 가려지지 않도록 `max-height`와 내부 scroll을 분리한다.
- marker click inspector는 하단 sheet로 연다. sheet 높이는 내용에 따라 `min(70dvh, 560px)`까지 자라고, 상세 편집은 별도 full sheet로 전환 가능하다.
- bottom nav가 있다면 지도 control, inspector, sheet footer는 `var(--tm-bottom-nav-h)` 위에 위치한다.
- Kakao map zoom control을 기본 위치에 두면 sheet button과 겹칠 수 있다. MVP에서는 custom control을 만들지 말고, 필요한 경우 map option으로 control을 끄고 TripMate zoom icon button을 오른쪽 아래에 둔다.

Tablet `768px-1023px`:

- desktop nav와 tab bar를 사용한다.
- 지도는 full-screen을 유지한다.
- 좌우 panel을 동시에 dock하지 않는다. `일정` 또는 `장소` 중 하나만 overlay panel로 보여준다.
- overlay panel 폭은 `min(380px, calc(100vw - 48px))`다.
- overlay panel은 왼쪽에 붙이는 것을 기본으로 하고, 장소 검색 panel은 오른쪽 붙임을 허용한다.
- inspector는 오른쪽 overlay로 열되, 이미 장소 panel이 열려 있으면 panel 내부 detail view로 전환한다.
- tablet landscape에서 `1024px` 이상이 되면 desktop 규칙을 따른다.

Desktop `1024px-1279px`:

- 좌측 일정 panel은 기본 open, 우측 장소 panel은 기본 open이다.
- panel 폭은 좌측 `320px-360px`, 우측 `300px-340px` 범위에서 시작한다.
- 지도는 panel 뒤에도 계속 렌더링된다. panel은 map을 밀어내지 않고 overlay한다.
- panel collapse button은 panel 바깥쪽 가장자리에 붙인다.
- panel resize handle은 desktop pointer 환경에서만 보인다. touch-only 환경에서는 resize를 숨긴다.
- 화면이 좁아져 map 가시 폭이 `420px` 미만이 되면 우측 panel을 자동 collapse한다.

Wide `1280px+`:

- 좌측 panel `368px`, 우측 panel `344px`를 기본값으로 한다.
- 오른쪽 panel 아래에 regional report compact section, Telegram/Gemini compact status를 접힘 section으로 둘 수 있다.
- selected place inspector는 우측 panel 내부 detail drawer로 우선 표시하고, map 위 floating card는 보조로만 쓴다.

Panel 전환 규칙:

| mode | day plan | place pool | inspector |
| --- | --- | --- | --- |
| `mobile_narrow` | bottom sheet | bottom sheet | bottom sheet |
| `mobile` | bottom sheet | bottom sheet | bottom sheet |
| `tablet` | left overlay | right overlay | right overlay 또는 panel detail |
| `desktop` | left docked overlay | right docked overlay | right panel detail |
| `wide` | left docked overlay | right docked overlay | right panel detail |

### Panel과 sheet 구현 규칙

`ResponsiveSheet.tsx`는 mobile sheet 공통 wrapper로 만들고, DayPlanPanel, PlacePoolPanel, PlaceInspector의 내용을 children으로 받는다.

필수 동작:

- open 상태에서 body scroll을 잠근다. 단, workspace 자체가 fixed라면 body style 변경 없이 overlay 내부 scroll만으로 충분한지 먼저 확인한다.
- backdrop click과 close button으로 닫힌다.
- `Escape`로 닫힌다.
- focus는 sheet 안에 유지한다. shadcn Dialog 또는 Radix Dialog를 이미 쓰는 repo라면 그 컴포넌트를 우선한다.
- sheet header 높이는 고정하고 content만 scroll한다.
- footer action button은 `position: sticky; bottom: 0;`으로 둔다.
- sheet max height는 mobile에서 `var(--tm-mobile-sheet-max-h)`, tablet overlay에서는 `calc(100dvh - var(--tm-workspace-top) - 24px)`다.
- keyboard가 올라올 때 input이 footer에 가려지지 않도록 content padding bottom을 footer 높이만큼 둔다.

금지:

- mobile에서 좌우 panel을 `display: none`한 뒤 같은 내용을 별도 component로 중복 구현하지 않는다. panel content component와 shell wrapper를 분리한다.
- `position: fixed` sheet 안에 또 fixed footer를 중첩해 iOS Safari에서 위치가 튀게 만들지 않는다.
- panel open/close에 따라 Kakao map container의 부모 크기가 계속 바뀌게 하지 않는다. overlay 방식으로 지도 크기는 안정적으로 유지한다.

### Kakao Map 반응형 규칙

Kakao map은 부모 크기 변화에 민감하므로 아래 규칙을 지킨다.

- `Map`의 직접 부모는 항상 `position: absolute; inset: 0; min-width: 0; min-height: 0;`을 가진다.
- tab 변경으로 map이 hidden 상태가 되면 `display: none` 대신 가능하면 opacity/visibility 또는 route-level 조건부 render를 사용한다. hidden container에서 Kakao map이 잘못된 크기로 초기화될 수 있다.
- sheet open/close는 map 크기를 바꾸지 않는다. panel collapse도 overlay width만 바꾸고 map container는 유지한다.
- desktop panel resize 후에는 Kakao map relayout이 필요할 수 있다. `map.relayout()`을 호출할 수 있도록 `onCreate`에서 map instance를 ref에 저장한다.
- mobile orientation change, tablet split view 변경, browser 주소창 높이 변화 후에도 marker가 잘 보이도록 resize observer 또는 viewport hook에서 relayout을 debounce한다.
- 선택 marker는 sheet보다 낮고 panel보다 낮은 z-index를 쓴다. marker overlay z-index 기준은 `10-20`, map controls `25`, tabs `30`, panels `40`, sheets/dialogs `50` 이상으로 둔다.
- marker label은 mobile에서 2-3글자 category 또는 order badge 중심으로 줄인다. 긴 장소명은 sheet/list에서 보여준다.

권장 map relayout hook:

```ts
function useKakaoMapRelayout(
  map: kakao.maps.Map | null,
  deps: readonly unknown[],
) {
  useEffect(() => {
    if (!map) return
    const id = window.setTimeout(() => {
      map.relayout()
    }, 80)
    return () => window.clearTimeout(id)
  }, [map, ...deps])
}
```

### Navigation과 tab 규칙

- 로그인 후 공통 app navigation은 desktop `md+`에서 상단 고정 nav를 쓴다.
- mobile에서는 상단 compact header와 하단 navigation을 함께 쓸 수 있다. 단, planner 화면에서는 지도 조작을 방해하지 않도록 하단 nav 높이를 모든 bottom sheet와 control 위치 계산에 반영한다.
- trip tab bar는 모든 viewport에서 높이 `44px`를 유지한다.
- tab label은 `계획`, `지역`, `알림`, `Gemini`, `파일`처럼 짧게 둔다. 긴 설명 문구를 tab 안에 넣지 않는다.
- mobile tab은 horizontal scroll을 허용하되 scroll bar는 숨긴다. active tab이 화면 밖이면 `scrollIntoView({ block: "nearest", inline: "center" })`로 보정한다.
- `파일` tab이 MVP 후속이면 disabled 상태로 두고, mobile에서 disabled tab이 첫 화면 폭을 밀어내지 않게 icon 또는 짧은 label을 쓴다.

### Overflow와 safe area 기준

전체 앱:

- `html`, `body`, Next root는 `min-height: 100%`를 가진다.
- x축 overflow는 전역으로 숨기는 대신 원인을 고친다. 최종 smoke에서 `document.documentElement.scrollWidth <= document.documentElement.clientWidth`를 확인한다.
- 지도 작업대는 body scroll이 아니라 내부 fixed 영역으로 처리한다.
- dashboard와 일반 tab content는 body 또는 route scroll을 허용하되 bottom nav padding을 둔다.

텍스트:

- button은 최소 `44px` 높이를 유지한다.
- icon-only button은 `44px x 44px`, desktop compact toolbar에서는 최소 `36px x 36px`까지 허용한다.
- mobile에서 한국어 title은 2줄 clamp, metadata는 1줄 clamp를 기본으로 한다.
- 긴 여행명, 긴 장소명, 긴 주소는 layout을 늘리지 말고 line clamp 또는 wrapping 처리한다.

터치:

- drag handle, collapse button, close button은 mobile에서 최소 터치 영역 `44px`다.
- resize handle은 mobile/tablet touch 환경에서 숨긴다.
- 지도 drag 영역 위에 투명 overlay를 두지 않는다.
- sheet backdrop은 map click과 분리되어야 한다. sheet가 닫힌 뒤 같은 tap이 지도 click으로 전파되지 않게 event propagation을 막는다.

### Responsive state와 URL 규칙

responsive mode 자체는 URL에 저장하지 않는다. URL은 사용자의 의미 있는 선택만 가진다.

URL에 허용:

- `tab`
- `day`
- `place`

React state에 허용:

```ts
export type ResponsiveUiState = {
  mode: ResponsiveMode
  panelPresentation: PanelPresentation
  openMobileSheet: "day_plan" | "places" | "inspector" | null
  tabletOverlay: "day_plan" | "places" | "inspector" | null
  leftPanelCollapsed: boolean
  rightPanelCollapsed: boolean
  leftPanelWidth: number
  rightPanelWidth: number
}
```

전환 동작:

- desktop에서 mobile로 줄어들면 열린 left/right panel 상태를 유지하되, 실제 presentation은 sheet로 바꾼다.
- mobile에서 desktop으로 넓어지면 `openMobileSheet`는 닫고, 이전 panel collapsed 상태를 복원한다.
- selected place가 있는 상태에서 mobile로 전환되면 inspector sheet를 자동으로 열지 않는다. 사용자가 marker/list를 다시 선택하거나 detail button을 눌렀을 때 연다.
- search input에 focus가 있을 때 viewport mode가 바뀌면 입력값과 후보 목록은 유지한다.

### 반응형 구현 순서

1. `/trips` dashboard에서 mobile 1열, tablet 2열, desktop 3열 grid를 먼저 만든다.
2. `TripWorkspace` fixed shell, `TripTabs`, full-screen `TripKakaoMap`을 만든다.
3. DayPlanPanel과 PlacePoolPanel의 content component를 viewport shell과 분리한다.
4. desktop docked overlay panel을 붙인다.
5. mobile `ResponsiveSheet`를 붙이고 `일정`, `장소`, inspector sheet를 연결한다.
6. tablet overlay presentation을 붙인다.
7. panel resize/collapse와 Kakao `relayout()`을 연결한다.
8. Playwright viewport matrix로 horizontal overflow, map nonblank, sheet open/close를 검증한다.

### 반응형 QA matrix

필수 viewport:

| 이름 | 크기 | 확인 |
| --- | --- | --- |
| small mobile | `360x740` | 좁은 Android. button text overflow 없음, sheet footer 보임 |
| iPhone style | `390x844` | bottom nav/safe area, map pill button, inspector sheet |
| large mobile | `430x932` | 긴 장소명, search keyboard 대응 |
| tablet portrait | `768x1024` | desktop nav, 단일 overlay panel, map 가시 폭 유지 |
| tablet landscape | `1024x768` | 좌우 panel 또는 자동 collapse, tab bar 고정 |
| laptop | `1280x800` | dashboard widgets, planner 좌우 panel, 지도 조작 |
| desktop | `1440x900` | wide panel width, sticky widgets, scroll 안정성 |

필수 자동 검사:

```ts
expect(await page.locator("[data-testid='trip-kakao-map']").isVisible()).toBe(true)
expect(
  await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth),
).toBe(true)
```

지도 app key가 없는 CI에서는 `trip-kakao-map` 대신 `map-unavailable` fallback이 보이면 통과한다. 단, fallback도 같은 viewport 높이와 panel/sheet layering 규칙을 지켜야 한다.

## 핵심 데이터 타입

프론트엔드는 API 응답을 `unknown`으로 받은 뒤 parser/type guard를 통과한 값만 React state에 넣는다. `return payload as T` 패턴은 쓰지 않는다.

### 공통 타입

```ts
export type ISODate = string
export type ISODateTime = string
export type UUID = string

export type Coordinate = {
  latitude: number
  longitude: number
}

export type DecimalCoordinateString = string
```

API 응답의 좌표가 문자열이면 parser에서 number로 변환한다. 변환 실패, 범위 오류는 UI에 표시 가능한 오류로 처리한다.

좌표 범위:

- `latitude`: -90 이상 90 이하.
- `longitude`: -180 이상 180 이하.
- 지도와 API 응답 표시는 EPSG:4326이다.

### 여행 목록

```ts
export type TripListItem = {
  id: UUID
  title: string
  description: string | null
  startDate: ISODate | null
  endDate: ISODate | null
  coverImageUrl: string | null
  isArchived: boolean
  dayCount: number
  placeCount: number
  memberCount: number
  telegramTargetCount: number
  upcomingStatus:
    | { kind: "ongoing"; currentDay: number; totalDays: number }
    | { kind: "starts_today" }
    | { kind: "future"; daysUntilStart: number }
    | { kind: "past"; daysSinceEnd: number }
    | { kind: "unscheduled" }
}
```

### 여행 작업대 응답

```ts
export type TripWorkspace = {
  trip: TripSummary
  days: TripDay[]
  places: TripPlace[]
  planItems: TripPlanItem[]
  categories: PlaceCategory[]
  layerStates: MapLayerState[]
  publicLayerMarkers: PublicLayerMarker[]
  telegramSummary: TelegramSummary
  geminiSummary: GeminiSummary
}

export type TripSummary = {
  id: UUID
  title: string
  description: string | null
  startDate: ISODate | null
  endDate: ISODate | null
  defaultCenter: Coordinate | null
  defaultZoomLevel: number | null
  ownerUserId: UUID
  canEdit: boolean
}

export type TripDay = {
  id: UUID
  tripId: UUID
  dayNumber: number
  date: ISODate
  title: string | null
  weatherSummary: {
    label: string
    temperatureC: number | null
    precipitationLabel: string | null
  } | null
}

export type TripPlace = {
  id: UUID
  tripId: UUID
  displayName: string
  address: string | null
  roadAddress: string | null
  coordinate: Coordinate | null
  categoryId: UUID | null
  categoryCode: string | null
  sourceType: "user_custom" | "kakao" | "public_data" | "system"
  providerRef: {
    provider: "kakao" | "public_data" | "tripmate"
    providerPlaceId: string | null
  } | null
  thumbnailUrl: string | null
  note: string | null
}

export type TripPlanItem = {
  id: UUID
  tripDayId: UUID
  resourceType:
    | "place"
    | "festival"
    | "beach"
    | "rest_area"
    | "fuel_station"
    | "route"
    | "custom"
  sortOrder: number
  tripPlaceId: UUID | null
  mapFeatureId: UUID | null
  festivalId: UUID | null
  titleSnapshot: string
  addressSnapshot: string | null
  coordinate: Coordinate | null
  startsAt: ISODateTime | null
  endsAt: ISODateTime | null
  note: string | null
}
```

### 지도 marker view model

```ts
export type MakiIconName =
  | "marker"
  | "marker-stroked"
  | "star"
  | "attraction"
  | "beach"
  | "fuel"
  | "highway-rest-area"
  | "restaurant"
  | "cafe"
  | "lodging"
  | "town-hall"
  | "information"

export type MarkerPaletteKey =
  | "rausch"
  | "coral"
  | "terracotta"
  | "amber"
  | "saffron"
  | "olive"
  | "sage"
  | "forest"
  | "teal"
  | "sky"
  | "indigo"
  | "lavender"
  | "luxe"
  | "plus"
  | "berry"
  | "charcoal"

export type MarkerPaletteToken = {
  key: MarkerPaletteKey
  name: string
  hex: string
  recommendedUse: string
}

export type MapMarkerKind =
  | "trip_place"
  | "plan_item"
  | "festival"
  | "beach"
  | "fuel"
  | "rest_area"
  | "report_area"
  | "draft"

export type MapMarkerViewModel = {
  id: string
  kind: MapMarkerKind
  title: string
  subtitle: string | null
  coordinate: Coordinate
  paletteKey: MarkerPaletteKey
  colorHex: string
  makiIconName: MakiIconName
  iconAlt: string
  thumbnailUrl: string | null
  dayNumber: number | null
  orderNumbers: number[]
  isSelected: boolean
  isDimmed: boolean
  isClickable: boolean
}
```

16색 marker palette:

```ts
export const MARKER_PALETTE: Record<MarkerPaletteKey, MarkerPaletteToken> = {
  rausch: { key: "rausch", name: "Rausch", hex: "#FF385C", recommendedUse: "시그니처 / 추천 / 선택" },
  coral: { key: "coral", name: "Coral", hex: "#FF7E5F", recommendedUse: "축제 / 이벤트" },
  terracotta: { key: "terracotta", name: "Terracotta", hex: "#D2603A", recommendedUse: "자연 / 투어" },
  amber: { key: "amber", name: "Amber", hex: "#E89B3C", recommendedUse: "음식 / 맛집" },
  saffron: { key: "saffron", name: "Saffron", hex: "#D9A441", recommendedUse: "문화 / 전시" },
  olive: { key: "olive", name: "Olive", hex: "#8B9D52", recommendedUse: "차분한 자연" },
  sage: { key: "sage", name: "Sage", hex: "#7BA889", recommendedUse: "소프트 그린" },
  forest: { key: "forest", name: "Forest", hex: "#2A9D7F", recommendedUse: "액티비티" },
  teal: { key: "teal", name: "Teal", hex: "#3A8B96", recommendedUse: "바다 / 수상" },
  sky: { key: "sky", name: "Sky", hex: "#428BFF", recommendedUse: "교통 / 안내" },
  indigo: { key: "indigo", name: "Indigo", hex: "#3D5A80", recommendedUse: "시티 / 행정" },
  lavender: { key: "lavender", name: "Lavender", hex: "#A78AC0", recommendedUse: "소프트 라벤더" },
  luxe: { key: "luxe", name: "Luxe", hex: "#460479", recommendedUse: "프리미엄 / 특별 레이어" },
  plus: { key: "plus", name: "Plus", hex: "#92174D", recommendedUse: "특별 추천 / Plus 맥락" },
  berry: { key: "berry", name: "Berry", hex: "#B83A65", recommendedUse: "베리 핑크 / 보조 강조" },
  charcoal: { key: "charcoal", name: "Charcoal", hex: "#3F3F3F", recommendedUse: "기본 카테고리" },
}
```

기본 marker icon mapping:

```ts
export const MARKER_MAKI_ICON_BY_KIND: Record<MapMarkerKind, MakiIconName> = {
  trip_place: "marker",
  plan_item: "star",
  festival: "attraction",
  beach: "beach",
  fuel: "fuel",
  rest_area: "highway-rest-area",
  report_area: "town-hall",
  draft: "marker-stroked",
}
```

기본 marker color mapping:

```ts
export const MARKER_PALETTE_BY_KIND: Record<MapMarkerKind, MarkerPaletteKey> = {
  trip_place: "charcoal",
  plan_item: "rausch",
  festival: "coral",
  beach: "teal",
  fuel: "amber",
  rest_area: "sky",
  report_area: "indigo",
  draft: "charcoal",
}
```

Kakao 장소 category가 더 구체적이면 `trip_place` 내부에서만 아래 보정 mapping을 적용한다. 없는 category는 `marker`로 fallback한다.

| Kakao/TripMate category | Maki icon | palette |
| --- | --- | --- |
| 음식점 | `restaurant` | `amber` |
| 카페 | `cafe` | `saffron` |
| 숙소 | `lodging` | `indigo` |
| 관광명소/명소 | `attraction` | `terracotta` |
| 자연/공원 | `attraction` | `olive` 또는 `sage` |
| 액티비티 | `attraction` | `forest` |
| 해수욕장/해변 | `beach` | `teal` |
| 공공 리포트/행정구역 | `town-hall` | `indigo` |
| 기타/정보 | `information` | `charcoal` |

색상은 `airbnb-marker-palette.html`의 16색만 쓴다. 선택 상태는 `paletteKey`를 `rausch`로 강제하기보다, 원래 category 색을 유지하고 ring, scale, z-index, badge로 강조한다. 사용자가 선택한 장소를 반드시 Rausch로 통일하라는 제품 결정이 있으면 그때만 변경한다.

### 검색 후보

```ts
export type PlaceSearchCandidate = {
  provider: "kakao"
  providerPlaceId: string
  name: string
  categoryName: string | null
  addressName: string | null
  roadAddressName: string | null
  phone: string | null
  homepageUrl: string | null
  coordinate: Coordinate
  distanceMeters: number | null
  cacheExpiresAt: ISODateTime | null
}
```

### 지도 클릭 draft

```ts
export type DraftPlace = {
  source: "map_click"
  coordinate: Coordinate
  suggestedAddress: string | null
  displayName: string
  note: string
  selectedDayId: UUID | null
}
```

## API 계약

### `GET /trips`

여행 목록 화면용 endpoint다.

인증:

- 일반 사용자 httpOnly cookie 세션 필수.

응답 예시:

```json
{
  "trips": [
    {
      "id": "00000000-0000-4000-8000-000000000101",
      "title": "부산 주말 여행",
      "description": "해운대와 광안리 중심",
      "start_date": "2026-06-12",
      "end_date": "2026-06-14",
      "cover_image_url": null,
      "is_archived": false,
      "day_count": 3,
      "place_count": 8,
      "member_count": 2,
      "telegram_target_count": 1
    }
  ]
}
```

오류:

- `401`: 로그인 필요.

### `POST /trips`

여행 생성 endpoint다.

요청:

```json
{
  "title": "부산 주말 여행",
  "description": "해운대와 광안리 중심",
  "start_date": "2026-06-12",
  "end_date": "2026-06-14",
  "default_sido_code": "2600000000",
  "default_sigungu_code": "2635000000"
}
```

규칙:

- `title`은 1자 이상 120자 이하.
- 날짜가 있으면 `start_date <= end_date`.
- 날짜 범위가 있으면 `trip_days`를 생성한다.
- 기본 지역 코드는 선택이다. 좌표 기본 중심 계산에 사용할 수 있다.

### `GET /trips/{trip_id}/workspace`

여행 상세 작업대의 초기 load endpoint다. 여러 API를 따로 호출해서 화면이 깜박이지 않도록 첫 구현부터 workspace endpoint를 둔다.

응답 예시:

```json
{
  "trip": {
    "id": "00000000-0000-4000-8000-000000000101",
    "title": "부산 주말 여행",
    "description": "해운대와 광안리 중심",
    "start_date": "2026-06-12",
    "end_date": "2026-06-14",
    "default_center": {
      "latitude": "35.15869700",
      "longitude": "129.16038400"
    },
    "default_zoom_level": 6,
    "owner_user_id": "00000000-0000-4000-8000-000000000001",
    "can_edit": true
  },
  "days": [
    {
      "id": "00000000-0000-4000-8000-000000000201",
      "day_number": 1,
      "date": "2026-06-12",
      "title": null,
      "weather_summary": null
    }
  ],
  "places": [],
  "plan_items": [],
  "categories": [],
  "layer_states": [
    { "layer_key": "festival", "display_name": "축제", "enabled_by_default": false },
    { "layer_key": "beach", "display_name": "해수욕장", "enabled_by_default": false }
  ],
  "public_layer_markers": [],
  "telegram_summary": {
    "connected_target_count": 0,
    "max_target_count": 3
  },
  "gemini_summary": {
    "last_run_id": null,
    "last_run_status": null
  }
}
```

인가:

- 본인 여행 또는 참여 중인 여행만 조회 가능.
- 현재 구현에 참여자 권한 테이블이 부족하면 owner 기준으로 먼저 구현하고, 문서에 후속 TODO를 남긴다.

오류:

- `401`: 로그인 필요.
- `403`: 접근 권한 없음.
- `404`: 여행 없음.

### `POST /trips/{trip_id}/places`

내부 여행 장소를 저장한다.

Kakao 후보 저장 요청:

```json
{
  "source_type": "kakao",
  "provider_place_id": "123456789",
  "display_name": "해운대해수욕장",
  "address": "부산광역시 해운대구 우동",
  "road_address": "부산광역시 해운대구 해운대해변로 264",
  "longitude": "129.16038400",
  "latitude": "35.15869700",
  "category_code": "beach",
  "note": null
}
```

지도 클릭 custom place 요청:

```json
{
  "source_type": "user_custom",
  "display_name": "첫날 숙소 근처 산책 지점",
  "address": "부산광역시 해운대구 우동 일대",
  "road_address": null,
  "longitude": "129.15890000",
  "latitude": "35.15810000",
  "category_code": "custom",
  "note": "지도 클릭으로 추가"
}
```

규칙:

- `source_type = user_custom`이면 provider id를 받지 않는다.
- 좌표는 EPSG:4326이며 API field는 `longitude`, `latitude` 순서다.
- 저장 시 point-in-polygon으로 행정구역 코드를 보강할 수 있다.
- provider raw response 전체를 저장하지 않는다.

### `POST /trips/{trip_id}/days/{trip_day_id}/items`

기존 `docs/api/trips.md` 기준을 유지하되 `trip_place_id`를 명시적으로 받을 수 있게 확장한다.

장소 일정 추가 요청:

```json
{
  "resource_type": "place",
  "trip_place_id": "00000000-0000-4000-8000-000000000301",
  "note": "점심 전 산책"
}
```

응답은 저장된 `TripPlanItem` shape다.

### `PUT /trips/{trip_id}/days/{trip_day_id}/items/reorder`

날짜 안 일정 순서를 저장한다.

요청:

```json
{
  "ordered_item_ids": [
    "00000000-0000-4000-8000-000000000401",
    "00000000-0000-4000-8000-000000000402"
  ]
}
```

규칙:

- 요청된 item은 모두 같은 `trip_day_id`에 속해야 한다.
- 누락/중복 id는 `422`.
- 성공 시 `sort_order`를 1부터 안정적으로 재부여한다.

### `GET /places/search`

Kakao 장소 검색 후보 endpoint다. 브라우저에서 Kakao REST API를 직접 호출하지 않는다.

요청:

```http
GET /places/search?query=해운대%20카페&longitude=129.160384&latitude=35.158697&radius_meters=3000
```

응답:

```json
{
  "provider": "kakao",
  "query": "해운대 카페",
  "cache_expires_at": "2026-05-08T21:30:00+09:00",
  "candidates": [
    {
      "provider": "kakao",
      "provider_place_id": "123456789",
      "name": "카페 예시",
      "category_name": "음식점 > 카페",
      "address_name": "부산광역시 해운대구 우동 000",
      "road_address_name": "부산광역시 해운대구 해운대해변로 000",
      "phone": "051-000-0000",
      "homepage_url": "https://example.kr",
      "longitude": "129.16038400",
      "latitude": "35.15869700",
      "distance_meters": 250
    }
  ]
}
```

규칙:

- `query`는 1자 이상 80자 이하.
- 좌표가 있으면 bias 검색에 사용한다.
- `radius_meters`는 provider 허용 범위 안에서 clamp한다.
- 결과는 TripMate 정규화 shape로 반환한다.
- Kakao raw response는 TTL cache에만 저장한다.
- cache key에는 provider, normalized query, 좌표 bucket, radius, page를 포함한다.

### `GET /places/reverse-geocode`

지도 클릭 후 주소 표시용 endpoint다.

```http
GET /places/reverse-geocode?longitude=129.1589&latitude=35.1581
```

응답:

```json
{
  "longitude": "129.15890000",
  "latitude": "35.15810000",
  "address_name": "부산광역시 해운대구 우동",
  "road_address_name": null,
  "legal_dong_code": "2635010500",
  "sigungu_code": "2635000000",
  "sido_code": "2600000000",
  "source": "postgis_then_kakao"
}
```

우선순위:

1. PostGIS 행정구역 point-in-polygon으로 행정구역 코드와 행정동/법정동 표시명을 찾는다.
2. 필요할 때만 Kakao reverse geocode를 호출한다.
3. Kakao 실패 시 좌표와 행정구역 근사 주소만 표시한다.

## Kakao 지도 컴포넌트 구현 세부

`TripKakaoMap.tsx`는 client component다.

필수 import:

```ts
"use client"

import {
  CustomOverlayMap,
  Map,
  MapTypeControl,
  MapTypeId,
  MarkerClusterer,
  Polyline,
  useKakaoLoader,
} from "react-kakao-maps-sdk"
```

사용하지 않는 import는 남기지 않는다. MVP에서 `MapTypeControl`을 쓰지 않으면 import하지 않는다.

### `useKakaoLoader`

`react-kakao-maps-sdk@1.2.1` 기준:

```ts
const [loading, error] = useKakaoLoader({
  appkey: kakaoAppKey,
  libraries: ["services", "clusterer"],
  retries: 2,
})
```

주의:

- `Map`을 loading 조건으로 완전히 숨기지 않아도 library가 로딩 상태를 관찰하지만, TripMate는 app key 누락/error UI를 명확히 보여준다.
- app key가 없으면 `useKakaoLoader`를 호출하지 않는 별도 wrapper를 둔다. React hook 규칙을 깨지 않기 위해 wrapper component를 나눈다.

권장 구조:

```tsx
export function TripKakaoMap(props: TripKakaoMapProps) {
  const appKey = process.env.NEXT_PUBLIC_KAKAO_MAP_APP_KEY
  if (!appKey) {
    return <MapUnavailable reason="missing_key" />
  }
  return <TripKakaoMapLoaded {...props} appKey={appKey} />
}

function TripKakaoMapLoaded({ appKey, ...props }: TripKakaoMapLoadedProps) {
  const [loading, error] = useKakaoLoader({
    appkey: appKey,
    libraries: ["services", "clusterer"],
    retries: 2,
  })

  if (error) return <MapUnavailable reason="load_error" />

  return (
    <Map
      id="trip-kakao-map"
      data-testid="trip-kakao-map"
      center={props.center}
      level={props.level}
      style={{ width: "100%", height: "100%" }}
      onCreate={props.onMapCreate}
      onClick={props.onMapClick}
      onIdle={props.onMapIdle}
      draggable
      zoomable
    >
      {props.showTraffic && <MapTypeId type="TRAFFIC" />}
      {/* markers */}
    </Map>
  )
}
```

`Map` event signature:

```ts
onClick?: (
  target: kakao.maps.Map,
  mouseEvent: kakao.maps.event.MouseEvent
) => void
```

지도 클릭 좌표:

```ts
function handleMapClick(
  _map: kakao.maps.Map,
  mouseEvent: kakao.maps.event.MouseEvent
) {
  const latLng = mouseEvent.latLng
  const latitude = latLng.getLat()
  const longitude = latLng.getLng()
  openDraftPlace({ source: "map_click", coordinate: { latitude, longitude } })
}
```

### marker icon asset

marker glyph는 Mapbox Maki icon을 내려받아 self-host한다. Maki는 POI 지도 icon set이고, 공식 저장소는 source SVG를 제공한다. 2026-05-07 확인 기준 `@mapbox/maki@8.2.0`의 license는 `CC0-1.0`이다.

설치:

```bash
npm install --workspace apps/web --save-dev @mapbox/maki
```

복사 대상:

```ts
export const REQUIRED_MAKI_ICONS = [
  "marker",
  "marker-stroked",
  "star",
  "attraction",
  "beach",
  "fuel",
  "highway-rest-area",
  "restaurant",
  "cafe",
  "lodging",
  "town-hall",
  "information",
] as const
```

권장 복사 script 위치:

```text
apps/web/scripts/sync-maki-icons.mjs
```

script 요구사항:

- `@mapbox/maki/icons/{iconName}.svg`에서 필요한 파일만 읽는다.
- 출력 위치는 `apps/web/public/map-icons/maki/{iconName}.svg`다.
- 출력 전 대상 directory를 생성한다.
- `REQUIRED_MAKI_ICONS` 중 누락된 파일이 있으면 exit code 1로 실패한다.
- SVG 내용을 임의로 다시 그리지 않는다. 색상 변경은 CSS filter보다 marker wrapper의 `background`, `border`, `mask` 또는 `img` opacity로 처리한다.
- license 확인을 위해 `@mapbox/maki/package.json`의 `version`, `license`를 console에 출력한다.

marker icon URL helper:

```ts
export function getMakiIconUrl(iconName: MakiIconName): string {
  return `/map-icons/maki/${iconName}.svg`
}
```

Maki 사용 금지 사항:

- `https://raw.githubusercontent.com/mapbox/maki/...` 같은 raw URL을 runtime에서 직접 참조하지 않는다.
- Mapbox GL symbol layer 전제를 가져오지 않는다. TripMate marker는 Kakao `CustomOverlayMap` 안에서 HTML/CSS로 렌더링한다.
- Maki icon을 Lucide icon으로 대체하지 않는다. Lucide는 UI button/action icon 전용이다.
- marker category/source 색상은 `airbnb-marker-palette.html`의 16색 안에서만 고른다. marker 색상에 한해 16색 팔레트가 `DESIGN.md`보다 우선한다.

### marker

일반 marker는 `CustomOverlayMap`을 우선한다. 이유는 TREK처럼 원형 사진/아이콘 marker와 order badge를 CSS로 정확히 표현하기 쉽기 때문이다.

`CustomOverlayMap` props:

```tsx
<CustomOverlayMap
  position={{ lat: marker.coordinate.latitude, lng: marker.coordinate.longitude }}
  clickable
  xAnchor={0.5}
  yAnchor={0.5}
  zIndex={marker.isSelected ? 20 : 10}
>
  <button
    type="button"
    data-testid={`map-marker-${marker.id}`}
    aria-label={`${marker.title} 지도 마커`}
    className="tm-map-marker"
    onClick={() => onMarkerSelect(marker.id)}
    style={{ "--tm-current-marker-color": marker.colorHex } as React.CSSProperties}
  >
    <span className="tm-map-marker-icon" aria-hidden="true">
      <img src={getMakiIconUrl(marker.makiIconName)} alt="" />
    </span>
    {marker.orderNumbers.length > 0 && (
      <span className="tm-map-marker-badge">{marker.orderNumbers[0]}</span>
    )}
  </button>
</CustomOverlayMap>
```

주의:

- `CustomOverlayMap` 자체의 클릭이 아니라 내부 button에서 selection을 처리한다.
- `clickable`을 true로 둬 overlay 클릭 시 지도 click이 같이 발생하지 않게 한다.
- marker DOM button은 40x40 이상 touch target을 확보한다.
- selected marker는 크기, border, z-index만 바꾸고 layout shift를 최소화한다.
- marker icon은 Maki SVG를 `img`로 표시하거나 CSS mask로 표시한다. MVP에서는 구현 단순성을 위해 `img`를 우선한다.
- `img`의 `alt`는 빈 문자열로 둔다. 접근 가능한 이름은 marker button의 `aria-label`이 담당한다.
- marker 색상은 `--tm-current-marker-color`로 주입한다. 이 값은 반드시 `MARKER_PALETTE`에서 온다.
- selected marker는 원래 palette color를 유지하고 ring, scale, z-index, badge contrast로 강조한다. 선택 상태만 무조건 Rausch로 덮어쓰지 않는다.
- Maki SVG 파일 자체를 색상별로 복제하지 않는다.
- marker shadow는 `--tm-shadow-card` 한 tier만 사용한다.

### clustering

공공 데이터 layer처럼 marker가 많을 때만 `MarkerClusterer`를 사용한다.

```tsx
<MarkerClusterer averageCenter minLevel={8} minClusterSize={3}>
  {clusteredMarkers.map(marker => (
    <CustomOverlayMap ... />
  ))}
</MarkerClusterer>
```

주의:

- 일정 marker와 선택 marker는 cluster 안에 넣지 않는다. 사용자가 선택한 일정 marker가 cluster에 묻히면 일정 편집성이 떨어진다.
- 축제/해수욕장 같은 public layer marker는 cluster 대상이다.

### polyline

MVP에서는 날짜별 일정 순서를 직선 polyline으로만 표시한다.

```tsx
<Polyline
  path={dayRoutePath}
  strokeWeight={3}
  strokeColor="#111827"
  strokeOpacity={0.7}
  strokeStyle="dash"
/>
```

주의:

- 이 선은 실제 이동 경로가 아니라 일정 순서 연결선이다.
- UI label은 `일정 순서 연결선` 또는 `직선 연결`처럼 표현한다.
- 실제 경로 최적화/길찾기는 provider 정책 검토 후 후속 작업이다.

### bounds와 viewport

Kakao map instance는 `onCreate`로 state/ref에 저장한다.

```ts
const [map, setMap] = useState<kakao.maps.Map | null>(null)
```

fit bounds는 자동으로 자주 실행하지 않는다.

규칙:

- workspace 최초 로드 후 좌표가 있는 장소가 있으면 한 번만 fit한다.
- 사용자가 지도 drag/zoom을 한 뒤에는 marker 추가, 날짜 변경만으로 무조건 fit하지 않는다.
- `fitKey`를 증가시키는 명시 행동에서만 fit한다. 예: `전체 보기`, 여행 변경, layer 최초 켜기.

## 프론트엔드 컴포넌트 책임

### `TripsDashboard`

책임:

- 인증된 사용자의 여행 목록을 조회한다.
- active/archived를 나눈다.
- 가장 가까운 여행을 spotlight로 고른다.
- 새 여행 modal을 열고 생성 성공 시 `/trips/{id}`로 이동한다.
- API 오류, empty state, loading skeleton을 표시한다.

하지 않는다:

- 지도 로직을 포함하지 않는다.
- 여행 상세 workspace state를 갖지 않는다.

필수 test id:

- `trips-dashboard`
- `new-trip-button`
- `trip-spotlight-card`
- `trip-card-${tripId}`
- `archived-trips-toggle`

### `TripWorkspace`

책임:

- `GET /trips/{trip_id}/workspace` 결과를 로드하고 route-local state를 관리한다.
- active tab을 관리한다.
- 좌우 panel collapse/resize 상태를 관리한다.
- 선택 상태를 지도/panel/inspector에 전달한다.
- mutation 성공/실패 후 state를 갱신한다.

하지 않는다:

- marker JSX 세부 구현을 직접 쓰지 않는다.
- Kakao SDK를 직접 import하지 않는다. 지도 구현은 `TripKakaoMap`에 둔다.
- 백엔드 응답을 무검증으로 state에 넣지 않는다.

필수 test id:

- `trip-workspace`
- `trip-tab-plan`
- `trip-tab-regional-report`
- `trip-tab-telegram`
- `trip-tab-gemini`

### `TripTopNav`

책임:

- 뒤로가기, 로고, 여행명, 공유/참여자, 알림, 사용자 메뉴를 표시한다.
- desktop에서는 fixed top nav.
- mobile에서는 compact top header.

필수 test id:

- `trip-top-nav`
- `trip-back-button`
- `trip-title`
- `trip-user-menu`

### `TripTabs`

책임:

- `계획`, `지역 리포트`, `알림`, `리서치`, 후속 tab을 표시한다.
- active tab을 URL query 또는 route-local state와 동기화한다.

규칙:

- MVP에서 구현되지 않은 tab은 숨기거나 disabled 상태와 tooltip을 둔다.
- 빈 tab을 누르면 아무 내용 없는 화면을 보여주지 않는다.

### `DayPlanPanel`

책임:

- 날짜별 section을 표시한다.
- 각 날짜의 weather summary, item count, 편집 action을 표시한다.
- plan item row 클릭 시 selection을 변경한다.
- 선택 날짜를 workspace에 알린다.
- 일정 item 추가/삭제/순서 변경 action을 호출한다.

필수 동작:

- 날짜 header click: `selectedDayId` 변경.
- item click: `selectedPlanItemId`, `selectedPlaceId` 변경.
- item hover/focus: marker hover state 전달.
- 날짜 접기/펼치기 상태는 sessionStorage에 저장할 수 있다.

필수 test id:

- `day-plan-panel`
- `day-section-${dayId}`
- `day-header-${dayId}`
- `plan-item-${itemId}`
- `add-item-to-day-${dayId}`

### `PlacePoolPanel`

책임:

- 저장 장소 목록과 Kakao 검색 후보를 표시한다.
- `전체`, `미배치`, `공공데이터`, `경로/트랙` 같은 filter를 제공한다. MVP는 `전체`, `미배치`만 필수다.
- category filter를 제공한다.
- `장소 추가` 버튼으로 manual/custom place dialog를 연다.
- Kakao 검색 input에서 debounce 후 `/places/search`를 호출한다.
- 검색 후보 선택 시 내부 장소 저장 flow를 호출한다.

필수 동작:

- 선택 날짜가 있으면 후보 `+` 클릭 시 장소 저장 후 해당 날짜 일정에 바로 추가한다.
- 선택 날짜가 없으면 장소만 저장하고 “날짜를 선택하면 일정에 추가할 수 있습니다” 상태를 표시한다.
- 검색 실패는 panel 안에 retry 가능한 inline 상태로 보여준다.

필수 test id:

- `place-pool-panel`
- `place-search-input`
- `place-filter-all`
- `place-filter-unplanned`
- `place-row-${placeId}`
- `place-search-candidate-${providerPlaceId}`
- `add-place-candidate-${providerPlaceId}`

### `TripKakaoMap`

책임:

- Kakao 지도 SDK load.
- 지도 full surface rendering.
- marker, public layer marker, draft marker, polyline 표시.
- 지도 click으로 draft place를 생성한다.
- marker click을 workspace selection으로 전달한다.
- map unavailable 상태를 명확히 표시한다.

필수 test id:

- `trip-kakao-map`
- `map-unavailable`
- `map-marker-${markerId}`
- `map-layer-toggle`
- `map-fit-bounds-button`
- `map-draft-place`

### `PlaceInspector`

책임:

- 선택된 장소/일정 item의 상세를 보여준다.
- 이름, 주소, category, provider, 메모, 참여자/날짜 연결 상태를 표시한다.
- edit/delete/add-to-day action을 제공한다.

Desktop:

- 오른쪽 panel 옆 또는 지도 위 floating inspector로 표시한다.

Mobile:

- bottom sheet로 표시한다.

필수 test id:

- `place-inspector`
- `place-inspector-close`
- `place-inspector-edit`
- `place-inspector-add-to-day`

### `DraftPlaceSheet`

책임:

- 지도 클릭으로 생긴 좌표 draft를 저장 가능한 장소로 확정한다.
- reverse geocode 결과를 표시한다.
- 사용자가 display name을 입력해야 저장 가능하다.

필수 field:

- 장소명.
- 주소 snapshot. reverse geocode 실패 시 비워둘 수 있다.
- category. 기본 `custom`.
- 메모.
- 선택 날짜에 바로 추가 여부 checkbox.

필수 test id:

- `draft-place-sheet`
- `draft-place-name-input`
- `draft-place-save`
- `draft-place-cancel`

### `RegionalReportPanel`

책임:

- 선택 여행 또는 선택 장소 기준의 지역 리포트를 표시한다.
- 행정구역 기반 근사임을 안내한다.
- 공공 데이터 layer toggle과 연결한다.

필수 test id:

- `regional-report-panel`
- `regional-report-approximation-note`
- `regional-layer-festival`
- `regional-layer-beach`

### `TelegramPanel`

책임:

- 여행별 Telegram 대상 연결 상태를 표시한다.
- 최대 3개 제한을 UI에서 강제한다.
- 테스트 발송 action을 제공한다.
- 실패 사유를 구분해 보여준다.

필수 test id:

- `telegram-panel`
- `telegram-target-count`
- `telegram-add-target`
- `telegram-test-send`

### `GeminiResearchPanel`

책임:

- Gemini Deep Research 수동 실행 버튼.
- 사용자 개인 API key 연결 상태.
- 최근 실행 이력과 결과 summary.
- 원천 데이터와 AI 결과 분리 표시.

필수 test id:

- `gemini-panel`
- `gemini-api-key-status`
- `gemini-run-button`
- `gemini-run-history`

## 상태 관리 세부

처음에는 Zustand 같은 새 전역 store를 도입하지 않아도 된다. route-local reducer 또는 `useState` 조합으로 충분하다. 여러 화면에서 재사용 필요가 확정되면 store를 분리한다.

권장 reducer state:

```ts
export type WorkspaceState = {
  workspace: TripWorkspace
  activeTab: "plan" | "regional_report" | "telegram" | "gemini" | "files"
  selectedDayId: UUID | null
  selectedPlaceId: UUID | null
  selectedPlanItemId: UUID | null
  hoveredMarkerId: string | null
  draftPlace: DraftPlace | null
  enabledLayerKeys: Set<string>
  search: {
    query: string
    status: "idle" | "loading" | "success" | "error"
    candidates: PlaceSearchCandidate[]
    errorMessage: string | null
  }
  panels: {
    leftCollapsed: boolean
    rightCollapsed: boolean
    leftWidth: number
    rightWidth: number
    mobileSheet: "day_plan" | "places" | "inspector" | null
  }
  responsive: {
    mode: ResponsiveMode
    panelPresentation: PanelPresentation
    tabletOverlay: "day_plan" | "places" | "inspector" | null
    lastKnownWidth: number | null
    lastKnownHeight: number | null
  }
  map: {
    center: Coordinate
    level: number
    fitKey: number
    userMovedMap: boolean
  }
}
```

규칙:

- `Set`은 React state로 직접 mutate하지 않는다. 새 `Set`을 만들어 갱신한다.
- API mutation 전 이전 state snapshot을 보관한다.
- mutation 실패 시 toast만 띄우고 state가 서버와 불일치한 채 남지 않게 rollback한다.
- search debounce는 250~400ms로 둔다.
- abort controller로 이전 search 요청을 취소한다.
- URL query 동기화는 MVP에서는 `tab`, `day`, `place`까지만 허용한다.
- responsive state는 URL에 넣지 않는다. viewport 변화로 `mode`만 바뀌고 사용자가 선택한 `tab`, `day`, `place`는 유지돼야 한다.
- `mode`가 `mobile_narrow` 또는 `mobile`이면 `panelPresentation`은 `sheet`다.
- `mode`가 `tablet`이면 `panelPresentation`은 `overlay`다. 동시에 두 panel을 열지 않는다.
- `mode`가 `desktop` 또는 `wide`이면 `panelPresentation`은 `docked`다. 좌우 collapse 상태와 폭을 보존한다.
- viewport 전환 후 Kakao map `relayout()`을 debounce 호출한다.

## 핵심 사용자 흐름

### 로그인 후 여행 목록

1. 사용자가 `/login`에서 로그인한다.
2. 성공하면 `/trips`로 이동한다.
3. `/trips`는 `GET /trips`를 호출한다.
4. trip이 없으면 새 여행 empty state를 보여준다.
5. trip이 있으면 가장 가까운 여행을 spotlight로 보여준다.
6. 사용자가 trip card를 클릭하면 `/trips/{tripId}`로 이동한다.

오류:

- `401`: `/login`으로 이동.
- network error: retry button 표시.
- 빈 목록: `새 여행` action만 표시.

### 새 여행 생성

1. 사용자가 `새 여행`을 누른다.
2. dialog에서 여행명, 날짜 범위, 기본 지역을 입력한다.
3. `POST /trips` 호출.
4. 성공하면 `/trips/{newTripId}` 이동.
5. 실패하면 field error 또는 dialog-level error 표시.

검증:

- title 필수.
- 날짜 순서.
- 기본 지역은 선택값.

### 여행 상세 initial load

1. `/trips/{tripId}` 진입.
2. `GET /trips/{tripId}/workspace` 호출.
3. parser 통과 후 state 생성.
4. `계획` tab을 기본 active로 둔다.
5. 좌표 있는 장소가 있으면 최초 1회 fit bounds.
6. 좌표가 없으면 기본 중심은 여행 기본 지역, 없으면 대한민국 중심 근사 좌표를 사용한다.

권장 fallback center:

```ts
{ latitude: 36.5, longitude: 127.8 }
```

### Kakao 검색으로 장소 추가

1. 사용자가 우측 panel 검색창에 query 입력.
2. 300ms debounce 후 `GET /places/search`.
3. 후보 row 표시.
4. 사용자가 후보 `+`를 누른다.
5. `POST /trips/{tripId}/places`로 내부 장소 저장.
6. 선택 날짜가 있으면 `POST /trips/{tripId}/days/{dayId}/items` 호출.
7. 성공하면 places와 planItems state를 갱신한다.
8. 새 marker를 selected 상태로 표시한다.

오류:

- search 실패: 후보 영역에 retry.
- 장소 저장 실패: 후보 row에 inline error 또는 toast.
- 일정 추가 실패: 장소는 저장됐지만 일정 추가 실패 상태를 명확히 알리고, `선택 날짜에 추가` 재시도 버튼 제공.

### 지도 클릭으로 custom place 추가

1. 사용자가 지도 빈 곳을 클릭한다.
2. `DraftPlace`를 만들고 draft marker를 표시한다.
3. reverse geocode endpoint를 호출한다.
4. `DraftPlaceSheet`에서 주소/좌표를 보여준다.
5. 사용자가 장소명을 입력한다.
6. 저장하면 `POST /trips/{tripId}/places` with `source_type=user_custom`.
7. 선택 날짜가 있거나 checkbox가 켜져 있으면 일정 item도 만든다.
8. draft state를 닫고 새 marker를 selected로 둔다.

오류:

- reverse geocode 실패: 주소 없이 좌표만 표시하고 저장 가능.
- 이름 미입력: 저장 button disabled.
- 좌표 범위 오류: draft를 만들지 않고 오류 표시.

### 날짜와 marker 동기화

1. 날짜 header 클릭: `selectedDayId` 변경.
2. 해당 날짜의 plan item marker만 order badge를 표시한다.
3. 우측 장소 panel은 `미배치` filter count를 갱신한다.
4. map은 자동 fit하지 않는다. 사용자가 `전체 보기`를 누르면 fit한다.

### layer toggle

1. 사용자가 지도 layer menu 또는 지역 리포트에서 `축제`를 켠다.
2. 이미 workspace에 marker가 있으면 즉시 표시한다.
3. 없으면 `GET /public/festivals/map-markers`를 호출한다.
4. marker가 많으면 cluster로 표시한다.
5. marker click은 public resource inspector를 연다.
6. `추가` 버튼은 선택 날짜에 `resource_type=festival`로 일정 item을 만든다.

## 백엔드 구현 세부

### 인증/인가

- 기존 일반 사용자 session dependency를 사용한다.
- 모든 `/trips` workspace/mutation endpoint는 현재 사용자 기준 인가를 수행한다.
- 현재 참여자 테이블이 불완전하면 owner-only로 먼저 구현하고 TODO를 문서에 남긴다.
- 관리자는 운영 확인 목적 조회 가능 여부를 기존 정책에 맞춘다. 일반 사용자 작업 화면에서 관리자 권한을 암묵적으로 섞지 않는다.

### DB 모델 확인 순서

구현 전 아래를 확인한다.

1. `apps/api/app/models/trip.py`
2. `apps/api/app/models/place.py`
3. `apps/api/app/models/user.py`
4. `apps/api/alembic/versions/*trip*`
5. `docs/architecture/user-trip-schema.md`
6. `docs/architecture/place-schema.md`
7. `docs/architecture/map-feature-schema.md`

이미 존재하는 테이블을 재정의하지 않는다. 필요한 column이 부족하면 migration을 추가한다.

### 권장 service 경계

`trip_workspace.py`:

- 여행 조회.
- 날짜, 장소, 일정 item, category, layer summary 조립.
- 좌표 문자열/Decimal 직렬화.
- 사용자 권한 field 계산.

`trip_plan.py`:

- 여행 생성/수정/삭제.
- 날짜 범위 기반 `trip_days` 생성/갱신.
- 장소 저장.
- 일정 item 추가/삭제/reorder.

`kakao_local.py`:

- Kakao Local REST API 호출.
- timeout, retry, error classification.
- provider response normalization.
- raw TTL cache read/write.

`place_search.py`:

- query validation.
- cache key 생성.
- Kakao Local 호출 결과를 TripMate 후보로 반환.
- reverse geocode에서 PostGIS 행정구역 조회와 Kakao fallback 조합.

### Kakao Local adapter 오류 분류

권장 오류:

- `KakaoLocalConfigError`: key 누락.
- `KakaoLocalTimeout`: timeout.
- `KakaoLocalQuotaError`: quota/rate limit.
- `KakaoLocalProviderError`: Kakao 5xx 또는 알 수 없는 provider 오류.
- `KakaoLocalBadRequest`: query/radius 등 client 입력 문제.

API 응답:

- config error는 서버 설정 문제로 `503`.
- timeout/provider error는 `502` 또는 `504`.
- bad request는 `422`.
- quota는 `429` 또는 `503` 중 기존 API 정책에 맞춘다.

### cache key

Kakao search cache key 권장 구성:

```text
kakao:place-search:v1:{normalized_query}:{lng_bucket}:{lat_bucket}:{radius}:{page}
```

Reverse geocode cache key:

```text
kakao:reverse-geocode:v1:{lng_5dp}:{lat_5dp}
```

주의:

- query 원문을 로그에 그대로 쓰지 않는다.
- cache key 저장에 query 원문이 필요하면 DB에 들어가는 값이 민감하지 않은지 판단하고, 가능하면 hash를 쓴다.
- provider raw payload TTL 만료 후 삭제 또는 재사용 불가 처리가 가능해야 한다.

## 구현 단계

### Phase 0. 구현 전 정리

Codex가 할 일:

- `git status --short`로 dirty 상태를 확인한다.
- 관련 파일의 기존 변경을 되돌리지 않는다.
- `apps/web/package.json`, `apps/web/app/shared/api-base.ts`, 기존 auth/login 구현을 읽는다.
- `apps/api/app/api/routes/trips.py`, `apps/api/app/schemas/trip.py`, `apps/api/app/services/trip_plan.py`가 있으면 먼저 읽는다.
- 필요한 경우 이 문서를 구현 세부에 맞게 먼저 갱신한다.

완료 조건:

- 실제 코드 구조에 맞춘 작업 범위가 정리됐다.
- 기존 user 변경과 충돌할 파일을 알고 있다.

### Phase A. `/trips` 대시보드

목표:

- 로그인 후 기본 화면을 TREK식 여행 목록 작업면으로 만든다.

프론트엔드 작업:

- `apps/web/app/trips/page.tsx` 추가.
- `TripsDashboard.tsx`, `TripCard.tsx`, `TripFormDialog.tsx` 추가.
- 기존 auth helper를 사용해 인증되지 않은 사용자를 `/login`으로 보낸다.
- `GET /trips` API client helper와 parser를 만든다.
- empty/loading/error state를 만든다.
- mobile layout overflow를 방지한다.

백엔드 작업:

- `GET /trips`가 없으면 추가한다.
- `POST /trips`가 없으면 최소 생성 endpoint를 추가한다.
- 날짜 범위 기반 `trip_days` 생성 로직을 service에 둔다.

검증:

```bash
wsl.exe -e bash -lc "cd /mnt/f/dev/mapplan && npm run lint"
wsl.exe -e bash -lc "cd /mnt/f/dev/mapplan && npm run typecheck"
```

백엔드 변경이 있으면:

```bash
wsl.exe -e bash -lc "cd /mnt/f/dev/mapplan/apps/api && uv run ruff check ."
wsl.exe -e bash -lc "cd /mnt/f/dev/mapplan/apps/api && uv run ruff format --check ."
wsl.exe -e bash -lc "cd /mnt/f/dev/mapplan/apps/api && uv run mypy ."
wsl.exe -e bash -lc "cd /mnt/f/dev/mapplan/apps/api && uv run pytest"
```

### Phase B. 여행 상세 shell

목표:

- 지도 없이도 상단 nav, tab bar, 좌우 panel shell이 보이는 작업대를 만든다.

프론트엔드 작업:

- `apps/web/app/trips/[tripId]/page.tsx` 추가.
- `TripWorkspace.tsx`, `TripTopNav.tsx`, `TripTabs.tsx`, `DayPlanPanel.tsx`, `PlacePoolPanel.tsx` 추가.
- `GET /trips/{trip_id}/workspace` client helper와 parser 추가.
- active tab state를 구현한다.
- desktop panel collapse와 mobile sheet state를 구현한다.
- 아직 지도 component가 없으면 중앙에 `지도 준비 중` placeholder를 둔다.

백엔드 작업:

- workspace endpoint 추가.
- 기존 데이터로 채울 수 없는 field는 null 또는 빈 배열로 명확히 반환한다.
- 임시 fake trip을 만들지 않는다.

완료 조건:

- 실제 로그인 사용자 여행으로 workspace shell이 열린다.
- 빈 여행이어도 DayPlanPanel과 PlacePoolPanel이 깨지지 않는다.

### Phase C. Kakao 지도 도입

목표:

- `react-kakao-maps-sdk` 기반 Kakao 지도 surface를 workspace 중앙에 붙인다.

프론트엔드 작업:

- 의존성 추가.
- `apps/web/tsconfig.json`에 `kakao.maps.d.ts` 추가.
- `TripKakaoMap.tsx` 추가.
- app key 누락, loader error, 정상 load 상태 구현.
- 저장 장소 marker와 draft marker 표시.
- marker selection sync 구현.
- 지도 클릭 draft 생성 구현.

주의:

- 지도 component는 client component다.
- Next.js server component에서 직접 Kakao SDK import를 하지 않는다.
- 필요하면 `next/dynamic`의 `ssr: false`로 map component를 import한다.

검증:

- app key 없는 상태에서 friendly fallback.
- app key 있는 상태에서 지도 표시.
- 지도 클릭 시 draft sheet 표시.
- marker click 시 inspector 표시.

### Phase D. Kakao 검색과 장소 저장

목표:

- 우측 panel에서 Kakao 장소 검색 후보를 보고 TripMate 내부 장소로 저장한다.

백엔드 작업:

- `GET /places/search`.
- `GET /places/reverse-geocode`.
- Kakao Local adapter.
- TTL cache 정책.
- provider raw response 장기 저장 방지 test.

프론트엔드 작업:

- `PlacePoolPanel` 검색 input.
- debounce + abort.
- 후보 parser.
- 후보 저장 flow.
- 선택 날짜 일정 추가 flow.
- 실패 시 retry/partial success UI.

완료 조건:

- 검색 후보 선택으로 장소가 저장된다.
- 선택 날짜가 있으면 일정 item까지 생성된다.
- 좌표/marker/list가 동기화된다.

### Phase E. 일정 reorder와 polyline

목표:

- 날짜별 item 순서를 바꾸고 지도에 직선 연결선을 표시한다.

작업:

- `PUT /trips/{trip_id}/days/{trip_day_id}/items/reorder`.
- `DayPlanPanel`에서 keyboard accessible reorder button 우선 구현.
- drag and drop은 후속으로 둬도 된다. 먼저 위/아래 icon button이 안정적이다.
- `Polyline`으로 선택 날짜의 일정 순서 연결선을 표시한다.

완료 조건:

- 순서 변경 후 새로고침해도 순서가 유지된다.
- marker badge order가 순서와 일치한다.

### Phase F. 공공 데이터 layer와 지역 리포트

목표:

- 축제/해수욕장 등 이미 있는 public marker API를 지도 layer로 연결한다.

작업:

- layer toggle UI.
- `GET /public/festivals/map-markers`.
- `GET /public/beaches/map-markers`.
- marker cluster.
- public marker inspector.
- `지역 리포트` tab에서 근사 안내와 layer 진입점 제공.

완료 조건:

- 기본 상태에서는 public layer가 꺼져 있다.
- 사용자가 켠 layer만 지도에 표시된다.
- marker 클릭 후 선택 날짜에 일정 추가 가능하다.

### Phase G. Telegram/Gemini panel

목표:

- TREK의 tab 작업대 안에 TripMate 고유 기능을 배치한다.

작업:

- `TelegramPanel`.
- 여행별 대상 최대 3개 제한 표시.
- `GeminiResearchPanel`.
- 수동 실행 button과 실행 이력 표시.

완료 조건:

- Telegram/Gemini 기능은 지도 계획 흐름과 분리되어 있으면서 같은 workspace shell에서 접근 가능하다.
- secret 저장 정책을 UI 문구와 API에서 지킨다.

## 테스트 계획

### Frontend unit/component

필수:

- API parser가 잘못된 좌표 문자열을 거부한다.
- `TripsDashboard` empty/loading/error/success 렌더링.
- `TripTabs` active tab 변경.
- `DayPlanPanel` 날짜 선택과 item 선택 callback.
- `PlacePoolPanel` 검색 debounce와 후보 렌더링.
- `DraftPlaceSheet` 이름 없으면 저장 disabled.
- `TripKakaoMap` app key 누락 fallback.
- `getResponsiveMode`가 `360`, `390`, `768`, `1024`, `1280` 폭을 올바른 mode로 분류한다.
- `ResponsiveSheet`가 open 상태에서 header, scroll content, sticky footer, close action을 렌더링한다.
- mobile mode에서 DayPlanPanel과 PlacePoolPanel content가 중복 구현 없이 sheet wrapper 안에서 재사용된다.

### Backend unit

필수:

- 여행 생성 날짜 범위 검증.
- 날짜 범위에서 `trip_days` 생성.
- reorder 중복/누락 id 검증.
- Kakao 후보 정규화.
- Kakao timeout/quota/error 분류.
- reverse geocode PostGIS 우선순위.

### Backend integration

필수:

- 인증 없으면 `/trips`와 workspace endpoint가 `401`.
- 다른 사용자 여행 workspace는 `403` 또는 `404`.
- 장소 저장 시 좌표와 행정구역 code가 보존된다.
- `source_type=user_custom`은 provider ref 없이 저장된다.
- Kakao raw payload는 TTL cache에만 저장된다.

### Playwright E2E

필수 smoke:

- 로그인.
- `/trips` 진입.
- 새 여행 생성.
- 여행 상세 진입.
- Kakao 지도 표시 확인 또는 app key 누락 fallback 확인.
- 지도 클릭 custom place draft 열기.
- custom place 저장.
- Kakao 검색으로 장소 추가.
- 날짜 선택 후 marker badge 확인.
- 축제 layer toggle.
- mobile viewport에서 `일정`, `장소` sheet 열기.
- tablet viewport에서 panel이 한 번에 하나만 overlay로 열리는지 확인.
- desktop viewport에서 좌우 panel이 docked overlay로 열리고 collapse가 동작하는지 확인.
- viewport 변경 후 Kakao map fallback 또는 map surface가 비어 있지 않은지 확인.
- horizontal overflow 없음.

필수 viewport matrix:

```text
360x740
390x844
430x932
768x1024
1024x768
1280x800
1440x900
```

각 viewport 공통 assertion:

- `document.documentElement.scrollWidth <= document.documentElement.clientWidth`.
- `trip-workspace` 높이가 viewport 높이와 맞고 page body가 불필요하게 scroll되지 않는다.
- `trip-kakao-map` 또는 `map-unavailable`가 보인다.
- tab bar, mobile sheet, desktop panel이 서로 겹쳐 주요 button을 가리지 않는다.
- 긴 한국어 여행명/장소명/주소가 button이나 panel 밖으로 넘치지 않는다.

권장 test id:

```text
trips-dashboard
new-trip-button
trip-spotlight-card
trip-card-{tripId}
trip-workspace
trip-top-nav
trip-tab-plan
trip-kakao-map
map-unavailable
mobile-day-plan-button
mobile-places-button
responsive-sheet
responsive-sheet-close
tablet-overlay-panel
day-plan-panel
day-section-{dayId}
plan-item-{itemId}
place-pool-panel
place-search-input
place-search-candidate-{providerPlaceId}
draft-place-sheet
draft-place-name-input
draft-place-save
place-inspector
regional-report-panel
telegram-panel
gemini-panel
```

## 오류 상태 표준

| 상황 | UI |
| --- | --- |
| 인증 만료 | `/login` 이동. 가능하면 “다시 로그인해 주세요” |
| workspace 404 | 여행을 찾을 수 없음 화면 + `/trips` 이동 버튼 |
| workspace 403 | 접근 권한 없음 화면 + `/trips` 이동 버튼 |
| Kakao app key 누락 | 지도 영역에 설정 누락 안내. 다른 panel은 계속 사용 가능 |
| Kakao script load 실패 | 지도 영역에 재시도 버튼 |
| Kakao 검색 실패 | 우측 panel 검색 결과 영역에 retry |
| reverse geocode 실패 | 좌표만 표시하고 custom place 저장 가능 |
| 장소 저장 성공, 일정 추가 실패 | 장소 저장 완료 상태와 일정 추가 재시도 버튼 |
| provider quota 초과 | 검색 일시 불가 안내. 기존 저장 장소/일정 편집은 계속 가능 |
| Telegram target 3개 초과 | 추가 버튼 disabled + 최대 3개 문구 |
| Gemini key 미설정 | 실행 버튼 disabled + key 설정 안내 |

## 구현 중 하지 말 것

- TREK 파일을 복사해서 붙여넣지 않는다.
- Mapbox/Leaflet 의존성을 추가하지 않는다.
- Kakao REST key를 `NEXT_PUBLIC_*`로 만들지 않는다.
- Kakao 검색을 브라우저에서 REST API로 직접 호출하지 않는다.
- API 응답을 `as TripWorkspace`로 바로 캐스팅하지 않는다.
- 지도 click으로 바로 DB 저장하지 않는다. 사용자가 이름을 확인하고 저장해야 한다.
- 공공 layer를 기본으로 모두 켜지 않는다.
- route polyline을 실제 길찾기 결과처럼 표현하지 않는다.
- MCP 관련 파일이나 scaffold를 만들지 않는다.
- backend test, Alembic, Docker 검증을 Windows PowerShell에서 직접 실행하지 않는다.
- `window.innerWidth`를 render 중 직접 읽어 SSR hydration mismatch를 만들지 않는다.
- horizontal overflow를 전역 `overflow-x: hidden`만으로 덮지 않는다. 원인 component 폭을 고친다.
- mobile sheet용 component와 desktop panel용 component를 따로 복사해 상태/버그가 갈라지게 만들지 않는다.
- marker 색상을 `DESIGN.md`의 단일 Rausch 원칙으로 축소하지 않는다. marker 색상은 `airbnb-marker-palette.html`의 16색 팔레트가 우선이다.
- marker에 16색 팔레트 밖의 임의 색을 추가하지 않는다.
- Maki SVG를 runtime CDN/raw GitHub URL로 hotlink하지 않는다.
- Maki icon 사용을 이유로 Mapbox GL, Mapbox token, Mapbox tile provider를 추가하지 않는다.

## Codex 구현 체크리스트

작업 시작:

- `git status --short` 확인.
- 관련 문서와 skill 읽기.
- 실제 파일 구조 확인.
- 기존 user 변경을 되돌리지 않기.

프론트엔드:

- `npm install` 명령은 workspace 기준으로 실행.
- client component/server component 경계를 지키기.
- API parser 작성.
- `data-testid` 추가.
- `DESIGN.md` 기준 color/type/radius/shadow가 유지되는지 확인.
- marker 색상은 `airbnb-marker-palette.html`의 16색 팔레트와 `MARKER_PALETTE`에서만 나오는지 확인.
- Maki marker icon을 `@mapbox/maki`에서 복사해 `apps/web/public/map-icons/maki/`로 self-host.
- mobile viewport 확인.
- `360x740`, `390x844`, `768x1024`, `1024x768`, `1280x800`, `1440x900` viewport에서 반응형 smoke 확인.
- mobile sheet, tablet overlay, desktop docked panel이 같은 content component를 재사용하는지 확인.
- panel collapse/resize 뒤 Kakao map `relayout()` 동작 확인.
- horizontal overflow assertion 확인.
- `npm run lint`, `npm run typecheck` 실행.

백엔드:

- route는 얇게, 규칙은 service에 둔다.
- Pydantic schema로 request/response 고정.
- SQLAlchemy model/migration/test fixture 정합성 확인.
- KST timezone-aware datetime 유지.
- provider adapter timeout/error/cache 구현.
- `ruff`, `mypy`, `pytest`, migration 검증 실행.

문서:

- 새 API가 생기면 `docs/api/*.md` 갱신.
- Kakao Local cache/TTL/저장 정책은 `docs/data-sources.md` 갱신.
- 지도 UI 기준이 바뀌면 `docs/architecture/map-marker-design.md` 갱신.
- 구현 중 안전한 가정을 했다면 이 문서 또는 관련 execplan에 남긴다.

## 완료 정의

아래가 모두 만족되면 이 계획의 MVP 구현 완료로 본다.

- 로그인 후 `/trips`가 기본 작업 화면으로 열린다.
- `/trips`는 TREK의 dashboard 형태처럼 spotlight card와 compact trip list를 제공한다.
- `/trips/{tripId}`는 TREK의 planner 형태처럼 상단 nav, tab bar, 좌측 일정 panel, 중앙 Kakao 지도, 우측 장소 panel을 제공한다.
- 전반 UI의 색상, type scale, radius, shadow, card density, CTA 표현은 `DESIGN.md` 룩앤필을 유지한다.
- 지도 marker 색상은 `airbnb-marker-palette.html`의 16색 팔레트를 우선 적용한다.
- Kakao 지도는 `react-kakao-maps-sdk`로 구현되어 있다.
- 지도 marker glyph는 `@mapbox/maki`에서 내려받아 self-host한 SVG를 사용한다.
- marker는 16색 팔레트 색상 + Maki icon을 함께 사용하고, 선택/active 상태는 ring/scale/z-index/badge로 명확히 표현한다.
- Kakao app key 누락/로드 실패 상태가 오류 없이 표시된다.
- 지도 클릭 custom place 추가가 가능하다.
- Kakao 검색 후보 선택으로 장소 저장이 가능하다.
- 선택 날짜가 있을 때 장소를 일정 item으로 추가할 수 있다.
- marker/list/inspector selection이 동기화된다.
- public 축제 또는 해수욕장 layer 중 하나 이상이 toggle로 표시된다.
- mobile에서 일정/장소/inspector sheet가 열리고 horizontal overflow가 없다.
- tablet에서 panel이 한 번에 하나만 overlay로 열려 map 가시 폭을 보존한다.
- desktop/wide에서 좌우 panel이 docked overlay로 열리고 collapse 또는 resize 후 Kakao map이 깨지지 않는다.
- 필수 viewport matrix에서 tab bar, panel, sheet, 지도 control, 긴 한국어 텍스트가 서로 겹치지 않는다.
- provider raw response 장기 저장 금지, Telegram 3개 제한, Gemini 수동 실행 원칙이 깨지지 않는다.
- 관련 lint/typecheck/test가 실행됐고 결과가 최종 보고에 기록됐다.

## 남은 제품 결정

- 로그인 후 기본 경로는 이 문서에서 `/trips`를 권장한다. 다른 경로를 원하면 router 구현 전 확정한다.
- `파일/메모` tab을 MVP에 넣을지 후속으로 둘지 결정한다. 현재는 후속/disabled 권장.
- Kakao Local API cache TTL은 86400초를 권장하지만, provider 정책 검토 후 `docs/data-sources.md`에 최종 확정한다.
- 일정 연결 polyline은 직선 연결로 시작한다. 실제 길찾기 provider는 별도 의사결정 후 붙인다.
- 여행 참여자 권한 테이블이 완성되기 전에는 owner-only 편집으로 시작할지, 현재 구현된 권한 범위까지 확장할지 구현 시작 시 확인한다.
