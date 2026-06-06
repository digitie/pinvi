# SPRINT-4 — 지도 + 사용자 UI + v0.1.0 릴리즈

- **상태**: proposed
- **선행**: Sprint 3 DoD 완료 (Admin으로 데이터 흐름 검증 완료)
- **목표**: 사용자 대면 지도 UI 완성 + `python-krtour-map` OpenAPI read 활성화
  + **`maplibre-vworld-js` 기능 finalize → v0.1.0 릴리즈**
- **릴리즈**: `v0.1.0` (Sprint 4 종료 시 tag). 사용자 대면 지도/여행 흐름 첫
  사용 가능한 상태. 현재 릴리즈 게이트는 `docs/sprints/README.md`,
  `docs/tasks.md`, `docs/resume.md`를 함께 본다.
- **DoD**:
  - 지도 어댑터 (`maplibre-vworld-js`) 통합 — VWorld + MapLibre GL JS (ADR-015)
  - viewport 기반 feature 로딩 + 클러스터링 (zoom < 7/11/14 단계별)
  - POI D&D + 양방향 패널 (`useSelectedPoiStore`)
  - 16색 팔레트 + maki 아이콘 (`apps/web/lib/markerPalette.ts`)
  - 우클릭 메뉴 4종 + 마커 우클릭 메뉴 3종
  - Trip 대시보드 (미래/과거 아코디언, 동반자 아바타)
  - krtour-map OpenAPI HTTP client lifespan 통합 — `GET /features/in-bounds`가
    krtour-map API 호출
  - `apps/api/app/clients/krtour_map.py` HTTP client 활성화
  - **GitHub Actions CI/CD 재활성화** (ADR-021) — Sprint 1~3 동안 비활성이었음.
    api/web/etl workflow + API key 없는 review reminder + lint/typecheck/test 게이트
    복원.
  - **`maplibre-vworld-js` 공통 기능 PR 머지 완료** — 2026-06-05 기준 완료
    (`maplibre-vworld-js` PR #37 + PR #46, merge `f1dd74b9`).
    `docs/integrations/maplibre-vworld.md` §6에 분류된 "라이브러리 PR 항목"
    모두 라이브러리에 머지된 후에만 v0.1.0 tag. TripMate 전용 항목은 본 저장소에
    구현.
  - `v0.1.0` git tag + GitHub Release notes.

## 산출물

### 백엔드

- `apps/api/app/clients/krtour_map.py` — krtour-map HTTP client lifespan
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
- 02-backend.md §5.4 (krtour-map OpenAPI 호출 패턴)
- 01-data.md §3 (라이브러리 위임 항목)
- `docs/architecture/frontend.md` (Next.js + Expo 공용 패키지 구조)
- `docs/architecture/user-location.md` §4.1 (지도 "내 위치로 이동" 버튼)
- `docs/architecture/notice-plans.md` (사용자 listing + copy 다이얼로그)

## 지도 호출량 / viewport 보호

- viewport debounce 250ms + AbortController 취소
- 동일 bounding box + zoom 1분 캐시 (TanStack Query)
- VWorld tile/API 호출은 도메인 등록 + 브라우저 HTTP 캐싱 정책을 따른다.
- 길찾기는 Sprint 6 일정 최적화에서 OR-Tools 직선 거리 또는 라이브러리 기능으로
  분리한다.
- 일 호출 한도 도달 시 fallback: PostGIS 직선 거리 표시

## 종료 체크리스트

- [ ] DoD 모두 통과
- [ ] 사용자가 PC와 모바일에서 가입 → 여행 생성 → POI 추가 → 지도 확인 가능
- [ ] `python-krtour-map` 통합 e2e 통과
- [x] **`maplibre-vworld-js` 라이브러리 PR 모두 머지** (§5) — PR #37 구현 +
  PR #46 카탈로그 정합화 완료
- [ ] **GitHub Actions CI/CD 모든 workflow green** (ADR-021)
- [ ] `docs/journal.md` Sprint 4 종료 엔트리
- [ ] `docs/resume.md` "다음 한 작업" → Sprint 5
- [ ] **`v0.1.0` git tag 생성 + GitHub Release notes 작성** (§6)

## 5. `maplibre-vworld-js` 라이브러리 PR / TripMate 전용 분류

본 Sprint의 v0.1.0 게이트는 라이브러리 ↔ TripMate 책임 분리에 달려 있다.

### 5.1 라이브러리 PR 항목 (공통 기능, `maplibre-vworld-js`에 박는다)

`docs/integrations/maplibre-vworld.md` §6.1~§6.9에 카탈로그. v0.1.0 전까지
라이브러리에 PR 후 머지 완료:

- viewport 이벤트 emitter (§6.1)
- 사용자 위치 marker primitive (§6.2)
- 우클릭 메뉴 hook (§6.3)
- Place / Price / Weather marker generic props 확장 (§6.4)
- Popup / Tooltip primitive (§6.5)
- 카메라 / 애니메이션 선언형 API (§6.6)
- 거리 측정 helper (§6.7)
- 좌표 validation (§6.8)
- SSR / hydration 안정화 (§6.9)

**상태 (2026-06-05)**: 라이브러리 구현 PR #37과 카탈로그 정합화 PR #46이 모두
머지되어 선행 라이브러리 조건은 완료다. 남은 작업은 TripMate frontend PR-C에서
`maplibre-vworld` dependency pin, 실제 import, 지도 e2e를 처리하는 것이다.

**판정 기준**: "어떤 지도 앱에서도 쓸 수 있는 일반 기능"이면 라이브러리. TripMate
도메인 (16색 팔레트 매핑 / POI dnd 비즈니스 룰 / Notice plan copy) 이면 TripMate.

### 5.2 TripMate 전용 (라이브러리에 박지 않는다)

- 16색 팔레트 → 카테고리 매핑 (`apps/web/lib/markerPalette.ts` + `app.category_mappings`)
- POI D&D 비즈니스 룰 (LexoRank reorder, optimistic lock)
- Notice plan copy 다이얼로그
- Trip 대시보드 UI
- 사용자 동의 확인 후 위치 권한 요청 흐름 (`useUserLocation` + 4 분리 동의)
- `feature_link_broken_at` 처리 (라이브러리 위임된 feature가 사라졌을 때)

### 5.3 책임 경계 점검 절차

본 Sprint 중간 (50% 시점)에 사용자 + AI agent가 함께 카탈로그를 훑고
재분류 — "이건 사실 공통 기능 아닌가?" 항목은 5.2에서 5.1로 이동 후 라이브러리
PR 생성.

## 6. v0.1.0 릴리즈 절차

1. Sprint 4 DoD + 종료 체크리스트 모두 통과
2. `maplibre-vworld-js` 신규 버전 npm 또는 git tag 발행 (라이브러리 측 PR 머지 후)
3. TripMate `package.json` `maplibre-vworld` 버전 pin 갱신
4. `pnpm install` / `npm install` + lockfile 갱신 commit
5. `CHANGELOG.md` 작성 — 사용자 대면 기능 위주
6. `git tag -a v0.1.0 -m "v0.1.0 — 지도 + 여행 + Admin 기본기능"`
7. `git push origin v0.1.0`
8. GitHub Releases 생성 — CHANGELOG 본문 첨부
9. `docs/journal.md`에 v0.1.0 출시 엔트리
10. `docs/resume.md` "현재 상태" → "v0.1.0 출시 완료. Sprint 5 진입 대기"

## 7. GitHub Actions CI/CD 재활성화 (ADR-021)

Sprint 1~3 동안 사용자 지시로 비활성이었음 (PR #10 직전 변경). 본 Sprint 시작과
함께 부활.

### 7.1 복원 대상 workflow

`.github/workflows/` 신규 / 복원:

- `api.yml` — `apps/api` ruff + mypy --strict + pytest -q
- `web.yml` — `apps/web` lint + typecheck + 단위 테스트
- `etl.yml` — `apps/etl` ruff + mypy + dagster definitions validation (Sprint 5에 정식 활성)
- `codex-pr-review.yml` — PR review reminder 트리거 (`docs/runbooks/pr-review-sprint4.md`)
- `codex-pr-monitor.yml` — 5분 주기 PR 감시 + review reminder

### 7.2 운영 룰

- PR은 repository ruleset `main-pr-only`에 따라 squash PR로만 머지한다.
- required status check는 T-065 이후 `Aggregate CI gate` 하나만 적용한다.
  `api` / `web` / `etl`은 path-filtered workflow로 유지하고, aggregate gate가 변경
  파일에 따라 필요한 check만 기다린다.
- workflow 실패는 머지 차단 — fix 후 재시도. `--no-verify` / hook 우회 금지
  (`AGENTS.md` Git Safety Protocol)
