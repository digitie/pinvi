# resume.md

## 현재 상태

**Sprint 2 핵심 DoD 마감 완료** (2026-06-01). OAuth G-4 + Notice copy + 통합
테스트 27개 green. Sprint 1~3 + Sprint 4 PR-A(#15 CI 복원) / PR-B(#16 features
API scaffolding) 머지 완료. 통합 테스트 harness(PostGIS testcontainer)가
`apps/api/tests/integration` 에 박힘 — 이후 백엔드 검증의 기반. async alembic 의
DDL 미커밋 잠재 버그도 함께 수정(`alembic/env.py`). 진행 추적 문서 정합성은
`resume.md` + `tasks.md` + `journal.md` 교차 확인이 기준(codex 2026-06-01 정리).
**개발 환경 모델 ADR-024로 확정** — NTFS worktree=git source of truth(Windows
git.exe) / WSL ext4=일회용 테스트 미러. 셋업·검증·함정 절차는
`docs/dev-environment.md`(에이전트 공통).
**Geocoding ADR-025로 확정** — 사용자 대면 geocoding(주소/좌표/행정구역)은
`kraddr-geo` v2 REST API 직접 호출(`docs/integrations/kraddr-geo.md`), feature
데이터는 krtour-map OpenAPI HTTP 계약(ADR-026). 열린 결정 8건은
`docs/architecture/geocoding-open-decisions.md`(잠정값으로 진행).
**문서 충돌 정정** (2026-06-02 codex) — `agent-guide`, `local-dev`, `architecture`
등에 남아 있던 ADR-024 이전 WSL git 모델, ADR-015 이전 Kakao/marker-wrapper 표현,
ADR-025 이전 `kraddr.geo` in-process 검색 표현을 정정.
**T-062 운영 게이트 확인/적용** (2026-06-02 codex) — GitHub Actions secret은
`0`개가 의도된 상태다. `OPENAI_API_KEY`는 쓰지 않는다. `codex-pr-review` /
`codex-pr-monitor`는 외부 API 호출 없이 review reminder만 남기도록 변경. `main`에는
repository ruleset `main-pr-only`(id `17146781`)를 적용했다(PR 필수, squash-only,
linear history, force push/deletion 차단, bypass 없음). Classic branch protection은
없다. required status check는 path-filtered workflow가 docs-only PR을 막을 수 있어
aggregate gate 설계 뒤 적용한다.
**로컬 dev 포트 고정** (2026-06-02 codex) — API `9021`, Web `9022`, Dagster `9023`.
`scripts/dev-up.sh`가 해당 포트를 점유한 프로세스를 종료하고 같은 포트로 다시 올린다.
프론트 실행은 계속 WSL ext4 미러 기준이며, Playwright e2e만 Windows에서 실행한다.
**RustFS / Docker app 포트 고정** (2026-06-03 codex) — RustFS API `9003`, console
`9004`. `scripts/docker-app.sh`가 Docker app build/up/down/status/logs/smoke를
제공하고, 시작 전 API `9021`, Web `9022`, RustFS `9003`/`9004` 점유 항목을
정리한다. `scripts/docker-app-smoke-test.sh`는 호환 wrapper다.
**krtour-map 연동 포트 고정** (2026-06-03 codex) — `python-krtour-map` 독립
프로그램의 API는 `9011`, admin은 `9012`를 기준으로 문서화한다. TripMate가 직접
소유하지 않는 서비스이므로 실행/검증은 그쪽 저장소 런북이 권위다.
**krtour-map 최신 main 계약 반영** (2026-06-04 codex) — 최신 `python-krtour-map`
`main`의 `openapi.user.json` / `openapi.json`을 확인해 ADR-026을 추가했다.
TripMate ↔ krtour-map은 더 이상 함수 직접 호출이 아니라 OpenAPI HTTP 계약(API
`9011`, admin `9012`)이다. `feature` / `provider_sync` schema 소유권은 그대로
krtour-map에 있고, TripMate는 `feature_id` + snapshot만 저장한다.
**KASI 특일/출몰시각 계약 추가** (2026-06-04 codex) — `python-kasi-api`를 통해
특일 계열 5개 dataset을 하루 1회, 과거 6개월~미래 18개월 범위로 upsert한다.
삭제는 없다. POI 생성 시에는 좌표와 방문일로 "위치별 해달 출몰시각 정보조회"를
1회 호출해 `app.trip_poi_rise_sets`에 저장한다.
**T-067 KASI 구현 완료** (2026-06-05 codex) — `apps/etl`에
`tripmate_kasi_special_days` asset과 `kasi_poi_rise_set_job`을 추가했고, API는 POI
생성 시 `app.trip_poi_rise_sets` 초기 row를 만든다. krtour-map 연계 없이
`python-kasi-api` + `DATA_GO_KR_SERVICE_KEY`만 사용한다.
**Production URL 확정** (2026-06-05 codex) — 운영 API는
`https://tripmateapi.digitie.mywire.org`, 운영 Web은
`https://tripmate.digitie.mywire.org`다. Google 승인된 JavaScript 원본은 Web origin,
OAuth redirect URI는 API origin의 `/auth/oauth/google/callback`이다. CORS는 Web
origin만 허용하고, 운영 cookie는 `TRIPMATE_ENVIRONMENT=production`으로 Secure를
강제한다.
**T-070 Sprint 2 잔여 마감** (2026-06-05 codex) — `email_queue` SKIP LOCKED
worker batch, 비밀번호 재설정 요청/확정 API, `api_call_log` httpx event hook
통합 테스트를 추가했다. `.github/workflows/api.yml`은 PR에서 `pytest
tests/integration -q`를 실행한다. Google OAuth client id는 네 TripMate worktree의
로컬 `.env`에 반영했다.

