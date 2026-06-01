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
데이터는 krtour-map 함수 호출 유지. 열린 결정 8건은
`docs/architecture/geocoding-open-decisions.md`(잠정값으로 진행).

## 다음 한 작업

우선순위 후보:

1. **Sprint 2 잔여 마감** (`docs/sprints/SPRINT-2.md` "잔여" 절):
   - `email_queue` SKIP LOCKED worker + 비밀번호 재설정 메일 흐름
   - `api_call_log` 미들웨어 통합 테스트
   - CI(`api.yml`)에 `tests/integration` 스텝 추가 검토
2. **Sprint 4 PR-B2** — `python-krtour-map` 실 client 주입 → `/features/in-bounds`
   동작 + **위치 감사 자동 적재 e2e**(Sprint 2 잔여 1건, krtour client 의존):
   - `apps/api/app/etl_bridge/krtour_map.py` — `AsyncKrtourMapClient` lifespan
   - `apps/api/app/services/cluster_query.py` / `trip_view_builder.py`
3. **운영 확인** — GitHub Actions secret(`docs/runbooks/secrets.md`) / branch
   protection(`.github/workflows/README.md`) 실제 적용 상태 점검.

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
- [x] Sprint 4까지 PR 리뷰·수정·머지 운영 runbook + 자동 리뷰 프롬프트 + 5분 주기 PR 감시 — T-023
- [x] Sprint 1 진입 PR (apps + packages scaffolding) — T-030

## 다음 ADR 후보 (Sprint 진입 시 박음)

- (ADR-024 박힘: NTFS worktree = git source of truth + WSL ext4 일회용 테스트 미러)
- (ADR-025 박힘: 사용자 대면 geocoding은 kraddr-geo v2 REST 직접)
- ADR-026(후보): 기능 read API와 `python-krtour-map` 실제 client readiness 경계 명문화
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
- `.github/workflows/codex-pr-monitor.yml`이 5분마다 열린 PR을 감시하고, 최신 head
  SHA 리뷰 마커가 없는 PR을 다시 리뷰한다.

## 차단 사유 / 결정 대기

- GitHub secret / branch protection의 실제 적용 상태 미확인
- Sprint 4 backlog 중 merge 완료 / 미완료 구분을 `tasks.md`에 재기록 필요
