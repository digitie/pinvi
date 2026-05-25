# SPRINT-4 — 지도 + 사용자 UI

- **상태**: proposed
- **선행**: Sprint 3 DoD 완료 (Admin으로 데이터 흐름 검증 완료)
- **목표**: 사용자 대면 지도 UI 완성 + `python-krtour-map` 라이브러리 read 활성화
- **DoD**:
  - 지도 어댑터 (`maplibre-vworld-js`) 통합 — VWorld + MapLibre GL JS (ADR-015)
  - viewport 기반 feature 로딩 + 클러스터링 (zoom < 7/11/14 단계별)
  - POI D&D + 양방향 패널 (`useSelectedPoiStore`)
  - 16색 팔레트 + maki 아이콘 (`apps/web/lib/markerPalette.ts`)
  - 우클릭 메뉴 4종 + 마커 우클릭 메뉴 3종
  - Trip 대시보드 (미래/과거 아코디언, 동반자 아바타)
  - `python-krtour-map` `AsyncKrtourMapClient` lifespan 통합 — `GET
    /features/in-bounds`가 라이브러리 호출
  - `apps/api/app/etl_bridge/krtour_map.py` DI helper 활성화

## 산출물

### 백엔드

- `apps/api/app/etl_bridge/krtour_map.py` — `AsyncKrtourMapClient` lifespan
- `apps/api/app/api/v1/features.py`
  - `GET /features/in-bounds?bounds=&zoom=&kinds[]=`
  - `GET /features/{id}`
  - `GET /features/{id}/weather` (KMA 시간축 + sources)
  - `GET /features/nearby?lat=&lng=&radius_m=&kinds[]=`
  - `POST /features/requests`
  - `GET /search`
- `apps/api/app/services/cluster_query.py` — zoom별 `bjd_lookup` 또는
  `ST_ClusterDBSCAN` 그루핑
- `apps/api/app/services/trip_view_builder.py` — `app` ↔ `feature` join

### 프론트엔드

- `apps/web/app/(app)/page.tsx` (Trip 대시보드)
- `apps/web/app/(app)/trips/[tripId]/page.tsx` (지도보기 메인)
- `apps/web/app/(app)/trips/[tripId]/share/[token]/page.tsx`
- `apps/web/components/map/{MapView,ViewportFeatureLayer,ClusterLayer,PoiMarkerLayer,SelectedPoiPopup,RightClickMenu,SearchOverlay}.tsx`
- `apps/web/components/poi/{PoiList,PoiCard,PoiActionsMenu}.tsx`
- `apps/web/components/trip/{TripHeader,CompanionAvatars,DayList,DayCard,DayActionsMenu}.tsx`
- 사용자 notice plan UI (`docs/architecture/notice-plans.md`):
  - `apps/web/app/(app)/notice-plans/page.tsx` (카테고리 탭 + 카드 그리드)
  - `apps/web/app/(app)/notice-plans/[planId]/page.tsx` (상세 + 지도 + day별 POI)
  - `apps/web/components/notice/CopyNoticePlanDialog.tsx` (POI 선택 + 새 trip/기존 trip 선택)
- `apps/web/components/map/MyLocationButton.tsx` (지도 "내 위치로 이동", `useUserLocation`)
- `apps/web/lib/{vworldMap,markerPalette,featureQueryKeys,locationAdapter}.ts`
- `apps/web/stores/{tripStore,mapViewportStore,selectedPoiStore}.ts`
- `apps/web/public/maki/*.svg` (vendor 8 ~ 14개)

### 테스트

- `tests/integration/test_features_in_bounds.py` (zoom별 클러스터링)
- `tests/integration/test_features_weather.py` (KMA sources 배열)
- `apps/web/tests/map-poi-flow.test.mjs` (Playwright — viewport / D&D / 우클릭)

### ADR

- ADR-015 (이미 박힘): 지도 클라이언트 `maplibre-vworld-js` + wrapping 금지 (TripMate는 직접 사용 + 부족 기능은 라이브러리에 PR)
- ADR-NNN: viewport 클러스터링 전략 (서버측 + 디바운스 250ms)
- ADR-NNN: feature_snapshot 동기화 정책 (라이브러리 변경 시 cache 갱신)

## SPEC V8 매핑

- 03-frontend.md 전체 (I-1 ~ I-7)
- 02-backend.md §5.4 (H-4 Feature/지도 API)
- 02-backend.md §6 (라이브러리 호출 패턴)
- 01-data.md §3 (라이브러리 위임 항목)
- `docs/architecture/frontend.md` (Next.js + Expo 공용 패키지 구조)
- `docs/architecture/user-location.md` §4.1 (지도 "내 위치로 이동" 버튼)
- `docs/architecture/notice-plans.md` (사용자 listing + copy 다이얼로그)

## 카카오맵 일 호출 한도 보호

- viewport debounce 250ms + AbortController 취소
- 동일 bounding box + zoom 1분 캐시 (TanStack Query)
- 카카오 모빌리티 길찾기는 일정 최적화에서만 (Sprint 6)
- 일 호출 한도 도달 시 fallback: PostGIS 직선 거리 표시

## 종료 체크리스트

- [ ] DoD 모두 통과
- [ ] 사용자가 PC와 모바일에서 가입 → 여행 생성 → POI 추가 → 지도 확인 가능
- [ ] `python-krtour-map` 통합 e2e 통과
- [ ] `docs/journal.md` Sprint 4 종료 엔트리
- [ ] `docs/resume.md` "다음 한 작업" → Sprint 5