## 다음 한 작업

우선순위 후보(krtour-map 비의존 작업 우선):

1. **T-063** — `maplibre-vworld-js` 선행 PR 및 consumer sync 체크리스트 정리
2. **T-065** — 항상 실행되는 aggregate CI gate 설계 후 required status check 적용
3. **보류: Sprint 4 PR-B2** — krtour-map OpenAPI HTTP client → `/features/in-bounds`
   동작 + **위치 감사 자동 적재 e2e**(krtour-map client 의존):
   - `apps/api/app/clients/krtour_map.py` — `httpx.AsyncClient` lifespan
   - `apps/api/app/services/cluster_query.py` / `trip_view_builder.py`
4. **운영 후속** — 현재 `api` / `web` / `etl`은 path-filtered라 바로 required
   check로 걸지 않는다.

이후 **PR-C (프론트엔드)**:

- `apps/web/components/map/*` (MapView, ViewportFeatureLayer, ClusterLayer, ...)
- `apps/web/lib/{vworldMap,markerPalette,featureQueryKeys,locationAdapter}.ts`
- Trip 대시보드 + notice plan UI

이후 **PR-D (통합 / 라이브러리 PR sync / v0.1.0 release)** — 자세히는
`docs/sprints/SPRINT-4.md`.

## 릴리즈 로드맵

| 버전 | Sprint | ETA | 핵심 |
|------|--------|-----|------|
| `v0.1.0` | Sprint 4 | 다음 | 지도 + maplibre-vworld finalize + CI/CD 재활성 |
| `v0.2.0` | Sprint 5 | +1 | 실시간 + ETL + Grafana embed + Backup 1차 |
| `v1.0.0` | Sprint 6 | +2 | MCP 외부 인터페이스 + Backup 핫스왑 UI + Korean geofencing + Odroid+N150 |
| `v1.1.0+` | post-Sprint 6 | 후속 | PWA / 푸시 / tripmate-ai-companion (별 repo) |

## 진척도

