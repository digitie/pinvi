# SPEC V8 #3 — 프론트엔드 · 실시간 (TripMate 적용 노트)

원본: `spec_v8_3_frontend.docx` (I 프론트엔드 + J 실시간).

> 본 노트는 SPEC V8의 frontend 결정 채택을 정리한다. **본 저장소의 본격
> Frontend 아키텍처는 [`docs/architecture/frontend.md`](../../architecture/frontend.md)**:
> Next.js 15 + shadcn/ui + Tailwind + React Hook Form + Zod + Zustand +
> TanStack Query 스택, DESIGN.md / `airbnb-marker-palette.html` 디자인 톤,
> Next.js / Expo 공용 `packages/*` monorepo 구조, Expo 대응 로드맵을 다룬다.
> 사용자 위치 정보는 [`docs/architecture/user-location.md`](../../architecture/user-location.md).

## 1. 스택 채택

| 계층 | 채택 |
|------|------|
| 프레임워크 (웹) | **Next.js 15** (App Router) + **React 19** |
| 프레임워크 (모바일, v2) | **Expo SDK 53+** (React Native + Expo Router) |
| UI 컴포넌트 (웹) | **shadcn/ui** + Radix Primitives (Tailwind 기반 vendoring) |
| 스타일 | **Tailwind CSS 3.4+** (NativeWind로 모바일 공유) |
| 상태(클라이언트) | **Zustand** (공용 `packages/state`) |
| 상태(서버) | **TanStack Query v5** (공용 `packages/api-client`) |
| 폼 | **React Hook Form** + **Zod** resolver (schema는 공용 `packages/schemas`) |
| D&D (웹) | dnd-kit |
| 지도 (웹) | **`maplibre-vworld-js`** (VWorld + MapLibre GL JS) — ADR-015로 SPEC V8 A-1 #4 (Kakao Maps SDK) superseded |
| 마커 | 16색 팔레트 P-01~P-16 + maki 아이콘 (`docs/design/marker-palette.md`) |
| 디자인 톤 | 본 저장소 루트 `DESIGN.md` + `airbnb-marker-palette.html` (단일 기준) |

자세한 스택·디자인 토큰·공용 패키지 구조는 [`docs/architecture/frontend.md`](../../architecture/frontend.md).

`apps/web` 구조 (Sprint 1 진입 PR로 박음):

```
apps/web/
├── package.json
├── next.config.mjs
├── app/
│   ├── (auth)/           # 비로그인
│   │   ├── login/
│   │   ├── signup/
│   │   ├── verify-email/
│   │   ├── reset-password/
│   │   └── oauth/callback/route.ts
│   ├── (app)/            # 로그인 필요
│   │   ├── layout.tsx
│   │   ├── page.tsx                  # 여행 목록 (미래/과거 아코디언)
│   │   ├── trips/
│   │   │   ├── new/page.tsx
│   │   │   └── [tripId]/
│   │   │       ├── page.tsx          # 지도보기 메인
│   │   │       ├── share/[token]/page.tsx
│   │   │       └── settings/page.tsx
│   │   └── profile/page.tsx
│   ├── admin/            # 역할 가드
│   │   ├── users/
│   │   ├── trips/
│   │   ├── features/
│   │   ├── pois/
│   │   ├── etl/
│   │   ├── api-calls/
│   │   ├── emails/
│   │   ├── audit/
│   │   ├── feature-requests/
│   │   ├── category-mapping/
│   │   ├── dedup-review/
│   │   ├── integrity/
│   │   ├── debug/
│   │   └── seed/         # dev only
│   └── shared/
│       ├── api-base.ts
│       ├── query-provider.tsx
│       ├── query-keys.ts
│       ├── stores.ts                 # zustand
│       └── file-upload-panel.tsx
├── components/
│   ├── map/
│   ├── poi/
│   ├── admin/{DataTable,FilterBar,KeyValueGrid,JsonViewer}.tsx
│   └── marker/                       # 16색 팔레트 사용
├── lib/
│   ├── vworldMap.ts
│   ├── websocket.ts
│   └── markerPalette.ts
├── stores/
│   └── tripStore.ts
└── tests/
```

## 2. 지도보기 화면 (I-2)

My Maps 스타일: 데스크탑 좌측 사이드 패널 + 지도. 모바일 bottom-sheet (TREK 패턴).

컴포넌트 트리:

```
<TripMapPage>
├── <TopBar>
│   └── <LoginAvatar /> <SearchButton /> <MoreMenu />
├── <SidePanel>                       # 모바일은 bottom-sheet
│   ├── <TripHeader>
│   │   ├── <CompanionAvatars>        # 가입O=녹색 / 가입X=주황 / 리더=체크
│   │   └── <TripActionsMenu />
│   └── <DayList>                     # 아코디언
│       └── <DayCard>
│           ├── <DayActionsMenu />
│           └── <PoiList draggable>   # dnd-kit
│               └── <PoiCard>
└── <MapView>
    ├── <ViewportFeatureLayer>
    ├── <ClusterLayer>
    ├── <PoiMarkerLayer />
    ├── <SelectedPoiPopup />
    ├── <RightClickMenu />            # I-7
    └── <SearchOverlay />
```

## 3. 상태 관리 (I-3)

| 스토어 | 도구 | 관리 |
|--------|------|-----|
| 서버 상태 | TanStack Query | trips/features/POIs/weather. 캐시·invalidate |
| UI 상태 | Zustand | 선택 day/POI, 사이드 패널, 모달 큐 |
| 지도 viewport | Zustand 별도 | center/zoom/bounds → feature fetch trigger |
| 실시간 | WebSocket → invalidate | 이벤트 수신 시 해당 query key |
| 폼 | React Hook Form + Zod | 회원가입 / POI / 공유 설정 |

