# resume.md

## 다음 한 작업 (2026-06-06 감사 후)

문서·구현 정합성 전수 감사 완료 — `docs/audit/2026-06-06-doc-impl-audit.md`.
사용자 결정 DEC-01~10 확정(`docs/decisions-needed-2026-06-06.md`). **다음**:
krtour-map 비의존 작업 루프 기준으로 T-143 지도/소셜 문서 정정을 처리한다.
feature read는 krtour HTTP 서비스 준비에 의존(T-066/DEC-06) — v0.1.0 게이트도 여기
대기.

**T-210c(ADR-045 Phase 6) TripMate 부분 완료** (2026-06-06): `apps/etl`은 `app`
schema 소유 job만 보유해 이관할 feature provider Dagster 스켈레톤이 없음 확인 +
`dagster-etl-bridge.md`/`runbooks/etl.md` phantom 스켈레톤 정합 + asset `__init__`
경계 가드. 남은 T-210d=T-066, T-210e는 krtour HTTP/OpenAPI 확정 후.

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
**T-063 maplibre consumer sync 완료** (2026-06-05 codex) — `maplibre-vworld-js`
PR #46(`docs/consumer-feature-catalog.md` 정합화, `build-and-test` green, merge
`f1dd74b9`)를 머지했고, TripMate §6/§11.1 snapshot과 Sprint 4 라이브러리 선행
조건을 완료 처리했다. 실제 `maplibre-vworld` dependency pin/import/e2e는 PR-C
frontend 구현에서 처리한다.
**T-065 aggregate CI gate 적용** (2026-06-05 codex) — 모든 PR에서 실행되는
`Aggregate CI gate` workflow를 추가했다. `api` / `web` / `etl`은 path filter를
유지하고, aggregate gate가 변경 파일 기준으로 필요한 check만 기다린다. `main-pr-only`
ruleset required status check는 `Aggregate CI gate`로 적용한다.
**T-071 Google OAuth 로그인 UI 연결** (2026-06-05 codex) — 로컬
`TRIPMATE_GOOGLE_OAUTH_CLIENT_ID` 반영 후 로그인 화면에서 `/auth/oauth/providers`를
조회해 Google 버튼을 활성화한다. `/auth/oauth/google/start`는 envelope 응답으로
authorize URL을 반환하고, PKCE verifier는 DB 평문 저장 없이 `state` + 서버 secret으로
재생성한다.
**T-072 Google OAuth 실패 UX** (2026-06-05 codex) — Google callback 실패는 API JSON
오류 대신 Web `/login?error=...`로 303 redirect한다. 로그인 화면은 `error` code를
고정 한국어 메시지로 매핑하고, 임의 `error_description`은 화면에 그대로 노출하지 않는다.
**T-073 Google OAuth profile 연결/해제 UI** (2026-06-05 codex) — `/auth/me`가
`has_password`와 `oauth_identities`를 반환하고, `/profile`에서 Google 연결 상태 확인,
연결 시작, 해제를 수행한다. 소셜-only 계정은 비밀번호 설정 전 Google 해제를 409로
차단한다.
**T-074 PR-C frontend 지도 shell** (2026-06-05 codex) —
`maplibre-vworld`를 `digitie/maplibre-vworld-js` commit `f1dd74b9...`의 GitHub
archive tarball로 pin하고
`/trips/map-shell`에서 `VWorldMap` / `ClusterLayer` / `MakiMarker` / `Popup`을
실제 import한다. feature 조회는 연결하지 않았고, Windows Playwright smoke에서
`/features/in-bounds`와 krtour-map API `9011` 미호출을 확인했다.
**T-075 Trip / notice plan 사용자 shell** (2026-06-05 codex) — krtour-map feature
조회 없이 공용 API client에 `/trips` / `/notice-plans` 사용자 endpoint를 추가하고,
Web `/trips`와 `/notice-plans` route, 사용자 navigation shell, 빈 상태, Trip 생성,
notice plan copy action을 연결했다. Windows Playwright smoke에서 `/features/*`와
krtour-map API `9011` 미호출을 확인했다.
**T-110 Admin Grafana iframe embed** (2026-06-05 codex) — `/admin/grafana`에
anonymous viewer용 Grafana iframe shell을 추가하고 `NEXT_PUBLIC_GRAFANA_URL`,
`NEXT_PUBLIC_GRAFANA_DASHBOARD_PATH`, Web `frame-src` CSP를 문서/환경변수와 맞췄다.
Grafana 컨테이너/provisioning 본체는 Sprint 5 인프라 작업으로 남겼다.
**T-109 한국 전용 geofencing FastAPI fallback** (2026-06-05 codex) —
`TRIPMATE_GEOFENCE_*` 환경변수와 `GeofenceMiddleware`를 추가했다. 기본 비활성이고,
활성 시 `CF-IPCountry` 기반으로 KR 외 요청을 451로 차단한다. health/docs 우회와
access token `roles` claim 기반 운영자 우회를 포함한다.
**T-115 Backup snapshot foundation** (2026-06-06 codex) — `scripts/backup-db.sh` /
`scripts/restore-db.sh`, `GET /admin/backup/snapshots`,
`POST /admin/backup/snapshot`, Web `/admin/backup` snapshot 목록/수동 trigger를
추가했다. 현재 범위는 Sprint 5 1차 snapshot foundation이며, 신규 DB/schema
cut-over와 `RestoreHotswapDialog`는 T-111로 유지한다.
**T-116 OAuth provider 범위 정리** (2026-06-06 codex) — 현재 OAuth provider는
Google만 활성이다. `/auth/oauth/providers`는 Google만 반환하고, Naver/Kakao는 미래
작업(T-122)으로 보류한다.
**T-117 회원가입 약관 동의** (2026-06-06 codex) — `POST /auth/register`가 필수
4종 동의(`tos`, `privacy`, `lbs_tos`, `location_collection`)를 요구하고,
가입 트랜잭션 안에서 `app.user_consents`에 저장한다. `/signup` 화면은 필수 전체
동의와 선택 `marketing` 동의를 제공하고, 필수 동의 전 제출을 막는다.
**T-118 Google OAuth 계정 매칭 UX** (2026-06-06 codex) — Google OAuth login은
같은 이메일의 로컬 계정을 자동 연결하지 않고 `OAUTH_ACCOUNT_LINK_REQUIRED`로
안내한다. profile link-mode 충돌은 `/profile`로 돌아와 사용자 메시지를 표시한다.
Naver/Kakao는 계속 T-122 미래 작업이다.
**T-119 회원 관리 Admin 보강** (2026-06-06 codex) — `/admin/users` 목록은 `q`
검색과 상태 필터를 함께 적용하고, 상세는 기본 이메일 마스킹 상태로 응답한다.
`reveal=true` + 사유가 있을 때만 원본 이메일을 반환하며 `user.reveal_pii` audit과
최근 audit 목록을 상세 UI에 표시한다.
**T-120 여행계획 Admin 목록/상세/상태 관리** (2026-06-06 codex) —
`/admin/trips` 목록은 `q` 검색, 상태/공개범위/owner 필터와 day/POI/companion/share
count를 제공한다. 상세는 companion/share metadata와 최근 audit을 표시하고, 상태
변경은 `access_reason` 필수 + `trip.update_status` audit으로 기록한다.
**T-121 POI Admin 목록/상세/연결 상태 관리** (2026-06-06 codex) —
`/admin/pois` 목록은 `q` 검색, `trip_id`, `has_broken_link` 필터와 owner 이메일
마스킹을 제공한다. 상세는 `feature_snapshot`, 일정/비용/메모/URL, 추가자 마스킹,
최근 audit을 표시한다. 연결 상태 변경은 TripMate 로컬 `feature_link_broken_at`만
수정하고 `poi.update_link_status` audit으로 기록한다. feature re-link는 krtour-map
client 준비 후로 유지한다.
**T-123 문서 정합 일괄 정정** (2026-06-06 codex) — README/API index의
`GET /search`·`/health/external` 누락을 보강하고, OAuth는 Google-only + Naver/Kakao
future provider 표현으로 맞췄다. share link URL은 `TRIPMATE_WEB_BASE_URL` 기반으로
수정했고, zoom 하한 5, dangling `release-plan.md` 링크, `python-kraddr-geo` 오타,
agent-guide 잔여 bullet/trailer를 정리했다.
**T-149 Gemini 책임 목록 정정** (2026-06-06 codex) — README/AGENTS/CLAUDE/SKILL과
`docs/integrations/README.md`에서 본 저장소의 현재 책임을 `AI companion 호출 계약`으로
표현했다. Gemini/Claude/Codex provider 구현은 ADR-020에 따라 별도
`tripmate-ai-companion` repo 책임이다.
**T-150 계획/추적 문서 정합화** (2026-06-06 codex) — Sprint 1/3/4/5 status를 최신
main 기준으로 맞추고, Sprint 5 ETL provider asset 계획을 krtour-map 책임으로 정정했다.
`resume.md`의 박힌 ADR 목록은 ADR-031까지 갱신했고, stale ADR 후보는 T-151/T-148
후속으로 재분류했다.
**T-151 미기록 ADR 백필** (2026-06-06 codex) — 인증 토큰(ADR-032), Admin
RBAC(ADR-033), Admin audit hash chain(ADR-034)을 구현 기준으로 박고, Sprint 문서의
남은 번호 미배정 placeholder를 번호 없는 후속 후보/구현 기준으로 정리했다.