- [x] git 흐름 정리 (v1 보존 / main 골격 재시작) — T-000
- [x] README / CLAUDE / AGENTS / SKILL — T-001
- [x] docs/architecture / agent-guide / dev-environment — T-002
- [x] docs/decisions (ADR-001 ~ ADR-010) — T-003
- [x] docs/journal / resume / tasks — T-004
- [x] docs/data-model / postgres-schema / test-strategy — T-005
- [x] docs/krtour-map-integration — T-006
- [x] docs/sprints/README + SPRINT-1 ~ SPRINT-6 — T-007
- [x] docs/spec/v8/ 6편 적용 노트 — T-008
- [x] docs/design/marker-palette + 루트 DESIGN.md / airbnb-marker-palette.html 복원 — T-009
- [x] docs/architecture/frontend.md (Next.js + Expo 공용 monorepo) — T-010
- [x] docs/architecture/user-location.md (Geolocation + expo-location) — T-011
- [x] docs/architecture/notice-plans.md (v1 추천 plan 도메인 이전) — T-012
- [x] v1 자산 전수 조사 + 매핑 매트릭스 (`docs/v1-to-v2-mapping.md`) — T-013
- [x] docs/api/ 11개 신규 (auth/users/trips/pois/features/notice-plans/storage/admin/public/regions/health/websocket + README + common) — T-014
- [x] docs/integrations/ 9개 신규 (resend/social-login/gemini/telegram/kakao-map/sentry/loki + README) — T-015
- [x] docs/runbooks/ 7개 신규 (local-dev/docker-app/etl/admin/file-storage/odroid-docker + README) — T-016
- [x] docs/compliance/ 4개 신규 (lbs-act/pipa/data-policy + README) — T-017
- [x] docs/conventions/ 6개 신규 (coding-style/database/testing/geospatial/normalization + README) — T-018
- [x] docs/architecture/ 5개 추가 (map-marker-design/youtube-travel-intelligence/mcp-tools/dagster-etl-bridge/api-contract) — T-019
- [x] AI agent 진입 절차 강화 (README/AGENTS/CLAUDE) — T-020
- [x] Sprint 4까지 PR 리뷰·수정·머지 운영 runbook + 5분 주기 PR 감시 — T-023
- [x] Sprint 1 진입 PR (apps + packages scaffolding) — T-030
- [x] GitHub Actions secret / branch protection 적용 상태 확인 — T-062
- [x] 최신 main 기준 문서 충돌 정정 — T-064
- [x] 최신 krtour-map/kraddr-geo/KASI 계약 문서 반영 — T-068
- [x] production API/Web URL + OAuth/CORS 보안 문서화 — T-069
- [x] KASI 특일/POI 출몰시각 Dagster 구현 — T-067
- [x] Sprint 2 잔여 마감(email queue/reset/api_call_log/integration CI) — T-070

## 다음 ADR 후보 (Sprint 진입 시 박음)

- (ADR-024 박힘: NTFS worktree = git source of truth + WSL ext4 일회용 테스트 미러)
- (ADR-025 박힘: 사용자 대면 geocoding은 kraddr-geo v2 REST 직접)
- (ADR-026 박힘: krtour-map OpenAPI HTTP 계약)
- ADR-027(후보): Sprint 4 프론트엔드 지도 계층 query key / viewport cache 전략
- ADR-028(후보): Sprint 4 진행 추적 문서 정규화 (`resume.md` / `tasks.md` / `journal.md`)

## 박힌 ADR

- ADR-001 ~ ADR-009: v2 시작 결정
- ADR-010: SPEC V8 채택
- ADR-011: Frontend 스택 + Next.js / Expo 공용 패키지 구조
- ADR-012: 사용자 위치 정보 획득 (Geolocation + expo-location)
- ADR-013: Notice plan 도메인 v1 → v2 이전 + 명명 분리
- ADR-014: v1 자산 전수 조사 + 누락 항목 일괄 반영 + 문서 일관성 정리
- ADR-015: 지도 클라이언트 변경 (Kakao Maps SDK → `maplibre-vworld-js`)
- ADR-016: AI 에이전트 도구 다중 지원 — `AGENTS.md` ↔ `CLAUDE.md` 동기 정책

## 운영 지시

- Sprint 4 완료 전까지 새 PR은 `docs/runbooks/pr-review-sprint4.md` 기준으로
  리뷰 → 상세 코멘트 → 코드 수정 → 기반 라이브러리 sync → 검증 → 머지를 반복한다.
- `.github/workflows/codex-pr-monitor.yml`이 외부 API key 없이 5분마다 열린 PR을
  감시하고, 최신 head SHA review reminder 마커가 없는 PR에 알림을 남긴다. 실제
  리뷰는 에이전트 또는 사람이 수행한다.

## 차단 사유 / 결정 대기

- required status check 적용은 항상 실행되는 aggregate CI gate 설계 이후
- Sprint 4 backlog 중 merge 완료 / 미완료 구분을 `tasks.md`에 재기록 필요