## 4. viewport 기반 로딩 (I-4)

zoom별 클러스터링 — 서버측 PostGIS `ST_ClusterDBSCAN` 또는 `bjd_lookup` 단위
그루핑:

- zoom < 7: `sido`
- zoom < 11: `sigungu`
- zoom < 14: `eupmyeondong`
- zoom ≥ 14: 개별 마커

디바운스 250ms + 이전 요청 AbortController 취소 + 1분 캐시.

## 5. 양방향 연동 (I-5)

`useSelectedPoiStore` (zustand) 단일 source of truth:

- 패널 카드 hover → 마커 강조 (scale 1.3x + 그림자)
- 패널 카드 클릭 → `flyTo(coord, zoom: 15)` + popup
- 마커 클릭 → 패널 카드 스크롤·하이라이트

## 6. 16색 마커 팔레트 (I-6)

`lib/markerPalette.ts`에 `MARKER_PALETTE` 상수. 자세히는
`docs/design/marker-palette.md`.

P-01 ~ P-16 + `label_color` + `name` (한글). 카테고리 ↔ maki 아이콘 + 기본 색상
매핑 표 (음식점=P-01 / 주유소=P-02 / 사찰=P-03 / 편의점=P-04 / 골프=P-05 /
청록 / 해수욕장=P-07 / 파랑 / 남색=박물관 / 보라=숙박 / 자홍=관광/event /
갈색=카페 / 회색 / 검정=공지 / 주홍=휴게소 / 청색=병원).

매핑은 DB(`app.category_mappings`)에 두고 Admin이 수정. UI는 DB 매핑 + library
default 상수 fallback.

## 7. 우클릭 메뉴 (I-7)

지도 우클릭:

- 계획에 추가 ▸ Day 선택 sub-menu
- 주변 관광지 보기 (10km)
- 이 지역 날씨 예보 보기
- feature 추가 요청

마커 우클릭 (제안):

- 마커 색/아이콘 변경
- 이 POI 메모 편집
- 이 POI 삭제

## 8. 스마트 정렬 미리보기 (I-8)

`POST /trips/{id}/days/{day_index}/optimize` 호출 → 미리보기 다이얼로그:

- 변경 전/후 순서 + 거리/시간 차이
- 옵션: 첫/마지막 POI 고정, 영업시간 고려
- [취소] / [적용] — 적용 시 fractional indexing 재산출 + WebSocket broadcast
- 적용 후 5초 "되돌리기" 토스트 (undo)

## 9. 실시간 동기화 (J장)

### 9.1 채널 (J-1)

`ws://api/v1/ws/trips/{trip_id}?token={jwt}`

서버 → 클라이언트:

```json
{
  "type": "poi.created",
  "trip_id": "...",
  "actor_user_id": "...",
  "ts": "2026-05-11T12:34:56+09:00",
  "version": 42,
  "payload": { ... }
}
```

클라이언트 → 서버:

- `presence.heartbeat`
- `presence.cursor` (옵션)

### 9.2 충돌 해결 (J-2)

| 전략 | 적용 |
|------|------|
| Last-Write-Wins (필드 단위) | POI memo/budget/marker_color 단순 필드 |
| Optimistic Lock (POI 단위) | `version` 컬럼 + `If-Match`. 409 → 다이얼로그 |
| Fractional Indexing | `sort_order` — D&D 충돌 안 남 (E-6 COLLATE "C" 필수) |
| Presence | 5초 heartbeat / 30초 무응답 offline |

### 9.3 국가유산 area UI (K)

`feature.kind=area` polygon/multipolygon 우선 렌더, point centroid 보조.
국가유산 상세는 명칭/유형/지정일/관리자/설명/source trace/RustFS 이미지 gallery.

## 10. 카카오맵 SDK 약관 주의

- 오프라인 캐싱 약관상 금지
- Service Worker Network Only 강제 (v1 PWA 미포함)
- 일 호출 한도는 카카오 개발자 콘솔 확인 후 ETL viewport 디바운스 / 캐시 조정

## 11. Sprint 매핑

| SPEC V8 항목 | Sprint | 본 저장소 산출물 |
|------|--------|------------------|
| `apps/web` scaffolding | Sprint 1 | `apps/web/package.json` + App Router skeleton |
| 로그인/가입/verify UI (G-2 와이어프레임) | Sprint 1 | `apps/web/app/(auth)/...` |
| Trip 대시보드 + 미래/과거 아코디언 (I-2) | Sprint 4 | `apps/web/app/(app)/page.tsx` |
| 지도 + maplibre-vworld-js (I-2 ~ I-5) | Sprint 4 | `apps/web/components/map/...` |
| 16색 팔레트 + maki (I-6) | Sprint 4 | `apps/web/lib/markerPalette.ts` |
| viewport 로딩 + 클러스터 (I-4) | Sprint 4 | `apps/web/components/map/ViewportFeatureLayer.tsx` |
| 우클릭 메뉴 (I-7) | Sprint 4 | `apps/web/components/map/RightClickMenu.tsx` |
| Admin 콘솔 (M-3) | Sprint 3 | `apps/web/app/admin/...` |
| WebSocket 클라이언트 (J-1) | Sprint 5 | `apps/web/lib/websocket.ts` |
| 스마트 정렬 UI (I-8) | Sprint 6 | `apps/web/components/poi/OptimizeDialog.tsx` |

## 12. 관련 문서

- `docs/architecture.md` §2.2 프론트
- `docs/design/marker-palette.md`
- `docs/spec/v8/02-backend.md` (API 쌍)
- `docs/spec/v8/04-admin.md` (Admin UI)