## 다음 한 작업

우선순위 후보(krtour-map 비의존 작업 우선):

1. **보류: Sprint 4 PR-B2** — krtour-map OpenAPI HTTP client → `/features/in-bounds`
   동작 + **위치 감사 자동 적재 e2e**(krtour-map client 의존):
   - `apps/api/app/clients/krtour_map.py` — `httpx.AsyncClient` lifespan
   - `apps/api/app/services/cluster_query.py` / `trip_view_builder.py`
2. **다음 비의존 후보** — T-143 지도/소셜 문서 정정. Kakao 어댑터 표현 제거,
   Google-only 소셜 로그인 기준, kraddr-geo stack 문구를 최신 상태로 맞춘다.
3. **운영 후보** — T-111 Backup/Restore UI 핫스왑. snapshot foundation은 T-115에서
   완료됐고, 신규 DB/schema cut-over PoC가 필요하다.

Naver/Kakao OAuth는 현재 사용하지 않는다. 후속 provider 구현은 T-122로 보류.

이후 **PR-C (프론트엔드)**:

- `apps/web/components/map/*` (MapView, ViewportFeatureLayer, ClusterLayer, ...)
- `apps/web/lib/{vworldMap,markerPalette,featureQueryKeys,locationAdapter}.ts`
- Trip 대시보드 + notice plan UI — feature 조회 없는 shell 완료(T-075)

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
- [x] Google OAuth profile 연결/해제 UI — T-073
- [x] PR-C frontend 지도 shell dependency pin/import/e2e — T-074
- [x] Trip / notice plan 사용자 shell — T-075
- [x] Admin Grafana iframe embed — T-110
- [x] 한국 전용 geofencing FastAPI fallback — T-109
- [x] Backup snapshot foundation + `/admin/backup` 1차 UI — T-115
- [x] OAuth provider 범위 Google-only 정리 — T-116
- [x] 회원가입 약관 동의 화면 + `user_consents` 저장 보강 — T-117
- [x] Google OAuth 계정 매칭 / profile 연결 UX 보강 — T-118
- [x] 회원 관리 Admin 검색/상세 audit UX 보강 — T-119
- [x] 여행계획 Admin 목록/상세/상태 관리 — T-120
- [x] POI Admin 목록/상세/연결 상태 관리 — T-121
- [x] 문서 정합 일괄 정정 — T-123
- [x] Gemini 책임 목록 정정 — T-149
- [x] 계획/추적 문서 정합화 — T-150
- [x] 미기록 ADR 백필(auth-token/RBAC/audit-chain) — T-151

## 다음 ADR 후보

- T-148 이후 — Sprint 4 backend 재작성 과정에서 viewport cache / feature snapshot
  동기화 정책이 실제 구현 결정으로 필요하면 신규 ADR 작성
- Sprint 5 진입 시 — WebSocket broker, optimistic lock, TripMate Dagster `app` job,
  Loki/Grafana embed 정책이 구현 결정으로 필요하면 ADR-035부터 배정

## 박힌 ADR

- ADR-001 ~ ADR-009: v2 시작 결정
- ADR-010: SPEC V8 채택
- ADR-011: Frontend 스택 + Next.js / Expo 공용 패키지 구조
- ADR-012: 사용자 위치 정보 획득 (Geolocation + expo-location)
- ADR-013: Notice plan 도메인 v1 → v2 이전 + 명명 분리
- ADR-014: v1 자산 전수 조사 + 누락 항목 일괄 반영 + 문서 일관성 정리
- ADR-015: 지도 클라이언트 변경 (Kakao Maps SDK → `maplibre-vworld-js`)
- ADR-016: AI 에이전트 도구 다중 지원 — `AGENTS.md` ↔ `CLAUDE.md` 동기 정책
- ADR-017: CodeGraph 인덱스 + agent별 고정 worktree 운영
- ADR-018: 한국 전용 서비스 — geofencing 3중 안전망
- ADR-019: TripMate MCP 외부 인터페이스 서빙(read-only)
- ADR-020: T-107 Gemini AI Companion 별도 서비스 분리
- ADR-021: GitHub Actions CI/CD 재활성화
- ADR-022: Backup / Restore 핫스왑 정책
- ADR-023: 운영 하드웨어 확장 — Odroid M1S + N150 16GB 병행
- ADR-024: NTFS worktree = git source of truth + WSL ext4 일회용 테스트 미러
- ADR-025: 사용자 대면 geocoding은 `python-kraddr-geo` v2 REST API 직접 호출
- ADR-026: TripMate ↔ `python-krtour-map`은 최신 OpenAPI HTTP 계약으로 전환
- ADR-027: krtour-map 통합은 운영급 HTTP 서비스로 확정
- ADR-028: 정규 `feature_id` 포맷은 krtour-map `make_feature_id` 출력
- ADR-029: `notice_plans` 명칭 충돌 해소 — 큐레이션은 `curated_trip_plans`
- ADR-030: 외부 API 규약 정본
- ADR-031: POI delete 정책(soft) + `trip_day_pois.feature_id` nullable
- ADR-032: 인증 토큰 기준(access JWT + httpOnly cookie)
- ADR-033: Admin 권한은 `users.roles[]` + 서버 dependency
- ADR-034: Admin 감사 로그 append-only hash chain

## 운영 지시

- Sprint 4 완료 전까지 새 PR은 `docs/runbooks/pr-review-sprint4.md` 기준으로
  리뷰 → 상세 코멘트 → 코드 수정 → 기반 라이브러리 sync → 검증 → 머지를 반복한다.
- `.github/workflows/codex-pr-monitor.yml`이 외부 API key 없이 5분마다 열린 PR을
  감시하고, 최신 head SHA review reminder 마커가 없는 PR에 알림을 남긴다. 실제
  리뷰는 에이전트 또는 사람이 수행한다.

## 차단 사유 / 결정 대기

- required status check는 `Aggregate CI gate`로 적용
- Sprint 4 backlog 중 merge 완료 / 미완료 구분을 `tasks.md`에 재기록 필요
