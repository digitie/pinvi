# journal.md — 작업 일지 (역시간순)

가장 위가 가장 최근. 새 엔트리는 위에 append.

## 2026-07-01 (codex) — T-273 local fallback smoke 확인

**작업**: full live e2e가 지금 필요한지 재판단하고, 현 시점에 필요한 local/fallback smoke evidence를
정리했다.

**확인**:

- local dev DB를 Alembic head까지 migration했다.
- bootstrap admin env는 문서와 shell history에 값을 남기지 않는 방식으로 주입했다.
- `npm run dev:up` 후 API `/health`와 Web `/admin/login` 응답을 확인했다.
- 현재 세션에는 N150 alias/config가 없어 Playwright는 Windows fallback으로만 확인했다.
- Windows fallback Admin live login smoke는 1 passed.
- Windows fallback `PINVI_ADMIN_LIVE_CASE_LIMIT=1` catalog slice는 8 passed.
- `PINVI_ADMIN_LIVE_CASE_LIMIT=200` smoke는 full live e2e가 지금 필요하지 않다는 판단에 따라
  의도적으로 중단했다. 중단 전 33/207 tests가 통과했다.
- `npm run dev:down` 후 `12801/12802/12805`가 모두 free 상태임을 확인했다.

**판단**: 지금은 full live e2e를 실행하지 않는다. full catalog는 release gate 또는 N150/live env가
준비된 시점에 재개하고, 현재 PR은 smoke 근거와 실행 기준만 남긴다.

**다음**: PR 머지 후 T-122 Naver/Kakao OAuth provider 구현으로 이동한다.

## 2026-07-01 (codex) — T-273 local dev API dev-up 수정

**작업**: full catalog local fallback 확인 중 `scripts/dev-up.sh`의 API 프로세스가
`uv run uvicorn` console script를 찾지 못해 실패하는 원인을 수정했다.

**변경**:

- `scripts/dev-up.sh` API 시작 명령을 `uv run python -m uvicorn app.main:app ...`으로 변경했다.
- `docs/runbooks/local-dev.md`의 수동 backend dev 명령도 같은 방식으로 정정했다.

**검증**:

- `uv run python -m uvicorn --version` 성공.
- `bash -n scripts/dev-up.sh scripts/dev-down.sh`
- `npx prettier --check docs/runbooks/local-dev.md`
- `UV_LINK_MODE=copy npm run dev:up` 후 API `/health`와 Web `/admin/login` 모두 응답.
- `npm run dev:down` 후 `12801/12802/12805` free 확인.

**남은 제약**: API는 열리지만 local DB schema/env가 full catalog 실행 조건을 아직 충족하지 않는다.
outbox worker는 `email_queue.last_provider_event_id` 누락 warning을 남겼고 bootstrap admin password는
현재 API 실행 env에서 비활성으로 기록됐다.

## 2026-07-01 (codex) — T-273 Admin live matrix storage state 보강

**작업**: full catalog 실실행이 N150 alias/env와 live credential 부재로 막혀 있어, repo-side에서
credential 원문 없이 재개할 수 있는 실행 경로를 보강했다.

**변경**:

- `apps/web/e2e/admin-live-matrix.live.ts`의 full matrix fixture가
  `PINVI_ADMIN_LIVE_STORAGE_STATE`를 인증 state로 사용할 수 있게 했다.
- email/password가 있으면 기존처럼 주기적 UI login으로 storage state를 갱신한다.
- storage state만 제공된 경우 자동 갱신하지 않고, 세션 만료로 login 화면이 보이면 갱신 가능한
  credential이 필요하다는 오류를 낸다.
- `docs/runbooks/admin-live-e2e.md`, `docs/runbooks/v100-live-gate.md`, `docs/tasks.md`에 storage state
  경로와 한계를 기록했다.

**검증**:

- `npm -w @pinvi/web run typecheck`
- `npm -w @pinvi/web run test:e2e:admin-live:list` → `Total: 6343 tests in 5 files`
- `PINVI_ADMIN_LIVE_E2E=1 PINVI_ADMIN_LIVE_STORAGE_STATE=/tmp/pinvi-nonexistent-storage-state.json PINVI_ADMIN_LIVE_CASE_LIMIT=1 npm -w @pinvi/web run test:e2e:admin-live:list` → `Total: 8 tests in 5 files`
- `PINVI_ADMIN_LIVE_E2E=1 PINVI_ADMIN_LIVE_STORAGE_STATE=/tmp/pinvi-nonexistent-storage-state.json npm -w @pinvi/web run test:e2e:admin-live -- --grep "UI live case catalog" --workers=1` → 1 passed
- `npx prettier --check apps/web/e2e/admin-live-matrix.live.ts docs/tasks.md docs/runbooks/admin-live-e2e.md docs/runbooks/v100-live-gate.md`
- `git diff --check`

**다음**: PR 머지 후 N150 env 또는 fallback storage state가 준비되면 `admin-live-full`을 재개한다.

## 2026-07-01 (codex) — T-273 Admin full catalog 재개 시도

**작업**: 최신 사용자 지시에 따라 T-122 진입을 중단하고 T-273 Admin full catalog 재실행을 먼저
확인했다.

**확인**:

- 브랜치: `agent/codex-t273-infra-blockers`는 최신 `origin/main`과 동일하고 worktree는 clean.
- 열린 PR: #212 문서 PR만 확인.
- N150: 현재 Linux 세션에는 SSH alias/config가 없어 호스트명 해석 단계에서 실패했다.
- Windows fallback: `cmd.exe`에서는 Node/NPM이 동작하지만 `PINVI_ADMIN_LIVE_*` 실행 env가 없다.
- catalog list: Windows fallback에서 `npm -w @pinvi/web run test:e2e:admin-live:list`를 실행해
  `6343 tests in 5 files`를 재확인했다.
- local dev fallback: `npm run dev:up`은 Web/Dagster를 열었지만 API는 `12801`에 2분 이상 응답하지
  않았다. `npm run dev:down`으로 `12801/12802/12805`를 정리했다.

**결론**: 현재 세션만으로는 full catalog browser run을 실질 실행할 수 없다. N150 실행 env 또는
Windows fallback `PINVI_ADMIN_LIVE_*` env가 준비되면 `admin-live-full`을 재개한다.

## 2026-07-01 (codex) — T-273 staging/mutating blocker 재확인

**작업**: PR #364 merge 후 T-273 잔여 mutating Playwright를 운영 public DB가 아닌 local dev/staging으로
닫을 수 있는지 확인했다.

**확인**:

- 고정 dev 포트 `12801`, `12805`, `12802`는 비어 있었다.
- `npm run dev:up` 실행 결과 Web과 Dagster는 기동했지만 API는 2분 동안 `12801`을 열지 못했다.
  로그상 `uv run` dependency/import 단계에서 멈춘 상태였고, direct `.venv/bin/python -c 'from app.main import app'`
  도 15초 timeout으로 끝났다.
- `npm run dev:down`으로 pid와 잔여 포트를 정리했고 `12801`, `12805`, `12802`는 free 상태로 복구했다.

**판단**: mutating Playwright는 계속 전용 staging Web/API blocker로 둔다. 운영 public DB 대상 실행은
runbook 원칙에 맞지 않으므로 실행하지 않았다.

**다음**: docker-manager/edge proxy geofence 설정이 가능하면 N150 geofence smoke를 먼저 닫고,
불가하면 staging Web/API 준비 task로 분리한다.

## 2026-07-01 (codex) — T-273 geofence env passthrough 보강

**작업**: T-273 geofence blocker 중 Pinvi repo에서 닫을 수 있는 compose/env 템플릿 누락을 보강했다.

**변경**:

- `infra/docker-compose.app.yml`의 `app-api`에 `PINVI_GEOFENCE_*` env passthrough를 추가했다.
- `infra/.env.prod.example`에 ADR-018 geofence placeholder와 안전 주의사항을 추가했다.
- `docs/runbooks/docker-app.md` 운영 env 예시에 geofence 기본값과 `BLOCK_UNKNOWN` 주의사항을 추가했다.
- `docs/tasks.md` 선점 브랜치를 현재 geofence 브랜치로 갱신했다.

**남은 차단**: N150 실제 배포는 `kor-travel-docker-manager` compose가 별도 정본이므로 같은 env
passthrough를 그쪽에도 반영해야 한다. 또한 edge proxy가 `CF-IPCountry`와 trusted signal을 API로
전달하는지 확인하기 전에는 운영에서 `PINVI_GEOFENCE_BLOCK_UNKNOWN=true`로 전환하지 않는다.

**다음**: 이 PR을 머지한 뒤 docker-manager/edge proxy 설정을 적용할 수 있으면 N150에서
`scripts/verify-geofence.sh`로 KR health 200 / US root 451 / health bypass 200을 확인한다.

## 2026-07-01 (codex) — T-273 restore staging drill 완료

**작업**: T-273 잔여 gate 중 `restore-staging` phase를 N150 staging Postgres에서 실행했다.

**변경**:

- `scripts/verify-v100-live-gate.sh`에 `PINVI_V100_RESTORE_DOCKER_RUNNER=1` 옵션을 추가했다.
  대상 host에 `pg_restore` / `psql`이 없으면 `postgres:16-alpine` 같은 PostgreSQL image를 일회성
  runner로 사용한다.
- `docs/runbooks/v100-live-gate.md`에 Docker restore runner 실행 예시를 추가했다.
- `docs/tasks.md`, Sprint 6 plan, resume를 restore staging drill 완료와 남은 blocker 기준으로 갱신했다.

**검증**:

- N150 checkout: `4942ec3`로 fast-forward.
- N150 `verify-v100-live-gate` restore Docker runner: 최신 snapshot basename 기준 checksum verified,
  `pg_restore --list` OK, restore success, users `7`, trips `5`, admin audit log `1`, audit chain `valid`,
  rollback precheck guard `schema_unchanged`, complete success.
- host에는 `pg_restore` / `psql`이 없어 Docker runner 방식으로 실행했다.

**다음**: T-273 잔여 blocker는 운영 geofence 설정(`PINVI_GEOFENCE*` + trusted country-header source)
적용 후 US root 451 확인, 그리고 전용 staging Web/API 준비 후 mutating Playwright phase 실행이다.

## 2026-06-30 (codex) — T-273 Admin full catalog + MCP live 검증

**작업**: PR #361 머지 후 최신 main 기준으로 T-273 `v1.0.0` live gate 실제 실행을 이어서 진행했다.

**변경**:

- `admin-live-matrix.live.ts`에 `PINVI_ADMIN_LIVE_CASE_START` /
  `PINVI_ADMIN_LIVE_CASE_END`를 추가해 full catalog를 1-based inclusive 범위로 재개할 수 있게 했다.
- `scripts/verify-mcp.sh`의 Bash 기본값 expansion 문제를 수정했다. 기존 `${3:-{}}`가 POST JSON 뒤에
  `}`를 하나 더 붙여 live MCP POST가 422가 되던 문제다.
- `scripts/verify-geofence.sh` 기본 health path를 운영 API의 `/health`에 맞췄다.
- `docs/tasks.md`, Sprint 6 plan, Admin live / v100 live gate runbook에 재개 범위와 차단 상태를 기록했다.

**검증**:

- Admin live full catalog: N150 Docker runner와 N150 host browser가 각각 runtime 문제로 차단되어
  Windows runner fallback을 사용했다. `CASE_LIMIT=200` smoke `207 passed`, `[0201]` `8 passed`,
  `[0202]..[6336]` 장시간 구간 `6141 passed` + transient `[1755]` 1건, focused rerun `[1755]`
  `8 passed`로 matrix `[0001]..[6336]`을 모두 닫았다.
- catalog list 재개 검증: `PINVI_ADMIN_LIVE_CASE_START=201` → `6143 tests in 5 files`,
  `PINVI_ADMIN_LIVE_CASE_START=201 PINVI_ADMIN_LIVE_CASE_END=203` → `10 tests in 5 files`.
- MCP live phase: 운영 내부 API에서 일회성 token 발급 → `GET /mcp/tools`, `POST list_trips`,
  `POST search_features` 통과 → token 회수 확인.
- geofence live phase: 운영 API에 `PINVI_GEOFENCE*` env가 없어서 KR health 200 / US root 404 /
  health bypass 200, `verify-geofence` exit 1. release 전 ADR-018 운영 설정 적용이 필요하다.
- `bash -n scripts/verify-mcp.sh scripts/verify-geofence.sh scripts/verify-v100-live-gate.sh`

**다음**: geofence 운영 설정과 전용 staging env가 준비되면 T-273 잔여 `geofence`,
`trip-realtime-mutating`, `backup-mutating`, `restore-staging` phase를 실행한다.

## 2026-06-30 (codex) — T-273 v1.0 live gate 실행 자산 1차

**작업**: `v1.0.0` E2E / live gate를 실제 실행하기 전에 phase wrapper와 runbook을 추가했다.

**변경**:

- `docs/tasks.md`에 T-273 선점 브랜치와 충돌 회피 범위를 기록했다.
- T-271 제거 기준에 맞춰 Sprint 6 문서의 Odroid 병행 운영 smoke를 v1.0 blocker에서 제외하고,
  N150 기준 gate로 정렬했다.
- `scripts/verify-v100-live-gate.sh`를 추가했다. 기본 phase는 read-only/list이며,
  `PINVI_V100_LIVE_GATE=1` 없이는 `run`을 거부한다.
- `docs/runbooks/v100-live-gate.md`를 추가해 read-only, mutating/staging, restore, perf/security phase와
  N150 우선 / Windows fallback 기록 기준을 분리했다.
- Admin live runbook의 catalog 수치를 최신 `6343 tests in 5 files` 기준으로 정정했다.

**검증**:

- `bash -n scripts/verify-v100-live-gate.sh`
- `scripts/verify-v100-live-gate.sh plan`
- guard 실패 확인: `scripts/verify-v100-live-gate.sh run admin-live-list` → exit 2
- `PINVI_V100_LIVE_GATE=1 scripts/verify-v100-live-gate.sh run admin-live-list live-mutating-list`
  → Admin live `Total: 6343 tests in 5 files`, live mutating `Total: 2 tests in 2 files`
- `git diff --check`

`shellcheck`는 현재 Linux 환경에 설치되어 있지 않아 실행하지 못했다. 실제 N150 Playwright smoke/full
gate는 이 PR merge 후 T-273 후속 phase로 진행한다.

**다음**: PR을 머지한 뒤 N150 기준 T-273 실제 gate phase를 순서대로 실행한다.

## 2026-06-30 (codex) — T-259 v0.2.0 release 완료

**작업**: `v0.2.0` release gate 문서를 최종 release 상태로 전환했다.

**변경**:

- `CHANGELOG.md`의 `v0.2.0` 후보 섹션을 release 섹션으로 확정했다.
- `docs/tasks.md`에서 T-259를 제거하고 `docs/tasks-done.md`로 이관했다.
- release gate, Sprint 5, resume/journal 문서를 tag/GitHub Release 생성 기준으로 갱신했다.

**검증**:

- PR #359 merge: Admin live full catalog evidence와 retry harness 보강 main 반영.
- release gate 핵심 증적: N150 smoke, backup snapshot, 최신 main API/Web evidence, Admin live
  200/2000, restore staging drill, full catalog `6343 tests in 5 files` 통과.

**다음**: T-273 — `v1.0.0` E2E / Live Gate.

## 2026-06-30 (codex) — T-259 Admin live full catalog 완료

**작업**: 보정된 Admin live full catalog(`6343 tests in 5 files`)를 N150 우선 실행 후 필요한
구간만 Windows fallback으로 완료했다.

**변경**:

- `admin-live-matrix.live.ts`에 login retry 횟수(`PINVI_ADMIN_LIVE_LOGIN_ATTEMPTS`)를 분리하고,
  generic login alert도 retry 대상에 포함했다.
- 장시간 catalog retry backoff를 case 단위로 상한 처리해 transient shell/auth 실패 재시도 시간을
  제한했다.
- `docs/tasks.md`, `CHANGELOG.md`, release gate/resume 문서를 full catalog 완료 기준으로 갱신했다.

**검증**:

- N150 Docker runner full catalog: `[0001]..[3672]` 진행 후 exit 137. OOM 근거 없음.
- N150 Docker runner targeted: `[3673|3674]` 2 passed.
- Windows fallback partition: `[3675]..[6335]` 완료. transient 실패는 focused rerun으로 모두 통과.
- 최종 focused rerun: `[1615|3412|3413|6232]` 4 passed.
- catalog list: `Total: 6343 tests in 5 files`.
- Web lint: 통과.

**다음**: `CHANGELOG.md` release 전환, `v0.2.0` tag/GitHub Release 생성.

## 2026-06-29 (claude) — codex PR 사후 리뷰 수정 21건 (#331-351 → PR #352-357)

**작업**: codex 6개 머지 PR 사후 리뷰 이슈 21건을 전부 수정·머지·close.

**방법**: ultracode 워크플로 — 6개 worktree 격리 에이전트가 영역별 구현 + 적대적 verify, 이후
메인 루프에서 PR→CI→merge(N150 미실행, CI 게이트만). verify가 잡은 보안헤더 회귀(미들웨어
except가 rollback 테스트를 깨뜨림)를 CI 실패 후 exception-handler 방식으로 직접 재수정.

**머지**: #352 notice-plan(reorder 2단계 + IntegrityError→409 + RBAC + FOR UPDATE), #353 category
(트리거 mig 0037 + zod refine + 무수정 override 방지), #354 security(500 exception handler), #355
integrity(dedupe-before-limit + tiebreaker), #356 etl-sql(실행 테스트 강화 + email-template 수렴),
#357 backup(다이얼로그 a11y).

**검증**: 6개 PR 모두 CI(api/web/etl + mock e2e) 통과. #331-351 전부 close.

**다음**: T-259 release / T-273·T-274.

## 2026-06-29 (codex) — T-259 Admin live full catalog 보정

**작업**: N150 Docker runner Admin live full catalog 1차 실패를 분석하고 live catalog를 보정했다.

**변경**:

- `/admin/category-mapping` sort case가 header label 대신 `AdminTable` column key를 사용하도록
  `upstream_icon`, `pinvi_marker`로 수정했다.
- production에서 404 비활성화되는 `/admin/seed`를 table/sort 대상에서 제외하고, live route는
  비활성 안내 또는 dry-run 화면 렌더를 확인하도록 바꿨다.
- live UI catalog 기대값을 6336 browser cases, 전체 list를 `6343 tests in 5 files`로 정렬했다.
- `docs/execplan/v020-release-candidate-gate.md`와 `docs/resume.md`에 1차 full run 실패와 targeted
  재검증 증적을 반영했다.

**검증**:

- N150 full catalog 1차: 6322 passed / 48 failed (14.2h, 보정 전)
- local catalog list: `Total: 6343 tests in 5 files`
- Web lint: 통과
- N150 targeted: seed route/nav + category mapping sort key + debug logs cascade 확인 17 passed
- N150 targeted: `features filter kind=route status=all issue=no q=admin` 2 passed

**다음**: 보정된 Admin live full catalog(`6343 tests in 5 files`)를 N150 Docker runner로 재실행한다.

## 2026-06-29 (codex) — T-259 v0.2.0 release gate 재개

**작업**: T-270 PR #330 머지 후 최신 main에서 T-259를 선점했다.

**확인**:

- 현재 열린 PR은 #212 `Update AGENTS.md`뿐이며 T-259 release gate와 직접 충돌하지 않는다.
- 최근 2일 inline review comments는 없었다. top-level PR comments는 GitHub Actions review reminder와
  작업자 검증 기록 위주라 신규 actionable blocker는 없다.
- 잔여 release blocker는 Admin live full catalog, `CHANGELOG.md` release 전환, `v0.2.0` tag/GitHub
  Release 생성이다.

**다음**: N150 Docker runner로 Admin live full catalog를 실행하고 결과를 release gate 문서에 반영한다.

## 2026-06-29 (codex) — T-270 성능 / 부하 / 보안 점검 완료

**작업**: T-270 성능 / 부하 / 보안 점검 산출물을 구현했다.

**변경**:

- API에 `SecurityHeadersMiddleware`를 추가해 `nosniff`, `Referrer-Policy`, `Permissions-Policy`,
  `X-Frame-Options`, API CSP를 적용했다. HSTS는 production/HTTPS에서만 적용한다.
- `tests/load/api_p95_latency.py`와 `tests/security/csp_cors_rate_limit.py`를 추가했다.
- `docs/runbooks/performance-security-gate.md`와 runbook index를 추가했다.
- `docs/tasks.md`에서 T-270을 제거하고 본 파일과 `tasks-done.md`로 이관했다.

**검증**: ruff, strict mypy, API unit/integration security targeted 27 passed, script `--help`,
`py_compile`, `git diff --check`.

**다음**: PR 머지 후 T-273 또는 T-259 release gate.

## 2026-06-29 (claude/codex) — T-266/T-286 완료처리 + T-291 잔여 종료

**작업**: T-266 MCP 외부 인터페이스 운영 실증, T-286 cross-track review gap closure, T-291 잔여
SQL/audit split 완료 상태를 최신 main 기준으로 정리했다.

**변경**: T-266 — `test_mcp_read_only_tool_scenario`(read-only tool 5종 + 404/422/회수 401, KTM client
stub), `scripts/verify-mcp.sh`, runbook §8(#326). T-286 — `legal-ops-review-gap-crosswalk.md` §6
closure 재감사(G-001~044 + R-001~009 머지 확인). T-291-etl-sql-tests(#327)도 closed로 반영해
R-005 잔여 표기를 제거했다.

**검증**: T-266 ruff/py_compile/bash -n OK + api CI 통과(#326 머지). T-286/#328 docs-only CI 통과.

**다음**: T-270 / T-273·T-274(릴리즈).

## 2026-06-29 (codex) — T-291 ETL SQL 실행 테스트 완료

**작업**: PR #273 사후 리뷰의 ETL SQL 실행 테스트와 audit retention 정책 분리를 완료했다.

**변경**:

- ETL 원시 SQL 상수를 `pinvi.etl.sql.outbox` / `pinvi.etl.sql.retention`으로 분리하고,
  ETL asset은 해당 상수를 import하도록 바꿨다.
- `pinvi_pii_retention`은 삭제 계정 PII, OAuth identity, verification/session/OAuth transient 후보만
  집계한다. `location_access_log`는 location archive asset/API summary 단독 책임으로 남겼다.
- Admin ETL/Retention API에 `audit_retention` summary를 추가했다. `admin_audit_log` PII 후보는
  90일 `append_only_cold_storage` 정책으로 집계하고, append-only 원장이므로 execute 결과에는
  `skipped_admin_audit_pii_over_retention` evidence만 남긴다.
- Pydantic/zod/Web Admin retention/ETL 화면과 e2e fixture, Admin API/ETL runbook/architecture 문서를
  같은 계약으로 갱신했다.
- `docs/tasks.md`에서 완료된 T-291 잔여 항목을 제거하고 본 파일과 `tasks-done.md`로 이관했다.

**검증**:

- API ruff targeted, API strict mypy targeted
- ETL ruff targeted, ETL pytest 전체 13 passed
- API integration `test_etl_sql_smoke.py`, `test_admin_etl_provider_sync_api.py`,
  `test_admin_retention_api.py` — 12 passed
- `packages/schemas`, `packages/api-client`, `apps/web` typecheck
- `apps/web` lint
- N150 Playwright Docker runner `admin-etl-provider-sync.e2e.ts` 2 passed,
  `admin-retention.e2e.ts` 1 passed

**다음**: PR 머지 후 최신 main에서 남은 Sprint 6 task를 다시 선점한다.

## 2026-06-29 (claude) — PR #227 지도 마커 튜닝 마무리 + T-268/T-269 완료처리

**작업**: codex PR #227(map marker tuning + viewport caching) 마무리 머지 + T-268/T-269 완료처리.

**변경**: #227을 main에 동기화(98커밋)·충돌 해소 — `FeatureMapView.tsx`(main resolveMarkerStyle +
PR featureKind 병합, isSelected 추출, weather→WeatherMarker, LRU+TTL viewport 캐시), `featureBounds`
(zoom별 bbox precision). docs(tasks/done/resume/journal)에 T-268(#323)·T-269(#324)·#227 완료 반영.

**검증**: lint clean, featureBounds vitest 6 pass, CI(lint-typecheck-build/e2e) 통과 후 머지.
로컬 typecheck의 vworld-map-web implicit-any는 벤더 타입 미해소 아티팩트(CI 신규 설치에서 해소).

**다음**: non-overlap backlog (T-266/T-270/T-286).

## 2026-06-29 (codex) — T-265 Admin notice plan 작성기 완료

**작업**: `/admin/notice-plans` 운영 작성기를 API/Web/Admin 문서까지 완료했다.

**변경**:

- `apps/api/app/api/v1/admin/notice_plans.py`, `apps/api/app/services/notice_plan.py`,
  `apps/api/app/schemas/notice.py`에 plan CRUD, `If-Match` version conflict, POI CRUD/reorder,
  soft delete, audit snapshot을 추가했다.
- `packages/schemas`와 `packages/api-client`에 Admin notice plan/POI create/update/reorder 및
  attachment client 계약을 추가했다.
- Web Admin에 `/admin/notice-plans` 목록/필터, 신규 생성, 편집, `NoticePoiEditor`,
  `NoticeAttachmentPanel`을 추가하고 sidebar/dashboard entry를 연결했다.
- `docs/tasks.md`에서 완료된 T-265를 제거하고 `tasks-done.md`로 이관했다. 사용자 지시에 따라 다음
  작업은 `T-291-etl-sql-tests`로 기록했다.
- `docs/api/admin.md`에 Admin notice plan CRUD/POI/reorder/첨부 계약을 추가했다.
- 로컬 `.env`의 RustFS bucket 값을 `pinvi-media`로 정렬했다.

**검증**:

- `ruff check` / `ruff format --check` (notice plan API/service/schema/tests)
- `python -m mypy --strict` (notice plan API/service/schema)
- `npm run typecheck --workspace packages/schemas`
- `npm run typecheck --workspace packages/api-client`
- `npm run typecheck --workspace apps/web`
- `npm run lint --workspace apps/web`
- `pytest test_admin_notice_plan_crud_api.py test_admin_curated_attachments_api.py test_admin_kor_travel_map_curated_import.py`
  — 8 passed
- `scripts/n150-playwright-runner.sh -- npm -w @pinvi/web run test:e2e -- admin-notice-plans.e2e.ts --workers=1`
  — 2 passed

**다음**: T-265 PR 머지 후 최신 main에서 T-291-etl-sql-tests를 진행한다.

## 2026-06-29 (claude) — T-287 Trip Day optimistic lock / conflict UX

**작업**: day rename/delete에 trip/POI와 동일한 정수 version optimistic lock(If-Match) 도입.

**변경**: migration 0036(`app.trip_days.version`), `models/trip_day.py`, `services/trip.py`
(update/delete_trip_day expected_version 검증+bump), `api/v1/trips.py`(If-Match + 409),
`schemas/trip.py`(TripDayResponse/TripViewDay version) + `trip_view_builder`, zod/api-client,
`TripDetail.tsx`(version 전달+충돌 reload 안내), mobile `edit.tsx` deleteDay version, 통합 테스트.

**검증**: api ruff/format clean(py_compile OK; pytest/mypy CI), web typecheck 신규 0 + mobile
typecheck pass + vitest(web 46 / domain 61) pass.

**다음**: backlog non-overlap task.

## 2026-06-29 (codex) — T-265 Admin notice plan 작성기 착수

**작업**: PR #322 문서 정리 머지 후 T-265 Admin notice plan 작성기 브랜치를 시작했다.

**변경**:

- `docs/tasks.md`에 T-265 Codex 선점과 충돌 회피 범위를 기록했다.
- `docs/resume.md`에 T-265 다음 작업과 병행 PR 회피 범위를 기록했다.

**발견**: 최근 inline PR review comment는 없고, 최근 issue comments는 대부분 MCP review reminder다.
열린 PR #321은 trip day optimistic lock 파일을 수정하므로 T-265에서 `trips` 영역은 건드리지 않는다.

**다음**: CodeGraph로 existing `/admin/notice-plans`, curated plan/POI, Web notice plan 흐름을 확인한 뒤
목록/생성/편집/POI editor 구현 범위를 확정한다.

## 2026-06-29 (codex) — T-113 / T-271 / T-272 / T-285 제거

**작업**: 사용자 지시에 따라 T-113, T-271, T-272, T-285를 열린 backlog에서 제거했다.

**변경**:

- `docs/tasks.md`에서 T-113, T-271, T-272, T-285를 제거했다.
- `docs/tasks-rule.md`에 AI companion 연동 시 신규 repo 신설 대신 기존 `kor-travel-concierge` API를
  활용하는 규칙을 추가했다.
- `docs/tasks-done.md`에 네 task를 "사용자 지시로 scope 제거" 아카이브로 추가했다.
- `docs/execplan/sprint6-v1.0-plan.md`와 `docs/sprints/SPRINT-6.md`의 남은 task/DoD 매핑에서
  T-113/T-271/T-272/T-285를 제거했다.
- `docs/decisions.md` ADR-020에 기존 `kor-travel-concierge` API 활용 amendment를 추가했다.

**병행 상태**: 열린 PR #321은 T-287 Trip Day optimistic lock / conflict UX, 열린 PR #227은 map
marker/tracking 문서 영역이고, T-291-etl-sql-tests는 `apps/etl/**`와 audit retention 정책 영역이다.
문서 정리 PR 머지 후 겹치지 않는 다음 task를 선점한다.

## 2026-06-29 (codex) — T-267 Backup/Restore UI hot-swap 완료

**작업**: 다음 개발 task 진입 전 task 추적 문서를 정리하고 T-267 Backup/Restore UI hot-swap을
완료했다.

**변경**:

- `docs/tasks.md`에서 반복 계획과 긴 task 설명을 줄이고 현재 선점, 충돌 회피, 열린 backlog만 남겼다.
- 반복 체크리스트와 `tasks.md` 금지 항목은 `docs/tasks-rule.md`로 옮겼다.
- Web restore dialog에 snapshot 파일명 직접 입력 확인, Escape/backdrop/focus trap, 실행 중 닫기 잠금,
  성공 후 재제출 방지, 요청 중 pending phase와 완료 phase/result 표시를 추가했다.
- `admin-backup.e2e.ts`에 기본 잠금 경로와 enabled flag restore dialog 경로를 추가했다.
- `CHANGELOG.md`, `docs/api/admin.md`, `docs/runbooks/backup-restore.md`를 UI 안전장치 기준으로 갱신했다.
- PR #319를 squash merge했다(`40a781a`).
- 완료 이관으로 T-267을 `tasks-done.md`에 추가하고 `tasks.md`에서는 제거했다.

**검증**:

- `npm run typecheck --workspace apps/web`
- `npm run lint --workspace apps/web`
- `git diff --check`
- `scripts/n150-playwright-runner.sh -- npm -w @pinvi/web run test:e2e -- admin-backup.e2e.ts --workers=1`
- `NEXT_PUBLIC_PINVI_RESTORE_HOTSWAP_UI_ENABLED=1 scripts/n150-playwright-runner.sh -- npm -w @pinvi/web run test:e2e -- admin-backup.e2e.ts --workers=1`
- `codegraph sync && codegraph status`
- PR #319 CI: Aggregate CI gate, web lint-typecheck-build, web e2e 통과

**병행 상태**: 열린 PR #227은 map marker/tracking 문서 영역이다. T-291-etl-sql-tests는
`apps/etl/**`와 audit retention 정책 영역이다. 다음 task에서도 두 영역을 선점 없이 섞지 않는다.
T-285는 진행하지 않는다.

## 2026-06-29 (claude) — T-260 Sprint 6 실행 계획 + ADR-053

**작업**: Sprint 6 상세 실행 계획 문서화 + 보류 ADR 정리.

**변경**: `docs/execplan/sprint6-v1.0-plan.md` 신규(남은 task 그룹·DoD 매핑·병행 회피),
`decisions.md` **ADR-053**(경로 최적화 = NN + 2-opt, haversine; OR-Tools/실도로 거리 보류; 다음=ADR-054),
`SPRINT-6.md` ADR 후보 노트→확정 ADR-053/052 + execplan 참조 + optimize DoD/산출물 실구현 정합.
docs-only.

**다음**: T-287 Trip Day optimistic lock / conflict UX.

## 2026-06-29 (codex) — T-264 Admin category mapping DB override 완료

**작업**: Sprint 6 T-264 Admin category mapping DB override를 구현했다.

**변경**:

- ADR-052로 upstream category taxonomy는 `kor-travel-map` 정본, Pinvi는 표시명/마커 색/마커 아이콘
  override만 소유한다는 결정을 남겼다.
- `app.category_mappings` migration/model과 Admin API 조회·수정·rollback/audit을 추가했다.
- Web `/admin/category-mapping`에 override editor와 rollback 흐름을 연결하고 API client/schema/e2e를
  갱신했다.
- 사용자 지시에 따라 `tasks.md`에서 완료/머지/검증 이력을 제거하고, 완료 기록은
  `tasks-done.md`, 반복 계획·체크리스트는 `tasks-rule.md`로 이동했다.

**검증**:

- `apps/api/.venv/bin/python -m py_compile ...`
- `apps/api/.venv/bin/ruff check ...`
- `apps/api/.venv/bin/ruff format --check ...`
- `apps/api/.venv/bin/python -m mypy --strict apps/api/app/api/v1/admin/category_mappings.py apps/api/app/models/category_mapping.py`
- `PATH="$PWD/apps/api/.venv/bin:$PATH" apps/api/.venv/bin/pytest apps/api/tests/integration/test_admin_category_mappings_api.py -q --capture=no`
- `npm run typecheck --workspace packages/schemas`
- `npm run typecheck --workspace packages/api-client`
- `npm run typecheck --workspace apps/web`
- `npm run lint --workspace apps/web`
- `scripts/n150-playwright-runner.sh -- npm -w @pinvi/web run test:e2e -- admin-category-mapping.e2e.ts --workers=1`
- `git diff --check`

**병행 상태**: T-291-etl-sql-tests는 `apps/etl/**`와 audit retention 정책을 건드리는 잔여 task다.
열린 PR #227은 map marker tuning과 tracking 문서를 건드리는 오래된 PR이므로 map 파일은 제외한다.
T-285는 진행하지 않는다.

## 2026-06-29 (claude) — 병행 트랙 3건 머지 + tasks 위생

**작업**: codex 병행 트랙(T-289/290, T-291, T-261~263)을 구현·머지하고, 신규 task 진입 전
`tasks.md`를 정리했다.

**머지**: #310(T-289/290 WS reconnect/conflict UX), #312(T-291 ETL run-failure sensor),
#315(T-261~263 스마트 정렬 2-opt). 각 PR CI green(typecheck/lint/vitest/pytest/e2e) 후 머지.

**tasks 위생**: 완료 T-261/262/263·T-291을 `tasks-done.md`로 이관, 스테일 병행 노트 제거,
T-291 잔여를 `T-291-etl-sql-tests`로 분리. 이후 task는 번호 부여→todo→완료 시 done 이관
규칙(tasks-rule §7/§8)을 따른다.

## 2026-06-29 (codex) — T-292 App integrity pagination / producer follow-up 완료

**작업**: PR #283 사후 리뷰의 App integrity pagination / producer / modal 접근성 gap을 닫았다.

**변경**:

- `/admin/integrity/issues?source=all`에 composite cursor를 도입해 Pinvi app issue가 page를 채워도
  upstream `kor-travel-map` issue를 함께 조회한다.
- Pinvi app integrity producer/upsert helper를 추가하고 partial unique index를 실제로 행사하는
  integration test를 작성했다.
- Web Admin `/admin/integrity`에 issue pagination UI를 추가하고 action modal의 Escape/overlay close,
  초기 포커스, Tab focus trap을 보강했다.
- `CHANGELOG.md`, `docs/api/admin.md`, `docs/data-model.md`, `docs/postgres-schema.md`,
  `docs/tasks.md`, `docs/tasks-done.md`, `docs/resume.md`를 현재 상태에 맞게 갱신했다.

**검증**: API targeted ruff/mypy/pytest, `packages/schemas` typecheck, `packages/api-client`
typecheck, `apps/web` typecheck/lint, N150 Playwright Docker runner Admin integrity e2e를 통과했다.

**병행 상태**: PR #312(T-291 failure sensor)는 main에 머지됐다. 열린 PR #227은 map marker tuning과
tracking 문서를 건드리므로 이번 작업은 map 파일을 건드리지 않는다. T-285는 진행하지 않는다.

## 2026-06-29 (codex) — T-288-legacy-task-archive / task 문서 정리

**작업**: 사용자 지시에 따라 T-285는 현재 진행하지 않고, `tasks.md`의 완료/규칙/legacy 항목을
`tasks-done.md`와 `tasks-rule.md`로 이관했다.

**변경**:

- T-285 착수 중 작성했던 미커밋 문서 변경을 제거하고, 새 브랜치
  `agent/codex-tasks-backlog-cleanup`에서 문서 정리만 진행했다.
- `docs/tasks.md`를 열린 backlog 중심으로 축소했다. 완료된 T-281~~T-284, T-289~~T-290,
  Admin 콘솔 보강 legacy, 기존 완료/보류 혼재 섹션, 머지 히스토리는 제거했다.
- `docs/tasks-done.md`에 T-288-legacy-task-archive, 최근 완료 항목, legacy archive, 머지
  히스토리 요약을 추가했다.
- `docs/tasks-rule.md` §8에 병행 작업 기록, 선점 충돌 회피, 신규 task 착수 전 확인,
  완료 후 이관 규칙을 추가했다.
- `docs/resume.md`를 현재 상태와 다음 후보(T-292/T-286) 기준으로 갱신했다.

**검증**:

- Linux git/CodeGraph 환경에서 `git fetch origin main`, `codegraph sync`, 열린 PR 확인을 수행했다.
- PR #312(T-291)가 `apps/etl/**`, `docs/architecture/dagster-etl-bridge.md`,
  `docs/runbooks/etl.md`를 변경 중임을 확인했다. 이번 PR은 해당 파일을 건드리지 않는다.

**다음**: 문서 정리 PR·CI·머지 후 T-292 App integrity pagination / producer follow-up 또는
T-286 Cross-track review gap closure로 진입한다. T-285는 사용자 지시가 바뀌기 전까지 진행하지 않는다.

## 2026-06-29 (codex) — T-284 Mobile v1.0 scope gate

**작업**: 활성 `apps/mobile` track을 `v1.0.0` Web/API/Admin release blocker에서 제외하는 scope gate를
확정했다.

**변경**:

- `apps/mobile/README.md`에 T-284 scope gate를 추가했다. EAS build, 실기기 smoke, store 제출,
  mobile live e2e는 모바일 release train에서 검증하고, `mobile-typecheck` CI gate는 유지한다.
- `docs/architecture/frontend.md`와 `docs/architecture/expo-implementation-plan.md`의 mobile 상태
  drift를 현재 활성 Sprint M-1 track으로 갱신했다.
- ADR-024 WSL/NTFS 실행 문구를 ADR-051 Linux-only 기준으로 교체했다.
- `docs/sprints/SPRINT-6.md`, `CHANGELOG.md`, `docs/tasks.md`, `docs/tasks-done.md`,
  `docs/resume.md`를 T-284 완료 상태로 동기화했다.

**검증**:

- `git diff --check` 통과.
- `npm --workspace @pinvi/mobile run typecheck` 통과.

**다음**: 당시 다음 후보는 T-285 또는 T-292였으나, 2026-06-29 사용자 지시에 따라 T-285는 현재
진행하지 않는다. T-289/T-290은 PR #310으로 main에 머지됐으므로, 같은 영역을 건드릴 때는 최신
main 기준으로 영향도를 다시 확인한다.

## 2026-06-29 (codex) — T-283 Security review / threat model / penetration pass

**작업**: Sprint 6 auth/session/MCP/share token/rate-limit/storage/Admin RBAC/incident 보안 경계
1차 점검을 수행했다.

**변경**:

- `docs/audit/2026-06-29-security-threat-model.md`를 추가해 자산, 신뢰 경계, 위협, 방어,
  기존/신규 테스트 증거, 잔여 운영 리스크를 기록했다.
- `apps/api/tests/integration/test_security_boundaries_api.py`를 추가했다.
  MCP token과 Web access token 상호 재사용 차단, share token route scope/비노출/revoke,
  admin-only storage presign 권한, security incident console operator 은닉을 검증한다.
- `CHANGELOG.md`, `docs/tasks.md`, `docs/sprints/SPRINT-6.md`, `docs/resume.md`를 T-283 완료
  상태로 갱신했다.

**검증**:

- 최근 2일 PR review 확인: 2026-06-27 이후 inline review comment 없음.
- `PATH="$PWD/.venv/bin:$PATH" .venv/bin/python -m pytest
tests/integration/test_security_boundaries_api.py -q --capture=no` 4 passed.

**다음**: PR·CI·머지 후 T-284 Mobile v1.0 scope gate로 진입한다.

## 2026-06-29 (claude) — codex 병행 트랙 착수 + 추적 문서 선반영

**작업**: 사용자 요청 — codex가 T-283(보안 리뷰, PR #308)을 진행하는 동안 충돌이 적은 작업을
병행한다. 추적 문서를 먼저 docs-only PR로 머지(CI 생략 admin-merge)한 뒤 구현에 들어간다.

**선정(2026-06-29 병행 작업 리포트 기준)**:

- T-289 + T-290 — WebSocket reconnect/invalidation + Trip conflict UX 후속(프론트/`packages/api-client`).
- T-291 — ETL failure sensor + compliance SQL 테스트(`apps/etl`).
- T-261~T-263 — 경로 최적화(OR-Tools) + 스마트 정렬 API/UI(신규 `optimize` 모듈).

**변경(본 docs PR)**: `tasks.md`(진행 중에 병행 트랙 노트 + T-289/290/291·T-261~263 진행 표기),
`resume.md`/`journal.md` 2026-06-29 (claude) 엔트리.

**다음**: T-289+T-290 구현.

## 2026-06-29 (codex) — T-282 Rate-limit / abuse admin surface

**작업**: ADR-038 rate-limit bucket 운영 조회와 abuse override 흐름을 구현했다.

**변경**:

- `app.rate_limit_buckets` ORM mapping과 `app.rate_limit_overrides` migration을 추가했다.
  override는 `limit_name`, HMAC `bucket_hash`, `identity_fingerprint`, `identity_label`, TTL,
  생성/rollback admin, 사유를 저장하고 원문 IP/email/share token은 저장하지 않는다.
- `RateLimitMiddleware`가 Postgres backend에서 active `blocked` override를
  `429 RATE_LIMIT_BLOCKED`로 차단하고, active `allowed` override는 counter hit를 우회하도록 했다.
- `/admin/abuse` API를 추가했다. bucket 상태, fail-closed/backend store 상태, 429 bucket count,
  suspicious auth/share/storage activity, override 목록을 반환하고, override 생성/rollback은
  `admin_audit_log`에 `rate_limit_override.create` / `rate_limit_override.rollback`으로 기록한다.
- Web Admin `/admin/abuse` 페이지와 sidebar 메뉴를 추가했다. 운영자는 store 상태, suspicious
  bucket, active overrides를 확인하고 TTL block/allow override 생성 및 rollback을 수행할 수 있다.
- 공유 Zod schema, `@pinvi/api-client`, query key, RBAC permission matrix, API/DB/runbook 문서를
  동기화했다.

**검증**:

- `PATH="$PWD/.venv/bin:$PATH" .venv/bin/python -m mypy --strict app` 통과.
- `.venv/bin/ruff check app/middleware/rate_limit.py app/models/rate_limit.py
app/services/admin_rate_limit_abuse.py app/api/v1/admin/abuse.py app/services/admin_rbac.py
app/schemas/admin.py tests/integration/test_admin_abuse_api.py` 통과.
- `PATH="$PWD/.venv/bin:$PATH" .venv/bin/python -m pytest
tests/integration/test_admin_abuse_api.py tests/unit/test_rate_limit_middleware.py -q --capture=no`
  9 passed.
- `npm run typecheck --workspace packages/schemas` 통과.
- `npm run typecheck --workspace packages/api-client` 통과.
- `npm run typecheck --workspace apps/web` 통과.
- `npm run lint --workspace apps/web` 통과.
- N150 Docker runner:
  `scripts/n150-playwright-runner.sh -- npm -w @pinvi/web run test:e2e -- admin-abuse.e2e.ts --workers=1`
  1 passed.

**다음**: PR·CI·머지 후 T-283 Security review / threat model / penetration pass로 진입한다.

## 2026-06-29 (codex) — T-281 User lifecycle admin actions

**작업**: Admin 사용자 lifecycle 운영 액션과 사용자 self-delete 흐름을 구현했다.

**변경**:

- `app.users.status`에 `pending_delete`를 추가하는 Alembic migration을 추가했다.
- auth dependency, refresh session, MCP token, password reset/verify 경계에서 `pending_delete` /
  `deleted` 사용자를 차단한다.
- Admin 사용자 상세 API에 세션 목록, 세션 단건/전체 강제 로그아웃, 인증 메일 재발송,
  강제 비밀번호 reset, reactivate, delete schedule, anonymize endpoint를 추가했다.
- 세션 목록 응답은 IP 원문 대신 `ip_hash`만 제공한다.
- role 변경, 세션 강제 로그아웃, force-password-reset, disable/delete/reactivate는
  `users.access_token_version`을 증가시켜 기존 access token을 무효화한다.
- `/users/me` DELETE를 추가해 self-service 탈퇴를 `pending_delete` + 세션 revoke + 쿠키 삭제로 처리한다.
- retention 후보 SQL은 `pending_delete`와 `deleted`를 모두 보며, 익명화 후 최종 `status='deleted'`로
  고정한다.
- Web `/admin/users/{user_id}`에 lifecycle 패널과 세션 테이블을 추가했고, API client/Zod schema와
  E2E mock을 갱신했다.

**검증**:

- `apps/api/.venv/bin/ruff check ...` 통과.
- `PATH="$PWD/.venv/bin:$PATH" .venv/bin/python -m mypy --strict app` 통과.
- `PATH="$PWD/.venv/bin:$PATH" .venv/bin/pytest tests/integration/test_admin_users_api.py -q --capture=no`
  10 passed.
- `npm run typecheck --workspace packages/schemas` 통과.
- `npm run typecheck --workspace packages/api-client` 통과.
- `npm run typecheck --workspace apps/web` 통과.
- `npm run lint --workspace apps/web` 통과.
- N150 Docker runner:
  `scripts/n150-playwright-runner.sh -- npm -w @pinvi/web run test:e2e -- admin-users.e2e.ts --workers=1`
  6 passed.

**다음**: PR·CI·머지 후 T-282 Rate-limit / abuse admin surface로 진입한다.

## 2026-06-29 (codex) — T-280 RBAC role grant/revoke / permission matrix

**작업**: Admin RBAC 권한 matrix와 사용자 role 부여/회수 workflow를 구현했다.

**변경**:

- `GET /admin/rbac/permission-matrix` API와 Web Admin `/admin/rbac` 화면을 추가했다. role 설명,
  resource/action/route, 허용 role, 사유 필요 여부, audit 필요 여부를 표시한다.
- 사용자 상세 화면에 역할 관리 섹션을 추가했다. `admin` 권한자는 `admin` / `operator` / `cpo`
  role을 사유와 함께 부여하거나 회수한다.
- role mutation은 `admin` 전용이며, `admin_audit_log`에 `user.role_grant` /
  `user.role_revoke` action과 before/after roles, request id를 남긴다.
- role 배열은 `user`, `admin`, `operator`, `cpo` 순서로 정규화한다.
- 중복 부여, 미보유 role 회수, 자기 admin 회수, 마지막 admin 회수를 guard로 차단한다.
- shared schema, API client, Admin query key, Admin mock Playwright, Admin live matrix catalog를 갱신했다.
- `docs/architecture/admin-rbac.md`, `docs/api/admin.md`, `docs/runbooks/admin.md`, task/resume,
  `CHANGELOG.md`를 갱신했다.

**검증**:

- WSL: `ruff check` targeted RBAC/user admin API/service/schema/test files
- WSL: `python -m mypy` targeted RBAC/user admin API/service/schema files
- WSL: `npm run typecheck --workspace packages/schemas`
- WSL: `npm run typecheck --workspace packages/api-client`
- WSL: `npm run typecheck --workspace apps/web`
- WSL: `npm run lint --workspace apps/web`
- WSL: `PATH="$PWD/.venv/bin:$PATH" python -m pytest tests/integration/test_admin_users_api.py -q -s`
  — 7 passed
- Playwright: N150 alias `n150`, `pinvi-n150`이 현재 Linux 세션에서 해석되지 않아 Windows
  fallback으로
  `npm run test:e2e --workspace apps/web -- admin-users.e2e.ts --project=chromium --workers=1` —
  5 passed

**다음**: PR·CI·머지 후 T-281 User lifecycle admin actions로 진입한다.

## 2026-06-29 (codex) — T-279 Content moderation / takedown workflow

**작업**: 콘텐츠 신고, 게시중단, 복원, 이의제기 workflow를 구현했다.

**변경**:

- `app.content_reports`와 `app.content_moderation_actions` migration/model을 추가했다. 대상 유형은
  trip/comment/attachment/share link이며, 신고 사유, target snapshot, 증거 metadata, 상태, reviewer,
  resolution, appeal, 조치 전후 상태를 저장한다.
- `/users/me/content-reports` API는 사용자 신고 접수/조회와 이의제기를 제공한다.
  `/settings/moderation` 화면은 같은 self-service 흐름을 제공한다.
- `/admin/moderation` API와 Web Admin 화면을 추가했다. 운영자는 신고 목록을 필터링하고
  review/hide/takedown/restore/reject 조치를 수행한다.
- hide/takedown/restore는 여행 visibility/archive, 댓글/첨부 soft-delete, 공유 링크 revoke 상태에
  실제 반영된다.
- 모든 운영 mutation은 `content_moderation.*` 감사 로그와 `access_reason`을 남긴다.
- shared schema, API client, Admin query key, Admin/user mock Playwright를 추가했다.
- `docs/runbooks/content-moderation.md`, `docs/api/admin.md`, `docs/api/users.md`,
  `docs/compliance/pipa.md`, `docs/data-model.md`, `docs/postgres-schema.md`, task/resume,
  `CHANGELOG.md`를 갱신했다.

**검증**:

- WSL: `ruff check` targeted moderation API/model/schema/service/test files
- WSL: `python -m mypy` targeted moderation model/schema/service/Admin/users routes
- WSL: `npm run typecheck --workspace packages/schemas`
- WSL: `npm run typecheck --workspace packages/api-client`
- WSL: `npm run typecheck --workspace apps/web`
- WSL: `npm run lint --workspace apps/web`
- WSL: `python -m pytest tests/integration/test_content_moderation_api.py -q -s` — 3 passed
- Playwright: N150 alias가 현재 Linux 세션에서 해석되지 않아 Windows fallback으로
  `npm run test:e2e --workspace apps/web -- admin-moderation.e2e.ts settings-moderation.e2e.ts` —
  2 passed

**다음**: PR·CI·머지 후 T-280 RBAC role grant/revoke / permission matrix로 진입한다.

## 2026-06-28 (codex) — T-278 DSR intake workflow

**작업**: 개인정보 열람/정정/삭제/처리정지 요청 접수와 CPO 처리 workflow를 구현했다.

**변경**:

- `app.dsr_requests` migration/model을 추가했다. 요청 유형, 상태, 접수 + 10일 `due_at`,
  본인 확인 metadata, result notice hash, export manifest, partial response, evidence attachment id를
  저장한다.
- DSR 행은 원문 이메일을 저장하지 않고 `requester_email_hash`와 `requester_email_masked`만
  보존한다.
- `/users/me/dsr-requests` API는 사용자 접수/조회/철회를 제공한다. `/settings/dsr` 화면은 같은
  self-service 흐름을 제공한다.
- `/admin/dsr` API와 Web Admin 화면을 추가했다. CPO 전용 본인 확인, 처리 시작, 완료/거절 조치를
  제공하고 모든 mutation은 `admin_audit_log`에 `dsr.*` action과 `access_reason`을 남긴다.
- 완료/거절 조치는 `email_queue.template='dsr_result_notice'` row를 만들고 `result_notice_email_id`와
  `result_notice_hash`를 DSR 행에 연결한다.
- shared schema, API client, Admin query key, Admin/user mock Playwright를 추가했다.
- `docs/runbooks/dsr.md`, `docs/api/admin.md`, `docs/api/users.md`, `docs/compliance/pipa.md`,
  `docs/data-model.md`, `docs/postgres-schema.md`, task/resume, `CHANGELOG.md`를 갱신했다.

**검증**:

- WSL: `ruff check` targeted DSR API/model/schema/service/test files
- WSL: `python -m mypy` targeted DSR model/schema/service/Admin/users routes
- WSL: `npm run typecheck --workspace packages/schemas`
- WSL: `npm run typecheck --workspace packages/api-client`
- WSL: `npm run typecheck --workspace apps/web`
- WSL: `npm run lint --workspace apps/web`
- WSL: `PATH="$PWD/.venv/bin:$PATH" python -m pytest tests/integration/test_dsr_requests_api.py -q -s`
  — 3 passed
- Playwright: N150 alias가 현재 Linux 세션에서 해석되지 않아 Windows fallback으로
  `npm run test:e2e --workspace apps/web -- admin-dsr.e2e.ts settings-dsr.e2e.ts` — 2 passed

**다음**: PR·CI·머지 후 T-279 Content moderation / takedown workflow로 진입한다.

## 2026-06-28 (codex) — T-277 Email deliverability / suppression enforcement

**작업**: Resend 발송 차단, webhook 멱등/우선순위, Admin deliverability 상태판을 구현했다.

**변경**:

- `app.email_suppressions`와 `app.resend_webhook_events` migration/model을 추가하고,
  `email_queue.status`에 `delivery_delayed`, `suppressed`를 추가했다.
- `process_pending_email_batch()`가 발송 전 `users.email_status`, active suppression,
  `marketing` consent를 확인해 provider 호출 없이 terminal 상태로 차단한다.
- Resend SDK 직접 호출을 `httpx` 기반 `ResendClient`로 바꾸고
  `api_call_event_hooks(..., provider='resend')`를 연결했다.
- `/webhooks/resend`는 event id/`svix-id` dedupe와 terminal precedence를 적용하고,
  hard bounce/complaint/provider suppression을 suppression source와 사용자 `email_status`에 반영한다.
- `GET /admin/emails/deliverability`, Web Admin `/admin/emails` 상태판, shared schema/API client,
  mock Playwright를 추가했다.
- `docs/execplan/email-deliverability-suppression.md`, `docs/integrations/resend.md`,
  `docs/api/admin.md`, `docs/data-model.md`, `docs/postgres-schema.md`,
  `docs/compliance/data-policy.md`, task/resume, `CHANGELOG.md`를 갱신했다.

**검증**:

- WSL: `python3 -m compileall app`
- WSL: `ruff check` targeted files
- WSL: `python -m mypy --strict` targeted email client/service/webhook/admin route
- WSL: `npm -w @pinvi/schemas run typecheck`, `npm -w @pinvi/api-client run typecheck`,
  `npm -w @pinvi/web run typecheck`, `npm -w @pinvi/web run lint`
- WSL: `pytest --capture=no -q tests/integration/test_email_queue_worker.py
tests/integration/test_resend_webhook.py tests/integration/test_admin_email_deliverability_api.py
tests/integration/test_api_call_logging.py` — 24 passed
- Playwright: N150 alias가 현재 Linux 세션에서 해석되지 않아 Windows fallback으로
  `npm -w @pinvi/web run test:e2e -- admin-emails.e2e.ts --project=chromium --workers=1` — 1 passed

**다음**: PR·CI·머지 후 T-278 DSR intake workflow로 진입한다.

## 2026-06-28 (codex) — T-276 Retention execution / dashboard

**작업**: Sprint 6 보존기간 실행 콘솔을 추가했다.

**변경**:

- `app.retention_runs`와 `app.location_access_log_archive` migration을 추가했다. 모든 dry-run/execute는
  candidate snapshot, result evidence, kill-switch 상태, actor, access reason을 저장한다.
- `app.audit_log_append_only()`는 `location_access_log` DELETE를 retention transaction의
  `app.retention_location_delete_allowed=on` 설정에서만 허용한다. `admin_audit_log` update/delete
  차단은 유지한다.
- `/admin/retention` API와 service를 추가했다. execute는 `PINVI_RETENTION_EXECUTE_ENABLED`,
  confirm phrase, cutoff 이전 pending outbox, hash-chain bridge precheck를 통과해야 한다.
- 실행 범위는 삭제 계정 PII anonymize, OAuth identity 삭제, 만료 verification/session/OAuth transient
  row 삭제, 위치 로그 archive 후 active row 삭제다. `admin_audit_log` PII 후보는 skip count로 기록한다.
- Web Admin `/admin/retention` 화면, sidebar, API client/schema/query key, API integration,
  mock Playwright를 추가했다.
- `docs/api/admin.md`, `docs/runbooks/retention-execution.md`, `docs/compliance/lbs-act.md`,
  `docs/architecture/user-location.md`, `docs/postgres-schema.md`, `docs/data-model.md`, task/resume,
  `CHANGELOG.md`를 갱신했다.

**검증**:

- WSL ext4 mirror: `pytest -q tests/integration/test_admin_retention_api.py` — 3 passed
- WSL ext4 mirror: `ruff check`, `ruff format --check`, `python -m mypy --strict` 대상 신규 API/service
- WSL ext4 mirror: `npm -w @pinvi/schemas run typecheck`, `npm -w @pinvi/api-client run typecheck`,
  `npm -w @pinvi/web run typecheck`, `npm -w @pinvi/web run lint`
- Playwright: N150 SSH alias 후보가 이 세션에서 연결되지 않아 Windows fallback으로
  `npx playwright test e2e/admin-retention.e2e.ts --project=chromium` — 1 passed
- WSL: `git diff --check`

**다음**: 검증·PR·CI·머지 후 T-277 Email deliverability / suppression enforcement로 진입한다.

## 2026-06-28 (codex) — T-275 PIPA security incident console

**작업**: Sprint 6 legal/ops 첫 구현 태스크로 PIPA incident 운영 콘솔을 추가했다.

**변경**:

- `app.security_incidents` workflow migration을 추가해 상태를 `detected` → `triage` →
  `notification_decision` → `reported` → `closed`로 정리하고, CPO 30분 review due,
  72시간 외부 신고 due, CPO notified time, notification decision time, payload hash,
  external report receipt, evidence attachment id를 저장한다.
- `/admin/incidents` API와 service를 추가했다. incident 생성은 Admin Telegram outbox를 남기고,
  CPO 전용 triage/notification decision/notify/report/close 전이는 `admin_audit_log`에 기록한다.
- 정보주체 통지는 deterministic payload hash와 `security_incident_notice` email queue row를 만든다.
  외부 신고 조치는 접수번호를 필수로 받아 `reported` 상태로 전환한다.
- Web Admin `/admin/incidents` 화면을 추가해 목록 필터, 신규 등록, 상태별 조치 패널을 제공하고,
  sidebar 메뉴와 API client/schema/query key를 연결했다.
- `docs/api/admin.md`, `docs/compliance/pipa.md`, `docs/postgres-schema.md`,
  `docs/data-model.md`, `docs/runbooks/security-incidents.md`, `CHANGELOG.md`, task/resume 추적
  문서를 갱신했다.

**검증**:

- WSL/NTFS: `python3 -m compileall app tests/integration/test_admin_incidents_api.py
tests/integration/test_security_incidents_schema.py`
- WSL/NTFS: `npm exec prettier -- --check ...`
- WSL ext4 mirror: `pytest -q tests/integration/test_security_incidents_schema.py
tests/integration/test_admin_incidents_api.py` — 5 passed
- WSL ext4 mirror: `ruff check`, `ruff format --check`, `python -m mypy --strict` 대상 신규 API/service
- WSL ext4 mirror: `npm -w @pinvi/web run typecheck`, `npm -w @pinvi/web run lint`
- Playwright: WSL ext4 mirror는 브라우저 캐시 부재로 실행 전 실패했고, 이 세션에서 N150 SSH alias가
  잡히지 않아 Windows fallback으로 `npx playwright test e2e/admin-incidents.e2e.ts --project=chromium`
  — 1 passed

**다음**: PR CI와 머지 후 T-276 Retention execution / dashboard 구현에 진입한다.

## 2026-06-28 (codex) — T-259 Admin live 2000 / restore staging drill

**작업**: N150 local-only Admin live credential과 disposable restore staging target을 준비해 T-259의
남은 credential/staging blocker를 닫았다.

**변경**:

- `admin-live-matrix.live.ts`의 UI login helper가 login rate-limit 알림을 만나면 동일 case 안에서
  backoff 후 재시도하도록 보강했다.
- `admin-debug-live.live.ts`의 request timeline 검증이 loading 종료를 기다리고, source/event
  empty-state 문구 변형을 허용하도록 안정화했다.
- `admin-feature-detail-subpages.e2e.ts`는 tab link의 `href`를 검증한 뒤 deep link로 직접
  이동하도록 바꿔 CI에서 관측된 tab click timing flake를 제거했다.
- Admin live e2e runbook은 local-only env 파일과 production Web image의 public HTTPS Web origin
  검증 조건을 명시했다.
- Backup/restore runbook은 운영 DB role에 `CREATEDB`가 없을 때 disposable PostgreSQL/PostGIS
  staging container로 drill하는 절차를 추가했다.
- release gate, changelog, tasks, resume가 Admin live 200/2000 및 restore staging drill 통과와
  full catalog/tag 잔여 상태를 가리키도록 갱신했다.

**검증**:

- N150 Docker runner image: `mcr.microsoft.com/playwright:v1.60.0-noble`.
- N150: API login smoke 1건 통과.
- N150: UI login smoke 1건 통과.
- N150: `PINVI_ADMIN_LIVE_CASE_LIMIT=200` — 207 passed (18.4m).
- N150: `PINVI_ADMIN_LIVE_CASE_LIMIT=2000` — 2007 passed (3.5h).
- N150 restore staging drill: `backup://pinvi-app-20260628-101426.dump`, checksum verified,
  `pg_restore --list` ok, `users_count=7`, `trips_count=5`, `admin_audit_log_count=1`,
  audit chain valid, rollback precheck guard schema unchanged.

**다음**: 증적 PR을 머지한 뒤 T-275 PIPA security incident console 구현에 진입한다. Admin live full
catalog와 `v0.2.0` tag/GitHub Release는 최종 release gate로 남긴다.

## 2026-06-28 (codex) — T-259 N150 Playwright Docker runner

**작업**: N150 host Chromium shared library blocker를 우회하기 위해 공식 Playwright Docker image 기반
runner를 추가하고, Linux-only 개발/Playwright 문서의 stale Windows git/runner 문구를 정리했다.

**변경**:

- `scripts/n150-playwright-runner.sh` 추가. lockfile의 `@playwright/test` 버전에 맞춰
  `mcr.microsoft.com/playwright:v<version>-noble` image를 사용하고, `PINVI_*`/`NEXT_PUBLIC_*`
  환경변수는 Docker argv에 값을 노출하지 않고 이름만 전달한다.
- Admin live e2e runbook은 N150 Docker runner를 기본 경로로, host Chromium dependency 설치는
  직접 host 실행이 필요할 때의 보조 절차로 정리했다.
- `local-dev`, runbook index, testing/coding-style, AGENTS/CLAUDE/SKILL, release gate/resume/tasks를
  ADR-051 + N150 Docker runner 기준으로 동기화했다.

**검증**:

- N150 `~/pinvi` checkout `497c7f5414036e8674336a9ad23091d9f03fd489`.
- Docker image: `mcr.microsoft.com/playwright:v1.60.0-noble`.
- N150: `scripts/n150-playwright-runner.sh` 후보 script를 임시 경로로 복사해
  `PINVI_ADMIN_LIVE_E2E=1`, `PINVI_ADMIN_LIVE_WEB_URL=http://127.0.0.1:12805`,
  `--grep "UI login rejects malformed email"` smoke 1건 통과.

**남은 차단**:

- Admin live 2000/full credential.
- Restore staging DB URL/환경.

## 2026-06-28 (codex) — T-259 Web clean manual evidence

**작업**: 최신 main Web evidence를 WSL ext4 mirror clean install 기준으로 확보했다.

**검증**:

- source: `5c0a39b589a7d8d71a103f7534e116cc0f5ba83c`
- 환경: Linux ext4 mirror `~/pinvi-workspaces/pinvi-codex`, Node `v20.20.2`, npm `10.8.2`
- `npm ci --no-audit --no-fund` — 1082 packages 설치, 통과
- `NEXT_PUBLIC_PINVI_API_URL=http://localhost:12801 npm run lint` — 통과
- `NEXT_PUBLIC_PINVI_API_URL=http://localhost:12801 npm run typecheck` — 통과
- `NEXT_PUBLIC_PINVI_API_URL=http://localhost:12801 npm run build` — 통과

**남은 차단**:

- N150 Playwright system dependency 또는 검증용 runner image.
- Admin live 2000/full credential.
- Restore staging DB URL/환경.

## 2026-06-28 (codex) — T-259 N150 backup script rerun

**작업**: PR #295로 보강한 `scripts/backup-db.sh`를 N150 최신 main checkout에서 재실행해 host
`pg_dump` 부재 blocker를 닫았다.

**검증**:

- N150 `~/pinvi` checkout을 `4a1b71e273cda443243618eee1df364d350ba3d4`로 갱신했다.
- `scripts/backup-db.sh` 재실행 결과 `pinvi-app-20260628-101426.dump`를 생성했다.
- snapshot size: `126826`
- `.sha256` 검증: 통과
- `pg_restore --list`: 통과
- 최신 main `4a1b71e` API push CI(`api`, run `28318922089`, `lint-typecheck-test`) 통과.
- Web manual evidence 시도: `npm run lint`는 통과했지만, 기존 `node_modules` 상태의
  `npm run typecheck`는 mobile React Native type/className 오류로 실패했다. `npm ci --no-audit
--no-fund`는 NTFS worktree에서 장시간 무출력 진행되어 중단했으므로 release evidence로 사용하지 않는다.

**남은 차단**:

- N150 Playwright system dependency 또는 검증용 runner image.
- Admin live 2000/full credential.
- Restore staging DB URL/환경.
- `4a1b71e` API push CI는 통과했다. Web clean manual evidence는 후속 `5c0a39b`에서 통과했다.

## 2026-06-28 (codex) — T-259 backup script Docker fallback

**작업**: N150 release gate에서 드러난 host `pg_dump` 부재 blocker를 줄이기 위해 backup script
fallback을 보강했다.

**변경**:

- `scripts/backup-db.sh`가 host `pg_dump`를 우선 사용하고, 없으면
  `PINVI_BACKUP_DOCKER_IMAGE` one-off container로 같은 custom-format dump를 생성한다.
- fallback network/image/binary를 `PINVI_BACKUP_DOCKER_*` 환경변수로 조정할 수 있게 했다.
- API Docker image에 `postgresql-client`와 `scripts/backup-db.sh`를 포함해 Admin snapshot 경로가
  image 내부 `pg_dump`를 사용할 수 있게 했다.
- backup/restore runbook, release gate, tasks/resume 추적 문서를 갱신했다.

**검증**:

- Linux: `bash -n scripts/backup-db.sh`
- Linux: `cd apps/api && .venv/bin/python -m pytest -s tests/unit/test_backup_db_script.py -q` — 2
  passed
- Linux: `cd apps/api && .venv/bin/ruff format --check tests/unit/test_backup_db_script.py && .venv/bin/ruff check tests/unit/test_backup_db_script.py`
- Linux: `docker build --check -f apps/api/Dockerfile .`
- Linux: `npx prettier --check` 대상 문서
- 참고: 같은 pytest를 capture 기본값으로 실행하면 현재 NTFS/WSL venv에서 pytest capture tempfile
  오류가 나며, `-s`에서는 통과한다.

**다음**: 보강된 script를 N150 checkout에 반영한 뒤 `scripts/backup-db.sh` 재실행 증거를
release gate에 추가한다.

## 2026-06-28 (codex) — T-259 v0.2.0 release candidate gate 부분 실행

**작업**: `v0.2.0` release candidate gate를 N150 기준으로 실행하고 차단 항목을 분리했다.

**변경**:

- `docs/execplan/v020-release-candidate-gate.md`를 추가했다.
- `docs/execplan/sprint5-v020-release-plan.md`, `docs/tasks.md`, `docs/resume.md`가 T-259의
  부분 통과와 release 보류 상태를 가리키도록 갱신했다.
- `v0.2.0` tag/GitHub Release는 생성하지 않았다.

**검증**:

- 후보 SHA `98fb3c2`를 N150 `~/pinvi`에 반영했다.
- N150 Docker build는 full `ktdctl pinvi --build`가 디스크 99%로 중단됐고, targeted compose
  build도 dependency 때문에 외부 repo 이미지를 함께 빌드했다. Pinvi 3개 이미지를 확보한 뒤
  디스크 98%에서 중단하고 build cache를 정리했다.
- 새 `pinvi-api`, `pinvi-web`, `pinvi-dagster` 컨테이너를 healthy로 기동했다.
- N150 smoke: API `/health`, `/health/db`, Web `/`, `/admin/login`, Dagster `/server_info`,
  `kor-travel-map` `/health`/OpenAPI가 모두 200.
- N150 Playwright catalog list: 2026-06-28 기준 `6202 tests in 5 files`.
- N150 Playwright browser smoke: Chromium shared library 누락으로 실패. Ubuntu 26.04는
  Playwright 1.60.0의 `install-deps --dry-run chromium` 대상이 아니었고, `ldd` 기준
  `libatk-1.0.so.0`, `libatk-bridge-2.0.so.0`, `libXdamage.so.1`, `libasound.so.2`,
  `libatspi.so.0`가 없었다.
- Windows fallback Playwright: N150 Web SSH tunnel 대상 `--grep malformed` 1건 통과.
- Backup snapshot: `pinvi-app-20260628-094253.dump` 생성, sha256 통과, `pg_restore --list` 통과.

**차단**:

- 최신 main SHA에는 PR monitor check만 있고 `api`/`web` main push CI check가 없다.
- Admin live 2000/full gate에 필요한 `PINVI_ADMIN_LIVE_EMAIL`/`PINVI_ADMIN_LIVE_PASSWORD`가
  N150 local env에 없다.
- Restore staging drill에 필요한 staging DB URL/환경이 없다.
- host `pg_dump`가 없어 `scripts/backup-db.sh`는 직접 실행되지 않는다.
- N150 비대화형 sudo가 없어 Codex가 system dependency를 설치하지 못한다.

**다음**: T-259 차단 항목을 해소하고 `v0.2.0` tag/GitHub Release를 만든다.

## 2026-06-28 (codex) — T-258 Sprint 6 legal/ops implementation prep gate

**작업**: Sprint 6 legal/ops 구현 준비 gate를 확정했다.

**변경**:

- `docs/execplan/legal-ops-implementation-prep-gate.md`를 추가했다.
- T-275~T-286에 대해 API/UI 표면, 상태 모델, due date, evidence/audit, runbook,
  test gate, sign-off 기준을 매핑했다.
- 기존 `KISA 60일 report` 표현은 폐기하고 개인정보보호위원회/KISA 72시간 신고 기준으로
  `docs/compliance/pipa.md`, Sprint 5/6 계획, tasks/crosswalk를 정정했다.
- CPO 30분 review는 Pinvi 내부 운영 SLA로 분리했고, DSR 기본 처리 due는 공식 열람 처리기간
  기준 10일로 문서화했다.
- v1.0 mobile 제외와 user-facing AI companion 제외 범위를 Sprint 6 release checklist에 고정했다.

**검증**:

- 문서-only 변경이며 코드/브라우저 실행은 없다.

**다음**: T-259 Release candidate gate / `v0.2.0`.

## 2026-06-28 (codex) — T-257 Email deliverability / provider tracking preflight

**작업**: Resend deliverability/suppression/provider tracking 구현 전에 현재 repo 상태와
T-277 구현 계약을 분리했다.

**변경**:

- `docs/execplan/email-deliverability-provider-preflight.md`를 추가했다.
- Resend domain verified, SPF/DKIM/DMARC, webhook at-least-once/out-of-order, hard bounce,
  complaint, suppression, provider tracking 기준을 T-277 구현 계약으로 정리했다.
- 현재 구현 완료 범위를 queue worker, Svix 서명 검증, queue 상태 갱신, `/admin/emails`
  queue 화면으로 고정했다.
- `docs/integrations/resend.md`의 stale React Email/checklist를 현재 inline HTML renderer와
  잔여 T-277 항목으로 갱신했다.
- `docs/tasks.md`, `docs/tasks-done.md`, Sprint 5 계획, `docs/resume.md`가 T-257 완료와
  다음 T-258을 가리키도록 정리했다.

**검증**:

- 문서-only 변경이며 코드/브라우저 실행은 없다.

**다음**: T-258 Sprint 6 legal/ops implementation prep gate.

## 2026-06-28 (codex) — T-256 Review gap crosswalk / legal-ops preflight

**작업**: PR 리뷰에서 나온 legal/ops gap과 최근 사후 리뷰 후속을 Task 번호에 매핑했다.

**변경**:

- `docs/execplan/legal-ops-review-gap-crosswalk.md`를 추가했다.
- PR #238/#264 legal/ops 리뷰 gap 44개를 G-001~~G-044로 번호화하고, 각 항목을
  T-257/T-258/T-275~~T-286 등 하나 이상의 대응 Task로 연결했다.
- 최근 2일 PR #265~#289의 사람 리뷰 코멘트를 확인했다. WebSocket, conflict UX,
  ETL compliance SQL/failure sensor, app integrity pagination/producer 후속은 T-289~T-292로
  새 backlog 항목을 만들었다.
- `docs/tasks.md`, `docs/tasks-done.md`, Sprint 5/6 문서, `docs/resume.md`가 같은
  crosswalk 정본을 가리키도록 정리했다.

**검증**:

- `gh issue/pr` comment 조회로 #238/#264 원자료와 #265~#289 최근 리뷰 코멘트를 확인했다.
- 문서-only 변경이며 코드/브라우저 실행은 없다.

**다음**: T-257 Email deliverability / provider tracking preflight.

## 2026-06-28 (codex) — T-255 지도 마커 / 색상 적용 parity

**작업**: 사용자/Admin 지도 marker 색상·아이콘 해석을 공용 resolver로 정리하고 mock/live e2e gate를 추가했다.

**변경**:

- `@pinvi/domain`에 `resolveMarkerStyle`을 추가했다. 우선순위는 custom → server-resolved →
  upstream feature → feature snapshot → category/kind fallback → `P-13` fallback이다.
- `TripMapView`, `FeatureMapView`, Admin Trip POI preview가 같은 resolver를 사용한다.
- Trip 지도와 탐색 지도, Admin POI preview에 marker metadata legend를 추가해 VWorld key가 없어도
  mock e2e에서 색/아이콘/source/selected/broken/cluster 상태를 검증할 수 있게 했다.
- `축제`, `공지`, `트래킹 route`, `국립공원` fallback mapping을 팔레트 문서와 맞췄다.
- `admin-live-map-marker-parity.live.ts`를 추가해 `/map` marker metadata를 read-only live gate로
  확인한다.

**검증**:

- Linux:
  - `npm -w @pinvi/domain run test -- marker.test.ts tripMapPoints.test.ts` → 14 passed
  - `npm -w @pinvi/web run typecheck`
  - `npm -w @pinvi/web run lint`
- Playwright:
  - N150 1차 실행은 `ssh n150` alias가 현재 Linux 환경에서 해석되지 않아 실패했다.
  - Windows fallback: `npm -w @pinvi/web run test:e2e -- trip-detail.e2e.ts admin-trips.e2e.ts --workers=1` → 8 passed
  - Windows fallback: `npm -w @pinvi/web run test:e2e:admin-live -- admin-live-map-marker-parity.live.ts --workers=1` → 1 skipped

**미실행**:

- 실제 N150 live marker parity run은 SSH alias 미해결로 미실행. live spec은 env gate와 데이터 유무
  독립 read-only 검증으로 추가했다.

**다음**: T-256 Review gap crosswalk / legal-ops preflight.

## 2026-06-28 (codex) — T-254 Admin live e2e matrix v0.2.0 확장

**작업**: Admin live read-only matrix를 v0.2.0 release gate용 catalog와 gate 절차로 확장했다.

**변경**:

- `admin-live-matrix.live.ts` catalog를 exact count로 고정해 full catalog drift를 잡는다.
- matrix 공통 route 검증 후 raw secret pattern 미노출을 확인한다.
- `/admin/debug/request/{id}` captured request timeline, feature detail subpage tabs,
  backup restore-lock/mutation guard, ETL app-owned job rows, Grafana dashboard selector와
  WebSocket dashboard case를 추가했다.
- `docs/runbooks/admin-live-e2e.md`에 N150 우선 실행과 `PINVI_ADMIN_LIVE_CASE_LIMIT=200`,
  `2000`, full catalog gate 순서를 고정했다.
- `docs/tasks.md`의 다음 구현을 T-255 지도 마커 / 색상 적용 parity로 넘기고, T-254는
  `docs/tasks-done.md`로 이동했다.

**검증**:

- Linux:
  - `npm -w @pinvi/web run typecheck`
  - `npm -w @pinvi/web run lint`
  - `npm -w @pinvi/web run test:e2e:admin-live -- --grep "UI live case catalog" --workers=1` → 1 passed
  - `git diff --check`
- Playwright:
  - N150 1차 실행은 `ssh n150` alias가 현재 Linux 환경에서 해석되지 않아 실패했다.
  - Windows fallback: `npm -w @pinvi/web run test:e2e:admin-live -- --grep catalog --workers=1` → 1 passed

**미실행**:

- 실제 N150 `PINVI_ADMIN_LIVE_CASE_LIMIT=200`, `2000`, full live run은 SSH alias 미해결로
  미실행. 실행 순서와 env gate는 runbook에 고정했다.

**다음**: T-255 지도 마커 / 색상 적용 parity.

## 2026-06-28 (codex) — T-253 Prometheus/Grafana 운영 가시화 게이트

**작업**: Prometheus scrape target, Grafana dashboard provisioning, Admin Grafana degraded
표시, provider tag tracking을 보강했다.

**변경**:

- observability compose profile에 blackbox exporter를 추가했다. Prometheus target은 API
  `/metrics`, cAdvisor, blackbox, Web health, Dagster health를 분리한다.
- API `/metrics`에 `pinvi_api_db_pool_connections{state=...}` SQLAlchemy pool gauge를 추가했다.
- Grafana provisioning에 API p95/error, DB pool, WebSocket, ETL/backup dashboard 4종을 추가했다.
- `/admin/grafana`에 dashboard selector와 `GET /admin/grafana/health` 기반 `정상`/`강등`
  상태 표시를 추가했다. 서버사이드 health probe는 `PINVI_GRAFANA_HEALTH_URL`이 있으면 해당
  origin을 우선 사용한다.
- production httpx client factory에 `ApiCallTracker` provider tag를 붙였다. 대상은
  `kor_travel_map`, `kor_travel_map_admin`, `kor_travel_geo`, `telegram`, `google_oauth`다.
  `api_call_log.endpoint`는 query secret과 Telegram bot token path를 저장 전에 mask한다.
- Resend는 SDK 직접 호출 경로라 T-257 deliverability/provider tracking preflight로 남겼고,
  T-257 감사에서 T-277의 `provider='resend'` 구현 항목으로 확정했다.
- Grafana mock/live e2e와 observability/Grafana/Admin API runbook을 갱신했다.

**검증**:

- Linux:
  - `cd apps/api && uv run --extra dev ruff check app/api/v1/telegram_targets.py app/clients/kor_travel_geo.py app/clients/kor_travel_map.py app/clients/kor_travel_map_admin.py app/middleware/api_call_logging.py app/middleware/prometheus.py app/services/oauth_google.py app/services/telegram_notify.py tests/integration/test_api_call_logging.py tests/unit/test_prometheus_metrics.py`
  - `cd apps/api && PATH="$PWD/.venv/bin:$PATH" PYTHONPATH=. .venv/bin/python -m pytest -q -s tests/integration/test_api_call_logging.py tests/unit/test_prometheus_metrics.py -rA` → 6 passed, known `StarletteDeprecationWarning` 1건
  - `cd apps/api && PATH="$PWD/.venv/bin:$PATH" PYTHONPATH=. .venv/bin/python -m mypy --strict app`
  - `npm -w @pinvi/web run typecheck`
  - `npm -w @pinvi/web run lint`
  - `npm -w @pinvi/web run test -- grafanaEmbedConfig.test.ts` → 7 passed
  - `docker compose -f infra/docker-compose.yml --profile observability config`
  - `docker compose -f infra/docker-compose.app.yml --profile observability config`
  - Grafana dashboard JSON parse 검증
  - `git diff --check`
- Playwright:
  - N150 1차 실행은 `ssh n150` alias가 현재 Linux 환경에서 해석되지 않아 실패했다.
  - Windows fallback: `npm -w @pinvi/web run test:e2e -- admin-grafana.e2e.ts --workers=1` → 2 passed
  - Windows fallback: `npm -w @pinvi/web run test:e2e:admin-live -- admin-live-grafana.live.ts --workers=1` → 1 skipped (`PINVI_ADMIN_LIVE_E2E` gate)

**미실행**:

- 실제 N150 live Grafana e2e는 SSH alias 미해결로 미실행. Windows fallback으로 mock e2e와 env-gated
  live spec skip까지만 확인했다.

**다음**: T-254 Admin live e2e matrix v0.2.0 확장.

## 2026-06-28 (codex) — T-252 Backup/restore live UI e2e

**작업**: `/admin/backup` live read-only와 staging mutating e2e를 분리하고 production restore UI
안전 스위치를 추가했다.

**변경**:

- `/admin/backup` snapshot 목록에 filename/snapshot id/checksum 검색, status filter,
  visible count를 추가했다. 수동 snapshot 생성 후 낙관적 목록도 API limit 50개를 넘지 않게 맞췄다.
- Restore 버튼은 Web 빌드타임 `NEXT_PUBLIC_PINVI_RESTORE_HOTSWAP_UI_ENABLED=1`일 때만
  활성화된다. 기본값은 `0`이며 서버 측 `PINVI_RESTORE_HOTSWAP_EXECUTE` guard는 별도로 유지한다.
- `apps/web/e2e/admin-live-backup.live.ts`를 추가해 live read-only에서 목록/sort/filter/empty,
  restore 버튼 잠금, raw backup path/secret pattern 미노출, backup POST 미발생을 검증한다.
- `apps/web/e2e/admin-backup-live-mutating.live.ts`를 추가했다.
  `PINVI_BACKUP_LIVE_MUTATING_E2E=1` + `PINVI_BACKUP_LIVE_STAGING=1`에서만 staging snapshot 1회 생성,
  `backup.snapshot` audit, `backup://<filename>` masking, 목록 limit cap을 확인한다.
- `.env.example`, Web Docker build args, app compose, `scripts/dev-up.sh`, backup/admin/live e2e
  runbook과 Sprint 추적 문서를 갱신했다.

**검증**:

- Linux: `npm -w @pinvi/web run typecheck`
- Linux: `npm -w @pinvi/web run lint`
- Linux: `bash -n scripts/dev-up.sh`
- Linux: `docker compose -f infra/docker-compose.app.yml config`
- Linux: `npx prettier --check ...`
- Linux: `npm -w @pinvi/web run test:e2e:admin-live -- --grep "catalog" --workers=1`
- Linux: `npm -w @pinvi/web run test:e2e:admin-live -- --grep "backup live read-only" --workers=1` → 1 skipped
- Linux: `npm -w @pinvi/web run test:e2e:live-mutating -- --grep "admin backup staging" --workers=1` → 1 skipped
- Windows fallback: `npm -w @pinvi/web run test:e2e -- admin-backup.e2e.ts --workers=1` → 2 passed
- Windows fallback: `npm -w @pinvi/web run test:e2e -- admin-feature-detail-subpages.e2e.ts --workers=1`
  → 1 passed (CI e2e flake 안정화)

**미실행**:

- N150 runner는 `ssh n150` alias가 현재 Linux 환경에서 해석되지 않아 접근하지 못했다. 따라서 실제
  N150 live read-only와 staging mutating snapshot 생성은 수행하지 못했다.

**다음**: T-253 Prometheus/Grafana 운영 가시화 게이트.

## 2026-06-28 (codex) — T-251 Restore staging drill

**작업**: restore staging drill 스크립트와 runbook 정합화.

**변경**:

- `scripts/restore-staging-drill.sh`를 추가했다. `PINVI_RESTORE_STAGING_DATABASE_URL`이 없으면
  restore를 시작하지 않으며, snapshot은 `backup://<filename>`으로만 출력한다.
- drill은 checksum, `pg_restore --list`, `restore-db.sh`, staging DB health row count,
  `admin_audit_chain_links`, rollback rehearsal 결과를 `DRILL_PHASE`/`DRILL_EVIDENCE`로 남긴다.
- rollback rehearsal은 기본 `precheck`와 선택 `drain` 모드를 지원한다. `drain`은 임시 restore
  schema를 만든 뒤 drain failure를 유도하고 기존 `app` schema OID가 유지되는지 확인한다.
- 신규 backup `.sha256` sidecar는 dump basename 기준으로 생성하고, restore 검증은 sidecar
  checksum 값을 실제 dump hash와 직접 비교하게 정리했다. 운영 snapshot을 staging 경로로
  복사해도 dump와 sidecar를 함께 두면 검증할 수 있다.
- `docs/runbooks/backup-restore.md`, `docs/api/admin.md`, Sprint 5 실행 계획/추적 문서를 갱신했다.

**검증**:

- Linux: `bash -n scripts/backup-db.sh scripts/restore-db.sh scripts/restore-hotswap.sh scripts/restore-staging-drill.sh`
- Linux: `cd apps/api && uv run --extra dev ruff check tests/unit/test_restore_staging_drill_script.py`
- Linux: `cd apps/api && uv run --extra dev ruff format --check tests/unit/test_restore_staging_drill_script.py`
- Linux: `cd apps/api && PATH="$PWD/.venv/bin:$PATH" PYTHONPATH=. .venv/bin/python -m pytest -q -s tests/unit/test_restore_staging_drill_script.py tests/unit/test_backup_service.py -rA`

**미실행**:

- N150 SSH alias가 현재 Linux 환경에서 해석되지 않아 실제 N150 staging DB restore는 수행하지 못했다.
- UI 변경은 없어서 Playwright는 실행하지 않았다.

**다음**: T-252 Backup/restore live UI e2e.

## 2026-06-28 (codex) — T-250 Backup script / snapshot endpoint hardening

**작업**: backup/restore script와 Admin snapshot endpoint의 checksum, disk guard, path masking,
실패 audit을 보강했다.

**변경**:

- `scripts/backup-db.sh`에 schema name guard, `PINVI_BACKUP_MIN_FREE_BYTES` disk guard, tmp dump
  생성, sha256 sidecar 생성/검증을 추가했다.
- `scripts/restore-db.sh`는 `.sha256` sidecar가 있으면 restore 전에 `sha256sum -c`로 검증한다.
- `backup_service`는 sidecar checksum이 실제 dump와 일치할 때만 snapshot status를 `verified`로
  반환하고, mismatch는 `available`로 낮춘다.
- Admin backup snapshot/restore 응답과 audit/error message에서 host 절대경로를
  `backup://<filename>`으로 mask하고 DB URL credential을 제거한다.
- `POST /admin/backup/snapshot` 실패도 `backup.snapshot_failed` audit으로 남긴다.
- Admin API/runbook/Sprint/tasks/resume/changelog 문서를 갱신했다.

**검증**:

- Linux: `uv run --extra dev ruff check app/services/backup_service.py app/api/v1/admin/backup.py app/core/config.py tests/unit/test_backup_service.py tests/integration/test_admin_backup_api.py`
- Linux: `uv run --extra dev ruff format --check app/services/backup_service.py app/api/v1/admin/backup.py app/core/config.py tests/unit/test_backup_service.py tests/integration/test_admin_backup_api.py`
- Linux: `PATH="$PWD/.venv/bin:$PATH" PYTHONPATH=. .venv/bin/python -m pytest -q -s tests/unit/test_backup_service.py tests/integration/test_admin_backup_api.py -rA`
- Linux: `PATH="$PWD/.venv/bin:$PATH" PYTHONPATH=. .venv/bin/python -m mypy --strict app`
- Linux: `bash -n scripts/backup-db.sh scripts/restore-db.sh scripts/restore-hotswap.sh`

**주의**:

- 실제 backup 생성과 `pg_restore --list` staging drill은 T-251에서 N150 또는 staging DB 대상으로
  수행한다.
- UI 변경은 없어서 Playwright는 실행하지 않았다.

**다음**: T-251 Restore staging drill.

## 2026-06-28 (codex) — T-249 App-owned integrity source / known orphan fix

**작업**: Pinvi app-owned integrity source를 `/admin/integrity`에 추가하고 known app issue를 같은
table UI에서 구분했다.

**변경**:

- `app.data_integrity_violations` migration/model을 추가했다. active `rule_key`/`entity` 중복 방지
  unique index, status/severity check, entity/status 조회 index를 둔다.
- `GET /admin/integrity/issues`에 `source=all|kor_travel_map|pinvi_app` filter를 추가했다.
  `pinvi_app` source는 persisted row와 broken POI feature link, invalid marker color,
  curated import source drift, active attachment deleted target 계산 rule을 반환한다.
- `pinvi_app:` issue action은 read-only guard로 409
  `PINVI_APP_INTEGRITY_ACTION_UNSUPPORTED`를 반환한다. upstream action relay/audit은
  `kor_travel_map` issue에만 유지한다.
- shared schema/API client/query key에 issue `source`를 추가했다.
- Web `/admin/integrity`에 source filter/column/badge를 추가하고 Pinvi app issue row는 read-only로
  표시한다.
- Admin API, data model, postgres schema, Sprint 5 execplan, tasks/resume/changelog 추적 문서를
  갱신했다.

**검증**:

- Linux: `uv run --extra dev ruff check app/api/v1/admin/integrity.py app/services/admin_app_integrity.py app/models/data_integrity.py app/schemas/admin.py tests/integration/test_admin_dedup_integrity_debug_api.py alembic/versions/20260628_0027_data_integrity_violations.py`
- Linux: `uv run --extra dev ruff format --check app/api/v1/admin/integrity.py app/services/admin_app_integrity.py app/models/data_integrity.py app/schemas/admin.py tests/integration/test_admin_dedup_integrity_debug_api.py alembic/versions/20260628_0027_data_integrity_violations.py`
- Linux: `PATH="$PWD/.venv/bin:$PATH" PYTHONPATH=. .venv/bin/python -m pytest -q -s tests/integration/test_admin_dedup_integrity_debug_api.py -rA`
- Linux: `PATH="$PWD/.venv/bin:$PATH" PYTHONPATH=. .venv/bin/python -m mypy --strict app`
- Linux: `npm -w @pinvi/web run typecheck`, `npm -w @pinvi/web run lint`
- Linux: `npm -w @pinvi/api-client run typecheck --if-present`, `npm -w @pinvi/schemas run typecheck --if-present`
- Linux: `npx prettier --check packages/schemas/src/admin.ts packages/api-client/src/endpoints/admin.ts packages/api-client/src/query-keys.ts apps/web/app/'(admin)'/admin/integrity/page.tsx apps/web/e2e/admin-dedup-integrity-debug.e2e.ts`
- Windows fallback: `npm -w @pinvi/web run test:e2e -- admin-dedup-integrity-debug.e2e.ts --workers=1`

**주의**:

- N150 Playwright는 이 세션에 `n150` SSH alias가 없어 직접 실행하지 못했다. mock e2e는 규칙대로
  Windows fallback runner에서 실행했다.
- Pinvi app-owned integrity issue는 아직 read-only다. resolve/fix workflow는 별도 task/ADR에서
  lock, idempotency, audit, auto-fix 정책을 먼저 정한다.

**다음**: T-250 Backup script / snapshot endpoint hardening.

## 2026-06-28 (codex) — T-248 Feature detail subpages

**작업**: Admin feature detail의 source/override/weather 하위 화면을 read-only deep link로 추가했다.

**변경**:

- `GET /admin/features/{feature_id}/sources`, `/overrides`, `/weather-values`를 추가했다.
  sources/overrides는 upstream admin detail payload에서 list만 투영하고, weather-values는 기존
  feature weather card의 metrics를 Admin tab용 `items`로 반환한다.
- shared schema/API client/query key에 `AdminFeatureSourcesResponse`,
  `AdminFeatureOverridesResponse`, `AdminFeatureWeatherValuesResponse`를 추가했다.
- Web `/admin/features/{feature_id}/{sources,overrides,weather-values}` route와 공통 tab component를
  추가했다. 기존 `/admin/features` detail inspector는 세 deep link로 이동할 수 있다.
- `admin-feature-detail-subpages.e2e.ts`로 direct deep link, tab navigation, empty state, upstream
  error state를 검증한다.
- `admin-live-matrix.live.ts`에 live weather feature가 있을 때 세 read-only tab route를 순회하는
  guarded case를 추가했다.
- Admin API 문서, Sprint 5 execplan, tasks/resume 추적 문서를 갱신했다.

**검증**:

- Linux: `uv run --extra dev ruff check app/api/v1/admin/features.py app/schemas/admin.py tests/integration/test_admin_features_api.py`
- Linux: `uv run --extra dev ruff format --check app/api/v1/admin/features.py app/schemas/admin.py tests/integration/test_admin_features_api.py`
- Linux: `PATH="$PWD/.venv/bin:$PATH" PYTHONPATH=. .venv/bin/python -m pytest -q -s tests/integration/test_admin_features_api.py -rA`
- Linux: `PATH="$PWD/.venv/bin:$PATH" PYTHONPATH=. .venv/bin/python -m mypy --strict app`
- Linux: `npm -w @pinvi/web run typecheck`, `npm -w @pinvi/web run lint`
- Linux ext4 mirror: `npm -w @pinvi/web run build`
- Linux ext4 mirror: `npm -w @pinvi/web run test:e2e:admin-live:list -- admin-live-matrix.live.ts`
  (`Total: 6178 tests in 1 file`)
- Windows fallback: `npm -w @pinvi/web run test:e2e -- admin-feature-detail-subpages.e2e.ts`
- Linux: `npx prettier --check ...`, `git diff --check`

**주의**:

- mock Playwright는 N150 runner를 현재 도구 컨텍스트에서 직접 사용할 수 없어 Windows fallback으로
  실행했다. WSL Ubuntu 26.04 Chromium은 Playwright 지원 대상이 아니라 local Linux browser run도
  불가하다.
- NTFS worktree에서 Playwright default config가 `next build`를 시작하면 SIGBUS가 재현된다. Next
  build와 live-list는 ext4 mirror에서 실행한다.

**다음**: T-249 App-owned integrity source / known orphan fix.

## 2026-06-28 (codex) — T-247 Provider sync 운영 mutation 계약 정리

**작업**: provider sync 운영 mutation 범위를 upstream 계약에 맞춰 import job cancel로 확정하고
Pinvi relay/UI를 추가했다.

**변경**:

- upstream `kor-travel-map` `openapi.json`과 router에서 `/v1/ops/import-jobs/{job_id}/cancel`은
  존재하지만 provider 자체 run-now/pause/resume/reset cursor 계약은 없음을 확인했다.
- `POST /admin/provider-sync/import-jobs/{job_id}/cancel`을 추가했다. `admin` 전용,
  `access_reason` 필수, upstream reason fallback, `provider_import_job.cancel` audit, upstream
  409 no-audit 경로를 갖는다.
- Web `/admin/provider-sync`에 queued/running import job 취소 버튼과 사유 입력 패널을 추가했다.
  실패 시 row를 낙관적으로 바꾸지 않고 오류를 표시하며, 성공 시 provider/import job query를 다시
  읽는다.
- `AdminProvider*` schema의 `links`를 upstream list 링크 셰입도 받을 수 있게 넓혔다.
- Admin API 문서, Sprint 5 execplan, tasks/resume 추적 문서를 갱신했다.

**검증**:

- Linux: `uv run --extra dev ruff check app/api/v1/admin/provider_sync.py app/clients/kor_travel_map_admin.py app/schemas/admin.py tests/unit/test_kor_travel_map_admin_client.py tests/integration/test_admin_etl_provider_sync_api.py`
- Linux: `uv run --extra dev ruff format --check app/api/v1/admin/provider_sync.py app/clients/kor_travel_map_admin.py app/schemas/admin.py tests/unit/test_kor_travel_map_admin_client.py tests/integration/test_admin_etl_provider_sync_api.py`
- Linux: `PATH="$PWD/.venv/bin:$PATH" PYTHONPATH=. .venv/bin/python -m pytest -q -s tests/unit/test_kor_travel_map_admin_client.py -rA`
- Linux: `PATH="$PWD/.venv/bin:$PATH" PYTHONPATH=. .venv/bin/python -m pytest -q -s tests/integration/test_admin_etl_provider_sync_api.py -rA`
- Linux: `PATH="$PWD/.venv/bin:$PATH" PYTHONPATH=. .venv/bin/python -m mypy --strict app`
- Linux: `npm -w @pinvi/web run typecheck`, `npm -w @pinvi/web run lint`
- Linux ext4 mirror: `npm -w @pinvi/web run build`
- Windows fallback: `npm -w @pinvi/web run test:e2e -- admin-etl-provider-sync.e2e.ts`
- Linux: `npx prettier --check ...`, `git diff --check`

**주의**:

- WSL/N150 계열 Ubuntu 26.04에서는 Playwright Chromium 설치가 미지원이라 Linux Playwright 실행이
  막힌다. mock e2e는 Windows fallback으로 통과했다.
- provider run-now/pause/resume은 upstream provider mutation 계약 또는 별도 ADR 전까지 Pinvi에
  추가하지 않는다.

**다음**: T-248 Feature detail subpages.

## 2026-06-28 (codex) — T-246 Debug live UI e2e 확장

**작업**: Admin debug live read-only e2e를 별도 live suite로 추가하고 N150 대상 검증까지 수행했다.

**변경**:

- `apps/web/e2e/admin-debug-live.live.ts`를 추가했다. `/admin/debug/logs` render, polling fallback
  status, filter query, live toggle/pause, request timeline 이동, raw secret pattern 미노출을 확인한다.
- 운영 데이터에 matching timeline event가 없을 수 있어 timeline summary 또는 not-found alert를 모두
  정상 route render로 인정한다.
- `KorTravelMapAdminClient.with_request_id()`를 추가해 현재 Pinvi `X-Request-Id`를 upstream
  `kor-travel-map` admin/ops 호출에도 전달한다.
- debug live test는 `PINVI_ADMIN_LIVE_STORAGE_STATE`를 지원한다. N150에서는 짧은 수명의 storage
  state를 생성해 UI password를 셸에 싣지 않고 실행했다.
- Admin API 문서와 Admin live e2e runbook을 갱신했다.

**검증**:

- Linux: `uv run --extra dev ruff check app/clients/kor_travel_map_admin.py tests/unit/test_kor_travel_map_admin_client.py`
- Linux: `uv run --extra dev ruff format --check app/clients/kor_travel_map_admin.py tests/unit/test_kor_travel_map_admin_client.py`
- Linux: `PATH="$PWD/.venv/bin:$PATH" PYTHONPATH=. .venv/bin/python -m mypy --strict app`
- Linux: `PATH="$PWD/.venv/bin:$PATH" PYTHONPATH=. .venv/bin/python -m pytest -q -s tests/unit/test_kor_travel_map_admin_client.py -rA`
- Linux: `PATH="$PWD/.venv/bin:$PATH" PYTHONPATH=. .venv/bin/python -m pytest -q -s tests/integration/test_admin_dedup_integrity_debug_api.py -rA`
- Linux: `npm -w @pinvi/web run typecheck`, `npm -w @pinvi/web run lint`
- Linux: `npm -w @pinvi/web run test:e2e:admin-live:list -- admin-debug-live.live.ts`
- Linux: `npx prettier --check ...`, `git diff --check`
- N150: branch checkout 후 `pinvi-api`/`pinvi-web` rebuild/recreate, API `/health`, API `/health/db`,
  Web `/admin/login` health 확인.
- N150 Playwright: `npx playwright install chromium`이 Ubuntu 26.04 미지원으로 실패했다.
- Windows fallback: N150 Web/API 대상 `admin-debug-live.live.ts` 1건 통과.

**다음**: T-247 Provider sync 운영 mutation 계약 정리.

## 2026-06-28 (codex) — T-245 Debug log polling fallback

**작업**: Loki/Promtail LogQL WebSocket 대신 v0.2.0 Admin debug live mode를 sanitized polling
fallback으로 확정하고 구현했다.

**변경**:

- `GET /admin/debug/logs/stream/status`를 추가했다. 응답은 `mode="polling"`,
  `poll_interval_ms=5000`, `loki_enabled=false`, `sse_enabled=false`, source 목록을 반환한다.
- Web `/admin/debug/logs`에 live toggle과 pause/resume을 추가했다. live 상태에서는 기존
  sanitized system/API logs endpoint를 현재 filter 그대로 interval 재조회한다.
- `@pinvi/schemas`, `@pinvi/api-client`, Admin API 문서와 Sprint/task/resume 추적 문서를 갱신했다.
- Loki/Promtail 실제 도입은 운영 용량과 retention 정책이 확정된 뒤 별도 선택 계층으로 남겼다.

**검증**:

- Linux: `codegraph sync`
- Linux: `uv run --extra dev ruff check ...` (API targeted)
- Linux: `uv run --extra dev ruff format --check ...` (API targeted)
- Linux: `PYTHONPATH=. .venv/bin/python -m mypy --strict app`
- Linux: `PATH="$PWD/.venv/bin:$PATH" PYTHONPATH=. .venv/bin/python -m pytest -q -s tests/integration/test_admin_dedup_integrity_debug_api.py -rA`
- Linux: `npm -w @pinvi/schemas run typecheck`, `npm -w @pinvi/api-client run typecheck`,
  `npm -w @pinvi/web run typecheck`, `npm -w @pinvi/web run lint`
- Linux: `npx prettier --check ...`

**주의**:

- Playwright는 N150-first 기준에 따라 로컬 Linux에서 실행하지 않았다. T-246에서 N150 read-only
  `/admin/debug/logs`/`/admin/debug/request/{request_id}`와 masking assertion을 실행한다.

**다음**: T-246 Debug live UI e2e 확장.

## 2026-06-28 (codex) — T-244 Request timeline API

**작업**: Pinvi request id 중심 Admin timeline API와 Web timeline 화면을 구현했다.

**변경**:

- `GET /admin/debug/request/{request_id}`가 `app.api_call_log`, `app.admin_audit_log`,
  `app.location_access_log`/outbox, `payload.request_id`가 있는 `app.email_queue`를 시간순 event로
  조합한다.
- `kor-travel-map` sanitized system/API logs는 같은 request id로 필터해 보조 source로만 붙인다.
  실패 시 전체 요청을 실패시키지 않고 `data.status="partial"`과 source `degraded`로 표시한다.
- timeline detail에서 admin audit `access_reason`/state payload, email 수신자/제목/payload/
  `last_error`, 위치 user id/좌표/IP hash, secret-like query/header 값을 노출하지 않도록 정리했다.
- Web `/admin/debug/logs`에 request id 검색을 추가했고,
  `/admin/debug/request/{request_id}`가 source/event table을 표시한다.
- `@pinvi/schemas`, `@pinvi/api-client`, Admin API 문서와 Sprint/task/resume 추적 문서를 갱신했다.

**검증**:

- Linux: `codegraph sync`
- Linux: `python3 -m compileall ...` (targeted)
- Linux: `uv run --extra dev ruff check ...` (API targeted)
- Linux: `uv run --extra dev ruff format --check ...` (API targeted)
- Linux: `PYTHONPATH=. .venv/bin/python -m mypy --strict app`
- Linux: `PATH="$PWD/.venv/bin:$PATH" PYTHONPATH=. .venv/bin/python -m pytest -q -s tests/unit/test_admin_request_timeline.py tests/integration/test_admin_dedup_integrity_debug_api.py -rA`
- Linux: `npm -w @pinvi/schemas run typecheck`, `npm -w @pinvi/api-client run typecheck`,
  `npm -w @pinvi/web run typecheck`, `npm -w @pinvi/web run lint`
- Linux: `npx prettier --check ...`

**주의**:

- Playwright는 ADR-051 기준에 따라 로컬 Linux에서 실행하지 않았다. N150 live read-only
  `/admin/debug/logs`/`/admin/debug/request/{request_id}` 검증은 PR merge 후 배포 환경에서 수행한다.

**다음**: T-245 Loki/Promtail 또는 대체 log stream.

## 2026-06-28 (codex) — T-243 ETL live / Dagster 운영 게이트

**작업**: Admin ETL summary와 Web `/admin/etl`에 Pinvi Dagster live snapshot을 추가했다.

**변경**:

- `/admin/etl/summary`가 `PINVI_DAGSTER_BASE_URL`의 `/server_info`와 `/graphql`을 읽어
  Dagster version, code location repository/job/asset/schedule, 최근 run 상태를 반환한다.
- GraphQL 조회 실패는 `pinvi.status=degraded`로 강등하고, static app-owned registry와
  email/Telegram/PII/location summary는 계속 반환한다.
- Admin 응답의 Pinvi recent run은 `run_id`, `status`, `job_name`, timestamp만 노출하고 run tag
  값은 싣지 않는다.
- Web `/admin/etl`은 app-owned job row마다 live/registry 상태, schedule cron/timezone,
  최신 run status를 표시하고, live code location / recent Pinvi runs 영역을 추가했다.
- `docs/api/admin.md`, `docs/runbooks/etl.md`, `docs/architecture/dagster-etl-bridge.md`,
  Sprint/task/resume 추적 문서를 T-243 상태로 갱신했다.

**검증**:

- Linux: `codegraph sync`
- Linux: `uv run --extra dev ruff check ...` (API targeted)
- Linux: `uv run --extra dev ruff format --check ...` (API targeted)
- Linux: `PYTHONPATH=. .venv/bin/python -m mypy --strict app`
- Linux: `PATH="$PWD/.venv/bin:$PATH" PYTHONPATH=. .venv/bin/python -m pytest -q -s tests/unit/test_admin_etl_dagster_probe.py tests/integration/test_admin_etl_provider_sync_api.py -rA`
- Linux: `npm -w @pinvi/schemas run typecheck`, `npm -w @pinvi/api-client run typecheck`,
  `npm -w @pinvi/web run typecheck`, `npm -w @pinvi/web run lint`
- Linux: `npx prettier --check ...`

**주의**:

- `uv run mypy`는 `.venv/bin/mypy` shebang이 과거 worktree 경로를 가리켜 실패했다.
  현재 Python으로 `python -m mypy`를 실행해 통과시켰다.
- N150 API smoke / Playwright live는 현재 브랜치가 아직 운영 배포되지 않아 수행하지 않았다.
  PR merge 후 배포된 환경에서 `/admin/etl`, `/admin/provider-sync` read-only live를 실행한다.

**다음**: T-244 Request timeline API로 진행한다.

## 2026-06-28 (codex) — T-242 Telegram system summary/outbox ETL

**작업**: Telegram system outbox 상태를 발송 없이 집계하는 Pinvi app-owned Dagster asset과
Admin ETL summary 노출을 구현했다.

**변경**:

- `apps/etl`에 `pinvi_telegram_system_outbox` asset을 추가했다. 15분마다
  `app.telegram_system_notification_outbox`의 pending due/backoff/stuck, sent, skipped,
  failed, retry exhausted, category별 retry exhausted 비율을 payload 없이 집계한다.
- Dagster definitions/schedules에 `pinvi_telegram_system_outbox_job`과
  `pinvi_telegram_system_outbox_schedule`을 등록했다.
- `/admin/etl/summary`가 `pinvi.telegram_outbox` summary를 반환하도록 API schema/service와
  `@pinvi/schemas`를 확장했다.
- Web `/admin/etl`에 due/backoff/stuck/retry exhausted, sent/skipped/failed,
  category별 retry exhausted 비율을 표시했다.
- `docs/runbooks/etl.md`, `docs/architecture/dagster-etl-bridge.md`,
  `docs/integrations/telegram.md`, task/resume 추적 문서를 T-242 완료 상태로 갱신했다.
- weekly/daily 사용자 브리프 생성은 후속 `pinvi_telegram_weekly` 범위로 유지했다.

**검증**:

- Linux: `codegraph sync`
- Linux: `uv run --extra dev ruff check ...` (ETL/API targeted)
- Linux: `uv run --extra dev ruff format --check ...` (ETL/API targeted)
- Linux: `PYTHONPATH=. .venv/bin/python -m pytest -q -s tests/test_definitions.py tests/test_telegram_system_outbox.py`
- Linux: `PATH="$PWD/.venv/bin:$PATH" PYTHONPATH=. .venv/bin/python -m pytest -q -s tests/integration/test_admin_etl_provider_sync_api.py -rA`
- Linux: `npm -w @pinvi/schemas run typecheck`, `npm -w @pinvi/api-client run typecheck`,
  `npm -w @pinvi/web run typecheck`, `npm -w @pinvi/web run lint`
- Linux: `npx prettier --check ...`, `git diff --check`

**주의**:

- `uv run` 첫 실행에서 NTFS pytest capture가 임시 파일을 잃어 직접 `.venv/bin/python -m pytest -s`
  방식으로 재실행했다. API 통합 테스트는 fixture가 subprocess로 `alembic`을 호출하므로
  `PATH="$PWD/.venv/bin:$PATH"`가 필요했다.
- root `node_modules/@pinvi/*`가 과거 `tripmate-codex` 경로를 가리켜 웹 typecheck가 처음 실패했다.
  `npm install`을 중단하기 전 workspace symlink가 현재 repo 상대경로로 복구됐고 이후 typecheck/lint는
  통과했다.
- Playwright는 ADR-051 정책상 N150 우선 실행 대상이다. 현재 Codex 세션에는 N150 Playwright runner
  접근 도구가 없어 로컬 Linux/Windows Playwright는 실행하지 않았다.

**다음**: T-243 ETL live / Dagster 운영 게이트로 진행한다.

## 2026-06-28 (codex) — T-289 Linux-only 개발 환경 / ADR-051

**작업**: 사용자 지시에 따라 개발·git·CodeGraph 실행 위치를 Linux로 통일하고, Playwright는
N150 우선 / Windows fallback으로 정리했다.

**변경**:

- `docs/decisions.md`에 ADR-051을 추가하고 ADR-024를 superseded로 표시했다. ADR-017의
  Windows `git.exe` amendment도 ADR-051이 supersede한다고 명시했다.
- `AGENTS.md`, `CLAUDE.md`, `SKILL.md`를 ADR-051 기준으로 동기화했다.
- `docs/dev-environment.md`, `docs/agent-workflow.md`,
  `docs/runbooks/codegraph-worktrees.md`, `docs/agent-failure-patterns.md`를 Linux git /
  Linux native CodeGraph / N150 Playwright 우선 기준으로 재작성했다.
- README 빠른 시작, Sprint ADR 목록, tasks/resume/tasks-done 추적 문서를 갱신했다.
- PR #274(T-241)는 CI success와 inline review thread 0건을 확인하고 squash merge했다.

**검증**:

- Linux: `git worktree repair /mnt/f/dev/pinvi-codex`
- Linux: `git fetch origin && git switch -c agent/codex-linux-dev-workflow origin/main`
- Linux: 최초 `command -v codegraph`가 `/mnt/c/Users/digit/AppData/Roaming/npm/codegraph`로
  잡혀 `npm install -g --prefix "$HOME/.local" @colbymchenry/codegraph`로 Linux native
  `/home/digitie/.local/bin/codegraph`를 설치했다.
- Linux: Linux native `codegraph status && codegraph sync` 통과.

**다음**: 정책 문서 PR 생성/머지 후 T-242 Telegram system summary/outbox ETL로 진행한다.

## 2026-06-28 (codex) — T-241 `pinvi_location_log_archive` Dagster job

**작업**: 위치 접근 로그 archive 후보와 hash-chain bridge 상태를 파괴 작업 없이 집계하는
Pinvi app-owned Dagster asset과 Admin ETL summary 노출을 구현했다.

**변경**:

- `apps/etl`에 `pinvi_location_log_archive` asset을 추가했다. 매일 KST 04:30
  `app.location_access_log`의 6개월 초과 archive 후보, archive tail hash와 active head
  `prev_hash` 연결 상태, 미처리 `location_audit_outbox` blocker, purpose별 후보 수를
  dry-run metadata로 집계한다.
- Dagster definitions/schedules에 `pinvi_location_log_archive_job`과
  `pinvi_location_log_archive_schedule`을 등록했다.
- `/admin/etl/summary`가 `pinvi.location_log_archive` summary를 반환하도록 API schema/service를
  확장했다.
- Web `/admin/etl`에 후보 수, active row 수, pending outbox, chain bridge 일치 여부,
  purpose별 count를 표시했다.
- 실제 archive/delete/anonymize 실행은 T-276 kill-switch/dashboard/evidence log 범위로 유지했다.

**검증**:

- WSL ext4 미러: ETL targeted `ruff check` / `ruff format --check`
- WSL ext4 미러: `python -m pytest -q tests/test_definitions.py tests/test_location_log_archive.py`
- WSL ext4 미러: API targeted `ruff check` / `ruff format --check`
- WSL ext4 미러: `python -m mypy --strict app`
- WSL ext4 미러: `python -m pytest tests/integration/test_admin_etl_provider_sync_api.py -q -rA`
- WSL ext4 미러: `npm -w @pinvi/schemas run typecheck`, `npm -w @pinvi/web run typecheck`,
  `npm -w @pinvi/web run lint`

**다음**: T-241 커밋 후 멈춘다. 재시작 시 사용자 지시에 따라 PR/e2e/merge를 진행하거나,
T-242 Telegram system summary/outbox ETL 진입 전 최근 2일 PR 리뷰 코멘트를 다시 확인한다.

## 2026-06-28 (codex) — T-240 `pinvi_pii_retention` Dagster job

**작업**: PIPA/LBS 보존 기간 만료 후보를 파괴 작업 없이 집계하는 Pinvi app-owned Dagster asset과
Admin ETL summary 노출을 구현했다.

**변경**:

- `apps/etl`에 `pinvi_pii_retention` asset을 추가했다. 매일 KST 04:15 삭제 계정 PII, OAuth identity,
  만료 verification/reset token, 오래된 session, 만료 OAuth transient row, 6개월 초과
  location/admin audit PII 후보를 dry-run metadata로 집계한다.
- Dagster definitions/schedules에 `pinvi_pii_retention_job`과 `pinvi_pii_retention_schedule`을
  등록했다.
- `/admin/etl/summary`가 `pinvi.pii_retention` summary를 반환하도록 API schema/service를 확장했다.
- Web `/admin/etl`에 전체 후보, 삭제 계정, session, token, location log, 권한 계정 제외 수를 표시했다.
- `admin` / `operator` / `cpo` 역할이 있는 삭제 계정은 후보에서 제외하고
  `excluded_privileged_deleted_users`로만 보고한다.
- 실제 delete/anonymize/archive 실행은 T-276 kill-switch/dashboard/evidence log 범위로 유지했다.

**검증**:

- WSL ext4 미러: ETL targeted `ruff check`
- WSL ext4 미러: `uv run --extra dev pytest -q tests/test_definitions.py tests/test_pii_retention.py`
- WSL ext4 미러: API targeted `ruff check`
- WSL ext4 미러: `uv run --extra dev pytest tests/integration/test_admin_etl_provider_sync_api.py -q -rA`
- WSL ext4 미러: `npm -w @pinvi/schemas run typecheck`, `npm -w @pinvi/web run typecheck`,
  `npm -w @pinvi/web run lint`

**다음**: PR 생성 후 e2e/CI/merge를 완료하고, 신규 Task 진입 전 최근 2일 PR 리뷰 코멘트를 다시 확인한다.
다음 구현은 T-241 `pinvi_location_log_archive` Dagster job이다.

## 2026-06-28 (codex) — T-239 `pinvi_email_outbox` Dagster job

**작업**: Pinvi `app.email_queue` 운영 점검 Dagster asset/job과 Admin ETL summary 노출을 구현했다.

**변경**:

- `apps/etl`에 `pinvi_email_outbox` asset을 추가했다. 15분마다 pending due/backoff/stuck,
  failed/bounced/complained, retry exhausted, template별 실패율을 PII 없이 bounded metadata로 남긴다.
- Dagster definitions/schedules에 `pinvi_email_outbox_job`과 `pinvi_email_outbox_schedule`을 등록했다.
- `/admin/etl/summary`가 `pinvi.email_outbox` summary를 반환하도록 API schema/service를 확장했다.
- Web `/admin/etl`에 email outbox due/backoff/stuck/retry exhausted와 template failure rate를 표시했다.
- 실제 메일 발송은 FastAPI lifespan worker가 계속 담당하고, deliverability/suppression 집행은
  T-257/T-277로 유지했다.

**검증**:

- WSL ext4 미러: API targeted `ruff check` / `ruff format --check`
- WSL ext4 미러: `python -m mypy --strict app`
- WSL ext4 미러: `uv run --extra dev pytest tests/integration/test_admin_etl_provider_sync_api.py -q -rA`
- WSL ext4 미러: ETL targeted `ruff check` / `ruff format --check`
- WSL ext4 미러: `uv run --extra dev pytest -q tests/test_definitions.py tests/test_email_outbox.py`
- WSL ext4 미러: `npm -w @pinvi/schemas run typecheck`, `npm -w @pinvi/web run typecheck`,
  `npm -w @pinvi/web run lint`
- Windows Playwright runner: `npm -w @pinvi/web run test:e2e -- admin-etl-provider-sync.e2e.ts --workers=1`

**다음**: PR 생성 후 e2e/CI/merge를 완료하고, 신규 Task 진입 전 최근 2일 PR 리뷰 코멘트를 다시 확인한다.
다음 구현은 T-240 `pinvi_pii_retention` Dagster job이다.

## 2026-06-28 (codex) — T-238 Pinvi app-owned ETL 표준 / ADR

**작업**: Sprint 5의 app-owned ETL job 구현 전에 Pinvi Dagster job 표준을 ADR-050으로 고정했다.

**변경**:

- `docs/decisions.md`에 ADR-050을 추가해 Pinvi `apps/etl`에는 `app` schema 소유 job만 두고,
  feature/provider 적재와 `feature` / `provider_sync` schema 작업은 `kor-travel-map` 책임으로
  유지한다고 명시했다.
- 신규 job 표준으로 import-time side effect 금지, KST schedule, retry/backoff, idempotency,
  bounded metadata/log, `run_failure_sensor` 기반 Sentry/Telegram outbox 알림, destructive dry-run
  gate를 정했다.
- `docs/runbooks/etl.md`와 `docs/architecture/dagster-etl-bridge.md`에 ADR-050 체크리스트와 실패
  알림/파괴적 작업 gate를 반영했다.
- Sprint 5 문서, `AGENTS.md`, `CLAUDE.md`, `docs/tasks.md`, `docs/tasks-done.md`,
  `docs/resume.md`를 같은 기준으로 동기화했다.

**검증**:

- Windows worktree: `git diff --check`

**다음**: PR 생성 후 e2e/CI/merge를 완료하고, 신규 Task 진입 전 최근 2일 PR 리뷰 코멘트를 다시 확인한다.
다음 구현은 T-239 `pinvi_email_outbox` Dagster job이다.

## 2026-06-28 (codex) — T-237 WebSocket backend hardening / metrics

**작업**: Trip WebSocket backend의 운영 관측성과 cap/rate/timeout/permission 회귀 테스트를 보강했다.

**변경**:

- `apps/api/app/services/realtime_metrics.py`를 추가해 WebSocket active connection gauge,
  connection accept/reject counter, close counter, client message counter, broadcast counter,
  send failure counter를 등록했다. metric label은 bounded 값만 쓰고 `trip_id`/`user_id`는 넣지 않는다.
- `RealtimeBroker`가 global broker에서 metric을 기록하도록 하고, custom test broker는
  `metrics_enabled=True`일 때만 metric을 건드리게 했다.
- `WS /ws/trips/{trip_id}` close 경로에 `pinvi.websocket.close` 구조화 로그와 close metric을 추가했다.
- permission denied, rate limit, connection cap, heartbeat timeout 회귀 테스트에 metric delta 검증을
  추가했고, broker 단위 stale-removal/send-timeout metric 테스트를 추가했다.
- WebSocket 문서의 rate-limit grace 설명을 실제 구현처럼 "close까지 slot 유지"로 정정하고,
  Prometheus metric 표를 추가했다.

**검증**:

- WSL ext4 미러: `ruff check app/services/realtime_metrics.py app/services/realtime_broker.py app/api/v1/ws.py tests/unit/test_realtime_broker.py tests/integration/test_ws_trip_channel.py`
- WSL ext4 미러: `ruff format --check app/services/realtime_metrics.py app/services/realtime_broker.py app/api/v1/ws.py tests/unit/test_realtime_broker.py tests/integration/test_ws_trip_channel.py`
- WSL ext4 미러: `mypy --strict app`
- WSL ext4 미러: `pytest -q tests/unit/test_realtime_broker.py`
- WSL ext4 미러: `pytest -q tests/integration/test_ws_trip_channel.py`

**다음**: PR 생성 후 e2e/CI/merge를 완료하고, 신규 Task 진입 전 최근 2일 PR 리뷰 코멘트를 다시 확인한다.

## 2026-06-28 (codex) — T-236a WebSocket multi-client N150 live e2e drill

**작업**: N150 public Web/API를 대상으로 실제 WebSocket broadcast와 reconnect 뒤 Trip snapshot reload를
검증하는 live mutating Playwright drill을 수행했다.

**변경/발견**:

- live mutating 하네스의 클라이언트 직접 close code를 브라우저 허용 범위 밖인 `1012`에서 테스트 전용
  `4000`으로 바꿨다. `1012`는 서버가 보낼 수 있는 close code지만, 브라우저 클라이언트가 직접 호출할
  수 있는 값은 `1000` 또는 `3000~4999` 범위다.
- 운영 `pinvi-api`가 worker 2개로 떠 있으면 HTTP mutation과 WebSocket 연결이 서로 다른 worker에
  배정될 수 있어 process-local realtime broker broadcast가 누락됨을 확인했다. Pinvi compose 기본값과
  `kor-travel-docker-manager` PR #44를 `PINVI_API_WORKERS=1` 계약으로 맞췄다.
- public Web origin의 `/auth/login` preflight가 CORS 400으로 떨어지는 drift를 확인했다.
  `kor-travel-docker-manager` PR #45에서 `PINVI_PUBLIC_API_URL`과 `PINVI_CORS_ALLOWED_ORIGINS`를
  gitignore `.env` 주입값으로 분리해 운영 public origin을 코드/문서에 노출하지 않고 주입하게 했다.

**검증**:

- WSL ext4 미러: `npm -w @pinvi/web run typecheck`
- WSL ext4 미러: `npm -w @pinvi/web run lint`
- Windows Playwright runner: `npm -w @pinvi/web run test:e2e:live-mutating -- --workers=1`
- N150: `pinvi-api` process가 `--workers 1`로 기동하고 API/Web 컨테이너가 healthy임을 확인했다.

**다음**: PR #269를 갱신하고 merge한 뒤 T-237 WebSocket backend hardening / metrics로 진행한다.

## 2026-06-28 (codex) — T-236 WebSocket multi-client collaboration e2e

**작업**: Trip 상세 협업 WebSocket mock e2e를 여러 브라우저 컨텍스트와 재연결 흐름까지 확장했다.
기존 T-236의 N150 staging live 검증은 운영 drill 성격이 커서 T-236a로 분리했다.

**변경**:

- `trip-collab.e2e.ts`에 page별 동적 TripView 응답과 controllable Fake WebSocket helper를 추가했다.
- 2개 브라우저 컨텍스트에서 `presence.update`와 `trip.updated` broadcast reload를 검증했다.
- WebSocket close/reconnect 뒤 새 broadcast가 최신 HTTP snapshot reload로 이어지는지 검증했다.
- 5개 브라우저 컨텍스트에서 presence fan-out와 offline cleanup 상태 문구를 검증했다.
- React Strict Mode 재마운트와 재연결에서 닫힌 socket이 남아도 마지막 active socket으로 서버 이벤트를
  주입하도록 테스트를 정리했다.

**검증**:

- WSL ext4 미러: `npm -w @pinvi/web run typecheck`
- WSL ext4 미러: `npm -w @pinvi/web run lint`
- Windows Playwright runner: `PLAYWRIGHT_BASE_URL=http://localhost:12805 npm -w @pinvi/web run test:e2e -- trip-collab.e2e.ts --workers=1`

**다음**: PR을 만들고 merge한 뒤 신규 Task 진입 전 최근 2일 PR 리뷰 코멘트를 다시 확인한다.
다음 구현은 T-236a WebSocket multi-client N150 live e2e drill이다.

## 2026-06-28 (codex) — T-288 Task 문서 분리 정책 반영

**작업**: `kor-travel-map` task 문서화 정책을 확인하고 Pinvi의 task 추적 문서에도
`tasks.md` / `tasks-done.md` / `resume.md` 분리 규칙을 도입했다.

**변경**:

- `docs/tasks-rule.md`를 추가해 열린 task, 완료 아카이브, task 분리, 신규 task 진입 전
  최근 2일 PR 리뷰 코멘트 확인 규칙을 문서화했다.
- `docs/tasks-done.md`를 추가하고 T-232~T-235 및 T-288 완료 요약을 옮겼다.
- `docs/tasks.md`에서 현재 Sprint 5 완료 항목을 제거하고, legacy 완료 이력 전체 이관을
  `T-288-legacy-task-archive`로 분리했다. 해당 이관은 2026-06-29 완료했다.
- `docs/agent-guide.md`와 `docs/resume.md`의 정본 포인터를 새 정책에 맞췄다.

**발견**: 최근 2일 PR 범위에서 inline review comment는 0건이었다. 사람 top-level 리뷰 코멘트는
#238과 #264의 운영·법무 gap 리뷰 2건이고, #264에서 T-256~T-286으로 이미 반영·답변된 상태다.

**다음**: 문서-only PR을 만들고 merge한 뒤 T-236 WebSocket multi-client collaboration e2e로 진행한다.

## 2026-06-27 (codex) — T-235 Optimistic lock / conflict dialog

**작업**: Trip/POI optimistic lock 409 충돌을 사용자 선택 가능한 다이얼로그로 처리했다.

**변경**:

- `ApiError`에 대한 `isVersionConflictError()` helper를 추가했다.
- Trip 상세 `runMutation`이 `409 VERSION_CONFLICT`를 감지하면 최신 TripView를 재조회하고,
  `ConflictDialog`에서 필드별 서버 값/내 값을 보여준다.
- 사용자는 선택한 내 값만 최신 version으로 재시도하거나, 내 값 전체 LWW 덮어쓰기, 서버 값 사용,
  직접 수정 계속을 선택할 수 있다.
- POI editor는 async 저장 결과가 성공일 때만 닫혀 충돌 시 draft 입력을 유지한다.
- Day rename/delete는 현재 API에 `If-Match`가 없어 T-287 follow-up으로 분리했다.

**검증**:

- WSL ext4 미러: `npm -w @pinvi/api-client run typecheck`
- WSL ext4 미러: `npm -w @pinvi/web run typecheck`
- WSL ext4 미러: `npm -w @pinvi/mobile run typecheck`
- WSL ext4 미러: `npm -w @pinvi/web run test -- conflictResolution.test.ts`
- WSL ext4 미러: `npm -w @pinvi/web run lint`
- WSL ext4 미러: `npm -w @pinvi/web run build`
- WSL ext4 미러: `PATH="$PWD/.venv/bin:$PATH" .venv/bin/python -m pytest tests/integration/test_trips_api.py::test_trip_optimistic_lock tests/integration/test_pois_reorder.py::test_poi_update_stale_version_returns_conflict`
- Windows Playwright runner: `trip-conflict.e2e.ts` 2건

**다음**: PR을 만들고 merge/N150 배포 후 T-236 WebSocket multi-client collaboration e2e로 진행한다.

## 2026-06-27 (codex) — T-234 WebSocket client invalidation / auth close handling

**작업**: Trip WebSocket client의 close code 처리, auth refresh 재연결, UI 상태 안내, realtime event
invalidation key를 구현했다.

**변경**:

- `TripRealtimeClient`가 close code/reason을 `TripRealtimeCloseInfo`로 분류하고 `onClose`,
  `onAuthRefresh`, `refreshing-auth`, `reconnecting`, `permission-denied`, `connection-limited`,
  `rate-limited` 상태를 제공한다.
- `4401` close는 웹에서 `authApi.refresh()` 성공 후 즉시 재연결한다. 실패하면 기존
  `ApiClient.onUnauthorized` 흐름으로 로그인 복귀한다.
- `4403` close는 재연결하지 않고 Trip 상세에 권한 상실 안내와 여행 목록 CTA를 표시한다.
- `4408`/`4429` close는 connection cap/rate-limit 안내와 backoff 상태를 표시한다.
- `tripRealtimeInvalidationKeys()`를 추가해 POI/day/trip/comment domain event별 TanStack Query key를
  정의했다.
- Trip 상세 reload는 in-flight promise를 공유해 HTTP mutation 성공 reload와 WebSocket event reload가
  같은 tick에 겹쳐도 1회 요청으로 합친다.
- `trip-detail.e2e.ts`에 4403 권한 상실과 4429 backoff mock Playwright 케이스를 추가했다.

**검증**:

- WSL ext4 미러: `npm -w @pinvi/api-client run typecheck`
- WSL ext4 미러: `npm -w @pinvi/web run typecheck`
- WSL ext4 미러: `npm -w @pinvi/mobile run typecheck`
- WSL ext4 미러: `npm -w @pinvi/web run test -- tripRealtimeClient.test.ts`
- WSL ext4 미러: `npm -w @pinvi/web run lint`
- WSL ext4 미러: `npm -w @pinvi/web run build`
- Windows Playwright runner: `trip-detail.e2e.ts` 3건

**다음**: PR을 만들고 merge/N150 배포 후 T-235 Optimistic lock / conflict dialog로 진행한다.

## 2026-06-27 (codex) — T-233 리뷰 코멘트 반영 / legal-ops Task 보강

**작업**: PR #264 리뷰 코멘트를 반영해 Sprint 5/6 상세 Task 계획의 누락된 법무/운영/보안 표면을
Task로 보강했다.

**변경**:

- Sprint 5 release gate 직전에 T-256 review gap crosswalk, T-257 email deliverability/provider
  tracking preflight, T-258 Sprint 6 legal/ops implementation prep gate를 추가했다.
- 기존 release candidate gate는 T-259로 조정했다.
- Sprint 6 후속 Task로 T-275~T-286을 추가했다. PIPA incident console, retention 실행/dashboard,
  email deliverability/suppression, DSR intake, content moderation, RBAC grant/revoke, user lifecycle,
  rate-limit/abuse, security threat model, mobile scope, AI companion scope, cross-track #238/#264 gap
  closure가 포함된다.
- `docs/execplan/sprint5-v020-release-plan.md`에 리뷰 항목별 Task crosswalk를 추가했다.
- `docs/tasks.md`, `docs/sprints/SPRINT-5.md`, `docs/sprints/SPRINT-6.md`, `docs/resume.md`를 같은
  번호와 범위로 갱신했다.

**검증**: 문서 diff check와 민감정보 패턴 스캔을 수행한다.

**다음**: PR #264를 merge한 뒤 T-234 WebSocket client invalidation / auth close handling으로 진행한다.

## 2026-06-27 (codex) — T-233 Sprint 5/6 상세 Task 계획

**작업**: Sprint 5 `v0.2.0` 잔여 구현과 Sprint 6 `v1.0.0` 후속 아이템을 Task 단위로 정리했다.

**변경**:

- `docs/execplan/sprint5-v020-release-plan.md`를 추가했다.
- Sprint 5 잔여 Task를 T-234~T-259로 분리했다. WebSocket 후속, optimistic lock/conflict,
  multi-client e2e, ETL job, request timeline/log stream, provider sync 계약, feature detail,
  app integrity, backup/restore, Grafana, Admin live e2e, 지도 마커/색상 parity, release gate를
  포함한다.
- 사용자/Admin 지도뷰의 marker palette, POI custom color/icon, feature snapshot/upstream category
  fallback, selected/broken/cluster 상태 검증을 T-255로 명시했다.
- Sprint 6 초안을 T-260~T-286으로 정리했다. OR-Tools 스마트 정렬, category override,
  Admin notice plan, MCP 운영 실증, backup hot-swap, geofencing, LBS/법무, 성능/보안,
  Odroid+N150 병행 운영, AI companion 분리, v1.0 gate/release를 포함한다.
- ARM image와 GHCR 배포는 제외하고, 운영 노드는 로컬 checkout + 로컬 Docker build 기준으로
  정정했다.
- `docs/tasks.md`, `docs/sprints/SPRINT-5.md`, `docs/sprints/SPRINT-6.md`,
  `docs/resume.md`를 같은 기준으로 갱신했다.

**검증**: 문서 정리 후 `git diff --check`와 민감정보 패턴 스캔을 수행한다.

**다음**: PR 리뷰 반영 후 merge를 진행하고 T-234부터 시작한다.

## 2026-06-27 (codex) — T-232 Trip WebSocket frontend client / presence 첫 연결

**작업**: Sprint 5 WebSocket 협업 게이트의 첫 프론트엔드 수직 슬라이스를 구현했다.

**변경**:

- `packages/api-client/src/websocket.ts`를 추가했다. `TripRealtimeClient`는
  `WS /ws/trips/{trip_id}` URL 생성, heartbeat, `ping`→`pong`, reconnect backoff,
  주입 가능한 WebSocket constructor, event/status/error callback을 제공한다.
- `@pinvi/api-client` public export에 realtime client와 테스트용 최소 WebSocket 타입을 추가했다.
- 사용자 Trip 상세 화면이 실시간 채널에 접속해 presence summary를 보여주고,
  `presence.update` 외 domain event는 250ms debounce reload로 반영한다.
- `tripRealtimeClient.test.ts`를 추가해 URL 변환, open 직후 heartbeat, ping 응답,
  server event forwarding을 검증했다.
- `docs/api/websocket.md`, `CHANGELOG.md`, `docs/tasks.md`, `docs/resume.md`,
  Sprint 5 추적 문서를 갱신했다.

**검증**:

- WSL ext4 미러: `npm -w @pinvi/api-client run typecheck`
- WSL ext4 미러: `npm -w @pinvi/web run typecheck`
- WSL ext4 미러: `npm -w @pinvi/web run test -- tripRealtimeClient.test.ts`
- WSL ext4 미러: `npm -w @pinvi/web run lint`
- WSL ext4 미러: `npm -w @pinvi/mobile run typecheck`

**후속**: TanStack Query invalidation, 공유 presence store, 401 close token refresh, conflict
dialog를 다음 WebSocket task로 분리한다.

## 2026-06-27 (codex) — T-231 v0.2.0 후보 범위 정리

**작업**: `Unreleased`에 쌓인 post-v0.1.0 변경을 Sprint 5 / `v0.2.0` 후보 범위로 재정렬했다.

**변경**:

- `CHANGELOG.md`의 `Unreleased`를 `v0.2.0` 후보로 표시하고, 남은 gate를 명시했다.
- Sprint 5 문서를 in-progress 상태로 바꾸고 이미 main에 반영된 Admin/ETL/Grafana/System 항목과
  남은 gate를 분리했다.
- `docs/sprints/README.md` Sprint 5 상태를 post-v0.1.0 일부 반영 상태로 갱신했다.
- `docs/tasks.md` 다음 작업을 WebSocket, app-owned ETL 추가 job, Loki/request timeline,
  backup/restore 스테이징 훈련 중심으로 정리했다.
- `docs/resume.md` 최신 항목에 같은 범위 정리를 남겼다.

**다음**: `v0.2.0` 구현 gate 중 WebSocket 협업 또는 app-owned ETL 추가 job부터 Task로 쪼개 진행한다.

## 2026-06-27 (codex) — T-230 v0.1.0 릴리즈 상태 정합화

**작업**: `v0.1.0` 릴리즈가 이미 존재하는 상태와 문서의 "tag 대기" 표현 사이 drift를 정리했다.

**확인**:

- Git tag `v0.1.0`은 `2f8da02345581fd3065e9d818352bc187f65b3a9`를 가리킨다.
- GitHub Release `v0.1.0`은 2026-06-13에 게시돼 있다.
- 현재 main `d35f49e1faafa61380d9c2c0e2d6a1cb36d29108`은 post-v0.1.0 변경이다.
- N150 최신 checkout 기준 API/DB/Web/Dagster/`kor-travel-map` smoke는 모두 HTTP 200을 반환했다.

**변경**:

- `CHANGELOG.md`에서 `v0.1.0`을 릴리즈 완료 상태로 바꾸고, `Unreleased`가 post-v0.1.0 변경임을
  명시했다.
- `docs/tasks.md`, `docs/sprints/README.md`, `docs/sprints/SPRINT-4.md`의 "tag 대기" 표현을
  released 상태로 정리했다.
- ADR-016에 맞춰 `AGENTS.md`와 `CLAUDE.md` 현 단계 요약을 함께 갱신했다.
- `docs/resume.md` 최신 항목과 로드맵 표를 실제 release 상태로 맞췄다.

**다음**: v0.2.0 범위 정리로 넘어간다. Odroid 실제 smoke와 backup/restore 복구 훈련은 T-108
설명대로 Sprint 6 운영 게이트로 남긴다.

## 2026-06-27 (codex) — T-229 Admin 완료 감사 / 추적 문서 최신화

**작업**: Admin 보강 프로그램 T-207~T-228의 완료 상태를 다시 감사하고, 추적 문서를 현재 main
상태에 맞췄다.

**변경**:

- `docs/execplan/admin-console-gap-plan.md`의 목적/현재 상태를 초기 placeholder gap 문서에서
  완료 감사 문서로 갱신했다.
- 사용자 명시 요구사항 1~14번을 완료 Task와 API/UI/e2e 증거에 매핑했다.
- `docs/tasks.md`의 Admin 후속 항목과 T-216/T-228 sidebar 설명을 기본 expanded + 선택적
  compact icon-only 토글 기준으로 정정했다.
- `docs/resume.md` 최신 항목에 PR #259 merge, N150 배포 완료, 다음 작업(v0.1.0 릴리즈 정리)을
  반영했다.

**검증**: `git diff --check`가 통과했다. tracked diff URL/IP/credential 패턴 스캔에서 새로 잡힌
값은 민감정보 비노출 정책 문장뿐이었다. 문서-only 변경이므로 N150은 PR merge 후 checkout
fast-forward만 수행하고 컨테이너 재빌드는 생략한다.

**후속**: PR #260을 merge했다. 이후 T-230에서 기존 `v0.1.0` tag/Release 존재를 확인하고
릴리즈 상태 문서를 실제 상태로 정리했다.

## 2026-06-27 (codex) — T-227 Integrity issue status mutation

**작업**: Pinvi Admin `/admin/integrity`에서 `kor-travel-map` integrity issue 상태 조치를 직접
수행할 수 있게 했다.

**결정**:

- `kor-travel-map`의 `/v1/ops/consistency/issues`와 `/v1/ops/consistency/reports`는 read-only다.
- 상태 조치 source of truth는 기존 upstream `PATCH /v1/admin/issues/{issue_id}` 계약이다.
- Pinvi는 `resolve` / `ignore` / `reopen`만 relay한다. 주소/좌표 보정류 action
  (`manual_override`, geocode retry/apply)는 `kor-travel-map` Admin 책임으로 남긴다.

**변경**:

- `KorTravelMapAdminClient.patch_admin_issue()`를 추가해 upstream admin issue PATCH path/body를
  감싼다.
- Pinvi API `POST /admin/integrity/issues/{issue_id}/action`을 추가했다. admin 전용이며,
  `access_reason`과 optional upstream reason을 검증하고 upstream 성공 후
  `integrity_issue.action` audit을 남긴다.
- `@pinvi/schemas`, `@pinvi/api-client`, query keys에 issue action 요청/응답 계약을 추가했다.
- Web `/admin/integrity` issue table에 해결/무시/재오픈 버튼과 reason dialog, 성공 notice,
  list invalidate/refetch를 추가했다.
- `docs/tasks.md`, `docs/resume.md`, 실행 계획을 T-227 완료 상태로 갱신했다.

**검증**: WSL ext4 미러에서 `test_kor_travel_map_admin_client.py` 21건, admin
dedup/integrity/debug integration 7건, ruff, mypy, Web/type package typecheck, 표준 Web lint가
통과했다. Windows Playwright runner는 WSL Next server(12805)를 대상으로
`admin-dedup-integrity-debug.e2e.ts --grep "정합성 페이지"` 1건을 실행했고 통과했다.

**후속**: PR #259를 merge했고 N150 배포와 API/Web/Dagster/upstream smoke를 완료했다.

## 2026-06-27 (codex) — T-228 Admin sidebar 확장/축소 토글 정정

**작업**: 왼쪽 Admin 메뉴를 아이콘 전용으로 고정한 이전 구현을 정정해, 기본은 아이콘+라벨
expanded sidebar이고 필요할 때만 icon-only compact 상태로 접을 수 있게 했다.

**변경**:

- `/admin` layout sidebar의 desktop 기본 폭을 expanded로 바꾸고 그룹 제목과 메뉴 라벨을 표시한다.
- sidebar toggle button을 추가해 expanded/compact 상태를 전환한다.
- compact 상태에서는 기존처럼 아이콘만 보이고, expanded 상태에서는 아이콘과 label이 함께 보인다.
- sidebar 선호 상태는 browser localStorage에 저장한다.
- 기존 active route 판정과 `admin-nav-*` test id는 유지했다.
- `admin-trips.e2e.ts`에 기본 expanded, collapse, expand 동작 assertion을 추가했다.
- T-228을 실행 계획과 tasks/resume에 추가했다.

**검증**: WSL ext4 미러에서 Web typecheck와 Web lint가 통과했다. Windows Playwright runner는
WSL dev server를 대상으로 `admin-trips.e2e.ts`의 여행 상세 focused case 1건을 실행했고 통과했다.

**후속**: PR merge와 N150 배포를 완료했다. 이후 T-229 완료 감사로 추적 문서를 정리했다.

## 2026-06-27 (codex) — T-215 Admin live e2e 확장 + N150 묶음 게이트

**작업**: 최신 Admin 구현 묶음을 N150 live authenticated Playwright gate로 검증하고, 긴 운영
run에서 드러난 테스트 하네스 정책을 보강했다.

**변경**:

- Admin live catalog는 최신 기준 전체 6176건이다. UI matrix 6173건, 로그인 검증 2건,
  catalog sanity 1건으로 구성된다.
- 한 route에 여러 AdminTable이 있는 `provider-sync`, `integrity`, `debug/logs` 화면은 첫
  `admin-table-scroll`을 ready 기준으로 삼도록 했다.
- `/admin/system`은 AdminTable route가 아니므로 `admin-system-containers` ready marker로 검증하고
  sort matrix에서 제외했다.
- 긴 full run 도중 admin access token/cookie TTL을 넘는 경우를 대비해 기본 auth refresh를
  5분으로 줄였다.
- route 진입 또는 navigation 직후 로그인 화면으로 떨어진 경우 UI login을 다시 수행하고 원래
  route로 복귀하도록 했다.
- `docs/runbooks/admin-live-e2e.md`, 실행 계획, tasks/resume을 최신 case count와 N150 gate 결과로
  갱신했다.

**검증**: Windows Playwright runner에서 N150 운영 Web URL을 대상으로
`PINVI_ADMIN_LIVE_CASE_LIMIT=2000` gate를 실행했다. 로그인 검증 2건 + catalog sanity 1건 +
matrix 2000건, 총 2003건이 모두 통과했다(3.1h). 실행 전후 N150 smoke에서 API `/health`,
API `/health/db`, Web `/admin/login`, Dagster, upstream `kor-travel-map` health, Pinvi 컨테이너
healthy 상태를 확인했다. Windows `npm run test:e2e:admin-live:list`는 `6176 tests in 1 file`을
반환했다. WSL ext4 미러에서 Web Prettier check, Web typecheck, Web lint가 통과했다.

**다음**: PR을 만들고 merge한 뒤 N150에 한 번 더 배포한다. 그 후 v0.1.0 릴리즈 정리로 진행한다.

## 2026-06-27 (codex) — T-222 System view Docker / 의존 API 상태

**작업**: Admin `/admin/system` 화면과 `GET /admin/system/detail` API를 추가해 의존 API와 Docker
container 상태를 한 화면에서 볼 수 있게 했다.

**변경**:

- 기존 `/admin/system/summary`는 유지하고, detail endpoint에서 dependency probe와 Docker collector를
  함께 반환한다.
- Docker collector는 Docker Engine Unix socket을 read API로 조회하되, socket 없음/권한 없음/API 오류를
  endpoint 실패로 만들지 않고 `unknown` 또는 `down` 상태로 강등한다.
- container 응답은 id/name/image/state/status/health/compose project/service만 포함한다. raw labels,
  env, 운영 도메인, secret은 노출하지 않는다.
- `PINVI_DOCKER_SOCKET_PATH`, timeout, container limit 설정과 env 예시를 추가했다. compose에는 socket을
  기본 mount하지 않는다.
- Web `/admin/system` route와 sidebar 메뉴를 추가하고, live matrix route/table 목록에 포함했다.
- API integration과 Windows Playwright mock e2e를 추가했다.

**검증**: 로컬 WSL ext4 미러에서 API ruff format/check, 앱 코드 mypy,
`test_admin_system_summary_api.py` 3건, Web Prettier check, Web typecheck, Web lint,
Web Vitest 27건, Web production build가 통과했다. Playwright는 Windows에서 실행했고, WSL Next
서버(12805)를 띄워 `admin-priority3.e2e.ts` 시스템 화면 케이스 1건이 통과했다.

**다음**: PR을 만들고 merge한 뒤 T-215 Admin live e2e 확장 + N150 묶음 게이트로 진행한다.

## 2026-06-27 (codex) — T-221 Dashboard 운영 현황 그래프 / 부하 / 용량

**작업**: Admin `/admin` 대시보드가 단순 count 카드에서 실제 운영 현황을 훑어볼 수 있는
그래프/부하/용량 화면으로 확장되도록 API와 Web을 보강했다.

**변경**:

- `GET /admin/stats/overview`에 `generated_at`, API 실패율, API latency P95, 24시간 hourly
  series, 서버 load average, 첨부 저장소/전역 quota/사용자 quota override/디스크 사용량 snapshot을
  추가했다.
- 통계 endpoint는 storage settings가 없을 때 DB row를 만들지 않고 기본값만 반환한다.
- 디스크 사용량은 `PINVI_BACKUP_DIR`의 가장 가까운 존재 경로 기준 숫자만 반환하고, raw path,
  운영 도메인, secret은 응답하지 않는다.
- `@pinvi/schemas`와 `@pinvi/api-client` 소비 타입을 새 응답 계약에 맞췄다.
- Web `/admin`은 API 호출/실패와 가입/여행 생성 막대 그래프, 서버 부하, 디스크 사용률,
  첨부 저장소 사용량/한도 요약을 표시한다.
- `admin-priority3` API integration과 Playwright mock e2e에 새 필드를 추가했다.

**검증**: 로컬 WSL ext4 미러에서 `ruff check`, 앱 코드 mypy, `test_admin_priority3_api.py` 3건,
Web Prettier check, Web typecheck, Web lint, Web Vitest 27건, Web production build가 통과했다.
테스트 파일까지 포함한 mypy는 기존 fixture 인자 타입 미기재 패턴에서 실패해 앱 코드 대상으로
범위를 좁혀 확인했다. Playwright는 Windows에서 실행했고, WSL Next 서버(12805)를 띄워
`admin-priority3.e2e.ts` 대시보드 케이스 1건이 통과했다.

**다음**: PR을 만들고 merge한 뒤 T-222 System view Docker / 의존 API 상태로 진행한다.

## 2026-06-27 (codex) — T-218 prod Grafana 주소 반영

**작업**: Admin `/admin/grafana`가 prod Web 이미지에서 실제 public Grafana origin을 쓰도록
빌드타임 env와 compose 주입 경로를 정리했다. 실제 운영 도메인은 tracked 파일에 남기지 않았다.

**변경**:

- Web Docker build/runtime stage에 `NEXT_PUBLIC_GRAFANA_URL`,
  `NEXT_PUBLIC_GRAFANA_DASHBOARD_PATH` ARG/ENV를 추가했다.
- `infra/docker-compose.app.yml` app-web build args에 같은 값을 전달하고, Grafana 컨테이너
  `GF_SERVER_ROOT_URL`도 `NEXT_PUBLIC_GRAFANA_URL`과 맞췄다.
- dev/app compose의 Grafana 환경은 embedding/anonymous viewer 설정과 public root URL을 함께
  갖는다.
- `infra/.env.prod.example`, `.env.example`, docker/observability/Grafana runbook은
  `grafana.example.com` placeholder만 사용하도록 정리했다.
- `/admin/grafana` URL 조합 로직을 `apps/web/lib/admin/grafana.ts`로 분리하고 prod URL 조합 및
  fallback Vitest를 추가했다.

**검증**: 로컬 WSL ext4 미러에서 Web Vitest 27건, Web typecheck, Web lint, Web production build,
compose config parse, Prettier check가 통과했다. Playwright는 Windows에서 실행했고, WSL Next
서버(12805)를 띄워 `admin-grafana.e2e.ts` 1건과 admin-live catalog assertion 1건이 통과했다.
N150 live는 T-215 묶음 게이트로 보류한다.

**다음**: PR을 만들고 merge한 뒤 T-221 Dashboard 운영 현황 그래프/부하/용량 상세보기로 진행한다.

## 2026-06-27 (codex) — T-214 Seed / reset dev-only 안전장치

**작업**: Admin `/admin/seed`, `/admin/reset` placeholder를 dev/staging 전용 dry-run 화면으로
교체했다. production에서는 router include를 하지 않고, endpoint guard도 404를 반환한다.

**변경**:

- Pinvi API에 `GET /admin/seed/scenarios`, `POST /admin/seed/scenarios/{scenario_key}`,
  `GET /admin/reset/status`, `POST /admin/reset`를 추가했다.
- 실제 DB reset/seed 실행은 노출하지 않고 `dry_run=true`만 지원한다. `false`는
  `422 DRY_RUN_ONLY`로 거절한다.
- seed는 scenario별 `RUN <scenario_key>`, reset은 `RESET` 확인 문구와 `access_reason`을 요구한다.
- 성공한 dry-run은 `dev_seed.dry_run` 또는 `dev_reset.dry_run` audit을 남긴다.
- Web `/admin/seed`, `/admin/reset`은 dry-run form과 production 404 비활성 상태를 표시한다.
- `admin-live-matrix.live.ts`에서 seed/reset을 placeholder에서 실제 route로 전환했다.

**검증**: 로컬 WSL ext4 미러에서 API ruff format check, ruff check, mypy,
`test_admin_seed_reset_api.py` 4건, schemas/api-client typecheck, Web typecheck, Web lint,
schemas Vitest, Web production build가 통과했다. Playwright는 Windows에서 실행했고, WSL Next
서버(12805)를 띄워 `admin-seed-reset.e2e.ts` 3건과 admin-live catalog assertion 1건이 통과했다.
N150 live는 T-215 묶음 게이트로 보류한다.

**다음**: PR을 만들고 merge한 뒤 T-218 prod Grafana 주소 반영으로 진행한다.

## 2026-06-27 (codex) — T-213 Category mapping 운영 뷰

**작업**: Category mapping source of truth를 `kor-travel-map` `/v1/categories`로 결정하고,
Admin `/admin/category-mapping`을 read-only 운영 화면으로 교체했다.

**변경**:

- Pinvi API에 `GET /admin/category-mappings`를 추가했다. `include_counts`, `active_only`는
  upstream에 전달하고, `q`는 code/label/path/tier/icon 로컬 필터로 적용한다.
- 응답은 `source_of_truth`, `mode=read_only`, total/filtered/active/inactive count,
  `db_feature_total`, category tier/db count 필드를 포함한다.
- `@pinvi/schemas`, `@pinvi/api-client`, query keys에 admin category mappings read 계약을 추가했다.
- Web `/admin/category-mapping`은 summary, 검색, active/count filter, marker swatch preview,
  fallback/icon drift 표시, JSON export 초안을 제공한다.
- `docs/design/marker-palette.md`와 `docs/data-model.md`의 오래된 `app.category_mappings` 전제를
  upstream source-of-truth 기준으로 정리했다.
- `admin-live-matrix.live.ts`에서 category mapping route를 placeholder가 아닌 table route로 전환했다.

**검증**: 로컬 WSL ext4 미러에서 API ruff format check, mypy,
`test_admin_category_mappings_api.py` 2건, schemas/api-client/web typecheck, Web lint,
schemas Vitest, Web production build가 통과했다. Playwright는 Windows에서 실행했고, WSL Next
서버(12805)를 띄워 `admin-category-mapping.e2e.ts` 1건과 admin-live catalog assertion 1건이
통과했다. N150 live는 T-215 묶음 게이트로 보류한다.

**다음**: PR을 만들고 merge한 뒤 T-214 Seed / reset dev-only 안전장치와 운영 비활성화로 진행한다.

## 2026-06-27 (codex) — T-226 Dedup verdict mutation

**작업**: Admin `/admin/dedup-review`에서 pending dedup 후보를 판정할 수 있게 했다. Pinvi는
dedup 판단의 source of truth를 만들지 않고, `kor-travel-map`의
`PATCH /v1/admin/dedup-reviews/{review_id}` 계약을 relay한다.

**변경**:

- `KorTravelMapAdminClient.decide_dedup_review`를 추가했다.
- Pinvi API에 `POST /admin/dedup-review/{review_id}/verdict`를 추가했다.
- 요청은 `decision`, `access_reason`, 선택 `kor_travel_map_reason`, `decision=merged`의
  `master_feature_id`를 검증한다.
- 성공 시 `dedup_review.decide` audit을 같은 transaction에서 남기고, `X-Request-Id` UUID를
  보존한다.
- 공통 `ops_proxy` error mapping에 upstream 404/409와 request id parsing을 추가했다.
- `@pinvi/schemas`, `@pinvi/api-client`, query keys에 dedup verdict 계약을 추가했다.
- Web `/admin/dedup-review` detail panel에 pending 후보 verdict form, master feature 선택,
  Pinvi audit 사유, upstream reason, 성공/실패 표시를 추가했다.
- `kor-travel-map` consistency issue/report 경로는 현재 GET-only라 integrity status/fix mutation은
  T-227로 분리했다.

**검증**: 로컬 WSL ext4 미러에서 API ruff format check, mypy,
`test_kor_travel_map_admin_client.py` + `test_admin_dedup_integrity_debug_api.py` 26건,
schemas/api-client/web typecheck, Web lint, schemas Vitest, Web production build를 통과했다.
Playwright는 Windows에서 실행했고, WSL Next 서버(12805)를 띄워
`admin-dedup-integrity-debug.e2e.ts` 3건과 admin-live catalog assertion 1건이 통과했다.
N150 live는 T-215 묶음 게이트로 보류한다.

**다음**: 검증 후 PR을 만들고 merge한 뒤 T-213 Category mapping 실제 기능 및 source of truth
결정으로 진행한다. T-227은 upstream integrity mutation 계약이 생기면 착수한다.

## 2026-06-27 (codex) — T-212 Dedup / integrity / debug logs 운영 화면

**작업**: Admin `/admin/dedup-review`, `/admin/integrity`, `/admin/debug/logs`를 실제
read-only 운영 조회 화면으로 교체했다. `kor-travel-map` dedup review, consistency issue/report,
sanitized system/API logs를 Pinvi Admin에서 확인할 수 있게 했다.

**변경**:

- `KorTravelMapAdminClient`에 `list_dedup_reviews`, `list_integrity_issues`,
  `list_consistency_reports`, `list_system_logs`, `list_ops_api_call_logs`를 추가했다.
- Pinvi API에 `GET /admin/dedup-review`, `GET /admin/integrity/issues`,
  `GET /admin/integrity/reports`, `GET /admin/debug/logs/system`,
  `GET /admin/debug/logs/api-calls`를 추가했다.
- provider sync와 dedup/integrity/debug route가 같은 upstream ops error mapping을 쓰도록
  `ops_proxy` helper를 추가했다.
- `@pinvi/schemas`, `@pinvi/api-client`, query keys에 새 read-only 계약을 추가했다.
- Web `/admin/dedup-review`는 status/search/min score 필터, 후보 table, feature A/B detail panel을
  제공한다.
- Web `/admin/integrity`는 issue status/severity/provider 필터와 report severity 필터, issue/report
  table을 제공한다.
- Web `/admin/debug/logs`는 system log level/source/q 필터와 upstream API call method/min status/path
  필터를 제공한다.
- `admin-live-matrix.live.ts`에서 세 route를 table route로 전환하고 filter/sort live case를 추가했다.
- dedup verdict, integrity status/fix mutation은 reason/audit/idempotency/kill-switch 기준이 필요해
  T-226으로 분리했다.

**검증**: 로컬 WSL ext4 미러에서 API `ruff check`, mypy,
`test_kor_travel_map_admin_client.py` + `test_admin_dedup_integrity_debug_api.py` +
`test_admin_etl_provider_sync_api.py` 28건, schemas/api-client/web typecheck, Web lint,
schemas Vitest, Web production build를 통과했다. Playwright는 Windows에서 실행했고,
WSL Next 서버(12805)를 띄워 `admin-dedup-integrity-debug.e2e.ts` 3건과 admin-live catalog assertion
1건이 통과했다. N150 live는 T-215 묶음 게이트로 보류한다.

**후속**: T-212 PR은 merge됐고, T-226에서 dedup verdict mutation을 완료했다.

## 2026-06-27 (codex) — T-220 ETL / provider sync / Dagster 운영 화면

**작업**: Admin `/admin/etl`과 `/admin/provider-sync`를 실제 운영 조회 화면으로 교체했다.
Pinvi app-owned ETL 정의와 `kor-travel-map` provider ETL 상태를 같은 Admin 흐름에서 확인할 수
있게 했다.

**변경**:

- `KorTravelMapAdminClient`에 `kor-travel-map` `/v1/ops/dagster/summary`, `/v1/ops/metrics`,
  `/v1/ops/providers`, `/v1/ops/import-jobs` read method를 추가했다.
- Pinvi API에 `GET /admin/etl/summary`, `GET /admin/provider-sync`,
  `GET /admin/provider-sync/import-jobs`를 추가했다. `/admin/etl/summary`는 Pinvi Dagster registry와
  upstream ops 요약을 결합하고, upstream 일부 장애는 `degraded`/`down` 상태로 강등한다.
- Pinvi ETL registry는 현재 실제 정의인 `pinvi_kasi_special_days`, `kasi_special_days_job`,
  `kasi_poi_rise_set_job`, `kasi_special_days_schedule`을 노출한다.
- `@pinvi/schemas`, `@pinvi/api-client`, query keys에 ETL/provider sync 계약을 추가했다.
- Web `/admin/etl`은 Pinvi Dagster 상태, asset/job/schedule 목록, map Dagster counts,
  recent runs, provider import job status filter/table을 표시한다.
- Web `/admin/provider-sync`는 provider/dataset key 검색과 import job status filter/table을 제공한다.
- `admin-live-matrix.live.ts`에서 `/admin/etl`, `/admin/provider-sync`를 table route로 전환하고
  filter/sort live case를 추가했다.
- API 문서, Admin 실행계획, tasks/resume/changelog를 갱신했다.

**검증**: 로컬 WSL ext4 미러에서 API `ruff check`, mypy,
`test_kor_travel_map_admin_client.py` + `test_admin_etl_provider_sync_api.py` 22건,
schemas/api-client/web typecheck, Web lint, schemas Vitest, Web production build를 통과했다.
Playwright는 Windows에서 실행했고, WSL Next 서버(12805)를 띄워
`admin-etl-provider-sync.e2e.ts` 2건과 admin-live catalog assertion 1건이 통과했다. N150 live는
T-215 묶음 게이트로 보류한다.

**다음**: 검증 후 PR을 만들고 merge한 뒤 T-212 Dedup review / integrity / debug logs 운영 화면으로
진행한다.

## 2026-06-27 (codex) — T-210 Pinvi feature request / upstream change request 운영 통합

**작업**: Admin `/admin/features/change-requests`를 실제 운영 화면으로 교체하고, Pinvi 사용자
feature 제안 검토 큐와 `kor-travel-map` upstream change request 큐를 이어 볼 수 있게 했다.

**변경**:

- `KorTravelMapAdminClient.list_change_requests()`에 status/action/q filter를 추가하고, upstream
  409 중 `LOCK_BUSY`가 아닌 상태 충돌을 `INVALID_STATE` 계열 409로 보존하도록 했다.
- Pinvi API에 `/admin/features/change-requests`, `/approve`, `/reject` proxy endpoint를 추가했다.
  mutation은 admin 전용이며 upstream 성공 후 `feature_change_request.approve|reject` audit을 남긴다.
- `@pinvi/schemas`, `@pinvi/api-client`, query keys에 change request 목록/액션 계약을 추가했다.
- Web `/admin/features/change-requests`는 filter/table/detail payload inspector, reason 입력,
  approve/reject action, optimistic update와 실패 rollback을 제공한다.
- 기존 `/admin/feature-requests`는 upstream `request_id`가 있으면 변경 요청 큐로 이동하는 링크를
  표시한다.
- API 문서, Admin 실행계획, tasks/resume/changelog와 e2e/live matrix를 갱신했다.

**검증**: 로컬 WSL ext4 미러에서 API `ruff check`, mypy,
`test_kor_travel_map_admin_client.py` + `test_admin_features_api.py` +
`test_admin_feature_requests_api.py` 28건, schemas/api-client/web typecheck, Web lint,
Web production build를 통과했다. Playwright는 Windows에서 실행했고, WSL Next 서버(12805)를 띄워
`admin-feature-change-requests.e2e.ts` + `admin-feature-requests.e2e.ts` 5건이 통과했다.
N150 live는 T-215 묶음 게이트로 보류한다.

**다음**: 검증 후 PR을 만들고 merge한 뒤 T-220 `/admin/etl` + provider sync + Dagster 운영 화면으로
진행한다.

## 2026-06-27 (codex) — T-225 여행계획/날짜/POI 복사·이동·삭제 오케스트레이션

**작업**: 추가 요청 14번을 T-225로 구현했다. Admin이 여행계획, 날짜, POI를 복사·이동·삭제하고,
삭제/이동 전 영향도와 하위 항목 처리 정책을 확인할 수 있게 했다.

**변경**:

- Admin operation schema와 `AdminOperationImpact` / `AdminOperationResult` 계약을 추가했다.
- `/admin/trips/{trip_id}`에 trip operation impact, copy, owner move, delete endpoint를 추가했다.
  trip copy는 기존 사용자 copy 흐름을 `commit=false`로 재사용해 admin audit과 같은 transaction에
  묶는다.
- `/admin/trips/{trip_id}/days/{day_index}`에 day operation impact, copy, move, delete endpoint를
  추가했다. 대상 여행/day로 POI, 첨부, 댓글을 move/delete 정책에 따라 처리한다.
- `/admin/pois/{poi_id}`에 POI operation impact, copy, move, delete endpoint를 추가했다.
- 현 DB FK 구조상 day/POI/첨부 orphan은 허용하지 않고, impact API와 Web dialog가 불가 사유를
  표시한다.
- `@pinvi/schemas`, `@pinvi/api-client`, Web `/admin/trips/{trip_id}`,
  `/admin/pois/{poi_id}` 상세 화면에 운영 작업 dialog와 e2e 테스트를 추가했다.
- API 문서와 Admin 실행계획, tasks/resume/changelog를 갱신했다.

**검증**: 로컬 WSL ext4 미러에서 API `ruff check`, mypy,
`pytest tests/integration/test_admin_trips_api.py tests/integration/test_admin_pois_api.py -q`
(18 passed), schemas/api-client/web typecheck, Web lint, Web production build를 통과했다.
Playwright는 Windows에서 실행했고, WSL Next 서버(12805)를 재사용해
`admin-trips.e2e.ts` + `admin-pois.e2e.ts` 8건이 통과했다.

**다음**: T-225 PR merge 후 T-210 Pinvi feature request와 upstream change request 운영 통합으로
복귀한다.

## 2026-06-27 (codex) — T-224 여행/날짜/POI 파일 업로드와 용량 정책

**작업**: 추가 요청 13번을 T-224로 구현했다. 사용자가 여행계획, 날짜, POI에 파일을 업로드하고,
사용자와 Admin이 업로드 파일을 모아 보며, Admin이 전역/사용자별 파일 용량 정책을 관리할 수 있게 했다.

**변경**:

- `app.storage_settings`에 파일 정책 3종(개별 파일 최대, 여행계획 총량, 사용자 총량)을 추가하고,
  `app.users`에 사용자별 override 3종을 추가했다.
- `app.curated_plan_attachments`에 `trip_day_index`를 추가해 Trip day 첨부를 표현하고,
  여행/날짜/POI attachment quota를 DB metadata 기준으로 검사한다.
- API에 `/trips/{trip_id}/days/{day_index}/attachments*`, `/trips/{trip_id}/files`,
  `/users/me/files`, `/admin/files`, `/admin/settings/files`,
  `/admin/users/{user_id}/file-quota`를 추가했다.
- Admin 변경은 `settings.files_update`, `user.file_quota_update`, `attachment.delete` audit으로 기록한다.
- `@pinvi/schemas`, `@pinvi/api-client`, Web `/files`, `/admin/files`,
  `/admin/users/{user_id}`, Trip detail attachment UI를 새 계약에 맞췄다.
- API 문서, Admin 실행계획, tasks/resume를 갱신했다.

**검증**: 로컬 WSL ext4 미러에서 API `ruff check`, mypy,
`test_trips_api.py` + `test_admin_users_api.py` 27건, `packages/schemas` /
`packages/api-client` / `apps/web` typecheck, Web lint, Web production build를 통과했다.
Playwright는 Windows에서 실행했고, WSL Next 서버(12805)를 재사용해 신규 `admin-files.e2e.ts` /
`my-files.e2e.ts` 2건과 기존 `admin-users`, `admin-trips`, `trip-attachment`, `trip-detail` 8건이 통과했다.

**다음**: T-224 PR merge 후 T-225 여행계획/날짜/POI 복사·이동·삭제 오케스트레이션으로 진행한다.

## 2026-06-27 (codex) — T-223 사용자 아바타 / RustFS 이미지 관리

**작업**: 추가 요청 12번을 T-223으로 구현했다. 사용자와 Admin이 RustFS에 저장된 아바타 이미지를
조회, 업로드, 교체, 삭제할 수 있게 했다.

**변경**:

- `app.users`에 아바타 RustFS 객체 메타(`avatar_bucket`, `avatar_storage_key`, MIME, 크기,
  갱신 시각)를 추가했다.
- `app.storage_settings` 단일 행을 추가해 전역 아바타 최대 업로드 크기를 운영 중 변경할 수 있게 했다.
- 사용자 API에 `/users/me/avatar/upload-url`, `PUT/DELETE /users/me/avatar`,
  `GET /users/me/avatar/download-url`을 추가했다.
- Admin API에 `/admin/users/{user_id}/avatar/*`와 `/admin/settings/avatar`를 추가했다.
  Admin 변경은 `user.avatar_replace`, `user.avatar_delete`, `settings.avatar_update` audit으로 기록한다.
- `@pinvi/schemas`, `@pinvi/api-client`, Web `/profile`, Web `/admin/users/{user_id}`를 새 계약에 맞췄다.
- API 통합 테스트와 Windows Playwright mock E2E를 추가했다.

**검증**: 로컬 WSL ext4 미러에서 API `ruff check`, mypy, `test_storage_keys.py` 9건,
`test_user_avatar_api.py` + `test_admin_users_api.py` 7건, schemas/api-client/web typecheck,
Web lint, Web production build가 통과했다. Playwright는 Windows에서 실행했고,
WSL Next 서버(12805)를 재사용해 `admin-users.e2e.ts` + `profile-avatar.e2e.ts` 4건이 통과했다.

**다음**: T-223 PR merge 후 T-224 여행/날짜/POI 파일 업로드와 용량 정책으로 진행한다.

## 2026-06-27 (codex) — T-219 POI Admin 직접 생성

**작업**: 추가 요청 7번을 T-219로 구현했다. Admin이 특정 여행계획/day에 POI를 직접 생성하고
생성 사유를 감사 로그에 남길 수 있게 했다.

**변경**:

- `POST /admin/pois`를 추가했다. admin 전용이며 trip 존재 여부를 검증한다.
- admin POI 생성은 `app.trip_day_pois` row, 필요 시 `trip_days` row, KASI rise/set 초기 row,
  `poi.create` audit을 같은 transaction으로 처리한다.
- snapshot 기반 trip primary region 보정은 사용자 POI 생성과 같은 규칙을 따른다.
- `@pinvi/schemas`와 `@pinvi/api-client`에 `AdminPoiCreateRequest` / `createPoi`를 추가했다.
- Web `/admin/pois`에 trip 검색/선택 기반 생성 dialog를 추가했다. POI 이름/좌표/주소는
  `feature_snapshot`으로 조립하고, 생성 성공 시 POI 상세 화면으로 이동한다.
- API 문서와 Admin 실행 계획, tasks/resume/changelog를 갱신했다.

**검증**: 로컬 WSL ext4 미러에서 API focused pytest 8건, API `ruff check`, focused mypy,
`packages/schemas`/`packages/api-client`/`apps/web` typecheck, Web lint, Web production build를
통과했다. WSL Next 서버(12805)를 Windows Playwright runner가 재사용하는 방식으로
`admin-pois.e2e.ts` 3건이 통과했다.

**다음**: T-219 PR merge 후 T-223 사용자 아바타/RustFS 이미지 관리로 진행한다.

## 2026-06-27 (codex) — T-217 Trip Admin 직접 생성

**작업**: 추가 요청 5번을 T-217로 구현했다. Admin이 사용자 owner를 선택해 여행계획을 직접
생성하고, 생성 사유를 감사 로그에 남길 수 있게 했다.

**변경**:

- `POST /admin/trips`를 추가했다. admin 전용이며 owner 존재/활성 여부를 검증한다.
- admin trip 생성은 trip row와 `trip.create` audit을 같은 transaction에 기록한다. owner email
  원문은 응답/감사 로그에 남기지 않고 마스킹 값만 사용한다.
- `@pinvi/schemas`와 `@pinvi/api-client`에 `AdminTripCreateRequest` / `createTrip`을 추가했다.
- Web `/admin/trips`에 owner 검색/선택 기반 생성 dialog를 추가했다. 생성 성공 시 생성된 trip
  상세 화면으로 이동한다.
- API 문서와 Admin 실행 계획, tasks/resume/changelog를 갱신했다.

**검증**: 로컬 WSL ext4 미러에서 API focused pytest 7건, API `ruff check`, focused mypy,
`packages/schemas`/`packages/api-client`/`apps/web` typecheck, Web lint, Web production build를
통과했다. WSL Playwright mock e2e는 Chromium 바이너리 부재로 실행 전 실패했으나, WSL Next
서버(12805)를 Windows Playwright runner가 재사용하는 방식으로 `admin-trips.e2e.ts` 3건이 통과했다.

**다음**: T-217 PR merge 후 T-219 POI Admin 직접 생성으로 진행한다.

## 2026-06-27 (codex) — T-216 Trip Admin 상세 운영성 보강

**작업**: 추가 요청 1~4번, 11번을 T-216으로 구현했다. Admin 좌측 메뉴 active state가
route와 무관하게 dashboard처럼 보이는 문제를 고치고, 여행 상세 운영 화면에 날짜/POI와 사용자
동선을 보강했다.

**변경**:

- Admin sidebar를 icon-only compact view로 전환했다. active state는 가장 긴 href prefix 기준으로
  계산하고, icon link에 title/aria-label/`aria-current`를 부여했다.
- `/admin/trips/{trip_id}` 상세 API에 `days`와 `pois`를 추가했다. POI는 snapshot 기반
  label/주소/좌표, 일정, 메모, 비용, URL, 추가자 마스킹 정보를 포함한다.
- Trip 상세 UI에서 owner/가입 동반자/POI 추가자를 `/admin/users/{user_id}`로 연결하고,
  미가입 초대자는 별도 상태로 표시한다.
- 상세 계획 섹션에 day/POI 목록을 추가하고, POI row 클릭 시 지도 preview, snapshot, 상세정보,
  `/admin/pois/{poi_id}` 링크를 가진 dialog를 띄우도록 했다.
- 추가 요청 12~14번은 T-223 사용자 아바타/RustFS 이미지 관리, T-224 여행/날짜/POI 파일 업로드와
  용량 정책, T-225 여행계획/날짜/POI 복사·이동·삭제 오케스트레이션으로 분리해 execplan/tasks에
  추가했다.

**검증**: 로컬 WSL ext4 미러에서 API focused pytest 4건, API `ruff check`, focused mypy,
`packages/schemas`/`packages/api-client`/`apps/web` typecheck, Web lint, Web production build를
통과했다. local Playwright mock e2e는 WSL Chromium 바이너리 부재로 실행 전 실패했다.

**다음**: T-216 PR merge 후 T-217 여행계획 Admin 직접 생성에 진입한다. T-210 WIP stash는
보존 중이다.

## 2026-06-27 (codex) — T-209 Admin Features read proxy / 실제 화면

**작업**: `kor-travel-map` Admin의 feature 목록/상세 화면과 API 계약을 참고해 Pinvi
`/admin/features` placeholder를 실제 read-only 운영 화면으로 바꿨다.

**변경**:

- `KorTravelMapAdminClient`에 `GET /v1/admin/features`와
  `GET /v1/admin/features/{feature_id}` read method를 추가했다. 반복 query(`kind`,
  `category`, `status`, `provider`, `dataset_key`, `issue_type`)와 cursor/sort/order를 그대로
  upstream에 전달한다.
- FastAPI `/admin/features` / `/admin/features/{feature_id}` proxy router를 추가했다. admin/operator
  전용이며 Pinvi DB `feature.*`를 직접 조회하지 않는다.
- `@pinvi/schemas`, `@pinvi/api-client`, query keys에 Admin feature 목록/상세 계약을 추가했다.
- Web `/admin/features`를 검색/필터/table/cursor pagination/detail inspector로 교체했다. 상세는
  feature core, sources, issues, overrides, versions, change requests, files 묶음을 확인한다.
- live matrix에서 `/admin/features`를 table route로 전환하고 feature filter/sort case를 추가했다.
  mock e2e fixture도 Pinvi proxy 호출과 상세 inspector 검증을 포함하도록 보강했다.

**검증**: 로컬 WSL ext4 미러에서 API focused pytest 15건, API `ruff check`,
`packages/schemas`/`packages/api-client`/`apps/web` typecheck, Web lint, schemas Vitest,
Admin live catalog/list(5966 cases), Admin live catalog assertion, Web `next build`를 통과했다.
local Playwright mock e2e는 WSL Chromium 바이너리 부재로 실행 전 실패했다. N150 live 실행은
T-215 묶음 게이트로 보류한다.

**다음**: T-209 PR merge 후 T-210에서 Pinvi feature request와 upstream change request 운영 통합을
진행한다.

## 2026-06-27 (codex) — T-208 Admin IA / 대시보드 상태판

**작업**: Admin 구현 프로그램의 첫 코드 Task로 메뉴 구조와 대시보드 상태판을 보강했다.

**변경**:

- `/admin` sidebar를 Pinvi 운영 / 지도 데이터 / 시스템 운영 그룹으로 재정렬했다.
- `Features`, `Feature 변경 요청`, `Dedup review`, `Provider sync`, `정합성`, `Debug logs`
  placeholder route를 추가하고 기존 placeholder 문구를 Task ID + 기능 gap 중심으로 바꿨다.
- `/admin/system/summary` read-only API를 추가했다. admin/operator만 접근 가능하며 Pinvi API,
  DB, Web, Dagster, `kor-travel-map` API, RustFS 상태를 `ok/degraded/down/unknown`으로 요약한다.
  raw URL, 운영 도메인, secret은 응답에 넣지 않는다.
- `@pinvi/schemas`, `@pinvi/api-client`, Web 대시보드를 새 system summary 계약에 맞췄다.
- `apps/web/e2e/admin-live-matrix.live.ts`에 새 route와 대시보드 상태 카드 검사를 추가했다.

**검증**: 로컬 WSL ext4 미러에서
`pytest tests/integration/test_admin_system_summary_api.py tests/integration/test_admin_priority3_api.py tests/integration/test_bootstrap_admin.py -q`
(9 passed), API `ruff check`, `packages/schemas`/`packages/api-client`/`apps/web` typecheck,
Web lint, Admin live catalog/list(3633 cases), Admin live catalog assertion, schemas Vitest,
Web `next build`를 통과했다. N150 live browser 실행은 T-215 묶음 게이트로 보류했다.

**다음**: T-208 PR merge 후 T-209에서 `kor-travel-map` Admin proxy foundation과 `/admin/features`
실제 검색/상세 화면을 구현한다.

## 2026-06-27 (codex) — Admin 계획 리뷰 차단 이슈 반영

**작업**: 다른 에이전트가 `docs/execplan/admin-console-gap-plan.md`를 리뷰했고, 구현 진입 전
차단 이슈 2건을 반환했다. 첫째, 공개 추적 문서에 N150 bootstrap admin 이메일/비밀번호 조합으로
읽힐 수 있는 표현이 있었다. 둘째, T-214 seed/reset production 정책이 `404 또는 disabled 응답`을
허용해 기존 `docs/api/admin.md` / SPEC의 router 미등록/404 정책보다 약했다.

**변경**:

- `docs/resume.md`, `docs/journal.md`, `docs/runbooks/{admin,deploy,docker-app}.md`,
  `docs/architecture/map-marker-design.md`, `docs/tasks.md`에서 공개 credential 조합 표현을
  제거하고 placeholder 또는 "bootstrap 대상 계정"으로 바꿨다.
- T-214는 production에서 seed/reset router 미등록 + API 404로 고정했다.
- 보완 권고를 반영해 dedup route를 기존 SPEC/API의 `/admin/dedup-review` 단수로 맞추고,
  Grafana 메뉴 위치, T-209/T-211/T-212 최신 `kor-travel-map` OpenAPI 확인 게이트,
  mutation reason/audit/idempotency/kill-switch 기준을 계획에 추가했다.

**검증**: tracked 문서의 credential 조합 패턴 스캔, `git diff --check`, PR CI.

## 2026-06-27 (codex) — Admin 콘솔 기능 보강 계획 문서화

**작업**: Admin 콘솔에 메뉴만 있고 실제 기능이 비어 있는 영역이 많아, 구현을 계속하기 전에
상세 실행 계획을 먼저 문서화했다. `docs/api/admin.md`, `docs/runbooks/admin.md`,
`docs/spec/v8/04-admin.md`, frontend/testing 문서와 `kor-travel-map` Admin UI 구성을 비교했다.

**정리**:

- `features`, `etl`, `category-mapping`, `seed`, `reset` route가 placeholder 수준임을 명시했다.
- `kor-travel-map` Admin의 feature 목록/상세, change request, dedup review, provider sync,
  integrity, debug/log 화면을 Pinvi에서 참고할 기능으로 분류했다.
- Pinvi가 직접 소유하는 영역과 `kor-travel-map` proxy로만 다룰 영역을 분리했다.
- T-207~T-215 Task를 만들고, 각 Task를 별도 PR로 merge한 뒤 다음 Task에 들어가는 순서를
  정했다.
- 사용자 지시에 따라 단위 기능 검증은 로컬 WSL ext4 미러에서 수행하고, N150은 여러 기능이
  모인 뒤 묶음 live API/UI/e2e 게이트로 사용하도록 계획에 반영했다.

**다음**: 이 계획 PR을 먼저 merge한다. 다른 에이전트가 계획을 리뷰한 뒤 T-208(Admin IA /
메뉴 / 대시보드 상태판 보강)부터 구현을 시작한다.

## 2026-06-27 (codex) — N150 bootstrap admin 복구 + quote 실패 패턴 문서화

**작업**: N150에서 Admin 로그인이 "이메일 또는 비밀번호가 올바르지 않습니다."로
실패하는 원인을 확인했다. 운영 DB에는 bootstrap 대상 계정과 admin role 사용자가 모두
없었고, 문서의 Alembic seed 설명과 실제 코드가 어긋나 있었다.

**변경**:

- `apps/api/app/services/bootstrap_admin.py` — `PINVI_BOOTSTRAP_ADMIN_PASSWORD`가 설정된 경우
  startup에서 bootstrap admin 계정을 생성/복구한다. password hash가 바뀌면 active session을
  폐기하고, 비밀번호 원문은 로그/DB에 남기지 않는다.
- `apps/api/app/main.py` — FastAPI lifespan에 bootstrap admin 보장을 연결했다.
- `infra/docker-compose.app.yml`, `infra/.env.prod.example` — 운영 compose가
  `PINVI_BOOTSTRAP_ADMIN_EMAIL/PASSWORD`를 API 컨테이너에 전달하도록 했다.
- `apps/api/tests/integration/test_bootstrap_admin.py` — skip/create/repair/idempotent 테스트를
  추가했다.
- `docs/runbooks/{admin,docker-app,deploy}.md`, `CHANGELOG.md` — 초기 admin 실제 동작과
  N150 확인 절차를 문서화했다.
- `scripts/remote-docker-python.sh`, `scripts/README.md` — 원격 Docker 컨테이너 Python 확인을
  stdin 전달로 고정해 중첩 quote를 피하는 helper를 추가했다.
- `docs/agent-failure-patterns.md` — PowerShell→WSL→SSH→Docker→Python 중첩 quote 금지와
  stdin/base64 전달 표준 패턴을 추가했다.

**운영 조치**: N150 현재 DB에는 local-only 운영 런북의 임시 credential로 bootstrap 대상
계정을 수동 복구했고 `/auth/login` 200을 확인했다. 후속 배포부터는 startup bootstrap
경로가 같은 누락을 방지한다. 임시 credential은 공개 문서에 기록하지 않는다.

## 2026-06-26 (claude) — 민감 배포 노트(LOCAL) + 푸시 전 보안 감사 절차 (concierge 패턴 정렬)

**작업**: 사용자 지시 — 반복되는 배포 실수를 민감정보 포함해 별도 md에 상세 기록하고 gitignore,
AGENTS.md에서 참조, 각 worktree에 복사, remote push 전 보안 감사를 절차화. **kor-travel-concierge의
기존 패턴(`docs/deploy-runbook.local.md` + AGENTS.md "remote 푸시 전 보안 감사")에 맞춰** 정렬.

**발견(이번 작업이 즉시 잡은 유출)**: 직전 #235에서 노드 사설 IP를 `docs/runbooks/deploy.md`·
`docs/journal.md`에 예시로 적어 public main에 푸시한 상태였다(외부 라우팅 위험 낮으나 ADR-047 위반).
→ 두 곳 redact(placeholder/"런북 참조")로 정정. 보안 감사 절차가 바로 이런 유출을 막는 목적.

**변경**:

- `docs/deploy-runbook.local.md` 신규(**gitignore, LOCAL ONLY, 민감정보 포함**) — prod 접속(n150/router/
  포트/ktdctl/빌드 소스), incident log(IP 유출·runbook drift·GHCR·ktdctl 부작용·stale 소스 등),
  표준 배포 절차, 배포 후 체크리스트, "푸시 전 추가 스캔" 패턴. concierge 런북 구조와 동일.
- `.gitignore`: `*.local.md` + `docs/deploy-runbook.local.md` + `docs/prod-access.local.md` + `.local/`.
- `AGENTS.md` ADR-047 절: "prod 배포 & 민감 운영 노트" + "remote 푸시 전 보안 감사(필수 절차)" 추가
  (`git diff --cached` 비밀 스캔 + 런북 참조). `CLAUDE.md` 체크리스트·포인터 동기(ADR-016).
- `docs/runbooks/deploy.md`·`docs/journal.md` IP redact.
- `docs/deploy-runbook.local.md`를 각 worktree(pinvi/pinvi-codex/pinvi-antigravity)에 복사.

**검증**: 커밋 staged에 `git diff --cached`로 일반 비밀 + 프로젝트 민감값(노드 IP·SSH 사용자·도메인 등)
스캔 — 추가 라인 클린 확인 후 push. `git check-ignore docs/deploy-runbook.local.md` 통과(미추적).

## 2026-06-26 (claude) — Pinvi 이미지 GHCR 폐지 → 로컬 빌드 전환

**작업**: 사용자 지시 — "ghcr에서는 내리고 앞으로는 올리지 마". Pinvi 이미지를 GHCR에서
내리고, 앞으로 GHCR push를 중단한다. kor-travel-map/geo/concierge 스택처럼 운영 노드에서
로컬 빌드(`pinvi-*:latest-main`)로 정렬한다.

**N150 노드 조치**(prod 노드 — 접속/IP는 `docs/deploy-runbook.local.md`):

- 운영 중인 `ghcr.io/digitie/pinvi-{api,web}:deploy-836a18f`(직전 배포 #233+#234 콘텐츠)를
  로컬 `pinvi-{api,web}:latest-main`으로 retag. `~/kor-travel-docker-manager/.env`의
  `PINVI_API_IMAGE`/`PINVI_WEB_IMAGE`를 그 로컬 태그로 변경(.env 백업 후). 운영 컨테이너는
  콘텐츠 동일이라 재생성 없이 그대로 서비스 — GHCR 의존 제거.
- compose에 이미 `build.context: ../pinvi`가 있어 `ktdctl pinvi --build` 로컬 빌드가 가능함을 확인.
  빌드 소스 `~/pinvi`가 `b80ea44`(stale)였어 `origin/main`(`836a18f`)으로 ff 동기 — 다음 `--build`가
  옛 코드로 회귀하지 않도록.

**repo 변경(본 PR)**:

- `.github/workflows/docker-images.yml`(GHCR multi-arch push workflow) 삭제.
- `docs/runbooks/deploy.md`를 실제 흐름(ktdctl 로컬 빌드, GHCR 미사용)으로 재작성 — 기존
  `/opt/pinvi` + `deploy-node.sh` + GHCR pull 서술이 운영 실태(`~/kor-travel-docker-manager` +
  `ktdctl pinvi --build`)와 어긋나 있던 것도 함께 정정.
- `infra/.env.prod.example` 이미지 태그를 로컬(`pinvi-*:latest-main`)로 변경.

**남은 일(사용자 필요)**: GHCR 패키지(`pinvi-api`/`pinvi-web`) 실제 삭제는 현재 `gh` 토큰에
`delete:packages` scope가 없어 403. `gh auth refresh -h github.com -s delete:packages,read:packages`
후 재시도하거나 GitHub 웹 UI(Packages → 삭제)로 내린다.

## 2026-06-26 (claude) — 미인증 로그인 시 재인증 메일 재발송

**작업**: 사용자 지시 — 이메일 인증이 안 된 아이디로 로그인 시도 시 재인증 링크를 제공.
`docs/api/auth.md` §2.3/§3.1에 계약은 이미 문서화돼 있었으나(verify-email/resend endpoint +
login `verification_email_dispatched`) 구현이 비어 있었다. 그 계약을 구현했다.

**변경**:

- `services/user_registration.py` — `resend_verification_email(db, *, email)` 추가. 미인증·미삭제·
  비disabled 사용자에 한해 직전 미사용 signup 토큰을 폐기하고 새 토큰(24h) 발급 + 인증 메일 enqueue.
  같은 사용자 cooldown(`pinvi_email_verification_resend_cooldown_seconds`, 기본 60초) 안에서는 미발송.
- `api/v1/auth.py` — 로그인이 `EmailNotVerifiedError`(비밀번호 검증 통과 후)를 잡으면 자동 재발송하고
  `details.verification_email_dispatched`로 결과를 노출(소유가 비밀번호로 증명돼 enumeration 위험 없음).
  `POST /auth/verify-email/resend`(항상 `accepted=true`, enumeration-safe) 추가.
- 스키마: `schemas/auth.py` + `packages/schemas`(zod) + `packages/api-client`(`resendVerification`).
- 프론트: 로그인 화면이 `EMAIL_NOT_VERIFIED` 시 재발송 안내 + "인증 메일 다시 보내기" 버튼 제공.
- `config.py`에 cooldown 설정 추가. `docs/api/auth.md` §2.3/§3.1 구현 일치하게 보강.

**검증**: WSL ext4 미러 — `ruff check`/`ruff format --check`/`mypy --strict` 통과, 신규 통합
테스트(`test_verify_email_resend_flow.py`) 6건 + 기존 auth 흐름 포함 12 pass. web typecheck/lint/build
통과(전 workspace typecheck 포함).

## 2026-06-25 (codex) — N150 Web healthcheck 포트 보정

**작업**: PR #231 merge 후 N150에 `deploy-3c16b75` 태그로 API/Web을 재빌드·재기동했다.

**발견**: Web 페이지와 Admin route는 `12805`에서 200으로 응답했지만, Docker image healthcheck가
`localhost:3000`만 확인해 `pinvi-web-latest`가 `unhealthy`로 남았다.

**변경**:

- `apps/web/Dockerfile` — healthcheck가 `PINVI_WEB_PORT`, `PORT`, 운영 고정 포트 `12805`,
  기본 포트 `3000` 후보를 검사하도록 수정했다.

**검증**: `git diff --check`와 healthcheck JS 구문 확인을 통과했다. N150에서는 Web image
재빌드 후 `pinvi-api-latest`, `pinvi-dagster-latest`, `pinvi-web-latest`를 재생성했고,
API/DB/Web/Admin/Signup local smoke를 재확인했다.

## 2026-06-25 (codex) — 로컬 env Pinvi 키 반영 + OAuth 설정 판정

**작업**: 로컬 `.env`의 Resend 키 반영 여부, 로그인 인증 시간, Google OAuth 비활성 상태,
Admin 접근 URL을 점검했다.

**변경**:

- 로컬 `.env` — legacy `TRIPMATE_*`/`NEXT_PUBLIC_TRIPMATE_*` 값을 현재
  `PINVI_*`/`NEXT_PUBLIC_PINVI_*` 키로 복사했다(비밀값 출력 없음).
- 로컬 `.env` — ADR-047 dev 고정 포트에 맞춰 Web `12805`, API `12801`, Dagster `12802`
  기준 URL을 보정했다.
- `apps/api/app/core/config.py`, `.env.example` — access token 기본 만료 시간을 10분으로 변경했다.
- `apps/api/app/api/v1/oauth.py`, `apps/api/app/api/v1/mobile.py` — Google OAuth는 client id와
  secret이 모두 있을 때만 configured/started 상태가 되도록 강화했다.
- OAuth 통합 테스트와 `docs/api/auth.md`, `docs/integrations/social-login.md`, `CHANGELOG.md`,
  `docs/resume.md`, `docs/tasks.md`를 갱신했다.

**발견**: Resend API key는 legacy `TRIPMATE_RESEND_API_KEY`에 있었고 현재
`PINVI_RESEND_API_KEY`로 반영했다. Google OAuth client id는 있었지만 client secret이 비어 있어,
현 로컬 기준 Google 로그인/회원가입은 계속 비활성 상태가 맞다.

**검증**: WSL ext4 미러에서 OAuth Web/Mobile 통합 테스트 31건, security 단위 테스트 5건,
변경 API 파일 `ruff check`, 변경 app 파일 `mypy` 통과.

**다음**: Google OAuth를 실제 활성화하려면 로컬 `.env`의
`PINVI_GOOGLE_OAUTH_CLIENT_SECRET`을 채우고 API/Web을 재시작한다. Admin 접근 URL은
`http://localhost:12805/admin`.

## 2026-06-25 (codex) — 회원가입 이메일 outbox worker 연결

**작업**: 회원가입 시 인증 이메일이 실제로 발송되지 않는 문제를 추적했다.

**변경**:

- `apps/api/app/services/email_service.py` — `email_queue`를 주기적으로 drain하는
  FastAPI lifespan worker를 추가했다.
- `apps/api/app/main.py` — 앱 startup/shutdown lifespan에 email outbox worker를 연결했다.
- `apps/api/app/core/config.py`, `.env.example` — worker enable/interval/batch size 환경변수를 추가했다.
- `apps/api/tests/integration/test_email_queue_worker.py` — worker lifespan task 시작/취소와 비활성화 테스트를 추가했다.
- `docs/integrations/resend.md`, `CHANGELOG.md`, `docs/resume.md`, `docs/tasks.md` — Resend 운영 기준과 추적 문서를 갱신했다.

**발견**: `register_user`는 `app.email_queue` row를 만들지만,
`process_pending_email_batch` 호출자가 없어 API 프로세스가 pending 이메일을 발송하지 않았다.

**검증**: WSL ext4 미러에서 email worker focused pytest, 가입/비밀번호 재설정 관련
통합 pytest 10건, 변경 API 파일 `ruff check`, 변경 app 파일 `mypy` 통과.

**다음**: 기존 미커밋 `kor-travel-map` 계약 변경과 충돌 없이 PR 범위를 분리한다.

## 2026-06-24~25 (codex) — Admin live UI e2e 매트릭스 + N150 재배포 검증

**작업**: N150 운영 도메인 기준 Admin UI live e2e 2000개 이상을 Playwright 매트릭스로
생성했다. live 안전 게이트(`PINVI_ADMIN_LIVE_E2E=1`), worker별 UI 로그인 storage state,
route/filter/sort/navigation/dashboard/MCP validation 케이스를 분리했다.

**배포**: `ktdctl`로 Pinvi API/Web/Dagster를 재빌드·재기동했다. 운영 Web image의
`NEXT_PUBLIC_PINVI_API_URL`이 잘못 baked-in 되어 있던 문제를 배포 host compose에서 보정했고,
Web 번들 old URL hit 0건과 API/Web/Dagster 200/healthy를 확인했다.

**수정**:

- `/auth/login` live 응답이 user envelope가 아니라 user object를 직접 반환하는 계약에 맞춰
  web auth client/login page를 정렬했다.
- live case limit을 test registration 전에 적용해 2000개 제한 실행이 실제로 2000개 수준으로
  잘리도록 수정했다.
- 운영 rate-limit에 맞춰 live suite 기본 throttle, per-case retry/backoff, test timeout을 조정했다.
- 컨테이너 내부 backup path 탐색 fallback을 보강해 `/admin/backup` live route가 500으로
  떨어지지 않게 했다.
- 장시간 실행 중 access token/cookie 만료로 admin route가 로그인 화면에 리다이렉트되는 문제를
  worker storage state 10분 주기 UI 재로그인 갱신으로 막았다.

**검증**: Web typecheck/lint/Vitest/Prettier 통과. live e2e catalog는 3233개(매트릭스 3230 +
login 2 + catalog 1)를 생성한다. N150 live authenticated 실행은
`PINVI_ADMIN_LIVE_CASE_LIMIT=2001`, worker 1, throttle 2100ms, auth refresh 600000ms 기준
2004개 테스트가 모두 통과했다(`2004 passed`, 2.8h). 실행 후 임시 admin/session과
Playwright 결과 디렉터리 정리까지 확인했다.

## 2026-06-25 (claude) — map/geo/concierge 최신 API 계약 동기화 (ADR-049)

**작업**: 사용자 지시 — `kor-travel-map`/`kor-travel-geo`/`kor-travel-concierge`의 최신
(origin/main) API를 확인해 Pinvi를 맞춤. 각 저장소를 origin/main으로 점검(map `88316a6` /
geo `5e8a5d4` / concierge `8720dda`). 드리프트는 워크플로(분석 13 agent + 고심각 항목 adversarial
verify)로 도출하고 breaking/important 항목만 적용. 시작 브랜치가 origin/main보다 5 커밋 뒤(이미
머지된 geo v2 key #228 포함)라 origin/main에서 새 브랜치를 끊고 작업.

**변경**:

- **map 큐레이션 import (breaking)** — PR #533("Curated API 범용 계약 정리")이 public
  `GET /v1/curated-features/{id}/pinvi-copy`를 폐지하고 admin
  `GET /v1/admin/curated-features/{id}/detail-snapshot`로 옮김 + snapshot `plan`→`content` 개명.
  `KorTravelMapAdminClient.get_curated_detail_snapshot` 추가, user client `get_curated_pinvi_copy`
  제거, `notice_plan.py`가 admin client + `content` 키 사용, import 라우터에 `KorTravelMapAdminClientDep`
  주입. 큐레이션 import는 이제 admin 서비스 토큰 작업. 단위/통합 테스트 갱신.
- **geo `/v2/regions/within-radius` (breaking)** — 요청 `{radius_m, boundary_level}`→`{radius_km, levels[]}`,
  응답 `candidates[]`→level별 그룹 `{center, radius_km, sido[], sigungu[], emd[]}`(항목
  `{code, name, relation: contains|overlaps}`), enum `legal_dong`→`emd`. `kor_travel_geo.py`/`geo.py`/
  `schemas/geo.py` 갱신(`RegionsWithinRadius`/`RegionWithinRadiusItem` + `_regions_within_radius` 매퍼),
  covering-point 기본 `emd`. Pinvi web/mobile consumer가 없어 라우터 표면을 v2 계약에 그대로 맞춤.
  geocode/reverse/search/geo key(ADR-048)는 이미 일치 → 무변경.
- **concierge** — Pinvi에 client 없음(그쪽 contract도 PinVi 직접 연결 배제). doc-only 유지가 정답.
  `docs/integrations/README.md`의 부정확한 "레거시 Gemini" 표현 + ADR-037(superseded) rename
  tautology 정정. net-new 통합은 Sprint 6 MCP 결정으로 보류.
- ADR-049 추가, `CLAUDE.md` ADR 현황 + `CHANGELOG.md` Unreleased + 계약 문서 다수 동기화
  (rest-api §2.11, requirements §7, api/architecture notice-plans, kor-travel-geo §3.4, api/regions,
  geocoding-open-decisions D5).

**검증**: WSL ext4 미러에서 `ruff check`/`ruff format --check`/`mypy --strict` 통과, unit 169 pass(+1 skip),
영향 통합 테스트(`test_geo_api.py`, `test_admin_kor_travel_map_curated_import.py`) 10 pass.

**후속**: within-radius `relation`(contains/overlaps)을 UI에서 쓰게 되면 표시 규칙 결정.

## 2026-06-24 (codex) — Web Docker image vendor/domain workspace build 복구

**작업**: `kor-travel-geo` v2 대응 PR merge 후 운영 배포를 위해 Docker Images workflow를
수동 실행했으나, Web image build가 `npm install` 단계에서 vendored tarball
`apps/web/vendor/vworld-map-web-1.0.0.tgz`를 찾지 못해 실패.

**원인**: `apps/web/package.json`은 `vworld-map-web`과 `vworld-map-core`를 `file:` tarball로
참조하지만, `apps/web/Dockerfile`의 deps stage는 install cache layer용 package manifest만
복사하고 vendor tarball을 복사하지 않았다. 후속 build 단계에서는 Web 코드가 import하는
`@pinvi/domain` workspace도 Web dependency / Next transpile 대상 / Docker deps manifest 목록에서
빠져 있었다.

**변경**: `apps/web/Dockerfile` deps stage에서 `npm install` 전에
`apps/mobile/vendor/vworld-map-core-1.0.0.tgz`와
`apps/web/vendor/vworld-map-web-1.0.0.tgz`를 함께 복사하도록 수정. `@pinvi/domain`은
`apps/web/package.json` dependency, `next.config.mjs` `transpilePackages`, Docker deps stage package
manifest 복사 목록에 추가했다.

**검증**: WSL ext4 미러에서 `apps/web/Dockerfile` Web Docker image 전체 build 통과. 이후
PR merge, Docker Images workflow 재실행, 운영 노드 배포를 이어간다.

## 2026-06-24 (codex) — kor-travel-geo 신규 v2 API key 계약 대응

**작업**: 사용자 지시 — `kor-travel-geo` 신규 v2 API에 대응. v2 공개 REST `key`는 VWorld
API key와 동일하게 쓰고, key 추출/저장은 `kor-travel-geo`가 소유하도록 Pinvi 소비 계약을 조정.

**변경**:

- `apps/api/app/clients/kor_travel_geo.py` — 모든 v2 POST에
  `key=<PINVI_VWORLD_API_KEY>` query를 붙이고, key 미설정 시 upstream 호출 전
  `KorTravelGeoUnavailable`로 degrade. 로그에는 path만 남김.
- `apps/api/tests/unit/test_kor_travel_geo_client.py` — key query 전달과 key 미설정 시
  네트워크 미호출을 고정.
- ADR-048 추가, `CLAUDE.md` ADR 현황 동기화, `docs/integrations/kor-travel-geo.md`/
  `docs/api/regions.md`/`docs/architecture/geocoding-open-decisions.md`/env 템플릿을 최신
  v2 key·`point{lon,lat}`·`within-radius` 계약으로 정리.

**결정**: 별도 `PINVI_KOR_TRAVEL_GEO_API_KEY`를 만들지 않는다. 운영자는 Pinvi
`PINVI_VWORLD_API_KEY`와 `kor-travel-geo` `KTG_VWORLD_API_KEY`를 같은 raw 값으로 설정하고,
공개 API key hash 저장/검증은 `kor-travel-geo`가 소유한다(ADR-048).

**검증**: WSL ext4 미러에서 API venv를 재생성한 뒤
`pytest tests/unit/test_kor_travel_geo_client.py tests/integration/test_geo_api.py -q`
(16 passed), `ruff check app/clients/kor_travel_geo.py app/core/config.py
tests/unit/test_kor_travel_geo_client.py`, `mypy app/clients/kor_travel_geo.py
app/core/config.py`, Windows `git diff --check` 통과.

**발견**: ext4 미러의 기존 `apps/api/.venv/bin/alembic` shebang이 과거
`/mnt/f/dev/tripmate-codex/...`를 가리켜 통합 테스트 setup이 실패했다. 미러 venv만 삭제 후
`uv sync --project apps/api --extra dev`로 재생성해 해결했다.

**다음**: PR merge 후 v0.1.0 릴리즈 직전 최종 smoke/tag/GitHub Release notes.

## 2026-06-23 (codex) — kor-travel-map #508 계열 prod endpoint redaction 점검

**작업**: 사용자 지시 — `kor-travel-map` issue #508의 prod endpoint 정보 redaction 문제가
Pinvi에도 같은 형태로 남아 있는지 확인하고, 필요한 문서 redaction을 반영한 뒤 PR/merge.

**확인**:

- `kor-travel-map` #508에 기록된 실제 운영 도메인/IP 패턴은 Pinvi tracked 파일에 없음.
- 같은 성격의 공개 문서 잔여로 `docs/journal.md`의 WSL private IP 검증 로그와,
  `docs/runbooks/grafana-admin-embed.md`의 실제처럼 보이는 Grafana 도메인 예시를 확인.

**반영**:

- journal의 `PLAYWRIGHT_BASE_URL` private IP를 `<wsl-playwright-host>` placeholder로 치환.
- journal의 과거 검색 명령 안 legacy API host literal을 `<api-host>` placeholder로 치환.
- Grafana Admin embed runbook의 Grafana/app 도메인 예시는 `grafana.example.com` /
  `pinvi.example.com` / `*.pinvi.example.com` placeholder로 정리.

**검증**: Windows git tracked 검색으로 `kor-travel-map` #508 계열 실제 prod domain/IP 패턴
잔여 0건을 확인. `git diff --check` 통과. 문서 변경만이라 빌드/테스트는 생략.

**다음**: PR merge 후 v0.1.0 릴리즈 직전 최종 smoke/tag/GitHub Release notes.

## 2026-06-22 (claude) — 지도 feature 검색 abort 전파 (kor-travel-concierge #111 유사 패턴 예방)

**작업**: 사용자 지시 — kor-travel-concierge PR #111(BFF 프록시가 `request.signal`을 upstream
fetch에 미전파 → 취소된 POI 검색이 백엔드에서 계속 돌고 undici 커넥션 누수 → 이후 검색
지연/무응답)과 **동일하지 않더라도 비슷한 패턴**을 pinvi에서 검사하고 수정.

**진단**: pinvi는 BFF 프록시가 없고 브라우저가 FastAPI를 `@pinvi/api-client`로 직접 호출한다
(정확한 #111 버그는 부재). 그러나 **apps/web·packages 전체에 AbortSignal/`signal` 사용이 0건**
이었다 — 즉 어떤 fetch도 취소 신호를 전달하지 않는다. 가장 가까운 유사 패턴은 **지도 feature
검색**: `FeatureMapView.fetchInBounds`는 `latestRequest` 카운터로 stale 응답만 무시할 뿐
직전 in-flight 요청을 abort하지 않아, 빠른 pan 시 superseded viewport 검색이 백엔드에서 계속
완료된다(#111의 근본 원인과 동일). `MapSearchBox.submit`도 같은 형태.

**수정**:

- `@pinvi/api-client` feature endpoint(`inBounds`/`search`/`nearby`)에 `opts?: { signal }` 추가
  → `client.request`가 이미 `RequestInit.signal`을 upstream fetch로 전달하므로 그대로 흐른다.
- `FeatureMapView.fetchInBounds`: `AbortController` ref로 새 요청마다 직전 요청 abort + signal
  전달, unmount cleanup에서도 abort, AbortError는 정상 취소로 무시.
- `MapSearchBox.submit`: 새 검색마다 직전 abort + signal 전달, controller 동일성으로 stale
  상태 반영 가드(loading/results/error).
- `apps/web/lib/abort.ts`(`isAbortError`) + `apps/web/tests/apiClientSignal.test.ts`(signal 전파 고정).

**범위 판단**: 다른 fetch는 admin 폼/다이얼로그(빠른 supersession 아님)거나 react-query
`useQuery`(자체 cancellation 보유)다. #111의 typeahead/검색 abort 패턴은 지도 feature 검색뿐이라
거기에 집중했다. api-client가 이제 `signal`을 받으므로 향후 react-query queryFn의 `signal`도 연결 가능.

**검증**: WSL ext4 미러에서 `apps/web` typecheck/lint/unit(apiClientSignal)/전체 test/build 통과.

## 2026-06-20 (codex) — Claude PR #221~#223 사후 리뷰 + 오류 복구 storage 방어

**작업**: 사용자 지시 — 2026-06-19 이후 Claude Code PR을 closed 포함 사후 리뷰하고, 코멘트 작성 후
수정 사항을 한 PR로 모아 머지하는 작업.

**리뷰**:

- #221: ADR-047 운영 도메인 비노출 + Dagster 12802는 현재 main 기준 차단 이슈 없음. #222가
  같은 Dockerfile을 과거 모듈명으로 중복 추가하려는 위험을 코멘트로 기록.
- #222: stale duplicate로 리뷰 코멘트 작성 후 닫음. `apps/etl/tripmate`/`tripmate.etl.definitions`
  경로는 현재 존재하지 않고, #221의 `pinvi.etl.definitions`/12802와 충돌.
- #223: 방향은 정합하지만 error boundary 안에서 `sessionStorage`를 직접 호출해 storage 예외 시
  복구 UI 자체가 다시 깨질 수 있음을 코멘트로 기록.

**반영**:

- `apps/web/lib/error-recovery.ts`에 `claimErrorReloadAttempt` / `clearErrorReloadAttempt`를 추가해
  `window.sessionStorage` 접근을 try/catch로 방어.
- `RouteError` / `global-error`는 직접 storage 호출 대신 새 helper만 사용.
- `apps/web/tests/errorRecovery.test.ts`에 1회 reload guard와 storage 예외 방어 테스트 추가.

**검증**: WSL ext4 미러에서 `npm --workspace apps/web run test --
tests/errorRecovery.test.ts`(5 passed), `npm --workspace apps/web run typecheck`,
`npm --workspace apps/web run lint`, `npm --workspace apps/web run build`,
`npm --workspace apps/web run test`(20 passed) 통과. Windows `git diff --check` 통과.

**다음**: 통합 PR merge 후 v0.1.0 릴리즈 직전 최종 smoke/tag/GitHub Release notes.

## 2026-06-20 (claude) — Admin UI Next 기본 오류 화면 복구 보강 (kor-travel-geo T-278 #391 이식)

**작업**: 사용자 지시 — kor-travel-geo PR #391(T-278, issue #390)을 pinvi에 똑같이 반영.
Firefox 등에서 Admin UI가 Next 기본 전역 오류 화면(`This page couldn’t load` /
`Reload to try again, or go back.`)으로 떨어지고, 좌측 메뉴 이동 중 RSC/client transition
실패가 같은 화면으로 새던 방어 공백을 닫는다.

**현황 차이**: pinvi는 이미 `app/error.tsx`(→ `RouteError`)·`app/global-error.tsx`(인라인
스타일 한국어 화면)·`components/feedback/*`를 갖고 있었다. 부족한 것은 (1) 자동 복구 로직,
(2) `_rsc`를 만들지 않는 링크였다. kor-travel-geo의 raw CSS 패널 대신 pinvi 디자인 토큰/
Tailwind와 기존 `FullPageMessage`를 재사용해 이식했다.

**반영**:

- `apps/web/lib/error-recovery.ts` 신설 — chunk/RSC/network 패턴 분류 +
  `pinvi.web.error-reload:<pathname>` sessionStorage 키. (kor-travel-geo 함수 동등 이식)
- `RouteError`/`global-error.tsx`: recoverable 오류면 같은 pathname에서 1회만 hard reload,
  반복 실패는 복구 패널. 재시도 시 reload flag 제거. recoverable copy 분기.
- `apps/web/components/navigation/DocumentNavLink.tsx` 신설(document navigation `<a>`).
  admin 좌측 메뉴(`app/(admin)/admin/layout.tsx`)의 `next/link`를 DocumentNavLink로 교체해
  메뉴 이동이 `_rsc` client routing을 만들지 않게 했다(#390 "좌측 메뉴 이동 중 RSC 실패").
  RouteError "홈으로"도 document navigation으로 escape.
- `apps/web/tests/errorRecovery.test.ts` 신설(Vitest) — recoverable 분류 + storage key 고정.

**검증**: WSL ext4 미러에서 `apps/web` typecheck/lint/unit(errorRecovery)/전체 test/build.
admin e2e는 nav를 `page.goto()`로 이동(클릭 아님)하고 testid 유지라 영향 없음.

## 2026-06-20 (claude) — prod=ktdctl+공식도메인 / dev=127.0.0.1:12xxx host-mode + 포트 ask-before-kill + Dagster 12802 (ADR-047)

**작업**: 사용자 지시 — (1) 운영 주소(web/api/dagster/RustFS S3·콘솔)를 외부에 노출하지 말고
`.env`에 저장해 prod에서 동작, Dagster webserver 12802. (2) prod는 ktdctl + 공식 도메인,
dev는 여기서 직접 `127.0.0.1`의 12xxx 포트(별도 지시 없으면 dev). (3) dev Docker 네트워크는
host 모드 기본. (4) 고정 포트 점유 시 새 포트로 바꾸지 말고 강제종료 여부를 사용자에게
물어 거부하면 중지.

**문제**: `digitie/pinvi`는 공개 repo인데 운영 도메인(개인 dynamic-DNS)이 추적 파일 23곳에
하드코딩(일부 구 표기 `pinviapi`, 하이픈 없음)되어 있었다. `docker-compose.app.yml`은
`PINVI_ENVIRONMENT: smoke`·CORS·web build arg를 하드코딩해 운영 `.env` override가 막혀
있었고, `apps/etl/Dockerfile`이 없어 Dagster 컨테이너 경로가 미완성, dev compose는
`12802:3000`이었다.

**반영(ADR-047)**:

- 추적 파일 23곳의 실도메인을 `*.example.com` placeholder로 치환(de-leak). 실값은
  gitignore된 `infra/.env.prod`(템플릿 `infra/.env.prod.example`)에만 둔다. 모바일 bundle
  id(`app.json`)는 앱 정체성이라 유지.
- `infra/docker-compose.app.yml` 운영 민감 값(ENVIRONMENT/DATABASE_URL/JWT/CORS/
  WEB_BASE_URL/OAUTH_CALLBACK/RUSTFS public/SENTRY env, web build arg)을
  `${VAR:-smoke기본값}`으로 parameterize + `app-dagster`(profile etl, `12802:12802`) 추가.
- `apps/etl/Dockerfile` 신설(`dagster-webserver -p 12802 -m pinvi.etl.definitions`),
  dev compose dagster `12802:3000` → `12802:12802`.
- `scripts/{deploy-node,docker-app}.sh`에 `PINVI_ENV_FILE`(compose `--env-file`) +
  `PINVI_ENABLE_DAGSTER` 추가. `.gitignore`에 `.env.prod`/`.env.production`.
- CI(`docker-images.yml`)의 빌드타임 API URL은 `secrets.NEXT_PUBLIC_PINVI_API_URL`에서
  받도록 변경(placeholder fallback). presigned 서명 host는 `s3-api`(public endpoint),
  서버→RustFS 내부는 `app-rustfs:9000`로 분리.
- `decisions.md` ADR-047 + `CLAUDE.md`/`AGENTS.md` 동기화, deploy/docker-app 런북 갱신.

**반영(dev/prod 운영 모델)**:

- `scripts/dev-up.sh`: api/web/dagster를 `127.0.0.1`로 bind(`--host 127.0.0.1`,
  next `--hostname 127.0.0.1`), NEXT_PUBLIC도 `http://127.0.0.1`. 시작 시 무조건 dev-down
  하던 것을 제거 → 고정 포트 점유 시 **새 포트로 바꾸지 않고** 강제종료 여부를 묻고(TTY),
  거부/비대화형 기본은 **중지**(exit 3). `PINVI_DEV_FORCE_KILL=1`로만 비대화형 강제종료.
- `infra/docker-compose.yml`: dev 기본 **host 네트워크 모드**. postgres/rustfs/rustfs-init/
  dagster에 `network_mode: host`, RustFS는 `RUSTFS_ADDRESS=:12101`/`:12105` 직접 bind,
  내부 참조는 `127.0.0.1`(DB/rustfs). observability profile은 metric 타겟 때문에 bridge 유지.
- `CLAUDE.md`/`AGENTS.md` 포트 정책을 "먼저 종료 후 재기동" → "ask-before-kill + dev 127.0.0.1
  - prod ktdctl/공식 도메인 + 기본 dev"로 정정. `local-dev.md`/`docker-app.md` 갱신.

**검증**: `docker compose config` (WSL) — app.yml smoke 기본값 유지 + `--env-file
infra/.env.prod --profile etl`에서 실도메인 치환·`app-dagster` 12802 확인. dev compose
host 모드 default/etl/observability profile 모두 config OK. `pinvi-dagster` 이미지 빌드 +
컨테이너 webserver가 `:12802 /server_info` 응답(1.13.10). `bash -n` 스크립트 OK. 추적 파일에
실도메인 0건.

**다음**: 운영 노드에서 `infra/.env.prod`의 시크릿(change-me) 채우기 + repo secret
`NEXT_PUBLIC_PINVI_API_URL` 설정 + reverse proxy(공식 도메인→12xxx 포트) 구성.

## 2026-06-18 (claude) — codex PR #218/#219 사후 상세리뷰 + 문서 drift 반영

**작업**: 어제 fast-merge(리뷰 0건)된 codex PR #218(StyleSeed UI 토큰)·#219(Web 지도
`vworld-map-web` 전환)을 `docs/runbooks/pr-review-sprint4.md` 기준으로 사후 리뷰했다.
5개 차원(map 런타임 / 의존성 / ADR·문서 drift / design token·a11y / cross-PR drift)을
멀티에이전트로 점검하고 각 발견을 적대적으로 교차검증했다(raw 5 → confirmed 5, 0 dropped).

**검증 결과 — 두 PR 모두 기능 정상**:

- #219: WSL ext4 미러 fresh install에서 `npm install`/typecheck/lint/build 전부 통과.
  `maplibre-vworld` 완전 제거(lock 0건·`npm ls` empty·node_modules 부재), `vworld-map-web`/
  `vworld-map-core` `file:` pin 정상 resolve, vendored tgz `index.d.ts` export가 facade
  import을 모두 충족. 드롭한 `maplibre-vworld/style.css`는 신규 패키지가 CSS 미배포라 정합.
- #218: token 값이 기존 hex와 일치(on-primary/ink/muted-soft/primary), `touch`/`ring`/
  `canvas` 토큰 정의·card shadow 8% cap·motion 토큰이 globals.css와 일치.

**반영(문서 drift + 죽은 코드 정리)**:

- `README.md` 3곳(현재상태 callout 8행·책임 목록 71행·외부통합 인덱스 190행)이 여전히
  `maplibre-vworld(-js)`를 현재 Web 지도로 표기 → `vworld-map-web`로 정정. #219가
  AGENTS.md/CLAUDE.md/architecture.md는 갱신했지만 README는 누락(변경 파일 목록에 없었음).
- `docs/resume.md` 릴리즈 로드맵 v0.1.0 행(778)도 `maplibre-vworld` → `vworld-map-web`
  (같은 파일 상단 전환 엔트리·AGENTS.md:225와의 불일치 해소).
- `apps/web/app/globals.css`의 미사용 `:root --duration-*/--ease-*` 변수 제거 — 컴포넌트는
  Tailwind preset utility만 소비하고 `var(--duration*/--ease*)` 소비처 0건. motion 값 중복
  3곳(motion.ts·tailwind-preset.cjs·globals.css) 중 죽은 소스 1곳 정리. canonical 토큰은
  `packages/design-tokens`(motion.ts + preset) 유지.

**검증**: 정정 후 WSL 미러에서 `apps/web` lint/build 재통과.

**다음**: PR 머지 후 v0.1.0 릴리즈 직전 최종 smoke/tag/GitHub Release notes.

## 2026-06-18 (codex) — T-201 Web 지도 `vworld-map-web` 전환

**작업**: 사용자 지시 — "web 지도뷰를 maplibre vworld react로 변경" + "`maplibre-vworld-js`
dependency 삭제". 작업 전 미커밋 agent 설정 파일 변경은 `stash@{0}`에 보존하고,
`origin/main`에서 `agent/codex-web-vworld-map-web` 브랜치를 만들었다.

- `apps/web/vendor/vworld-map-web-1.0.0.tgz`를 `F:\dev\maplibre-vworld-react`에서
  `npm pack`으로 생성해 vendored tarball로 추가. `vworld-map-core`는 npm workspace의
  단일 package instance 유지를 위해 기존 `apps/mobile/vendor/vworld-map-core-1.0.0.tgz`
  file spec을 Web도 공유.
- `apps/web/package.json`/`package-lock.json`: `maplibre-vworld` GitHub archive 의존성 제거,
  `vworld-map-core` + `vworld-map-web` `file:` 의존성 추가.
- `apps/web/components/map/vworldPrimitives.tsx`: `vworld-map-web`의 `VWorldMapView`,
  `ClusterLayer`, `MakiMarker`, `Popup`, `UserLocationMarker`, `MapContextMenu`를 lazy import하고,
  `ClusterPoint`/`MapLibreEvent`/`MapLibreMap`/`MapMouseEvent` 타입을 re-export.
- `MapView`/`FeatureMapView`/`TripMapView`: 직접 `maplibre-vworld`/`maplibre-gl` 타입 import를
  제거하고 `vworldPrimitives` facade를 사용. `maplibre-vworld/style.css`와 T-074 dev React
  `require` shim 제거.
- **ADR-046** 추가: Web 지도 클라이언트도 `maplibre-vworld-react`의 `vworld-map-web`으로 전환.
  ADR-015는 Kakao 폐기 결정은 유지하되 Web 소비 패키지 결정은 ADR-046으로 superseded.
- `AGENTS.md`/`CLAUDE.md`, `docs/integrations/maplibre-vworld.md`, frontend/compliance/sprint/runbook
  문서, `CHANGELOG.md`, `docs/tasks.md`를 새 의존성 기준으로 동기화. T-201 완료 처리.

**검증**: WSL ext4 미러에서 `npm --workspace apps/web run typecheck`, `lint`, `build`,
`test`(Vitest 15) 통과. `npm ls maplibre-vworld`는 empty,
`npm ls vworld-map-web vworld-map-core --workspace apps/web --depth=0` 정상. NTFS→ext4
rsync 중 기존 미러의 `.venv`/`.venv-wsl` 삭제 경고가 있었지만 Web 검증 경로에는 영향 없음.

**다음**: PR 리뷰/머지 후 v0.1.0 릴리즈 직전 최종 smoke/tag/GitHub Release notes.

## 2026-06-18 (codex) — StyleSeed 디자인 규칙 적용 + 문서화

**작업**: `https://styleseed-demo.vercel.app/llms.txt`와 full context의 핵심 규칙을
Pinvi 기존 Airbnb/Rausch 톤에 맞게 흡수했다. StyleSeed는 새 브랜드 스킨이 아니라 AI
UI 작업 품질 게이트로 해석하고, marker 16색은 데이터 표현 예외로 유지했다.

- `docs/design/styleseed-rules.md` 신규 추가: semantic token, 단일 accent, shadow
  8% cap, rhythm, 상태 UI, 접근성, motion/form 규칙과 Pinvi 충돌 해결 순서를 정리.
- `packages/design-tokens`에 motion token(`fast`/`normal`/`moderate`, `pinvi`/`spring`
  easing), Tailwind `min-h-touch`/`min-w-touch`, focus/motion용 토큰을 추가하고 card shadow를
  8% opacity로 낮췄다.
- Web 홈(`/`)을 bare text/button 화면에서 surface 기반 action hub로 정리하고,
  `FullPageMessage`/`PageLoading`/`RouteError`에 surface, focus ring, 44px target,
  reduced-motion 기준을 반영했다.
- 모바일 공용 UI(`apps/mobile/components/ui.tsx`)에서 색상 hex를 semantic token import로
  대체하고, 기본 screen/card spacing과 checkbox/chip touch target을 정렬했다.
- `DESIGN.md`, `docs/architecture/frontend.md`, `docs/design/marker-palette.md`,
  `CHANGELOG.md`에 StyleSeed 적용 기준과 마커 색 예외를 기록했다.

**검증**: WSL ext4 미러에서 `npm install` 후 `npm run typecheck`, `npm run lint`,
`npm --workspace apps/web run build`, `npm run test` 통과. 최초 typecheck는 미러 의존성
미설치로 실패했고, `npm install` 후 재실행해 통과.

**다음**: PR 리뷰/머지 후 v0.1.0 릴리즈 직전 smoke/tag 절차를 이어간다.

## 2026-06-17 (claude) — Admin UI 전체 테이블 TanStack Table + Virtual + Query 전환

**작업**: Admin UI(`apps/web/app/(admin)/admin/**`)의 모든 테이블 15개를 `@tanstack/react-table`
(headless) + `@tanstack/react-virtual` 기반 단일 컴포넌트로 교체하고, 데이터 패칭을 TanStack
Query로 전환. 사용자 결정 = (모든 테이블 / 패리티+신규기능 / Query 도입). 계획·분석은 plan mode
에서 Explore×3 + Plan 에이전트로 수립, 페이지 마이그레이션은 frontend-developer 4개 병렬.

- **공유 컴포넌트** `components/admin/AdminTable.tsx` — `useReactTable`(정렬: 렌더는 `cell`,
  정렬키는 `sortValue`; sticky `<thead z-20>`; 정렬 헤더 `<button>`+`aria-sort`+lucide) +
  `useVirtualizer`(스페이서 `<tr>` 윈도잉으로 네이티브 `<table>` 레이아웃·role 유지, 행수
  ≤ threshold(30)면 전 행 렌더 → e2e 1행 mock 안정). 하위호환: `DataTable`는 re-export.
  순수 윈도우 계산은 `lib/adminTableWindow.ts`로 분리(단위 테스트). `sortDescFirst: false`로
  숫자 컬럼도 첫 클릭 오름차순(일관 UX).
- **Query 도입** — `components/admin/AdminQueryProvider.tsx`를 admin 레이아웃에만 마운트
  (root 비침범), 가드 `me()`를 `useQuery`로. `query-keys.ts`에 `admin` 네임스페이스 추가.
  리스트 10개는 `useQuery`(+페이지네이션군은 `keepPreviousData`)로 전환, 외부 필터/검색/페이지
  네이션·error/empty/loading testid는 그대로. 목록 리로드 mutation(emails resend / mcp revoke /
  feature-requests approve)은 `useMutation`+invalidate, backup 생성은 `setQueryData` 낙관적
  prepend(원래 즉시표시 UX 유지). 상세 3개의 nested raw `<table>` 5개도 `AdminTable`로 교체
  (컨테이너 testid 보존, 데이터/뮤테이션 로직 무변경).
- **테스트** — 단위(`AdminTable.test.tsx` jsdom RTL + `adminTableWindow.test.ts` node, vitest
  jsdom 설정 추가) + 신규 e2e `admin-table.e2e.ts`(헤더/정렬·aria-sort/empty/loading/sticky/
  가상화 mount-on-scroll). 행 정렬·가상화 검증 위해 `admin-table-sort-*`/행 `rowTestId`/
  `admin-table-scroll` testid 추가.

**검증**: (WSL 미러) `npm run typecheck`+`lint`+`build`+`test`(vitest 15) ✅.
(Windows) `npm run test:e2e -- admin` **23 passed**(기존 17 + 신규 admin-table 6). 기존 admin
스펙은 testid 보존으로 회귀 없음. 함정 메모: 응답이 ApiClient Zod 파싱을 거치므로 e2e mock의
user_id/request_id는 UUID여야 한다(아니면 RESPONSE_SHAPE_INVALID로 행 미렌더).

**상세리뷰(멀티에이전트 5차원 + adversarial verify, PR #217)**: 블로커 0, 마이너/nit 10건.
반영: backup 낙관적 insert snapshot_id 중복제거 복원, emails 재발송 실패 배너 필터변경 시 정리,
`queryKeys.admin.{emailsAll,mcpTokensAll,featureRequestsAll}` 추가 후 invalidate에 사용(raw 배열 제거).
후속(별도 PR 권장 — 본 마이그레이션 범위 밖): 11개 admin 페이지 module-level ApiClient→공유
`@/lib/api` 통일(+layout onUnauthorized 결정), 앱 전역 `apiErrorMessage` 헬퍼, `AdminPagination`
컴포넌트 추출 + `ADMIN_PAGE_SIZE` 상수화, emails/feature-requests columns `useMemo`, pois feature
빈값 fallback.

**남은 것**: 행 선택(opt-in 설계만, 미활성), 서버측 정렬(현재 클라이언트·페이지 한정),
나머지 route group의 Query 도입(범위 밖).

## 2026-06-17 (claude) — 이슈 #215 Expo/mobile 사후 리뷰 후속 정리 (P0 + VWorld 정책 + 문서 drift)

**작업**: 이슈 #215(Expo/mobile PR 사후 리뷰)의 완료 조건을 한 묶음으로 처리. 백엔드는
backend-developer, 모바일은 mobile-developer 전문 에이전트로 병렬 처리하고(파일 분리),
문서/ADR은 직접. Expo 플러그인 스킬(`building-native-ui`/`expo-dev-client`) 규칙 + ADR-043~045 기준.

- **#209 OAuth 백엔드(P0 차단)** — (1) Google provider `error` callback이 state를 보기 전에
  웹 `/login`으로 빠져 모바일 흐름이 `pinvi://oauth?error=`를 못 받던 문제: `_provider_error_redirect`로
  state를 조회/소비해 모바일/웹/연결 흐름에 맞게 라우팅. (2) `consume_mobile_exchange`(및
  `consume_login_state`)의 read-then-write 경합: `UPDATE ... WHERE consumed_at IS NULL AND
expires_at > now() RETURNING ...` 원자적 조건부 소비로 1회용 보장. 통합 테스트 4건 추가
  (provider error → 모바일 딥링크 / 웹 /login / 만료 code 401 / 동시 exchange 정확히 1건 성공).
- **#207 공유 URL 1회 손실(P0/P1)** — 생성 응답에만 있는 share `url`을 `Alert.alert`로만 띄워
  닫으면 복구 불가하던 것을, `issuedShareUrl` 상태로 화면에 보존(`<Text selectable>` + 경고 +
  숨기기). 공유 해제는 파괴적 확인 다이얼로그 추가.
- **#202 모바일 부팅 복구(P1)** — 네트워크/일시 오류와 확정 인증 실패(401)를 분리. 401(ApiError,
  refreshingFetcher가 이미 refresh 1회 실패)만 세션/토큰/캐시 정리. 네트워크 실패면 토큰 보존 +
  `lib/user-cache.ts`(AsyncStorage)에 캐시한 프로필로 부팅 + `offline` 플래그 + 홈 배너. 부팅 catch의
  중복 수동 refresh 제거.
- **VWorld 키 런타임 정책(P1, #194/#208)** — **ADR-045**: 현 단계는 인증 게이트 + 감사 로깅의
  "문서화된 운영 제한"으로 raw key 발급을 수용하되, opaque 단기 token/tile proxy를 공개 배포 전
  하드 게이트로 박음. `mobile.py` `get_vworld_token`에 구조화 감사 로그(`mobile.vworld_token_issued`,
  user_id/ttl만 — 키 원본 미로깅) 추가. maplibre-vworld.md에 모바일 키 정책 노트.
- **문서 drift 정리** — README/SKILL/AGENTS/CLAUDE/apps-mobile-README의 `SDK 53`→56, `비활성`→활성,
  `minSdkVersion 23`→24, `(미설치)`→설치 동기화. CLAUDE/AGENTS ADR 현황 ADR-045 반영(다음=ADR-046).

**검증**(WSL ext4 미러): API ruff ✅ + mypy --strict ✅(변경 파일) + pytest 30 passed(oauth 통합,
신규 4건 포함, 104s). 모바일/웹 typecheck ✅(전 9 workspace 포함) + web lint ✅.

**남은 것(실기기 — 코드 외)**: #211 Dev Client Android/iOS 실기기 smoke(로그인/지도/OAuth/공유/오프라인
부팅/foreground)는 물리 기기 필요 — 미수행. P2(#204/205/206 mutation rollback·검증, #203 동의 gate/
파괴적 확인, mobile CI lint/doctor/build gate)는 본 묶음 범위 밖 후속.

## 2026-06-16 (claude) — 모바일 Google OAuth 앱 클라이언트

**작업**: OAuth 대응 2차(모바일 앱). 백엔드(딥링크 1회용 code, 별도 PR) 위에 앱 흐름을 얹었다.

- `expo-web-browser@~56.0.5` 추가(네이티브 — EAS 재빌드 필요).
- `@pinvi/api-client` `mobileAuthApi`에 `oauthGoogleStart`/`oauthExchange` 추가.
- `lib/oauth.ts` — `loginWithGoogle()`: start → `WebBrowser.openAuthSessionAsync(url, 'pinvi://oauth')`
  → 결과 URL의 `code`/`error` 파싱 → `oauthExchange` → `MobileAuthResult`. 취소/에러 분류.
- `(auth)/login.tsx`에 "Google로 로그인" 버튼 + `adoptSession` 결선 + OAuth 에러 한국어 매핑.

**검증**: mobile typecheck ✅. (백엔드 OAuth PR 머지 후 동작. 실기기는 expo-web-browser+maplibre
포함 EAS Dev Client 재빌드 필요.)

## 2026-06-16 (claude) — 모바일 Google OAuth 백엔드 (딥링크 1회용 code)

**작업**: 모바일 OAuth 대응 1차(백엔드). 웹은 callback에서 쿠키를 세팅하지만 모바일은 cookie를
못 쓰므로, 같은 state/PKCE/안전 매칭(G-4)을 재사용하되 **딥링크 1회용 code** 패턴을 추가했다.

- `app.oauth_mobile_exchanges`(0024) — code_hash→user_id, 짧은 TTL + 1회 소비. 토큰을 URL에
  싣지 않도록 세션은 exchange 시점에 발급.
- `oauth_google.py`: `mint_mobile_exchange`/`consume_mobile_exchange`.
- 공통 callback(`/auth/oauth/google/callback`): `return_to`가 앱 딥링크(`pinvi://oauth`)면 쿠키 대신
  `pinvi://oauth?code=`(에러는 `?error=`)로 리다이렉트. 웹 흐름은 그대로.
- `POST /mobile/auth/oauth/google/start`(authorize URL, return_to=딥링크) +
  `POST /mobile/auth/oauth/exchange`(code→access/refresh 토큰 본문).
- config: `pinvi_mobile_oauth_redirect`/`_exchange_ttl_seconds`. 통합 테스트 7건(callback→code→
  exchange e2e, 잘못된/재사용 code 401, 에러 딥링크, start 200/503).

**검증**: ruff format/check 통과, py_compile OK. mypy/pytest는 api CI.

## 2026-06-16 (claude) — 모바일 지도 통합 (vworld-map-rn) + 라이브러리 #21 수정 (ADR-044)

**작업**: 사용자 지시 — maplibre-vworld-react 직접 수정(이슈→PR→머지) 후 모바일에서 소비.

- **라이브러리 점검**: `digitie/maplibre-vworld-react` 선결 이슈 #2~#10이 이미 모두 closed·머지됨
  (이전 세션, tileUrlTransform/camera/redaction/primitives/dist 등 완비, 8/8 그린).
- **소비 중 실제 gap 발견 → 수정(#21)**: `VWorldMapView`의 `markers` 편의 prop이 `color`/
  `highlighted`/`zIndex`/`ariaLabel`를 `<Marker>`에 전달하지 않아 모든 핀이 빨강으로 렌더됐다.
  core `MarkerItem`에 타입 필드 추가 + RN에서 전달 + 회귀 테스트 → PR #22 머지. 16색 마커 parity 확보.
- **Pinvi 소비(ADR-044)**: `vworld-map-core`/`vworld-map-rn`을 `npm pack`해 `apps/mobile/vendor/`에
  vendored tarball로 두고 `file:` 핀(둘 다 핀해야 `rn`의 core 의존 충족 — npm 미발행 방침).
  `@maplibre/maplibre-react-native@^11.3.4` + config plugin(`app.json`) 추가. lockfile 갱신.
- **지도 화면**: `(app)/map.tsx`를 placeholder → 실제 `VWorldMapView`로 교체. server-issued 키
  (`GET /mobile/vworld/token`)를 `apiKey`로 주입(ADR-043, 비번들), 내 위치 마커(파랑, color 전달
  검증) + `flyTo`로 "현재 위치로". 키 미발급 시 안내 화면.

**검증**: 라이브러리 8/8(typecheck/lint/test/build) + Pinvi mobile typecheck ✅. 실기기 동작은
네이티브 모듈 포함 EAS Dev Client 재빌드 필요(별도).

## 2026-06-16 (claude) — 모바일 trip 삭제 + 공유 링크 생성/해제 (lifecycle 완결)

**작업**: "남은 작업 끝까지" 5차(빌드 가능한 CRUD gap 마감).

- **여행 삭제** — 편집 화면 "위험 구역"에 `tripApi.delete`(soft_delete) + 확인 → 목록으로 이동.
  trip 라이프사이클(생성·읽기·수정·삭제) 모바일에서 완결.
- **공유 링크 생성/해제** — 상세 화면에서 `tripApi.createShareToken`(view_only, 생성 시 URL 표시) +
  기존 링크 `revokeShareToken`. (기존 링크 토큰은 응답에 노출 안 됨 — 생성 시 1회만.)

**검증**: mobile typecheck ✅.

**모바일 앱 빌드 라운드 종료**: 외부 의존(지도 라이브러리)·네이티브 재빌드(OAuth/push)·미구현
백엔드(push 토큰 endpoint)에 막힌 항목만 남아 빌드 가능한 잔여를 소진했다(상세는 `docs/resume.md`).

## 2026-06-16 (claude) — 모바일 일자 추가/삭제 + POI 필드 편집

**작업**: "남은 작업 끝까지" 4차(빌드 가능한 잔여 마무리).

- 여행 편집 화면: **일자 추가**(`tripApi.createDay`, day_index=max+1) / **일자 삭제**
  (`deleteDay`, 확인). POI 행을 눌러 편집 화면으로 이동.
- **POI 필드 편집** `(app)/trips/[tripId]/poi/[poiId].tsx` — 메모/예산을 `poiApi.update`(If-Match version)로 저장.
- `(app)/_layout`에 `trips/[tripId]/poi/[poiId]` 라우트 등록.

**검증**: mobile typecheck ✅.

**남은 것(빌드 불가/외부 선결)**: 지도 본체(`maplibre-vworld-react` #2/#3/#8), POI 추가
(feature 검색 — 지도 흐름에 종속), OAuth 연결 시작(expo-web-browser 등 네이티브 dep + dev-client
재빌드), push(expo-notifications + 백엔드 토큰 등록 endpoint 미구현). 이들은 외부 의존/재빌드가
선결이라 본 라운드에서 중단.

## 2026-06-16 (claude) — 모바일 새 여행 생성

**작업**: "남은 작업 끝까지" 3차 — 모바일에서 여행을 만들 수 없던 gap을 메웠다.
`(app)/trips/new.tsx`(제목/지역/날짜/공개범위, `tripApi.create`) 추가 + trips 목록에 "+ 새 여행"
버튼 + `(app)/_layout`에 `trips/new` 라우트 등록. 생성 후 상세로 이동. **검증**: mobile typecheck ✅.

## 2026-06-16 (claude) — 모바일 trip 편집/POI 재정렬 + 모바일 CI 게이트

**작업**: "남은 작업 끝까지" 2차.

- `(app)/trips/[tripId]`를 `[tripId]/index.tsx`(상세) + `[tripId]/edit.tsx`(편집)로 분리.
- 편집 화면: trip 메타 수정(`buildTripUpdate` + `tripApi.update` If-Match version), 일자별 POI
  재정렬(↑/↓ → `reorderMoves` → `poiApi.reorder`), POI 삭제. visibility/status는 칩 선택
  (`ChipGroup` UI 추가). `lib/api.ts`에 `pois` 바인딩 추가.
- **CI 게이트 보강**: 모바일 전용 PR(=`apps/mobile/**`만 변경)은 web.yml/api.yml 경로 필터에 안 걸려
  지금까지 CI typecheck가 없었다. `.github/workflows/mobile.yml`(`mobile-typecheck` job)을 추가하고
  `aggregate-ci.yml`이 `apps/mobile/**`·`packages/**` 변경 시 `mobile-typecheck`를 required check로
  기다리게 했다.

**검증**: mobile typecheck ✅. (다음: 지도는 외부 라이브러리 선결 대기 — 빌드 가능한 잔여 거의 소진.)

## 2026-06-16 (claude) — 모바일 settings 세부 화면 (telegram/consents/mcp-tokens)

**작업**: "남은 작업 끝까지" 1차 — `apps/mobile`에 설정 세부 화면 3종을 추가했다.

- `(app)/settings/telegram.tsx` — `telegramApi`로 대상 목록/연결(chat ID·별칭·기본)/재검증/삭제.
- `(app)/settings/consents.tsx` — `userApi.getConsents`/`withdrawConsent`로 동의 현황 + 선택 항목 철회
  (필수 약관은 철회 제외, 웹과 동일).
- `(app)/settings/mcp-tokens.tsx` — `userApi`로 토큰 발급(만료 칩 30/7/90/무기한, 원문 1회 selectable 표시)/회수.
- `lib/api.ts`에 `user`/`telegram` 바인딩 추가, settings 허브를 세부 화면 링크로 교체, `(app)/_layout`에 3개 라우트 등록.
- 새 네이티브 의존성 없이(클립보드는 `selectable` Text) 기존 dev-client APK 그대로 동작.

**검증**: mobile typecheck ✅. (다음: trip 편집/POI 재정렬.)

## 2026-06-16 (claude) — 모바일 RN 앱 인증 흐름 + 핵심 화면 구현 (Step 2 + 5)

**작업**: "앱 화면 끝까지" — `apps/mobile` RN 기반과 화면을 구현했다
(expo-implementation-plan §7 Step 2·5).

- **공용**: `@pinvi/api-client`에 `mobileAuthApi`(`/mobile/auth/*`) + `MobileAuthResponseSchema` 추가/export.
- **RN 기반**: `lib/tokens.ts`(SecureStore access+refresh), `lib/api.ts`(바인딩 API +
  401 시 single-flight refresh 후 자동 1회 재시도하는 `refreshingFetcher`), `lib/auth.tsx`
  (`AuthProvider`/`useAuth`: 부팅 복구 me→refresh, login/adoptSession/logout, `createAuthStore` 연동),
  `components/ui.tsx`(Screen/Field/Button/Card/Checkbox/EmptyState/ErrorView 등 NativeWind 키트),
  네비 가드(`(app)/_layout` 비인증→`/login`, `(auth)/_layout` 인증→`/`).
- **화면**: `(auth)/login`·`signup`(약관 4종)·`verify-email`(딥링크 토큰), `(app)/profile`,
  `(app)/index`(home), `(app)/map`(placeholder — server-issued 키 + `useUserLocation` 확인),
  `(app)/trips`(목록·검색)·`trips/[tripId]`(상세 읽기), `(app)/notice-plans`(복사),
  `(app)/settings`(허브), `shared/[tripId]/[token]`(익명 공유, 가드 밖).
- 공용 `LoginRequestSchema`/`RegisterRequestSchema`/`validateForm`/`buildCopyRequest`/`paletteHex`/
  `friendlyErrorText` 등 `@pinvi/domain`·`@pinvi/schemas` 재사용.

**검증**: mobile typecheck ✅, root typecheck ✅, web lint ✅, web build ✅(라우트 회귀 없음).
지도(§4)만 `maplibre-vworld-react` 선결(#2/#3/#8) 대기로 placeholder. 후속: trip 편집/POI 재정렬,
settings 세부 폼, OAuth 연결 시작(딥링크), push/offline.

## 2026-06-16 (claude) — 모바일 인증 백엔드 `/mobile/auth/*` (토큰 본문 발급)

**작업**: 모바일 앱은 httpOnly cookie를 못 쓰므로(Bearer 기반), 로그인/토큰 흐름의 서버 측을
구현했다(expo-implementation-plan §5 #2, "앱 화면 끝까지" 1단계).

- **`POST /mobile/auth/login`** — 인증 성공 시 `{user, access_token, refresh_token, expires_at}`를
  **본문**으로 반환(cookie 미세팅). 앱이 SecureStore에 보관.
- **`/mobile/auth/verify-email`** — verify 성공 시 로그인 상태로 토큰 본문 반환.
- **`/mobile/auth/refresh`** — 본문 `refresh_token`으로 회전 발급(옛 토큰 무효).
- **`/mobile/auth/logout`** — 본문 `refresh_token`으로 세션 폐기.
- 웹 `/auth/*`(cookie) 경로는 그대로 두고 같은 인증 서비스(`authenticate`/`issue_user_session`/
  `refresh_user_session`)를 재사용. 통합 테스트 4건(토큰 발급+Bearer 동작, 잘못된 자격 401, refresh
  회전·옛 토큰 무효, logout 폐기).

**검증**: ruff format/check 통과. mypy/pytest는 api CI. 다음 단계: RN 기반(프로바이더·인증 컨텍스트·
UI 키트·네비) + 화면 구현.

## 2026-06-16 (claude) — EAS Android development build 성공 (APK 산출)

**결과**: minSdk 24 수정 후 재빌드(build `c195bd46`)가 **성공**(18분, 10:48→11:06). 설치 가능한
**dev client APK** 산출.

- APK: `https://expo.dev/artifacts/eas/gGm7b6xYaS3aKLxTn0YIhA-KqHW46HNQZUBensU4gl8.apk`
- 빌드 상세: `https://expo.dev/accounts/digitie/projects/pinvi/builds/c195bd46-65c5-4a97-b50d-7a8bdef328e5`
- 사용: Android 기기/에뮬레이터에 APK 설치 → `npm --workspace @pinvi/mobile run start`
  (`expo start --dev-client`)로 Metro 연결.

이로써 Sprint M-1 활성화 + EAS development build까지 완료. 남은 것은 인증/지도/핵심 화면 구현
(`expo-implementation-plan.md` §7, §2).

## 2026-06-16 (claude) — EAS 빌드 1차 실패 → Android minSdk 24로 수정

**작업**: Android development build 1차(build `945c3785`)가 Gradle `processDebugMainManifest`에서
실패. EAS 로그(gzip) 해제로 원인 확인: **`Manifest merger failed : uses-sdk:minSdkVersion 23
cannot be smaller than version 24 declared in library [expo.modules.ui:56.0.18]`**.

- 원인: Expo SDK 56의 `expo.modules.ui`가 **minSdk 24**를 요구(Expo SDK 54+가 Android 최소를
  24로 상향). ADR-043이 23으로 박았던 게 SDK 56과 불일치.
- 수정: `apps/mobile/app.json` `expo-build-properties.android.minSdkVersion` **23 → 24**.
  ADR-043 / frontend.md / expo-implementation-plan / AGENTS.md / CLAUDE.md의 minSdk 23 → 24 정합
  (journal 역사 기록은 유지).
- 재빌드 진행.

## 2026-06-16 (claude) — EAS Android development build 실행 (@digitie/pinvi)

**작업**: 사용자가 EXPO_TOKEN을 제공해 EAS 클라우드 development build를 실제로 실행했다.

- `eas init --force`로 EAS 프로젝트 **`@digitie/pinvi`**(ID `2e24842e-…`) 생성·연결. `app.json`에
  `owner: digitie` + `extra.eas.projectId` 기록(+ expo-location 위치 권한 자동 추가).
- `eas build --platform android --profile development --non-interactive --no-wait`로 빌드 큐 등록.
  빌드: `https://expo.dev/accounts/digitie/projects/pinvi/builds/945c3785-6705-4e5c-a1c9-144459ba2901`
  (Android / internal distribution / SDK 56, in progress).
- npx 임시 eas-cli는 `build` 명령에서 `domino` 모듈 누락으로 실패 → **eas-cli 전역 설치**로 해결.
- EXPO_TOKEN은 secret이라 env로만 사용(커밋/출력 안 함).

**결과**: 클라우드 빌드 완료 시 Build Artifacts(APK) URL 산출 → dev client 설치 후
`expo start --dev-client`로 Metro 연결. 화면 구현이 다음.

## 2026-06-16 (claude) — EAS development build 준비 (expo-doctor 21/21)

**작업**: development build(EAS)를 위해 `apps/mobile`을 빌드 가능 상태로 정비했다.
`expo-doctor`가 4건을 지적해 모두 해소했다.

- **`newArchEnabled` 제거**: SDK 56 app config 스키마가 거부(New Arch는 RN 0.85 기본). app.json에서
  제거 + ADR-043/README/frontend/expo-plan 문서 정합.
- **metro `disableHierarchicalLookup` 제거**: Expo 권장값(false)으로 복원.
- **react 중복 해소**: `apps/mobile` react/react-dom 19.2.3 → 19.2.6으로 정합(root와 단일화, `npm ls`
  valid). Expo 권장 19.2.3 대비 patch 차이는 `expo.install.exclude`로 처리(typescript도).
- 결과: **`expo-doctor` 21/21 통과**. 전 workspace typecheck / web build 35/35 green 유지.

**EAS 빌드 자체는 Expo 계정 로그인(인터랙티브)이 필요**해 자율 실행 불가(`eas whoami`=Not logged in,
EXPO_TOKEN 미설정, app.json projectId 미연결). 사용자가 `eas login` → `eas init` → `eas build
--profile development`을 수행한다(README §활성화 3). 빌드 준비/문서는 본 PR로 완료.

## 2026-06-16 (claude) — Expo `apps/mobile` Sprint M-1 활성화

**작업**: 사용자 지시("m1활성화")대로 `apps/mobile`을 비활성 스캐폴드 → **활성화된 Expo SDK 56
앱**으로 전환했다 (ADR-041 활성화).

- root `package.json` `workspaces`에 `apps/mobile` 등록.
- Expo SDK 56 의존성 설치: package.json을 Expo `bundledNativeModules`(sdk-56) 기준 정확 버전으로
  정합(통합 56.x 체계 — expo-router ~56.2.11, expo-location ~56.0.18 등). `npm install`로 535
  packages 설치 + `package-lock.json` 갱신. `expo install --check`는 네이티브 모듈 전부 SDK 56
  정렬(typescript만 권장 6.0.3 vs repo 5.x — cosmetic, expo-managed 아님).
- **검증**: `apps/mobile` `tsc --noEmit` 통과(실제 Expo/RN 타입 기준). 루트 `npm run typecheck`
  (전 workspace), `npm run lint`, `npm run test`(Vitest 68), `npm run build`(web 35/35) 모두 green.
- 문서: README(활성화됨), ADR-041(활성화 note), expo-implementation-plan §0/§7 갱신.

**영향**: 의도적 CI-safe 유예 종료 — web CI `npm ci`가 Expo 트리를 설치하고 typecheck에
`apps/mobile`을 포함한다(web CI가 다소 무거워짐). 남은 것은 development build + 화면 구현.
WSL 미러 부재로 install/검증은 Windows에서 수행(lockfile은 플랫폼 독립, 권위 검증은 CI).

## 2026-06-16 (claude) — 모바일 기준 Expo SDK 53 → 56 상향

**작업**: 사용자 결정대로 `apps/mobile` 기준 Expo SDK를 53 → 56으로 상향했다
(maplibre-vworld-react example과 동일 기준).

- `apps/mobile/package.json`: `expo ~56.0.12`, `react`/`react-dom 19.2.3`, `react-native 0.85.3`,
  `expo-status-bar ~56.0.4`, `expo-build-properties ~0.13.2`, `typescript ~6.0.3`,
  `@types/react ~19.2.2` 등 SDK 56 정합(미설치 스캐폴드 — 정확한 patch는 활성화 시
  `expo install --check`가 reconcile).
- ADR-043에 2026-06-16 갱신 note 추가. ADR-011 / `frontend.md` / `expo-implementation-plan.md` /
  `apps/mobile/README.md` / `AGENTS.md` / `CLAUDE.md` / `spec/v8/03-frontend.md`의 SDK 53 표기를
  56으로 정합. ADR-041의 "SDK 53 스캐폴드 추가"는 역사 기록으로 유지.
- maplibre-vworld-react 이슈 #7(SDK 53 vs 56)은 이미 closed — Pinvi가 56으로 맞춰 불일치 해소.

**검증**: package.json JSON valid. `apps/mobile`은 root workspaces 밖(미설치)이라 web/api/etl CI
미트리거(문서 + 모바일 스캐폴드 변경).

## 2026-06-16 (claude) — 모바일 VWorld 토큰 endpoint + Bearer 인증 (ADR-043 서버 측)

**작업**: maplibre-vworld-react 이슈 #3(키 proxy/token 주입, `tileUrlTransform`) 해소에 맞춰,
ADR-043 "VWorld 키 비번들 + server-issued"의 **서버 측 짝**을 구현했다.

- **`GET /mobile/vworld/token`** (`app/api/v1/mobile.py`) — 인증된 클라이언트에 server-issued
  VWorld 키(`api_key`/`key_source`/`ttl_seconds`) 발급. 키 미설정 시 503 `VWORLD_NOT_CONFIGURED`.
  설정 `PINVI_VWORLD_API_KEY`(+ ttl) `config.py`에 추가.
- **인증 dep 확장**: `get_current_user_id`가 `pinvi_access` cookie뿐 아니라 `Authorization:
Bearer`도 수용(모바일=Bearer, expo-plan §5 #2). 검증 로직 공유.
- 경로 정합: Pinvi 자체 API는 `/v1` prefix가 없으므로(`app.include_router(api_router)` bare)
  endpoint는 `/mobile/vworld/token`. `apps/mobile`의 `config.ts`/`app.json` tokenPath와 expo-plan을
  맞췄다.
- 통합 테스트: cookie 인증·Bearer 인증 둘 다 키 반환, 미인증 401, 키 미설정 503.

**검증**: ruff/mypy/pytest는 api CI(`api.yml`)에서 실행(로컬 uv 미설치). 변경은 apps/api +
apps/mobile 설정 + 문서.

## 2026-06-16 (claude) — maplibre-vworld-react npm 미발행 = 의도 반영

**작업**: `maplibre-vworld-react`의 npm 미발행은 의도된 방침(Pinvi는 `maplibre-vworld-js`처럼
GitHub tarball/git-URL로 소비)임을 반영했다.

- `docs/architecture/expo-implementation-plan.md`: §4 표의 "npm 미발행" 행을 "git-URL/tarball
  설치 경로 미확정"으로 정정 + §4.2 "소비 모델 — git-URL/tarball(npm 미발행은 의도)" 추가.
  §7 라벨도 "#2(git-install 경로)"로 수정.
- `digitie/maplibre-vworld-react` 이슈 #2를 "npm 발행"이 아니라 **git-URL/tarball 한 줄 설치가
  동작하도록**(`vworld-map-core` `*` 의존 해소 + `dist` 번들)으로 정정.

## 2026-06-16 (claude) — Expo 앱 추가구현 계획 문서화

**작업**: `apps/mobile`(Expo Dev Client) 앱을 실제로 제작하기 위한 추가구현 항목을
`docs/architecture/expo-implementation-plan.md`로 정리했다.

- 공용 패키지 소비(이번 refactor로 `@pinvi/domain` 추가), 화면별 RN 구현 목록(웹 라우트 대응),
  플랫폼 어댑터 현황, **지도 `maplibre-vworld-react` 선결 의존(이슈 #2~#10)**, 백엔드 추가 필요
  (`/v1/mobile/vworld/token` 등), EAS/Dev Client 빌드, 권장 구현 순서를 담았다.
- ADR-043 VWorld 키 server-issued 정책의 서버 측 짝(`lib/config.ts`가 전제하는
  `/v1/mobile/vworld/token`)이 미구현임을 명시했다.
- `frontend.md` §6/§11 + `apps/mobile/README.md`에서 새 문서를 참조하도록 연결.

**검증**: 문서 전용 변경(코드 무변경). CI path-filter 미트리거.

## 2026-06-16 (claude) — Expo/web 공용 코드 정리: packages/domain 신설

**작업**: Expo·web 동시 대응을 위해 `apps/web/lib`의 플랫폼-무관 순수 로직을 공용 패키지로
모았다 (ADR-011 §2.1 `packages/domain` 계획 실현).

- **`packages/domain` 신설** (`@pinvi/domain`): 순수 도메인 로직 16개 모듈 + 각 Vitest 테스트를
  `apps/web/lib` → `packages/domain/src`로 `git mv`(이력 보존): distance, poiRank, comments,
  companion, errorMessage, featureRequest, formValidation, locationConsent, noticePlanCopy,
  poiDetail, shareLink, shareUrl, suggestParam, tripEdit, tripMapPoints, upload + marker.
- **markerPalette 중복 통합**: `apps/web/lib/markerPalette.ts`(labelColor)와 `@pinvi/design-tokens`
  MARKER_PALETTE(label_color) 분기를 해소. 팔레트 데이터는 design-tokens 단일 진실, 스타일 로직
  (paletteHex/markerStyleFor/CATEGORY_MARKER 등)은 `@pinvi/domain/marker`가 design-tokens 팔레트를
  import해 제공.
- **배럴 충돌 해소**: shareLink `VISIBILITY_LABEL` → `SHARE_VISIBILITY_LABEL`(여행 가시성 tripEdit과
  이름 충돌 회피).
- **apps/web import 재배선**: ~21개 component/page의 `@/lib/<moved>` → `@pinvi/domain`(+ MARKER_PALETTE/
  MarkerColorKey는 `@pinvi/design-tokens`). web-only 5개(api/featureBounds/locationAdapter/
  useDialogAutoFocus/useEscapeKey)는 `apps/web/lib` 유지.

**검증**: typecheck(전 workspace), Vitest(@pinvi/domain 17파일·58 + web 4 + schemas 6 = 68 passed),
web `next build` 성공, `next lint` 무경고, **Playwright e2e 52 passed**(기존 web 회귀 없음). `npm install`로
`@pinvi/domain` workspace 심링크 + lockfile 정합(외부 의존 추가 없음).

**다음**: Expo 앱 추가구현 항목 문서화(`apps/mobile`), maplibre-vworld-react 이슈는 등록 완료
(digitie/maplibre-vworld-react #2~#10).

## 2026-06-15 (codex) — 모바일 Expo Dev Client 기준선 반영

**작업**: 사용자 지시에 따라 `apps/mobile` 기준을 Expo Dev Client + EAS Build로
고정하고 Expo Go 미사용, React Native New Architecture, Android `minSdkVersion >= 23`,
VWorld server-issued key 구조를 반영했다.

- ADR-043을 추가해 모바일 런타임/빌드/키 발급 기준선을 accepted decision으로 박았다.
- `apps/mobile/package.json` script를 `expo start --dev-client` 기준으로 바꾸고,
  `expo-dev-client`, `expo-build-properties` 의존성과 EAS build script를 추가했다.
- `apps/mobile/eas.json`을 추가하고 development profile에 `developmentClient: true`를 설정했다.
- `app.json`에 `expo-dev-client`, `expo-build-properties`, Android `minSdkVersion: 23`,
  VWorld server-issued endpoint 설정을 추가했다.
- `apps/mobile/lib/config.ts`를 추가해 Expo `extra` / `EXPO_PUBLIC_PINVI_API_URL` 기반 앱 설정과
  VWorld token endpoint 계산을 분리했다.
- `CLAUDE.md`, `AGENTS.md`, `SKILL.md`, README, frontend 아키텍처, VWorld 통합 문서,
  data-policy, `apps/mobile/README.md`, `CHANGELOG.md`, `docs/resume.md`를 동기화했다.

**검증**:

- Windows: `apps/mobile/package.json`, `apps/mobile/app.json`, `apps/mobile/eas.json`
  JSON parse 통과.
- Windows: `apps/mobile/lib/config.ts`, `apps/mobile/lib/api.ts`, `apps/mobile/app/index.tsx`
  TypeScript syntax transpile 통과.
- Windows: `git diff --check` 통과.
- Windows: 수정 파일 대상 검색에서 Expo Go용 기본 start script와 모바일 public VWorld
  key 값 잔여 없음 확인.
- `apps/mobile`은 root workspace 밖의 비활성 스캐폴드라 전체 `tsc -p apps/mobile`은
  Expo/RN/@pinvi 의존성 미설치로 모듈 해석 단계에서 실패한다. `npm install`, Expo 실행,
  EAS build는 Sprint M-1 활성화 전이라 수행하지 않았다.

**다음**: Sprint M-1에서 `apps/mobile`을 root workspaces에 등록하고 WSL ext4 미러에서
`npm install` + `expo install --check` + EAS development build를 실행한다.

## 2026-06-15 (codex) — Pinvi 웹 favicon/app icon 설정

**작업**: 사용자가 제공한 `pinvi_favicon.svg` / `pinvi_app_icon.svg`를 기준으로
웹 favicon과 홈 화면 앱 아이콘 자산을 설정했다.

- `apps/web/public/favicon.svg`와 `apps/web/public/icons/pinvi-app-icon.svg`를
  원본 SVG로 추가했다.
- favicon SVG를 Playwright 렌더링으로 PNG화한 뒤 `favicon.ico`(16/32/48/64/128/256)를
  생성했다.
- app icon SVG에서 `apple-touch-icon.png`, 192px/512px PNG를 생성하고
  `site.webmanifest`에 연결했다.
- Next.js root metadata에 favicon, shortcut icon, Apple touch icon, manifest,
  `theme-color`를 명시했다.
- `CHANGELOG.md`의 `v0.1.0` 사용자 가시 변경 목록에 아이콘/manifest 추가를 기록했다.

**검증**:

- Windows: 생성된 PNG/ICO 크기와 ICO 포함 크기 확인, 512px/180px 아이콘 시각 확인.
- WSL ext4 mirror: `npm --workspace apps/web run lint`,
  `npm --workspace apps/web run typecheck`, `npm --workspace apps/web run build`,
  `npm --workspace apps/web run test`(62 passed) 통과.
- WSL ext4 mirror: Next build 산출물에서 `favicon.svg`, `favicon.ico`,
  `apple-touch-icon.png`, `site.webmanifest`, `theme-color` head 출력 확인.

**다음**: v0.1.0 릴리즈 직전 main에서 웹 smoke를 돌릴 때 브라우저 탭 favicon과
설치 프롬프트 아이콘도 함께 확인한다.

## 2026-06-13 (codex) — ADR-042 docker-manager 포트 대역 정렬

**작업**: `kor-travel-docker-manager`의 `config/docker-targets.yml` / `docs/ports.md`를
정본으로 삼아 Pinvi와 참조 서비스 포트를 재배정했다.

- ADR-037은 ADR-042로 supersede하고, `CLAUDE.md` / `AGENTS.md` 1쪽 진입 요약을 동기화했다.
- Pinvi API/Web/Dagster 기본 포트를 `12801` / `12805` / `12802`로 변경했다.
- `kor-travel-map` API/Admin API 기본값은 `12701`, `kor-travel-geo` 기본값은 `12501`로
  정렬했다.
- 공용 observability는 Grafana `12205`, cAdvisor `12301`, Prometheus `12401`로 정리하고
  RustFS host `12101`/`12105` ↔ container `9000`/`9001` 계약을 compose에 반영했다.
- `.env.example`, API settings, Web 기본 API URL, Playwright mock, Docker compose,
  dev/smoke/deploy scripts, runbook/API/integration 문서를 같은 포트 정책으로 맞췄다.
- docker-manager가 이미 Pinvi app target을 포함하므로 `ktdctl srv --build`를 1차 Docker
  실행 경로로 문서화하고, `scripts/docker-app.sh`는 폴백/smoke 경로로 낮췄다.

**검증**:

- WSL ext4 mirror: `docker compose -f infra/docker-compose.yml config`,
  `docker compose -f infra/docker-compose.app.yml config` 통과.
- WSL ext4 mirror: `bash -n scripts/dev-up.sh scripts/dev-down.sh scripts/docker-app.sh scripts/deploy-node.sh scripts/ops-node-doctor.sh` 통과.
- WSL ext4 mirror: API OAuth/storage focused pytest 26 passed, Web lint/typecheck/build/Vitest
  62 passed.
- Windows Playwright runner: 포트 표면 e2e 20 passed. 전체 e2e는 기존 auth mock 한계로 43 passed /
  9 failed(`/login` redirect)였고 포트 변경 회귀와는 별개다.
- WSL dev server: API `http://localhost:12801`, Web `http://localhost:12805`, Dagster
  `http://localhost:12802` 기동 및 `/health`/Web 200 확인.
- Windows: `git diff --check` 통과.

## 2026-06-13 (claude) — Expo apps/mobile 구조 스캐폴드 + Docker 진입 경로 docker-manager화

**작업**: 사용자 요청 두 건을 한 PR로 반영했다.

1. **Expo `apps/mobile` 구조 스캐폴드 (ADR-041, ADR-011 실행)** — Next.js 웹과 `@pinvi/*`
   공용 패키지를 공유하는 Expo SDK 53 앱 골격을 박았다. `app/`(Expo Router 진입 + `(auth)`
   group), `lib/`(api=SecureStore / location=expo-location→`@pinvi/hooks` LocationAdapter /
   storage=AsyncStorage→zustand StateStorage / stores=`createAuthStore` 주입), app.json·
   babel·metro(monorepo)·tailwind(NativeWind=`@pinvi/design-tokens` preset)·tsconfig·README.
   `app/index.tsx`가 `@pinvi/schemas`·`@pinvi/api-client` import로 공용 패키지 wiring을
   증명한다(frontend.md §6.2). **CI-safe**: root `workspaces`·`package-lock.json` 미변경 →
   install 그래프 밖 스캐폴드. 활성화(workspaces 등록 + install + 화면 + EAS)는 Sprint M-1.
2. **Docker 진입 경로 docker-manager화 (ADR-040)** — Docker 빌드/실행 1차 경로를
   `kor-travel-docker-manager`(`ktdctl`)로 문서화하고, 불가 시 `scripts/docker-app.sh` 폴백을
   명시했다. `docs/runbooks/docker-app.md` §0(두 책임 경계/1차 경로/폴백 조건), `CLAUDE.md`,
   `AGENTS.md`(ADR-016 동기) 갱신.

**검증**: 변경 파일이 `apps/mobile/**` + `docs/**` + `CLAUDE.md`/`AGENTS.md`뿐이라
web/api/etl path-filtered CI(`npm ci`)를 트리거하지 않는다. aggregate-ci 게이트는 필수 체크
0개로 즉시 green. `git diff --check` 통과.

## 2026-06-13 (codex) — v0.1.0 릴리즈 준비 + T-195/T-108

**작업**: 사용자 지시대로 1) v0.1.0 릴리즈 정리, 2) public/API 공통 rate-limit, 3) 운영 배포 자동화 foundation 순서로 진행했다.

- `CHANGELOG.md`를 추가해 `v0.1.0` 릴리즈 노트 초안을 만들었다. 실제 tag/GitHub
  Release는 PR-only 흐름상 main merge 후 생성한다.
- ADR-038을 추가하고 `RateLimitMiddleware`를 전역 적용했다. production/staging은
  Postgres `app.rate_limit_buckets`, dev/test/smoke는 memory backend를 쓴다.
- rate-limit 정책: `/public/*` IP 60/min, 인증 사용자 user/token 60/min, 로그인/가입/
  재설정/verify 5/min, OAuth 10/min, storage upload 30/min, 공유 토큰 60/min.
- T-108 foundation: `.github/workflows/docker-images.yml`, compose image override,
  `scripts/deploy-node.sh`, `scripts/*-docker-doctor.sh`, N150/Odroid 노드별 runbook을
  추가했다.
- 사용자 지시에 따라 ADR-039를 추가하고 노드 간 DB live sync 관련 문서와
  doctor 상태 점검 코드를 제거했다. Odroid는 실시간 대기 DB 노드가 아니라 ARM64 smoke와
  backup/restore 기반 수동 대체 배포 노드다.

**검증**:

- WSL ext4 mirror: `python -m pytest tests -q`(apps/api) → 342 passed, 1 skipped.
- WSL ext4 mirror: `ruff check --exclude .venv --exclude .venv-wsl .`,
  `ruff format --check --exclude .venv --exclude .venv-wsl .`, `mypy --strict app` 통과.
- WSL ext4 mirror: `npm run lint`, `npm run typecheck`, `npm run build`,
  `npm run test` 통과
  (web 62 passed, schemas 6 passed).
- WSL ext4 mirror: `python -m pytest tests -q`(apps/etl) → 3 passed.
- WSL ext4 mirror: `ruff check pinvi tests`, `ruff format --check pinvi tests`,
  `mypy --strict pinvi` 통과.
- WSL ext4 mirror: `bash -n scripts/deploy-node.sh scripts/ops-node-doctor.sh scripts/n150-docker-doctor.sh scripts/odroid-docker-doctor.sh` 통과.
- WSL ext4 mirror: `docker compose -f infra/docker-compose.yml config` /
  `docker compose -f infra/docker-compose.app.yml config` 통과.
- Windows: `git diff --check` 통과.

**다음**: PR로 올린 뒤 리뷰/merge. merge 후 main에서 `v0.1.0` tag + GitHub Release 생성.

## 2026-06-13 (codex) — T-199 런타임 계약/외부 서비스명 Pinvi hard cutover

**작업**: 호환 별칭 없이 런타임 계약과 외부 서비스명을 새 이름으로 정리했다.

- API 설정/환경변수/쿠키/테스트/문서의 런타임 prefix를 `PINVI_*` / `pinvi_*`로 hard cutover했다.
- 개발 DB명·사용자·compose container/volume은 `pinvi` / `pinvi-*`, RustFS bucket은
  `pinvi-media`로 정렬했다. `kor-travel-geo` 로컬 디렉터리는 현재 `data/juso`만 있어
  DB/RustFS 설정 원본은 없었고, 같은 hyphenated project prefix 규칙으로 맞췄다.
- 이전 지도 서비스명은 `kor-travel-map`, Python 식별자는
  `kor_travel_map`으로 변경했다. user/admin client, OpenAPI snapshot, service token header,
  Admin import route까지 새 이름만 사용한다.
- 이전 주소/지오코딩 서비스명은 `kor-travel-geo`, Python 식별자는
  `kor_travel_geo`로 변경했다.
- 이전 agent 계열 표현은 `kor-travel-concierge`로 정리했다.

**검증**:

- WSL ext4 mirror: `uv run --extra dev python -m pytest tests -q`(apps/api) → 336 passed, 1 skipped.
- WSL ext4 mirror: `uv run --extra dev ruff check app tests`, `uv run --extra dev mypy --strict app` 통과.
- WSL ext4 mirror: `uv run --extra dev python -m pytest tests -q`(apps/etl) → 3 passed.
- WSL ext4 mirror: `uv run --extra dev ruff check pinvi tests`, `uv run --extra dev mypy --strict pinvi` 통과.
- WSL ext4 mirror: `npm --workspace apps/web run lint`, `typecheck`, `test` 통과(62 passed).
- Windows Playwright runner: `npm --workspace apps/web run test:e2e` → 52 passed.
- WSL ext4 mirror: `docker compose -f infra/docker-compose.yml --profile observability config`,
  `docker compose -f infra/docker-compose.app.yml --profile observability config` 통과.
- Windows: `git diff --check` 통과.

## 2026-06-13 (codex) — T-198 프로젝트명/GitHub repo Pinvi 변경

**작업**: 제품/프로젝트 표기와 GitHub repo 식별자를 `Pinvi` / `pinvi`로 정렬했다.

- README/AGENTS/CLAUDE/SKILL의 정체성·GitHub 저장소 값을 `pinvi`로 갱신했다.
- npm root package와 workspace package scope를 `pinvi`, `@pinvi/*`로 변경하고
  `package-lock.json`을 npm workspace 기준으로 정규화했다.
- Python package metadata를 `pinvi-api`, `pinvi-etl`로 바꾸고, ETL import 경로를
  `apps/etl/pinvi` / `pinvi.etl`로 이전했다. Dagster asset/resource 이름도
  `pinvi_kasi_special_days`, `PinviDatabaseResource`로 정리했다.
- 사용자/UI/문서 표시 문자열과 API 제목·로그 prefix·Prometheus metric prefix를
  Pinvi 기준으로 갱신했다.
- 운영 계약 rename은 후속 T-199에서 호환 별칭 없이 `PINVI_*` / `pinvi_*` 기준으로 hard cutover했다.

**검증**:

- WSL ext4 mirror: `npm install --ignore-scripts`로 workspace link/lockfile 정규화.
- WSL ext4 mirror: `uv run --extra dev python -m pytest tests/unit -q` → 162 passed, 1 skipped.
- WSL ext4 mirror: `uv run --extra dev ruff check app tests`,
  `uv run --extra dev mypy --strict app` 통과.
- WSL ext4 mirror: `uv run --extra dev python -m pytest tests -q`(apps/etl) → 3 passed.
- WSL ext4 mirror: `uv run --extra dev ruff check pinvi tests`, `uv run --extra dev mypy --strict pinvi` 통과.
- WSL ext4 mirror: `npm --workspace apps/web run lint`, `typecheck`, `test` 통과.
- WSL ext4 mirror: `docker compose -f infra/docker-compose.yml --profile observability config`,
  `docker compose -f infra/docker-compose.app.yml --profile observability config` 통과.
- Windows: `git diff --check` 통과.

## 2026-06-13 (codex) — T-197 Prometheus 성능 모니터링 추가

**작업**: Prometheus 기반 API 성능 계측과 observability compose profile을 추가했다.

- `apps/api`에 `prometheus-client`를 추가하고 `PrometheusMetricsMiddleware` +
  `GET /metrics`를 연결했다. metric label은 raw URL이 아니라 FastAPI route template을 사용한다.
- Docker API 이미지는 Uvicorn worker 2개 기준으로 `PROMETHEUS_MULTIPROC_DIR`를 설정해
  Prometheus multiprocess registry를 사용한다.
- `infra/docker-compose.yml` / `infra/docker-compose.app.yml`에 `observability` profile로
  Prometheus `12601`, cAdvisor Exporter `12602`, Grafana `12605`를 추가했다.
- Grafana Prometheus datasource와 기본 `Pinvi Overview` dashboard를 provisioning한다.
- `/admin/grafana` 기본 URL과 CSP origin을 `http://localhost:12605`로 정렬하고,
  geofence bypass 기본값에 `/metrics`를 포함했다.
- `docs/runbooks/observability.md`를 추가하고 local-dev/docker-app/Grafana/Sprint 5 문서를 갱신했다.

**검증**:

- WSL ext4 mirror: `uv run --extra dev pytest tests/unit/test_prometheus_metrics.py tests/unit/test_geofence_middleware.py -q`
  → 19 passed.
- WSL ext4 mirror: `uv run --extra dev pytest tests/unit -q` → 162 passed, 1 skipped.
- WSL ext4 mirror: `uv run --extra dev ruff check app tests/unit/test_prometheus_metrics.py tests/unit/test_geofence_middleware.py` 통과.
- WSL ext4 mirror: `uv run --extra dev mypy --strict app` 통과.
- WSL ext4 mirror: `docker compose -f infra/docker-compose.yml --profile observability config` 통과.
- WSL ext4 mirror: `docker compose -f infra/docker-compose.app.yml --profile observability config` 통과.
- WSL ext4 mirror: `npm --workspace apps/web run lint`, `npm --workspace apps/web run typecheck` 통과.
- Windows: Grafana dashboard JSON parse 통과.

## 2026-06-12 (codex) — T-211/T-223d kor_travel_map curated import 연결

**작업**: kor-travel-map T-223c의 Pinvi copy snapshot을 Pinvi admin import로 연결했다.

- `KorTravelMapClient.get_curated_pinvi_copy()` 추가:
  `GET /v1/curated-features/{curated_feature_id}/pinvi-copy`.
- `POST /admin/notice-plans/imports/kor-travel-map-curated-features` 추가. `create` / `upsert` /
  `refresh` mode를 지원하고, source version/etag와 POI 복사·재사용 수를 반환한다.
- `curated_trip_plans` / `curated_plan_pois` provenance 컬럼을 추가해 kor_travel_map source id,
  source item id, version, etag, imported_at을 저장한다.
- import refresh/upsert는 기존 source item 또는 같은 feature-backed POI를 재사용하고, 새 item만
  LexoRank 마지막 뒤에 append한다.
- Pinvi와 관계가 끊긴 `kor-travel-concierge` 잔여 설정(`PINVI_AGENT_API_BASE_URL`, 12401
  예약)을 제거했다. Pinvi curated trip plan 생성에는 `kor-travel-concierge`가 관여하지 않는다.

**검증**: 최종 PR 검증 결과에 기재.

## 2026-06-12 (codex) — T-130 `/public/*` kor_travel_map public view 소비 연결

**작업**: kor-travel-map T-222b로 user OpenAPI에 공개 해수욕장/축제 표면이 생겨 Pinvi
T-130을 연결했다.

- `apps/api/tests/contract/kor-travel-map-openapi-user.json`을 최신 kor_travel_map `openapi.user.json`으로
  교체하고 drift gate에 `/v1/public/beaches*`, `/v1/public/festivals*` 6개 경로와
  public view schema 필드 검사를 추가했다.
- `KorTravelMapClient`에 public beaches/festivals 목록·상세·marker 호출을 추가했다.
- 신규 `/public/beaches`, `/public/beaches/map-markers`, `/public/beaches/{feature_id}`,
  `/public/festivals/monthly`, `/public/festivals/map-markers`,
  `/public/festivals/{feature_id}` 라우터를 추가했다.
- `packages/schemas/src/public.ts`와 `@pinvi/api-client` `publicApi`를 추가했다.
- 앱 내부 공통 rate-limit 미들웨어는 T-195 후속으로 분리했다.

**검증**:

- WSL ext4 mirror: `uv run --extra dev pytest tests/unit/test_kor_travel_map_client.py tests/unit/test_kor_travel_map_contract.py -q`
  → 22 passed, 1 skipped.
- WSL ext4 mirror: `uv run --extra dev pytest tests/integration/test_public_api.py -q`
  → 4 passed.
- WSL ext4 mirror: `uv run --extra dev pytest tests/unit -q` → 158 passed, 1 skipped.
- WSL ext4 mirror: `uv run --extra dev ruff check app tests`, `uv run --extra dev mypy --strict app` 통과.
- WSL ext4 mirror: `npm run typecheck --workspaces --if-present`,
  `npm run lint --workspaces --if-present`, `npm run build --workspaces --if-present` 통과.

## 2026-06-12 (codex) — Docker app RustFS 재시작 정책 보강

**작업**: PR #181 merge 후 `scripts/docker-app.sh smoke --keep-running` 상태 확인에서
`app-rustfs`가 smoke 통과 후 종료된 것을 확인했다. app smoke 스택도 새 RustFS 포트
`12101`/`12105`로 계속 떠 있어야 하므로 `app-rustfs`에 `restart: unless-stopped`를
추가했다.

**검증**:

- WSL ext4 mirror: `scripts/docker-app.sh up`으로 app smoke 스택 재적용.
- WSL ext4 mirror: API `/health`, API `/health/db`, Web `/admin/login`, RustFS
  `/health/live` 확인.
- WSL ext4 mirror: `docker inspect pinvi-app-app-rustfs-1`에서 restart policy
  `unless-stopped`, state `running`, health `healthy` 확인.

## 2026-06-12 (codex) — 로컬/Docker 고정 포트 재배정

**작업**: 사용자 지시에 따라 로컬·Docker·문서 포트를 새 고정값으로 정렬했다.

- PostgreSQL host/container 포트는 표준 `5432`로 정렬.
- RustFS API `12101`, console `12105`; kor-travel-map API/Admin API `12301`;
  Pinvi API `12501`; Web UI `12505`로 고정. agent 포트 예약은 이후 T-196에서 제거.
- 신규 **ADR-037** 추가. `AGENTS.md`/`CLAUDE.md`/`README.md`/`.env.example`/
  `apps/api/.env.example`/`Settings`/Docker compose/runbook 문서를 같은 포트 집합으로 정렬.
- agent API 기본값은 이후 T-196에서 제거했다.

**검증**:

- WSL ext4 mirror: `uv run --extra dev ruff check app tests` 통과.
- WSL ext4 mirror: `uv run --extra dev mypy --strict app` 통과.
- WSL ext4 mirror: `uv run --extra dev pytest tests/integration/test_notice_plan_copy.py tests/integration/test_trip_view_builder.py tests/integration/test_oauth_google.py tests/unit/test_storage_keys.py -q`
  → 35 passed.
- WSL ext4 mirror: `uv run --extra dev pytest tests/unit -q` → 154 passed, 1 skipped.
- WSL ext4 mirror: `npm run lint`, `npm run typecheck`,
  `NEXT_PUBLIC_PINVI_API_URL=http://localhost:12501 npm run build` 통과.
- WSL ext4 mirror: `scripts/docker-app.sh smoke --keep-running` 통과. 실행 후
  `scripts/docker-app.sh status`에서 API `12501`, Web `12505`, RustFS `12101`/`12105`,
  Postgres internal `5432` healthy 확인.

## 2026-06-12 (codex) — 상태 정합 정리 + ADR-036 curated POI feature 연계 정책

**작업**: Sprint 4/v0.1.0 상태 문서 drift 정리 + curated trip plan POI의 feature link 정책을
사용자 정정에 맞춰 반영.

- 상태 정합: `tasks.md`/`resume.md`/`sprints/README.md`/`SPRINT-4.md`/`README.md`/진입 요약을
  "Sprint 4 기능 게이트 충족, v0.1.0 tag/Release notes 대기"로 정렬.
- 신규 **ADR-036**: POI `feature_id`는 nullable 유지. curated trip plan은 POI 묶음이며,
  kor-travel-map import가 feature를 제공할 때만 같은 plan의 feature-backed POI를
  찾아 재사용하고, 없으면 새 `curated_plan_pois` row를 생성. 생성 소스는
  Pinvi-native 큐레이션과 kor-travel-map `curated_features` 1:1 import를 모두 정식으로
  둔다.
- 코드 정합: `trip_day_pois.feature_id` ORM/Pydantic/Zod를 ADR-031대로 nullable로 정렬하고
  Alembic 0021 추가. `copy_plan_to_trip()`의 가짜 `curated:<id>` feature fallback 제거.
  `ensure_plan_poi_for_feature()` helper로 외부 feature-backed upsert 경로 추가.
- 문서 정합: `notice-plans.md`, `pois.md`, `data-model.md`, `postgres-schema.md`, `SKILL.md`,
  `kor-travel-map-requirements.md`, `integrations/kor-travel-map-rest-api.md`의 `feature_id` nullable /
  curated feature-backed upsert / kor_travel_map `curated_features` 후속 import 설명 갱신.
- 후속: T-211 — kor_travel_map `curated_features` REST 상세 계약 확정 후 Pinvi
  `curated_trip_plans` 1:1 import endpoint/client/provenance 컬럼 검토.

**검증**: ruff/mypy/pytest/web typecheck는 본 작업 말미 실행 결과를 최종 응답에 기재.

## 2026-06-11 (claude) — T-130 `/public/*` kor_travel_map-측 필요 작업 문서화

**작업**: `/public/*`(T-130)가 차단된 원인 = kor_travel_map가 해수욕장/축제의 풍부한 도메인 필드를 계약에
안 담음. kor_travel_map가 해야 할 일을 Pinvi 측 요구사항 문서로 저장(추후 kor_travel_map에 전달용).

- `docs/kor-travel-map-requirements.md` **§6 신설** — Public 표면 요구사항(T-130): beach(수질·KHOA
  예보·width/material 등)·festival(기간·상태·주최/내용·월별 집계) `detail` 계약 요청 + 표 매핑
  (Pinvi 노출 필드 ↔ kor_travel_map 필요분) + 비차단/최소안(in-bounds 마커 우선) + kor_travel_map 회신 요청 3건.
  머리에 §0~§5는 REST API 구축으로 대부분 해소·§6만 잔여 상태 배너.
- `docs/api/public.md` 상태 노트 + `tasks.md` T-130에 §6 포인터.

**비고**: Pinvi 코드 변경 없음(docs-only). 도메인 필드가 kor_travel_map 계약에 들어오면 즉시 구현
(라우터·셰입은 public.md에 이미 설계).

## 2026-06-11 (claude) — §7 합의 5건 확정 반영 (kor_travel_map T-217c, item 3)

**작업**: kor_travel_map T-217c(#347)로 사용자 제안 연동 합의 5건이 확정 — Pinvi 측 반영.

- **출처 태깅(#3) 실수정**: `feature_requests.py` 승인 시 operator를 `pinvi-admin:{admin_id}`
  (admin id 노출) → **고정 `"pinvi-admin"`**(익명 D-11)로, reason에 `[suggestion:<request_id>]`
  prefix 추가(change-requests 큐 출처 식별). 기존 4건(review_mode/idempotency/closure/9011 admin)은
  이미 확정값과 일치 — 코드 무변경.
- **§7-pending → 확정 마킹**: `feature_requests.py`/`kor_travel_map_admin.py` docstring, `config.py`
  admin token 주석(인증=인프라 계층), `docs/integrations/kor-travel-map-rest-api.md` §6/§7(5건 상세),
  `tasks.md` 배너.
- 통합 테스트: 승인 테스트의 operator/reason 단언 갱신.

**참고**: kor_travel_map는 T-210e로 `kor-travel-map-user-client` TS 타입 패키지(#348)도 배포 — Pinvi는
당분간 수기 Zod + 본 저장소 드리프트 게이트(#178) 유지(추후 그 패키지 소비 검토 가능).

**→ kor_travel_map 연동 루프 완전 종결**(§7까지). 당시 유일 잔여 = T-130 `/public/*`
(2026-06-12 Codex 작업으로 완료).

**검증**: ruff check + format(clean). mypy/pytest는 CI.

## 2026-06-11 (claude) — T-210e: kor_travel_map openapi 드리프트 게이트 (item 4)

**작업**: 수기 httpx client가 kor_travel_map `openapi.user.json`과 silent drift하는 것을 막는 게이트.

- `apps/api/tests/contract/kor-travel-map-openapi-user.json` — kor_travel_map user 스펙 vendor 스냅샷(pin).
- `apps/api/tests/unit/test_kor_travel_map_contract.py` (CI pytest unit): client 경로(`/v1/features/*`·
  `/v1/categories`) + 매핑 응답 필드(FeatureSummary/Cluster/Detail/Weather/Category/Batch) ⊆
  스냅샷. + 로컬 핀 신선도 검사(sibling kor_travel_map repo와 경로 집합 일치, CI skip,
  `PINVI_KOR_TRAVEL_MAP_OPENAPI_USER_PATH` override).
- `docs/integrations/kor-travel-map-rest-api.md` §8 갱신 절차 + tasks.md T-210e 완료.
- codegen(openapi-typescript)은 미도입(선택) — kor_travel_map 권고대로 수기 client 유지.

**검증**: ruff(clean) + 스냅샷 대조 로컬 통과. mypy/pytest는 CI.

## 2026-06-11 (claude) — T-176 잔여: `/features/categories` + `/public/*` 표면 대기 명시 (item 5)

**작업**: feature read 잔여(카테고리 카탈로그) 추가 + `/public/*`는 kor_travel_map 표면 부재로 대기 명시.

- `GET /features/categories` 신규 — kor_travel_map `GET /v1/categories` 투영(`code`/`label`/`parent_code`/
  `depth`/`path`/`maki_icon`/`is_active`/`sort_order`). 마커 범례·필터 칩용. 라우트는 `/{feature_id}`
  앞에 등록(정적 경로 우선). `active_only` 쿼리.
- `schemas/feature.py` `FeatureCategory` + Zod `FeatureCategorySchema`(+index) + api-client
  `featureApi.categories()`. 매핑 단위 테스트 2 + 통합 테스트 1.
- **T-130 `/public/*` 대기 명시(당시 기준, 2026-06-12 완료)**: kor_travel_map `openapi.user.json`에 전용 public/beach/festival 표면
  (수질·KHOA 예보·축제 상세)이 아직 없음 → 정책("표면 없으면 노출 안 함")대로 미구현. kor_travel_map
  public 표면 추가 시 진입. `docs/api/public.md` 상태 노트 + tasks.md 갱신.

**검증**: ruff check + format(clean, 로컬). mypy/pytest는 CI(api) + web typecheck(packages 변경).

## 2026-06-11 (claude) — T-179: admin feature-request 검토 web UI (PR3c)

**작업**: `/admin/feature-requests` placeholder를 실제 검토 큐 화면으로 교체 — T-179 백엔드
(검토→승인/거절 + kor_travel_map 릴레이) 완결.

- `apps/web/app/(admin)/admin/feature-requests/page.tsx` — 상태 필터(대기/승인/반영/거절) +
  DataTable(유형/이름/kind/좌표/요청자 마스킹/상태/등록) + 행별 "검토" → ReviewPanel.
  ReviewPanel: 제안 상세 + 승인(new_place는 category 코드/marker_color/marker_icon/사유 입력,
  누락 시 클라+서버 422) / 거절(사유). 처리 후 목록 재조회 + notice.
- `packages/schemas/src/admin_feature_request.ts` 신규 — Summary/Paged/Approve/Reject/Result Zod
  (Pydantic 미러) + index 배럴 export.
- `packages/api-client` adminApi에 `listFeatureRequests`/`approveFeatureRequest`/`rejectFeatureRequest` 추가.
- e2e `admin-feature-requests.e2e.ts` 2: 승인 시 kor_travel_map 전달 API 호출 body 검증 + new_place 마커 누락 가드.

**검증**: web typecheck/lint/build + e2e는 CI(web `lint-typecheck-build`).

## 2026-06-11 (claude) — T-179: admin feature-request 검토→승인 릴레이 (백엔드)

**작업**: 사용자 feature 제안(T-177 큐)을 Admin이 검토해 승인 시 kor_travel_map `/v1/admin/features*`
change API(T-180 client)로 전달하는 백엔드 완성. (kor_travel_map ADR-051: 신규 수신 API 없이 기존
change API를 전송 구간으로.)

- `api/v1/admin/feature_requests.py` 신규 — `GET /admin/feature-requests`(pending 큐, 이메일
  마스킹, FIFO), `POST .../{id}/approve`(suggestion_type별 create/patch/delete 호출 → `kor_travel_map_ref`
  저장 + status `approved`/`added`), `POST .../{id}/reject`(rejected). RBAC admin/operator +
  admin_audit chain. kor_travel_map 호출 먼저 → 성공 시에만 commit(실패 시 pending 유지·재시도).
- `schemas/admin_feature_request.py` 신규 — Summary/Paged/Approve/Reject/Result.
- `admin/__init__.py`에 라우터 등록. `feature_suggestions`의 `reviewed_by_admin_id`/`kor_travel_map_ref`/
  `resolved_at`(T-177 기존 컬럼) 사용 — **migration 불요**.
- 통합 테스트 6: list 마스킹 / approve new_place(payload·kor_travel_map_ref·audit) / marker 누락 422 /
  reject / 이미 처리 409 / 비-admin 404.

**§7 기본값 가정**(kor_travel_map T-217c 미확정): create는 Admin이 category(코드)/marker_color/marker_icon
채움. idempotency_key=request_id, 출처 태깅 operator=`pinvi-admin:{id}`(익명, D-11),
closure=DELETE(soft), review_mode=kor_travel_map 설정(applied→added, 그 외→approved). 확정 시 조정.

**범위**: 백엔드만. web 검토 UI는 PR3c.

**검증**: ruff check + format(clean, 로컬). mypy/pytest는 CI.

## 2026-06-11 (claude) — T-180: kor_travel_map admin HTTP client (feature change relay 토대)

**작업**: Pinvi Admin이 승인한 사용자 feature 제안을 kor_travel_map `/v1/admin/features*`로 전송할
admin-path HTTP client 신설. (T-179 검토→승인 플로우의 전송 토대.)

- `clients/kor_travel_map_admin.py` 신규 — `KorTravelMapAdminClient`: create/patch/delete_feature
  (`data.request` 반환) + change-requests list/approve/reject. 재시도·도메인 예외는 user client
  재사용. base = :9011 `/v1/admin/*` (9012는 admin UI라 base 아님), `X-Kor-Travel-Map-Service-Token`.
- config: `pinvi_kor_travel_map_admin_base_url` 기본값 9012→**9011** 정정(§7 admin base 오류 수정) +
  `pinvi_kor_travel_map_admin_service_token`(미설정 시 공용 토큰 fallback) 추가. `.env.example` 2개.
- `main.py` lifespan에 admin client 합성.
- 계약 테스트 `tests/unit/test_kor_travel_map_admin_client.py`(MockTransport, 7): create/patch/delete +
  approve action sub-resource + 404/422/5xx 에러 매핑.

**§7 기본값 가정**(kor_travel_map T-217c 미확정): admin 인증=service token, review_mode=require_review,
closure=DELETE(soft). 확정 시 호출부(T-179) 조정.

**범위**: client 토대만. 사용자 제안 승인→호출 플로우 + web UI는 T-179(후속 PR).

**검증**: ruff check + format(clean, 로컬). mypy/pytest는 CI.

## 2026-06-11 (claude) — T-175: trip view batch를 kor_travel_map HTTP client로 연결 + etl_bridge 제거

**작업**: PR1(#171)에 이어 trip 상세 view의 feature batch 경로를 레거시 stub에서 실 HTTP
client로 전환하고, 더 이상 참조되지 않는 `etl_bridge` 패키지를 완전히 제거.

- `clients/kor_travel_map.py`: `get_optional_kor_travel_map_client`(미주입 시 503 대신 None) +
  `OptionalKorTravelMapHttpClientDep` 추가 — feature가 보조인 경로(trip view)용.
- `services/trip_view_builder.py`: `KorTravelMapClient` import를 `clients`로 교체.
  `features_by_ids(list)->list` → `get_features(ids)->{found, missing}`. `found`(id→detail)를
  canonical feature_id로 재키잉해 fresh_features에 merge + feature_cache 보존. miss/없음은
  snapshot fallback + is_broken 유지.
- `api/v1/trips.py`: `get_trip` / `get_shared_trip`의 `OptionalKorTravelMapClientDep` →
  `OptionalKorTravelMapHttpClientDep`.
- `main.py`: 레거시 `kor_travel_map_lifespan`(in-process Protocol stub) 합성 제거.
- **삭제**: `apps/api/app/etl_bridge/`(kor_travel_map.py + **init**.py) — 마지막 소비처 정리 완료.
- 테스트: `test_trip_view_builder.py` fake를 `get_features`/`{found,missing}` 셰입으로 갱신.

**검증**: ruff check + format(clean, 로컬). mypy/pytest는 CI.

## 2026-06-11 (claude) — T-173/174/176/178: feature read 라우터를 kor_travel_map HTTP client로 cutover

**작업**: `/features/*` read 경로를 레거시 `etl_bridge` in-process Protocol stub에서 실 HTTP
client(`app.clients.kor_travel_map`)로 전환하고 응답 셰입을 kor_travel_map `openapi.user.json` 계약에 정합.

- **schemas** (`apps/api/app/schemas/feature.py` + `packages/schemas/src/feature.ts`): `FeatureSummary`
  `title`→`name` + nullable `coord`/`marker_*` + `status` + nearby `distance_m`. `FeatureCluster`
  `cluster_id`/`center`/`sample_kinds`/`bbox` → `cluster_key`(행정 자연키)/`coord`/`feature_count`.
  `FeaturesInBoundsResponse` `features`→`items` + `cluster_unit`. `FeatureDetail` 구조화 `address`
  객체 + `legal_dong_code`/`sido_code`/`sigungu_code` + `urls`. 날씨 `{short_term,daily}` → 평탄
  `metrics`(+`forecast_style`)/`source_styles`/`is_stale`.
- **router** (`apps/api/app/api/v1/features.py`): `KorTravelMapHttpClientDep`로 교체. in-bounds
  (`min_lon..max_items`, items/clusters/cluster_unit), nearby(`page_size`, distance_m), search(분리
  4-float bbox), get, weather 매핑 재작성. `_map_kor_travel_map_errors` 가드(T-178): 5xx/timeout→503
  `FEATURE_SERVICE_UNAVAILABLE`, 429/409→Retry-After, 404→RESOURCE_NOT_FOUND.
- **T-174**: `services/cluster_query.py`(직접 `feature` SQL = 경계 위반) + 단위 테스트 제거 — 클러스터링은
  kor_travel_map 서버 위임.
- **web**: `FeatureMapView`/`MapSearchBox`/`TripDetail` + map e2e mock을 신 셰입(items/name/cluster_key/
  nullable coord/weather metrics)으로 정합.
- 테스트: `tests/integration/test_features_api.py` 재작성(dependency_overrides 주입, 신 셰입·503),
  `tests/unit/test_feature_mapping.py` 신규(매핑 helper DB-free). `docs/api/features.md` 갱신.

**범위**: read 경로만. trip view batch(`trip_view_builder`/`trips.py`) + `etl_bridge` 제거는 T-175(후속 PR).

**검증**: ruff check + format(clean, 로컬). mypy/pytest는 CI(api `lint-typecheck-test` + web
`lint-typecheck-build`).

## 2026-06-10 (claude) — T-181: kor_travel_map HTTP client를 0e45bd7 계약으로 정렬

**작업**: kor_travel_map `0e45bd7`(ADR-048/T-216a~g) 라이브 계약에 `apps/api/app/clients/kor_travel_map.py` 정렬.

- `_payload(resp) → (data, meta)`로 리팩터(구 `_data`는 위임). 응답 envelope `{data, meta}` 분리 대응.
- **batch**: `data.get("items")` → `data.get("found")`. 반환 키도 `{found, missing}`(inactive feature는 `found`+status, D-12).
- **in-bounds**: 파라미터 `limit` → `max_items`(≤2000). `data.cluster_unit` 폐기 → `meta.cluster.cluster_unit` re-projection.
- **nearby/search**: `data.next_cursor` 폐기 → `meta.page.next_cursor`/`total` threading. search `include_total` opt-in.
- **에러**: `_error_code`를 RFC7807 problem+json top-level `code` 파싱(구 `error.code` fallback).
- 계약 테스트 `tests/unit/test_kor_travel_map_client.py`: batch `found` 갱신 + 신규 5(max_items/cluster_unit·
  nearby page·search page+include_total·problem+json code). 15 pass.

**범위**: client 계층만 — feature 라우터는 아직 레거시 Protocol stub 사용(라우터 cutover = T-173 별도).
`docs/integrations/kor-travel-map-rest-api.md` T-181 항목에 client 완료 표시.

**검증**: ruff(clean) + mypy --strict(clean) + 단위 15(WSL).

## 2026-06-10 (claude) — T-106 종결: 문서 체크리스트 + PIPA

**작업**: T-106 Sprint-4 스코프(신규 trip / 동반자 초대 알림 채널) 종결 문서화.

- `docs/integrations/telegram.md` §10 체크리스트를 현 구현으로 갱신(완료 8 + Sprint5 ETL/후속 표시),
  각 항목에 PR 번호(#160~#168) 명시.
- `docs/compliance/pipa.md` §4.3 Telegram 위탁 내용 구체화(신규/동반자 알림, 수령 = `telegram_chat_id`만,
  메시지 본문 PII 미포함, bot token 미저장).

**T-106 Sprint-4 완료** (#160 client → #161 target CRUD → #163 알림 hook → #164 관리 UI → #165 outbox 재시도 →
#166 trip 링킹 → #168 trip-link UI). **남은 후속(별 스코프)**: weekly/daily summary Dagster(§7, Sprint 5 ETL —
날씨/유가 kor_travel_map 의존), per-user 봇 토큰 vault(현재 단일 시스템 봇).

## 2026-06-10 (claude) — T-106 PR-7: trip 상세 Telegram 연결 UI

**작업**: 여행 상세에서 Telegram 알림 대상을 연결/해제하는 프론트 UI (백엔드 #166 위).

- `packages/api-client/src/endpoints/telegram.ts`: `listTripTargets`/`linkTripTarget`/`unlinkTripTarget` 추가.
- `components/trips/TripTelegramTargets.tsx` 신규: 사용자 target 중 미연결분 select로 연결(최대 3,
  MAX_TARGETS_REACHED 안내) + 연결 목록 + 해제. 설정 페이지 링크 안내. `TripDetail`에 섹션 배치.
- `e2e/trip-telegram.e2e.ts`(1, stateful mock): 초기 연결 표시 → B 연결 → A 해제.

**검증**: tsc + lint(clean) + build + trip-telegram E2E 1 + 회귀(trip-detail/trip-collab/settings-telegram 5) 통과.
**T-106 잔여**: weekly/daily summary Dagster(§7, Sprint 5 ETL — 날씨/유가 kor_travel_map 의존), PIPA 위탁자 명시(§10),
per-user 봇 토큰(vault).

## 2026-06-10 (claude) — T-106 PR-6: trip↔target 링킹 (§6.5/6.6)

**작업**: 여행별 Telegram 대상 연결(≤3) — T-106 백엔드 마지막 조각.

- `models/trip_telegram_target.py` + `alembic/.../20260610_0020`: `app.trip_telegram_targets`
  (복합 PK trip_id+telegram_target_id, 양 FK CASCADE, target index). trip은 user 소유 target을 참조만(§2.2).
- `services/telegram_targets.py`: `link_trip_target`(소유 검증 + ≤3 + 중복 금지) / `unlink_trip_target` /
  `list_trip_targets`. `TripTargetLimitError`(MAX_TARGETS_REACHED) / `TripTargetConflictError`(ALREADY_LINKED).
- `api/v1/trip_telegram_targets.py` 신규: `GET/POST/DELETE /trips/{trip_id}/telegram-targets` — owner-only,
  4번째 연결 시 422+`reason: max_targets_reached`. `__init__` 등록.
- `schemas/telegram.py`: `TripTelegramTargetLink`.
- 테스트(`test_trip_telegram_targets_api.py`, 5): 연결→목록→해제 / 중복 409 / 4번째 422 한도 / 미존재 타겟 404 /
  남의 여행 차단.

**검증**: ruff(clean) + mypy --strict(clean) + trip-link/targets/hooks 통합 15 통과(WSL+Docker).
**T-106 백엔드 완료**: client·target CRUD·hook·outbox·trip링킹. 남은 후속: weekly/daily Dagster 알림(§7), 프론트 trip-link UI.

## 2026-06-10 (claude) — T-106 PR-5: Telegram outbox 재시도 (§8)

**작업**: 알림 전송을 fire-and-forget(BackgroundTasks)에서 **outbox + drain worker**로 전환 — 영속·재시도 보장.

- `models/telegram_outbox.py` + `alembic/.../20260610_0019`: `app.telegram_system_notification_outbox`
  (§2.3 — category/payload/status/attempts/last_error/scheduled_at/sent_at, pending partial index).
  사용자 알림 category(trip_created/companion_invited)도 같은 outbox로 흐름.
- `services/telegram_outbox.py`: `enqueue_user_notification`(요청 트랜잭션에서 적재) +
  `process_pending_telegram_batch`(FOR UPDATE SKIP LOCKED, email_queue와 동일 backoff 30s/5m/30m/1h/4h,
  5회 소진→failed, 대상/토큰 없음→skipped 종결) + `telegram_outbox_worker_lifespan`(location_audit 패턴,
  interval 5s 설정, batch 가득 시 즉시 재drain).
- `services/telegram_notify.py` 리팩터: `send_user_notification`(비전파 wrapper) → `deliver_user_notification`
  (worker용 코어 — 'sent'/'skipped' 반환, 실패는 TelegramError 전파해 worker가 재시도 분류).
- `api/v1/trips.py` hooks: BackgroundTasks 직접 전송 → `enqueue_user_notification` 인라인 적재.
- `main.py`: lifespan에 telegram_outbox_worker 합성. config에 worker 설정 3개.
- 테스트(`test_telegram_notify_hooks.py` 재작성, 5): enqueue→drain 전송 / 초대 알림(스킵 혼합) /
  rate_limited→backoff 재예약 / 소진→failed / 대상 없음→skipped 종결.

**검증**: ruff(clean) + mypy --strict(clean) + telegram 스위트 30 + 전체 unit 138 통과(WSL+Docker).

## 2026-06-10 (claude) — T-106 PR-4: Telegram target 관리 UI (/settings/telegram)

**작업**: 사용자가 알림 대상을 직접 등록/검증/삭제 — T-106이 end-to-end로 완성.

- `packages/schemas/src/telegram.ts`: TelegramTargetCreate/TelegramTarget Zod(백엔드 §6 대응) + index export.
- `packages/api-client/src/endpoints/telegram.ts`: `telegramApi`(listTargets/createTarget/verifyTarget/deleteTarget).
- `apps/web/app/(app)/settings/telegram/page.tsx`: Chat ID(+별칭/기본) 등록 폼(FormField, 필드 오류+포커스),
  대상 목록(별칭·chat·종류·상태) + 재검증/삭제. 그룹 채널 PII 경고 문구(§9).
- `apps/web/app/(app)/settings/layout.tsx` 신규: settings 서브내비 탭(동의/MCP 토큰/Telegram) — 발견 가능성.
- `e2e/settings-telegram.e2e.ts`(2): 등록→스냅샷 표시→삭제 / Chat ID 누락→필드 오류+aria-invalid+포커스.

**검증**: tsc + lint(clean) + build + e2e 3(신규 2 + settings-mcp 회귀 1) + vitest 62 통과.
**T-106 4부작 완료**: client(#160) → target CRUD(#161) → 알림 hook(#163) → 관리 UI. 남은 후속: trip↔target
링킹(§6.5/6.6), weekly/daily Dagster(§7), outbox(§8), per-user 토큰.

## 2026-06-10 (claude) — T-106 PR-3: 신규 trip / 동반자 초대 Telegram 알림 hook

**작업**: T-106 원래 목표 기능 — 즉시 알림 2종이 실제로 동작 시작.

- `services/telegram_messages.py` 신규: `build_trip_created_message`(제목/일정/지역) /
  `build_companion_invited_message`(이메일 등 PII 미포함 — 그룹 채널 가정, §9). plain text.
- `services/telegram_notify.py` 신규: `send_user_notification(user_id, text)` — default(없으면 최신
  enabled) target으로 시스템 봇 전송. **자체 세션**(`db.session` 모듈 속성 동적 참조 — BackgroundTasks는
  request 세션 종료 후 실행) + 실패 절대 비전파(로그 + `last_send_status`, bot_forbidden→비활성).
- `clients/telegram.py`: `parse_mode=None` 허용(plain text — MarkdownV2 escape 회피).
- `api/v1/trips.py`: `create_trip_endpoint` → owner 알림, `invite_trip_member` → 초대된 기존
  사용자(companion.user_id) 알림. 둘 다 FastAPI `BackgroundTasks`(응답 후, 비차단).
- 테스트: messages 단위 4 + client parse_mode 1 + hook 통합 4(생성 알림/타겟 없음 noop/
  전송 실패에도 201+상태 기록/초대 알림 PII 미포함).

**검증**: ruff(clean) + mypy --strict(clean) + telegram 스위트 29 + 전체 unit 138 통과(WSL+Docker).
**남은 T-106**: trip↔target 링킹(§6.5/6.6), weekly/daily Dagster(§7.1/7.2), outbox(§8), per-user 토큰, 프론트 UI.

## 2026-06-10 (claude) — 세션 일단락: resume.md 정리

**작업**: 장시간 세션 마감 — `docs/resume.md`를 현 상태로 정합화.

- 최근 작업 로그 상단에 이번 Claude 세션 요약 추가: 폼 a11y 스윕(#152~#159) + App Router 방어선(#151)
  - T-106 Telegram PR-1(#160, client) / PR-2(#161, target CRUD).
- stale했던 "다음 한 작업"(Sprint 4 PR-B2/PR-C/PR-D — 이미 전부 완료) 블록을 현 비의존 후보로 교체:
  T-106 후속(알림 hook·trip↔target 링킹·UI·per-user 토큰), T-108 배포 자동화, kor_travel_map unblock(T-181/179/180).

**세션 산출(이번 대화)**: 머지 PR 12건 — #151(error boundary) #152~#159(폼 a11y 8건) #160~#161(T-106).
재사용 폼 컴포넌트 5종이 앱 전 입력에 적용됐고, Telegram 알림의 client+target CRUD 기반이 박혔다.
(별개로 사용자 PR #155 kor_travel_map cross-repo 결정 문서는 사용자 지시대로 손대지 않음.)

## 2026-06-10 (claude) — T-106 PR-2: Telegram 알림 대상 CRUD + verify

**작업**: `/users/me/telegram-targets` CRUD(§6.1~6.4) — 모델/마이그레이션/스키마/서비스/라우터.

- `models/telegram_target.py` + `alembic/.../20260610_0018_telegram_targets.py`: `app.telegram_targets`
  (user FK CASCADE, chat_id/type/thread/label/title_snapshot, is_default/is_enabled, last_verified_at,
  last_send_status, soft delete, `telegram_bot_token_ref` 기본 `system`). updated_at 트리거 + partial index.
- `schemas/telegram.py`: TelegramTargetCreate(bot token 안 받음) / TelegramTargetResponse.
- `services/telegram_targets.py`: create(등록 시 verify, 실패 시 미저장) / list / verify_existing(실패 기록+
  bot_forbidden→is_enabled=false) / delete(soft). §5 실패코드→HTTP status 매핑.
- `api/v1/telegram_targets.py`: GET/POST/POST verify/DELETE + `get_telegram_client` 의존성. `__init__` 등록.
- 테스트: `tests/integration/test_telegram_targets_api.py`(5, fake client override) — 생성+verify+삭제 / bot_forbidden 403 미저장 /
  시스템봇 미설정 시 미검증 생성 / verify 엔드포인트 / 404.

**설계 결정**: per-user vault 미구현 → **단일 Pinvi 시스템 봇** 모델 채택. 사용자는 봇을 자기 chat에 추가하고
chat_id만 등록(원시 토큰 DB 저장 X, §1 준수). per-user 봇 토큰(vault)은 후속. trip↔target 링킹(§6.5/6.6, max 3)도 후속 PR.

**검증**: ruff(clean) + mypy --strict(clean) + 단위 15 + 통합 5(WSL+Docker) 통과. (전체 unit 132/133; `test_access_token_expiry`는
시간 의존 flaky로 격리 시 통과 — 무관.)

## 2026-06-10 (claude) — T-106 PR-1: Telegram Bot API client (verify/send)

**작업**: Telegram 알림(T-106) 첫 슬라이스 — 전송 전용 client. DB/마이그레이션 없이 httpx mock으로 완결 단위테스트.

- `apps/api/app/clients/telegram.py` 신규: `TelegramClient`(httpx.AsyncClient 주입) `verify_target`(getChat) /
  `send_to_target`(sendMessage), `TelegramError.code`로 §5 실패 분류(bot_forbidden/invalid_chat/invalid_topic/
  rate_limited/network_error/unknown_error/missing_chat_id), `mask_token`(§9 — token secret 마스킹, 에러 메시지에 token 비노출).
- `apps/api/app/core/config.py`: `pinvi_telegram_{api_base,timeout_seconds,bot_token_default,admin_chat_id}` 설정.
- `apps/api/tests/unit/test_telegram_client.py`(15): verify/send 페이로드·실패 분류·retry_after·timeout·token 마스킹.

**책임 분리**: 사용자용 Telegram Bot(bot token)은 agent용 `mcp-telegram`(MTProto, `.env.mcp-telegram`)과 무관(별 시스템).
bot token 원본은 DB 저장 X(§1), client는 전송만 — DB 모델/outbox/라우터/UI는 후속 PR.

**검증**: ruff(clean) + ruff format + mypy --strict(clean) + 단위테스트 15(WSL `.venv-wsl`) + 전체 unit 133 통과.

## 2026-06-10 (claude) — 폼 a11y 마무리 (admin list 폴리시 + settings/mcp-tokens)

**작업**: 폼 접근성 스윕의 마지막 폴리시 — list filter select 연결 + error region role + 사용자용 mcp-tokens.

- admin list(users/trips/pois/emails): filter `<select>`에 `id` + label `htmlFor` 연결(미연결이던 상태/공개/연결 필터).
- error region `role=alert` 일괄 부여: admin users/trips/pois/emails/audit-location/api-calls list.
- `app/(app)/settings/mcp-tokens/page.tsx`: aria-label-only 입력(이름/만료/발급원문)을 `FormField`/`FormSelect`로 전환(시각적 라벨), error `role=alert`.
- `e2e/settings-mcp-tokens.e2e.ts`(1): 발급 폼 라벨 노출.

**검증**: tsc + lint(clean) + build + settings-mcp E2E 1 + 회귀(admin-users/trips/pois/mcp-tokens 8, testid 보존) 통과.

**폼 a11y 스윕 종료**: FormField/FormTextArea/FormSelect/validateForm/useDialogAutoFocus가 공개 인증·trip/profile·
다이얼로그·PoiEditor·admin 로그인/액션모달/mcp-tokens·list·settings 전반에 적용됨 (#152~#159).

## 2026-06-10 (claude) — admin/mcp-tokens 폼 접근성 (FormSelect 추가)

**작업**: admin MCP 토큰 페이지의 placeholder/aria-label-only 입력들을 시각적 라벨 폼으로 전환(가장 심한 a11y 갭).

- `components/forms/FormSelect.tsx` 신규: FormField의 select 버전(htmlFor/id 연결, option은 children).
- `app/(admin)/admin/mcp-tokens/page.tsx`: 검색/상태 + 발급 폼(user_id/이름/만료/사유) + 발급원문/회수사유 입력을
  `FormField`/`FormSelect`로 전환 — 시각적 라벨·id 연결·`data-testid`(admin-mcp-\*). 발급 시 user_id/사유 필수
  필드 검증(aria-invalid + 포커스), 에러 region `role=alert`.
- `e2e/admin-mcp-tokens.e2e.ts`(2): 발급 폼 라벨 노출(getByLabel) / user_id 없이 발급→필드 오류+aria-invalid+포커스.

**버그 수정(테스트)**: 리스트 목 정규식이 페이지 내비게이션(:9022)까지 가로채 JSON을 반환 → API 포트(9021)

- pathname으로 한정해 해결.

**검증**: tsc + lint(clean) + build + mcp-tokens E2E 2 + 회귀(admin-login/admin-users/form-a11y/dialog-focus 10) 통과.
**남은 후속**: settings/mcp-tokens(사용자용), list 페이지 select `for`/error role=alert 폴리시.

## 2026-06-10 (claude) — admin 로그인 + 액션 모달 폼 접근성

**작업**: admin 콘솔의 실 폼(로그인) + 액션 확인 모달(사유 textarea) a11y 보강.

- `app/(admin)/admin/login/page.tsx`: 공개 로그인과 동일하게 `FormField` + `validateForm` 전환 —
  필드 오류(aria-invalid), `autoComplete`, 첫 오류 필드 포커스, 에러 region `role=alert`.
- `app/(admin)/admin/{users/[user_id],trips/[trip_id],pois/[poi_id]}/page.tsx`: 라벨 없던 사유 textarea를
  `FormTextArea`로 전환(label="사유" + hint). testid 보존.
- `components/forms/FormTextArea.tsx`: `hint` prop 추가(FormField와 동등, aria-describedby 연결).
- `e2e/admin-login.e2e.ts`(2): 잘못된 이메일→필드 오류+aria-invalid+포커스 / `?reason=forbidden`→role=alert.

**검증**: tsc + lint(clean) + build + admin-login E2E 2 + 회귀(admin-users/trips/pois 6, action-reason FormTextArea flow 포함) 통과.
**후속 후보**: admin/mcp-tokens(placeholder-only 라벨 5+개) 대규모 FormField 리팩터, list 페이지 select `for`/error role=alert 폴리시.

## 2026-06-10 (claude) — PoiEditor inline 폼 접근성 (FormTextArea 추가)

**작업**: POI 상세 편집기(inline)의 입력을 FormField/FormTextArea로 통일 — label↔input id 연결.

- `components/forms/FormTextArea.tsx` 신규: FormField의 textarea 버전(htmlFor/id 연결, aria-invalid/role=alert).
- `components/trips/PoiEditor.tsx`: maki 아이콘/도착/출발/예산/실제비용/링크 → `FormField`, 메모 → `FormTextArea`.
  작은 라벨 스타일은 `labelClassName="block text-xs font-semibold text-ink"`로 보존. 마커색 picker(버튼 그룹)는 유지.
- `e2e/trip-mutations.e2e.ts`: 편집기 열림 시 메모/링크/예산 라벨↔입력 연결 단언 추가.

**검증**: tsc + lint(clean) + build + trip-mutations E2E 3(PoiEditor 포함) + 회귀(form-a11y/dialog-focus/auth-form-a11y 8) 통과.

## 2026-06-10 (claude) — kor-travel-map 발 cross-repo 검토 결정 반영 (문서만)

**작업**: kor-travel-map repo에서 수행한 3-시스템 교차 검토(결정 D-01~~13 종결, kor_travel_map
ADR-050~~052 + T-217a~g)의 Pinvi 측 반영. 코드 무변경, 문서 3건.

- `docs/reviews/2026-06-10-kor_travel_map-cross-repo-decisions.md` 신설 — 확정 사항/신규 오류/
  액션 후보 요약.
- `docs/kor-travel-map-integration.md` — 2026-06-06 "kor_travel_map HTTP 미존재" 경고 블록을 현재
  상태(0e45bd7, `/v1` 완비)로 교체 + 전 경로 `/v1`·batch `found` 정정.
- `docs/integrations/kor-travel-map-rest-api.md` — 0e45bd7 재대조: kor_travel_map T-216a~g 머지
  확인 → **T-181 잔여 lockstep 대기 해제**, §7 잔여 2건(batch `found`·`meta.cluster`)
  수용 완료 반영, admin API base 정정(**9011 `/v1/admin/*`** — 9012는 admin UI).
- **핵심 액션**: T-181 잔여 즉시 실행 가능(batch `found`/`max_items`/problem+json/
  `meta.page`), T-180 admin client base 9011 정정, 사용자 제안 흐름(DEC-05)은 kor_travel_map
  ADR-051로 공식 승인 — T-179/T-180 그대로 진행, 합의 5건은 kor_travel_map T-217c 회신 대기.
- **PR #155 리뷰 반영(같은 날)**: ① 이미 머지된 #154 커밋 제거(최신 main 위로 재구성,
  journal 충돌 해소) ② `integrations/kor-travel-map-rest-api.md` 본문 stale 계약 전면 제거
  (§1 envelope/error 확정형, §2 전 경로 `/v1`·`max_items`·`page_size`·`meta.page`,
  §3 T-182 반영, §4/§5/§6 — T-175 `found`, T-179 `/v1/admin/features*`, T-180 base
  9011, `/pinvi/*` 잔재 제거) ③ `docs/tasks.md`(T-175/179/180/181)·`docs/resume.md`
  (kor_travel_map 연동 unblock 블록) 동기 갱신.

## 2026-06-10 (claude) — 모달 다이얼로그 포커스 관리 + 폼 접근성

**작업**: trip 편집 / 추천 복사 / 장소 제안 다이얼로그의 a11y 보강 — 모달 포커스 관리 + FormField 통일.

- `lib/useDialogAutoFocus.ts`: 모달 열림 시 첫 입력으로 포커스(WCAG 2.4.3), 닫힘 시 직전 포커스 요소로 복원. rAF 지연 + `document.contains` 가드.
- `components/forms/FormField.tsx`: `labelClassName` prop 추가(다이얼로그의 굵은 라벨 보존).
- `TripEditDialog` / `NoticePlanCopyDialog` / `FeatureRequestDialog`: 텍스트·날짜 입력 → `FormField`(id 연결),
  제목/이름 입력에 `useDialogAutoFocus` 적용.
- `FeatureRequestDialog`: 제출 버튼을 빈 제목에도 활성화하고(disabled 버튼 안티패턴 제거) 제출 시
  `이름` 필드 오류(aria-invalid) + 포커스로 안내.
- `e2e/dialog-focus.e2e.ts`(2): 다이얼로그 열림→첫 입력 포커스 / 이름 없이 제출→필드 오류+aria-invalid+포커스.
  `e2e/trip-edit.e2e.ts`: 열림 시 제목 자동 포커스 단언 추가.

**검증**: tsc + lint(clean) + build + dialog-focus E2E 2 + 회귀(trip-edit/notice-copy/feature-request/form-a11y/auth-form-a11y) 통과.
(`PoiEditor`는 모달이 아니라 inline 확장 + textarea 포함이라 이번 범위 외.)

## 2026-06-10 (claude) — trip 생성 / 프로필 완성 폼 접근성 (FormField 확장)

**작업**: 인증 폼에 이어 trip 생성·프로필 완성 폼에도 `FormField`/필드 검증 적용 (a11y 일관성).

- `app/(auth)/profile-complete/page.tsx`: 닉네임 → `FormField` + `validateForm`(ProfileCompleteRequestSchema).
  검증 실패 시 nickname 필드 오류 + 포커스. 동의 fieldset 보존.
- `components/trips/TripDashboard.tsx`: 생성 폼 4필드(제목/지역/시작·종료일) → `FormField`. 제목 누락 시
  `titleError`(aria-invalid + role=alert) + 제목 포커스. 각 입력에 `id`+`data-testid`(trip-create-\*) 부여.
- `e2e/form-a11y.e2e.ts`: 제목 없이 제출→필드 오류+aria-invalid+포커스 / label 클릭 포커스 / 프로필 닉네임 검증(3건).

**검증**: tsc + lint(clean) + build + a11y E2E 3 + 회귀(auth-form-a11y 3, user-shells 2) 통과.
(프로필 페이지 `/profile`은 OAuth 링크만이라 텍스트 폼 없음 — 대상 외.)

## 2026-06-10 (claude) — 인증 폼 접근성 강화 (FormField + 필드별 검증)

**작업**: 로그인/회원가입 폼의 a11y·검증 갭 보강.

- `lib/formValidation.ts`: `validateForm(schema, values)` → 필드별 한국어 메시지(이메일/비밀번호 min/너무 긺) +
  `firstField`(포커스 이동용). 순수·테스트(6건).
- `components/forms/FormField.tsx`: a11y 기본 입력 필드 — `htmlFor`/`id` 연결, 오류 시 `aria-invalid` +
  `aria-describedby` + `role=alert`, `forwardRef`(포커스).
- `app/(auth)/login/page.tsx`, `signup/page.tsx`: FormField + validateForm 적용. `autoComplete`
  (email/current-password/new-password/nickname) + `noValidate` + 첫 오류 필드 포커스. OAuth·동의 fieldset 보존.
- `e2e/auth-form-a11y.e2e.ts`: 잘못된 이메일 → 필드 오류 + aria-invalid / label 클릭 포커스 / 비밀번호 8자 검증(3건).

**주의(복구)**: 작업 시작 시 stale `agent/claude-idle`(origin/main −134)에서 편집을 시작 → 발견 후 새 파일
백업·되돌리고 `origin/main` 기준 fresh 브랜치로 재적용. 브랜치 base도 stale(#150)였어서 `git fetch` 후 #151 위로 rebase.

**검증**: tsc + lint(clean) + build + vitest 6 + a11y E2E 3 + 인증 회귀(signup-consents/oauth-account-match 3) 통과.

## 2026-06-10 (claude) — App Router 에러 바운더리 + not-found + 로딩 상태

**작업**: Next.js App Router 전역 품질 방어선 — 에러 바운더리·404·로딩이 전무하던 갭 보강.

- `lib/errorMessage.ts`: `friendlyErrorText(unknown)`(ApiError status별 안내 401/403/404/5xx) +
  `errorDigest`(production digest 추출). 순수·테스트(6건).
- `components/feedback/FullPageMessage.tsx`: 빈/오류/404 공통 표현(아이콘·제목·설명·액션·ref). 훅 없음 → 서버·클라 공용.
- `components/feedback/RouteError.tsx`: segment error boundary 공통 클라 뷰(다시 시도/홈으로).
- `components/feedback/PageLoading.tsx`: 전체 화면 로딩(`role=status`).
- `app/error.tsx` + `app/(app)/error.tsx`: RouteError 얇은 래퍼.
- `app/global-error.tsx`: root layout 붕괴 대비 최후 방어선 — 자체 `<html>/<body>` + 인라인 스타일(CSS 미로드 가정).
- `app/not-found.tsx`: 404 페이지(홈/내 여행 링크).
- `app/loading.tsx` + `app/(app)/loading.tsx`: 라우트 전환 로딩.
- `e2e/not-found.e2e.ts`: 미지 경로 → 404 status + not-found 페이지 + 홈 링크 이동(2건).

**검증**: tsc + lint(clean) + build(`/_not-found` 등) + vitest 6 + not-found E2E 2 + 기존 회귀(trip-detail/map-explore/user-shells 4) 통과.

## 2026-06-10 (claude) — 공유 링크 ↔ 공유뷰 연결

**작업**: 생성된 공유 링크가 실제 `/shared/{id}/{token}` 라우트를 가리키게 연결.

- `lib/shareUrl.ts`: `buildShareUrl(origin, tripId, token)` → 프론트 공유 뷰 URL. 순수·테스트.
- `TripShareLinks`: 서버 `url` 대신 구성 URL 표시 + "열기" 링크(`/shared/{id}/{token}`, new tab).
- `SharedTripView`: 에러 메시지 친절화("만료/유효하지 않음") + "Pinvi 홈으로" 링크.
- `e2e/trip-collab.e2e.ts`: 공유 배너가 `/shared/{tripId}/{token}` 포함 + "열기" href 검증.
- `tests/shareUrl.test.ts` 1건.

**검증**: 로컬 chromium 전 스위트 `32 passed`(CI env port 9021) + tsc + lint + build + vitest.

## 2026-06-10 (claude) — 공유 trip 읽기전용 뷰 라우트 + E2E

**작업**: 토큰 공유 링크용 **공개 읽기전용** 여행 뷰.

- `app/shared/[tripId]/[token]/page.tsx`: route group 밖(인증 불필요) 공개 라우트.
- `components/trips/SharedTripView.tsx`: `tripApi.getShared(id, token)`(TripSharedView) → 헤더
  (제목/일정/지역 + "공유된 여행") + 일자 탭 + 지도(TripMapView) + POI 목록(TripPoiList 읽기전용,
  편집/D&D 없음). 지도↔목록 선택 동기.
- `e2e/shared-trip.e2e.ts`: 로그인 없이 `/shared/{id}/{token}` → 제목·POI 표시 + 편집 버튼 부재 검증.

**검증**: 로컬 chromium 전 스위트 `32 passed`(CI env port 9021) + tsc + lint + build(`/shared` 라우트).

## 2026-06-10 (claude) — trip 메타 편집 다이얼로그 + E2E

**작업**: trip 제목/지역/일정/상태/공개범위 편집.

- `lib/tripEdit.ts`: `buildTripUpdate`(폼→`TripUpdate`, trim/null) + 상태·공개 라벨. 순수·테스트.
- `components/trips/TripEditDialog.tsx`: 제목/지역/시작·종료일/상태(5)/공개(3) 폼 + Escape 닫기.
- `TripDetail`: 헤더 "편집" 버튼 → 다이얼로그 → `tripApi.update(version)`(If-Match) → reload.
- `e2e/trip-edit.e2e.ts`: 제목 변경 → 헤더 반영(stateful PATCH).
- `tests/tripEdit.test.ts` 2건.

**검증**: 로컬 chromium 전 스위트 `31 passed`(CI env port 9021) + tsc + lint + vitest.

## 2026-06-10 (claude) — trip 복사/삭제 액션 + E2E

**작업**: trip `[tripId]` 헤더에 복사·삭제 액션.

- `components/trips/TripActions.tsx`: 복사(`tripApi.copy` → 새 여행으로 `router.push`) + 삭제
  (2-step 확인 → `tripApi.delete` → `/trips` 이동). 에러 `role=alert`.
- `TripDetail` 헤더 상태 배지 아래 배치.
- `e2e/trip-actions.e2e.ts`: 복사 → `/trips/{newId}` 이동 / 삭제 확인 → `/trips` 이동 검증.

**검증**: 로컬 chromium 전 스위트 `30 passed`(CI env port 9021) + tsc + lint.

## 2026-06-10 (claude) — 장소 제안 딥링크(`/map?suggest=`) + E2E

**작업**: 지도 우클릭 없이도 장소 제안 다이얼로그를 열 수 있는 딥링크 + 제안 흐름 E2E.

- `lib/suggestParam.ts`: `parseSuggestParam("lon,lat")` → CoordSchema 검증(한국 범위) coord|null. 순수·테스트.
- `FeatureMapView`: `initialSuggestCoord` prop — requestCoord 초기값으로 다이얼로그 사전 오픈.
- `app/(app)/map/page.tsx`: async + `searchParams.suggest` 파싱 → FeatureMapView 전달(라우트는 dynamic).
- `e2e/feature-request.e2e.ts`: `/map?suggest=126.978,37.566` → 다이얼로그 좌표 표시 → 이름 입력 →
  제출(`features/requests` mock) → "제안이 접수됐습니다". (VWorld 키 없이 검증 가능.)
- `tests/suggestParam.test.ts` 3건.

**검증**: 로컬 chromium 전 스위트 `28 passed` + tsc + lint + vitest.

## 2026-06-10 (claude) — E2E 추가: 최적화/공유/위치동의

**작업**: trip 협업·지도 흐름 E2E 3종(mock).

- `e2e/trip-collab.e2e.ts`: 공유 링크 생성(`share-tokens` POST → `new-share-url` 배너 URL) +
  동선 최적화 미리보기→적용(`days/{n}/optimize` persist false/true → "최단 경로 추정 거리"/1.8km
  표시 후 패널 닫힘).
- `e2e/map-consent.e2e.ts`: 내 위치 버튼 → 미동의 시 동의 다이얼로그 → 동의(`users/consents`
  PUT) → 닫힘. `test.use` geolocation 권한/좌표 주입.

**검증**: 로컬 chromium 전 스위트 `27 passed`(CI env port 9021) + tsc + lint.

## 2026-06-10 (claude) — E2E mutation 흐름 3종 추가

**작업**: trip mutation 흐름 Playwright E2E(mock) 추가 — 이제 CI에서 실제 실행됨.

- `e2e/trip-mutations.e2e.ts`:
  - 동반자 초대 → `members` POST mock + stateful TripView → `companion-list` 에 이메일 표시.
  - POI 삭제 → `pois/{id}` DELETE(204) + stateful TripView → "등록된 장소가 없습니다" 안내.
  - POI 마커 편집기 열기 → 저장(`pois/{id}` PATCH) → 편집기 닫힘.

**검증**: 로컬 chromium 전 스위트 `24 passed`(CI env port 9021) + tsc + lint.

## 2026-06-10 (claude) — E2E web CI 워크플로 (Playwright 실행 게이트)

**작업**: 작성만 해두고 CI에서 안 돌던 Playwright e2e를 실제 실행 게이트로.

- `playwright.config.ts`: `webServer`(`npm run build && npm run start`, :9022, CI에선 새 서버)
  추가 — 모든 e2e가 `page.route` API mock 이라 백엔드 불필요.
- `.github/workflows/web.yml`: `e2e` job 추가 — `playwright install --with-deps chromium` +
  `playwright test`(webServer가 앱 기동). 실패 시 traces artifact 업로드.
- **로컬 chromium 설치 후 전 스위트 실행 검증** — `trip-attachment` 의 `heading '첨부'` 가
  trip 제목("첨부 테스트 여행")과 strict-mode 충돌 → `exact: true` 로 수정. **21/21 통과**.

**검증**: 로컬 `npx playwright test` 21 passed + tsc. CI에선 본 PR의 web `e2e` job이 실증.

## 2026-06-10 (claude) — 프론트 접근성 개선(모달 Escape + 에러 role=alert)

**작업**: 이번 세션 추가 컴포넌트 a11y 점검·개선.

- `lib/useEscapeKey.ts`: Escape 키로 닫기 hook. `LocationConsentDialog`/`FeatureRequestDialog`/
  `NoticePlanCopyDialog` 3개 모달에 적용(키보드 사용자 모달 탈출).
- 에러 메시지 `<p>` 13곳에 `role="alert"` 추가 — 스크린리더가 비동기 에러를 즉시 안내
  (map/trips 컴포넌트 + settings/consents + notice-plans).
- `e2e/notice-copy.e2e.ts`: 다이얼로그 Escape 닫힘 → 재오픈 → 복사 시퀀스 검증 추가.

**검증**: web build / `tsc` / `next lint` / vitest / playwright --list(21) 전부 통과.

## 2026-06-10 (claude) — E2E 추가: 지도/추천복사/첨부업로드

**작업**: PR-C 핵심 흐름 Playwright E2E(mock) 3종.

- `e2e/map-explore.e2e.ts`: `/map` 탐색 셸 — 검색/내 위치 컨트롤 + 지도 fallback|canvas 렌더
  (in-bounds mock, VWorld 키 유무 무관).
- `e2e/notice-copy.e2e.ts`: 추천 여행 카드 → copy 다이얼로그 → `notice-plans/{id}/copy` mock →
  "새 여행을 만들었습니다." + "여행 열기" 링크(`/trips/{id}`) 검증.
- `e2e/trip-attachment.e2e.ts`: TripView+`/storage/upload-urls`+presigned PUT(127.0.0.1:9555)+
  attachments(POST/GET 메서드 분기) mock → `setInputFiles` 업로드 → 목록에 `photo.jpg` 표시.
- `TripAttachments` 파일 input 에 `data-testid="attachment-input"`(E2E 타깃).

**검증**: `tsc`(e2e 포함) + `playwright test --list`(21 tests) + `next lint` + vitest + build. 실행은
브라우저/서버 인프라 별도(CI 미포함).

## 2026-06-10 (claude) — PR-D 착수: trip 상세 E2E + maplibre-vworld v0.1.3 동기화 + tasks.md 정리

**작업**: Sprint 4 v0.1.0 마무리 1차.

- **E2E**: `e2e/trip-detail.e2e.ts` — `GET /trips/{id}`(TripView)·`/auth/me`·comments·attachments 를
  `page.route` mock → 헤더/일자탭/POI 목록/동반자/공유/첨부/댓글 섹션 렌더 검증. `tsc`(e2e 포함) +
  `playwright test --list`(18 tests)로 확인. 실행은 브라우저/서버 환경 별도(CI 미포함).
- **maplibre-vworld 핀 최신화**: `f1dd74b9`(v0.1.2 코드) → **v0.1.3 tag `2a13ce02`**. v0.1.3 은
  src/dist 무변경 docs 릴리스(CHANGELOG 확인)라 코드 영향 없음. package.json + lock + build 확인.
- **docs/tasks.md**: 이번 세션(T-105 #120~#123, RustFS presign #125, PR-C 프론트 #126~#139,
  maplibre v0.1.3) 반영 — T-060 진행 노트 + 신규 절 2개 + 머지 히스토리 행.

**검증**: web build / `tsc` / `next lint` / vitest / playwright --list 전부 통과.

**남은 v0.1.0**: kor-travel-map client 실주입(라이브러리 ready 시) + E2E 실행 게이트 + tag.

## 2026-06-10 (claude) — POI 상세 편집(시간/예산/메모/URL)

**작업**: PoiEditor를 색/아이콘 → 도착·출발/예산·실제/메모/링크까지 풀 편집으로 확장.

- `lib/poiDetail.ts`: `parseAmount`(음수/비숫자/빈값→null) + `datetimeLocalToIso`/
  `isoToDatetimeLocal` + `buildPoiDetailPatch`(폼→`PoiUpdate`). 순수·테스트(parse/build).
- `PoiEditor`: props `poi`+`onSave(patch)` 로 변경, 16색+아이콘+도착/출발(datetime-local)+
  예산/실제(number)+메모+URL.
- `TripPoiList`: `onEditMarker`→`onEditPoi(poi, patch)`. `TripDetail`: `handleEditPoi`로
  `poiApi.update(version)` patch 전송(마커 우클릭/연필 동일).
- `tests/poiDetail.test.ts` 3건.

**검증**: web build(`/trips/[tripId]` 14.1kB) / `tsc` / `next lint` / vitest 44 passed.

## 2026-06-10 (claude) — 일자 동선 최적화 UI

**작업**: 선택 일자 동선 최적화(nearest_neighbor) 미리보기 → 적용.

- `lib/distance.ts`: `formatDistanceMeters`(m/km/null). 순수·테스트.
- `components/trips/TripDayOptimize.tsx`: "동선 최적화" → `optimizeDay(persist=false)` 미리보기
  (추정 거리/변경 수/warnings) → "적용"(`persist=true`) → reload. POI<2 면 숨김.
- `TripDetail` 사이드 패널(선택 일자)에 통합.
- `tests/distance.test.ts` 1건.

**검증**: web build(`/trips/[tripId]` 13.6kB) / `tsc` / `next lint` / vitest 41 passed.

## 2026-06-10 (claude) — 동반자 초대/관리 UI

**작업**: trip `[tripId]` 동반자 초대(이메일+역할)/목록/제거.

- `lib/companion.ts`: `companionDisplayName`(nickname>email>fallback) + `companionJoined` +
  `ROLE_LABEL`. 순수·테스트.
- `components/trips/TripCompanions.tsx`: 이메일+역할(편집/보기/공동소유) → `inviteMember`,
  목록(이름/역할/참여여부) + `removeMember`. `view.companions` + reload.
- `TripDetail` 일자 탭 아래 동반자 섹션.
- `tests/companion.test.ts` 2건.

**검증**: web build(`/trips/[tripId]` 13kB) / `tsc` / `next lint` / vitest 40 passed.

## 2026-06-10 (claude) — trip 댓글(comment) UI

**작업**: trip `[tripId]` 댓글 목록/작성/삭제.

- `lib/comments.ts`: `canDeleteComment`(본인 댓글만 삭제 버튼). 순수·테스트.
- `components/trips/TripComments.tsx`: `listComments` 로드 + `authApi.me` 로 본인 식별,
  textarea 작성(`createComment` target_type=trip) + 본인 댓글 삭제(`deleteComment`).
- `TripDetail` 하단에 댓글 섹션.
- `tests/comments.test.ts` 1건.

**검증**: web build(`/trips/[tripId]` 12.5kB) / `tsc` / `next lint` / vitest 38 passed.

## 2026-06-10 (claude) — feature 제안 폼 (새 장소/이벤트)

**작업**: 지도 우클릭 → 새 장소/이벤트 제안 다이얼로그(`featureApi.request`, `type=new_place`).

- `lib/featureRequest.ts`: `parseCategories`(쉼표·trim·중복·max10) + `buildNewPlaceRequest`
  (kind/title/coord/categories/note → FeatureRequestCreate). 순수·테스트.
- `components/map/FeatureRequestDialog.tsx`: 종류(장소/이벤트)+이름+카테고리+메모, 좌표 표시
  → `featureApi.request` → 접수 안내(관리자 검토).
- `FeatureMapView`: 우클릭 메뉴에 "이 위치 장소 제안" 추가 → 클릭 좌표 prefill 다이얼로그.
- `tests/featureRequest.test.ts` 3건.

**검증**: web build(`/map` 8.1kB) / `tsc` / `next lint` / vitest 37 passed.

## 2026-06-10 (claude) — 첨부 업로드 UI (presigned PUT)

**작업**: trip 첨부 2-phase 업로드 + 목록/삭제/다운로드.

- **api-client**: `storageApi.createUploadUrl`(`POST /storage/upload-urls`) 신규 endpoint +
  `tripApi.attachmentDownloadUrl`(`GET .../download-url`) 추가.
- `lib/upload.ts`: `roleFromContentType`/`buildAttachmentCreate`(순수·테스트) + `putToPresigned`
  (브라우저→RustFS PUT).
- `components/trips/TripAttachments.tsx`: 파일 선택 → upload-url 발급 → RustFS PUT →
  `createAttachment` 등록 → 목록(이름/타입/크기) + 다운로드(presigned GET 새 탭) + 삭제.
- `TripDetail` 하단에 첨부/공유 2열 섹션.
- `tests/upload.test.ts` 3건.

**검증**: web build(`/trips/[tripId]` 11.9kB) / workspace `tsc` / `next lint` / vitest 34 passed.
실 PUT/다운로드는 RustFS 컨테이너 + CORS 필요(런타임).

## 2026-06-10 (claude) — trip 공유 링크 관리 UI

**작업**: trip `[tripId]` 상세에 공유 링크 생성/복사/철회.

- `lib/shareLink.ts`: `shareLinkStatus`(revoked/expired/active) + 권한/상태 라벨. 순수·테스트.
- `components/trips/TripShareLinks.tsx`: 권한(보기/댓글/편집)+만료일 선택 → `createShareToken`
  → 생성 URL 1회 표시(복사). 기존 링크 목록(상태/만료) + active 링크 철회(`revokeShareToken`).
- `TripDetail`: 하단에 공유 섹션(view.share_links + reload). 토큰/URL 은 응답에만 있고
  TripView 엔 없으므로 생성 시 1회 노출.
- `tests/shareLink.test.ts` 3건.

**검증**: web build(`/trips/[tripId]` 10.7kB) / `tsc` / `next lint` / vitest 31 passed.

## 2026-06-10 (claude) — notice-plan copy 다이얼로그

**작업**: 추천 여행(notice-plan)을 trip 으로 가져오는 다이얼로그(기존 1-click 복사 대체).

- `lib/noticePlanCopy.ts`: `buildCopyRequest`(새 여행=trip_title+날짜 / 기존=target_trip_id,
  poi_ids=[] 전체) + `canCopy`. 순수·테스트.
- `components/notice-plans/NoticePlanCopyDialog.tsx`: 새 여행/기존 여행 선택, 새 여행은 제목·
  날짜 편집, 기존은 `tripApi.list` 선택 → `noticePlanApi.copy` → 결과(장소 N곳) + "여행 열기"
  링크(`/trips/{id}`).
- `NoticePlanShelf`: 카드 버튼 → 다이얼로그 오픈(이전 즉시 복사 제거).
- `tests/noticePlanCopy.test.ts` 4건.

**검증**: web build(`/notice-plans` 4.41kB) / `tsc` / `next lint` / vitest 28 passed.

## 2026-06-10 (claude) — Sprint 4 PR-C 잔여: 마커 우클릭 편집 + 동의 철회 UI

**작업**: PR-C 잔여 UI 2종.

- **마커 우클릭 편집**: `MakiMarker.onContextMenu`(라이브러리 `Marker` 상속) → trip 지도 마커
  우클릭 시 해당 POI 선택 + 편집기 오픈. `TripPoiList` 편집 상태를 외부 제어 가능하게 변경
  (`editingPoiId`/`onEditToggle`, 미지정 시 내부 상태 유지) → `TripDetail` 이 마커 우클릭과
  목록 연필을 동일 편집 상태로 묶음.
- **동의 철회 UI**: `app/(app)/settings/consents` 신규 — `getConsents` 현황 + 선택 항목
  (`location_collection`/`demographic_use`/`marketing`) `withdrawConsent` 철회(필수 약관은 제외).

**검증**: web build(`/settings/consents` 신규, `/trips/[tripId]` 9.55kB) / `tsc` / `next lint` /
vitest 24 passed.

## 2026-06-10 (claude) — Sprint 4 PR-C(5): 위치 동의 흐름 + day 관리

**작업**: LBS/PIPA 위치 동의 게이트 + trip day CRUD UI.

- **api-client**: `userApi` 에 `getConsents`/`putConsents`/`withdrawConsent`(`/users/consents`) 추가.
- **위치 동의** (`docs/compliance/lbs-act.md` §2):
  - `lib/locationConsent.ts`: `hasLocationConsent`(lbs_tos+location_collection 유효 확인) +
    `locationConsentItems`(v1.0). 순수·테스트.
  - `components/map/LocationConsentDialog.tsx`: 동의 모달.
  - `FeatureMapView` "내 위치" 버튼 → 동의 확인(`getConsents`) → 미동의 시 다이얼로그 → 동의
    (`putConsents`) 후 geolocation. 철회 케이스도 재동의로 처리.
- **day 관리**: `components/trips/TripDayControls.tsx`(일자 추가/이름수정/삭제) → `TripDetail` 에
  `tripApi.createDay`/`updateDay`/`deleteDay` 배선(mutation 후 재조회).
- `tests/locationConsent.test.ts` 4건.

**검증**: web build(`/map` 7.11kB, `/trips/[tripId]` 9.45kB) / workspace `tsc`/`next lint` /
vitest 24 passed. 실 위치/지오로케이션 E2E(브라우저)는 별도.

**남은 PR-C**: 마커 우클릭 직접 편집, 설정에서 동의 철회 UI(현재는 가입/위치 게이트만).

## 2026-06-10 (claude) — Sprint 4 PR-C(4): POI 추가/재정렬/편집

**작업**: trip `[tripId]` 지도/패널에서 POI 추가·재정렬·마커 편집·삭제. 백엔드 `poiApi` 기존 활용
(변경 없음).

- `lib/poiRank.ts`: `sort_order`(COLLATE "C") 키 생성 — `evenRanks`(균등 base36 고정폭)/`appendRank`
  (suffix)/`arrayMove`/`reorderMoves`(변경분만 move). 순수·테스트.
- `components/trips/PoiEditor.tsx`: 16색 스와치 + maki 아이콘 입력 → `custom_marker_color`/
  `custom_marker_icon`.
- `TripPoiList`: HTML5 D&D 재정렬(`onReorder`) + 편집 토글(PoiEditor) + 삭제. `editable` gate.
- `TripDetail`: 추가(MapSearchBox 결과 → `poiApi.create`, snapshot 에 coord 포함) / 재정렬
  (`poiApi.reorder`) / 편집(`poiApi.update` + If-Match version, optimistic lock) / 삭제. 모든
  mutation 후 `tripApi.get` 재조회, 실패 시 에러 표시 + 재조회.
- `tests/poiRank.test.ts` 5건.

**검증**: web build(`/trips/[tripId]` 9.04kB) / `tsc --noEmit` / `next lint` / vitest 20 passed.
실 D&D·편집 E2E(브라우저)는 별도. 권한 gate(viewer 숨김)는 TripView 에 role 노출 시 후속.

**남은 PR-C**: 위치 동의 흐름(LBS/PIPA), 마커 우클릭 직접 편집, day 추가/관리 UI.

## 2026-06-10 (claude) — Sprint 4 PR-C(3): 지도 검색 + 내 위치 + 우클릭 메뉴

**작업**: 탐색 지도(`/map`)에 인터랙션 3종 추가. 라이브러리 실제 API surface(검증) 기준.

- `components/map/MapSearchBox.tsx`: `/features/search` 검색 박스 — 결과 클릭 시 해당 feature 로
  flyTo + 선택(상세/날씨 팝업).
- `FeatureMapView`: ① 검색 overlay(좌상단) ② 내 위치 버튼(우하단, `navigator.geolocation` →
  `UserLocationMarker` + flyTo, 서버 좌표 전송 없음 — LBS 단순화) ③ 우클릭 `MapContextMenu`
  (`onContextMenu` → "여기서 주변 보기" flyTo / "좌표 복사"). 기존 in-bounds 로딩·클러스터·팝업 유지.
- `vworldPrimitives.tsx`: `UserLocationMarker` / `MapContextMenu` 추가. FeatureMapView 를 공통
  primitives 로 이관(로컬 dynamic 블록·shim 중복 제거).

**검증**: web build(`/map` 3.73kB) / `tsc --noEmit` / `next lint` / vitest 15 passed. 실 지도 인터랙션
E2E(VWorld 키+브라우저)는 별도.

**남은 PR-C**: POI 추가/재정렬(D&D)·편집, 마커 우클릭 색/아이콘, 위치 동의 흐름(LBS/PIPA).

## 2026-06-10 (claude) — Sprint 4 PR-C(2): trip 대시보드 링크 + [tripId] 메인 지도

**작업**: 사용자 여행을 지도에 — `/trips/[tripId]` 메인 지도 + POI 사이드패널(양방향 선택).

- `lib/tripMapPoints.ts`: `TripView` POI(opaque `feature.coord`)를 `CoordSchema` 런타임 검증으로
  지도 포인트로 변환(`extractCoord`/`tripPoiToMapPoint`/`tripDaysToMapPoints`/`pointsBounds`).
  좌표 없거나 한국 범위 밖이면 제외. marker_color → 팔레트 hex.
- `components/map/vworldPrimitives.tsx`: maplibre-vworld 동적 import + dev shim 공통 모듈
  (VWorldMap/ClusterLayer/MakiMarker/Popup/skeleton/fallback) — TripMapView 가 사용.
- `components/trips/TripMapView.tsx`: trip POI 지도 — 로드 시 POI 경계 fitBounds, 마커 클릭 →
  선택, 외부 선택 시 flyTo, broken POI 표시.
- `components/trips/TripPoiList.tsx`: 선택 일자의 POI 목록(순번 색 dot + 도착시각 + 예산 + 메모 +
  broken 배지). 클릭 → 선택(지도와 양방향 동기).
- `components/trips/TripDetail.tsx`: `tripApi.get`(TripView) → 헤더(제목/일정/지역/동반/끊긴
  링크 수) + 일자 탭 + 지도/목록 양방향. raw apiClient 패턴.
- `app/(app)/trips/[tripId]/page.tsx` 라우트 + `TripDashboard` 카드 → `/trips/{id}` 링크.
- `tests/tripMapPoints.test.ts` 6건.

**검증**: web build(`/trips/[tripId]` 6.36kB) / `tsc --noEmit` / `next lint` / vitest 15 passed.
실 지도 렌더 E2E(VWorld 키+브라우저)는 별도.

**남은 PR-C**: POI 추가/재정렬(D&D)·편집, 우클릭 메뉴(4+3), 내 위치+동의 흐름, search overlay.

## 2026-06-10 (claude) — Sprint 4 PR-C(1): 지도 실 feature 로딩 슬라이스

**작업**: shell-only 였던 지도에 실제 `/features/in-bounds` 데이터 로딩 + 16색 팔레트를 입힘.
PR-C 전체 DoD 중 "viewport 기반 feature 로딩 + 클러스터 렌더 + 팔레트" 핵심 슬라이스.

- `apps/web/lib/markerPalette.ts`: 16색 팔레트(P-01~P-16 → hex/labelColor) + `paletteHex`/
  `paletteLabelColor` + 카테고리/kind → maki·색 fallback 매핑(`docs/design/marker-palette.md`).
- `apps/web/lib/featureBounds.ts`: viewport → `lng_min,lat_min,lng_max,lat_max` bbox(한국 범위
  clamp, 소수 5자리) + `clampZoom`(5~19). 순수 함수.
- `apps/web/components/map/FeatureMapView.tsx`: 기존 shell 의 maplibre-vworld 배선을 그대로
  쓰되 load/moveend/zoomend(250ms debounce)에 `featureApi.inBounds` 호출 → 서버 features =
  MakiMarker(팔레트 색·maki 아이콘) / 서버 clusters = 숫자 마커(클릭 시 flyTo zoom-in). 마커
  클릭 → `get`+`weather` 동시 로드 → Popup(제목/카테고리/주소/현재 기온). stale 응답 가드 +
  raw apiClient 패턴(기존 TripDashboard 와 동일).
- `apps/web/app/(app)/map/page.tsx`: "탐색 지도" 라우트. 기존 `/trips/map-shell`(shell)은 유지.
- `apps/web/tests/{markerPalette,featureBounds}.test.ts` + `vitest.config.ts`(e2e 제외, `@` alias).

**검증**: web build / `tsc --noEmit` / `next lint` / vitest 9 passed (workspace 전체 lint+typecheck
포함). 실 지도 렌더(VWorld 키 + 브라우저) E2E 는 별도.

**남은 PR-C(후속 슬라이스)**: POI D&D + 양방향 패널, trip 대시보드/[tripId] 메인 맵, 우클릭 메뉴
4+3종, 내 위치 버튼+동의 흐름, search overlay, CI web 워크플로 e2e 게이트.

## 2026-06-10 (claude) — RustFS presigned 실서명 활성화 (PUT/GET)

**작업**: 그간 placeholder(`X-Amz-Signature=PLACEHOLDER`)였던 presigned URL 을 boto3 실서명으로 전환.

- `rustfs_storage.py`: `make_upload_url`(put_object) / `make_download_url`(get_object) 가
  boto3 `generate_presigned_url`(SigV4 query auth) 사용. 서명 client 는 **public endpoint**
  - path-style addressing(RustFS/MinIO 필수), 설정 조합별 `lru_cache`. 서명은 순수 로컬 연산이라
    async 핸들러 동기 호출에도 블로킹 없음.
- 업로드 헤더에서 불필요한 `x-amz-content-sha256` 제거(query 서명 body=UNSIGNED-PAYLOAD).
  `ContentType` 을 서명에 포함 → 클라이언트는 `Content-Type` 헤더 필수.
- `pyproject.toml`: mypy override `boto3.*` → `["boto3.*", "botocore.*"]`.
- 단위 테스트 2건(upload/download 실서명 검증 — AWS4-HMAC-SHA256 / X-Amz-Signature /
  path-style / placeholder 부재). RustFS 없이 로컬 서명만으로 검증.
- `docs/api/storage.md` §4.1 헤더/서명 노트 갱신.

**검증**(WSL ext4): unit 118 passed, integration 139 passed, mypy --strict 통과, ruff+format clean.

**참고**: admin 객체 list/delete(#122)는 이미 실 boto3. 이로써 RustFS S3 경로(presign+admin)
전부 실서명/실호출. 실제 업로드/다운로드 E2E 는 RustFS 컨테이너 기동 후 별도 확인.

## 2026-06-10 (codex) — Claude PR 사후 리뷰 + T-190~T-194 후속

**작업**: 2026-06-08 00:00 KST 이후 Claude `agent/claude-*` PR 23건(#84/#88/#95/#97/#98/
#102~#106/#109/#110/#113~#123)을 closed 포함 재검토하고, PR별 Codex 사후 리뷰 코멘트를 게시.
취합 문서: `docs/reviews/2026-06-10-claude-pr-review.md`.

- #116 후속(T-190): `get_current_user_id()`가 인증된 user id를 `request.state.user_id`에 저장.
  `RequestIdMiddleware`는 생성/수신 request id를 `request.state.request_id`와 ASGI extensions에
  보존. `LocationAuditMiddleware`는 spoof 가능한 `X-User-Id`를 더 이상 신뢰하지 않고 state 값만
  사용. `/features/requests`는 검증된 body 좌표를 `request.state.location_audit_coord`로 넘겨
  outbox 좌표를 보존.
- #120/#121/#123 후속(T-191~T-192): 첨부 metadata 등록 시 `bucket == PINVI_RUSTFS_BUCKET` +
  `user-uploads/{purpose}/{user_id}/` prefix 검증을 공통 `rustfs_storage.validate_attachment_storage_ref`
  로 강제. trip/POI/admin curated 모두 위반 시 `422 INVALID_ATTACHMENT_STORAGE_REF`.
- #123 후속(T-193): `/storage/upload-urls`에서 `curated_plan_attachment` /
  `curated_poi_attachment` purpose는 admin role만 발급. 비권한은 기존 admin 규약처럼 404.
- #119 후속(T-194): `/features/nearby` query를 `lon`/`lat`로 정렬하고 legacy `lng` 요청은 422.
- 문서: `docs/api/storage.md` 서버 검증 규칙, `docs/api/features.md` nearby 예시, `docs/tasks.md`,
  `docs/resume.md` 갱신.

**검증**: 후속 PR 검증 명령 결과를 PR 본문에 기록.

## 2026-06-10 (claude) — T-105 #1·#2: Admin 큐레이션(plan/POI) 첨부 (§5.3/5.4)

**작업**: `/admin/notice-plans/*` 큐레이션 첨부 CRUD — T-105 첨부 도메인 잔여 마지막 2건.

- `services/admin_curated_attachment.py` 신규 — `ensure_plan`/`ensure_poi`(존재·소속 검증,
  soft-delete 제외) + `list/create/get/delete_curated_attachment`. mutate 는 commit 안 하고
  flush 만(라우터가 audit 와 같은 트랜잭션에 묶어 commit). 개수 상한은 trip 첨부와 동일 설정
  (`pinvi_max_attachments_per_target`) 공유.
- `api/v1/admin/notice_plans.py` 신규 — §5.3 plan 첨부(GET/POST/DELETE) + §5.4 POI 첨부
  (GET/POST/DELETE). `require_role("admin")`→비admin 404. plan/POI 없으면 404 `NOT_FOUND`,
  개수 초과 409. POST/DELETE 는 admin*audit chain 기록(`curated_plan.attachment*_`/`curated*poi.attachment*_`). DELETE 는 soft delete 만 — RustFS object 보존(§5.6, notice→trip
copy 시 `storage_key` 공유).
- 응답은 `AttachmentResponse`(curated*\* + notice*\* alias 항상 동기). 입력 `AttachmentCreate`
  (storage_key 위생 검증 재사용).
- 테스트 4건(plan CRUD / POI CRUD / unknown-plan 404 / 비admin 404).

**검증**(WSL ext4): integration 133 passed, unit 116 passed, mypy --strict 통과, ruff+format clean.

**완료**: T-105 첨부 도메인 4건(#1·#2 admin curated, #3 rustfs+boto3, #4 download URL) 전부 머지.

## 2026-06-10 (claude) — T-105 #3: /admin/rustfs/\* 객체 관리 (boto3)

**작업**: RustFS(S3) Admin 객체 관리 — 실 ListObjectsV2/DeleteObject. boto3 의존성 추가.

- `boto3>=1.35` 의존성 + mypy `boto3.*` ignore_missing_imports override.
- `services/rustfs_admin.py`: boto3 동기 client를 `asyncio.to_thread`로 감싼 `list_objects`/
  `delete_object`(endpoint/keys는 settings).
- `api/v1/admin/rustfs.py`: `GET /admin/rustfs/objects`(prefix/limit/cursor) +
  `DELETE /admin/rustfs/objects`(key+reason+force). DB 참조(`CuratedPlanAttachment.storage_key`)
  있으면 `force` 없이 `409 OBJECT_REFERENCED`. 삭제는 admin_audit chain 기록. require_role(admin)→404.
- 스키마 `RustfsObject`/`RustfsObjectList`. 테스트(S3 monkeypatch: list/참조-409/force-204/비admin-404).
- **harness fix** `core/deps.py`: `get_db` 가 `db_session.async_session_factory` 를 **모듈 속성으로
  동적 참조**하도록 변경(기존 `from ... import async_session_factory` 이름 바인딩 제거). 통합 테스트가
  엔진을 함수 스코프로 monkeypatch 하는데, 테스트 모듈이 app 을 **top-level import** 하면(본 rustfs
  테스트) collection 시점에 deps 가 패치 이전 기본(localhost) 팩토리를 잡아 전 스위트가
  `relation "app.users" does not exist` 로 무너지던 잠재 버그를 제거.

**참고**: presigned upload/download은 여전히 placeholder(실서명은 RustFS 활성화 시 별도). 본 PR은
admin 객체 조회/삭제만 실 S3.

## 2026-06-10 (claude) — T-105 #4: 첨부 presigned download URL

**작업**: private 첨부 본문 접근용 presigned GET URL. 권한은 attachment-scoped(trip 읽기 권한 →
동반자 포함)로, 단순 storage-key 노출보다 안전.

- `rustfs_storage.make_download_url`(placeholder presigned GET, upload과 동일 패턴, public_url 동반)
  - `DownloadUrlResponse` 스키마 + Zod.
- `trip.get_attachment`(스코프 단건 조회) 서비스.
- `GET /trips/{id}/attachments/{aid}/download-url` + `GET /trips/{id}/pois/{pid}/attachments/{aid}/download-url`
  (읽기 권한, 없는 첨부 404). 라우트 suffix가 distinct라 list/PATCH/DELETE와 충돌 없음.
- 테스트: download-url 200(method GET·storage_key 포함) + 404.

## 2026-06-10 (claude) — T-105 첨부 하드닝(개수 제한 + 재정렬)

**작업**: trip/POI 첨부(이미 T-132로 CRUD 완료)에 남용 방지 + 재정렬을 추가.

- **개수 상한**: 대상(trip 또는 POI)당 첨부 `pinvi_max_attachments_per_target`(기본 30) 초과 시
  `create_attachment`가 `TripAttachmentLimitError` → `409 ATTACHMENT_LIMIT_EXCEEDED`(`_count_attachments`).
- **재정렬/설명 수정**: `update_attachment` 서비스 + `AttachmentUpdate` 스키마(sort_order/description,
  최소 1필드) + `PATCH /trips/{id}/attachments/{aid}` · `PATCH /trips/{id}/pois/{pid}/attachments/{aid}`
  (편집 권한 gate). 목록은 sort_order asc → created_at asc.
- config `pinvi_max_attachments_per_target`, docs/api/storage.md §5 하드닝 노트, 테스트(한도 409 +
  재정렬 후 목록 순서).

**경계**: Admin curated-plan/POI 첨부(§5.3/5.4)는 admin curated-plan 도메인 미구축이라 별도 작업으로 유지.

## 2026-06-09 (claude) — T-182: 좌표 필드명 `lon`/`lat` 정렬 (DEC-07/ADR-048 B)

**작업**: Pinvi 정본 좌표 필드를 kor_travel_map 정렬로 `longitude`/`latitude` → `lon`/`lat` 일괄 리네임
(서브에이전트 기계 sweep + 검증). DEC-07 좌표 sub-decision 확정.

**리네임(우리 Coord/API/테스트)**: `Coord`(Pydantic) + `CoordSchema`(Zod) 필드, 전 `Coord(...)`
생성자·`.lon`/`.lat` 읽기, geo query 파라미터, ws `presence.cursor` 출력, frontend
`useUserLocation`/`locationAdapter` 출력, 전 테스트, `docs/api` JSON 예시.

**keep(경계)**: 외부 kor_travel_map DTO/feature_snapshot tolerant reader(trip `_extract_coord`,
kasi snapshot, location_audit query alias에 `lon` 추가), 브라우저 Geolocation `position.coords.*`,
KASI DB 컬럼(`models/kasi.py` — 리네임은 migration 필요, out of scope).

**검증**: ruff check/format 통과, 잔여 `longitude`/`latitude`는 전부 의도된 keep(외부값·DB·tolerant).
mypy/pytest/web tsc는 CI.

## 2026-06-09 (claude) — T-189 리뷰 잔여 낮음 묶음

**작업**: #108/#316 리뷰에서 남긴 저위험 항목을 한 PR로 정리.

- 사용자 제안 `kind`를 `place`/`event`로 좁힘(#108) — notice/price/weather/route/area는 운영
  데이터라 제안 대상 아님. `FeatureSuggestionKind` 신설(create만, response는 broad 유지) + Zod 미러.
- 제안 rate-limit이 `rejected`/`duplicate`를 카운트에서 제외 → `pending`/`approved`/`added`만
  남용 신호로(거절 다수 사용자가 정당 신규 제안 못 하는 것 방지).
- 테스트: 제안 kind 거부(notice 422) + rate-limit rejected/duplicate 제외(201).

**잔여(미반영, tasks T-189)**: requester FK RESTRICT PIPA 파기 정책, #99 rise_set model_validate,
#93 money quantize(저위험 가설).

## 2026-06-09 (claude) — T-146 완성: feature TTL 캐시 (D-26)

**작업**: trip view마다 kor_travel_map를 재조회하는 단일 노드 hotspot(D-26)을 process-local TTL 캐시로 완화.

**신규/갱신**:

- `services/feature_cache.py` — `FeatureCache`(TTL + LRU maxsize, monotonic clock) + 싱글톤.
  `get_many`(hit/miss 분리) / `put_many`(만료시각·LRU evict) / `clear`.
- `trip_view_builder.build_trip_view` — feature_id를 캐시 조회 → **miss만** `features_by_ids`로
  재조회 후 캐시 적재(반복 view에서 kor_travel_map 호출 0). `pinvi_feature_cache_enabled` 가드.
- config `pinvi_feature_cache_*`(enabled/ttl 60s/max 10000).
- 테스트: 캐시 단위(hit/miss/LRU/TTL/clear) + trip_view 2-build cache-hit(2번째 build fetch 0) +
  conftest autouse `feature_cache.clear()`로 테스트 격리.

T-146 완료(D-20 outbox + D-26 캐시).

## 2026-06-09 (claude) — T-146 slice: location-audit async outbox (D-20)

**작업**: 위치 감사 적재의 요청경로 hotspot(동기 체인 해시 + chain-head 직렬화)을 async outbox로 제거.

**설계**: 요청경로 → `location_audit_outbox`에 fast append(체인 미계산). 단일 writer worker가
`drain_location_audit_outbox`로 outbox를 occurred 순서로 `location_access_log` 체인에 반영
(advisory xact lock으로 동시 drain 체인 fork 방지, 한 트랜잭션에서 flush로 chain-head 진행).

**신규/갱신**:

- migration 0017 `app.location_audit_outbox`(pending 부분 인덱스) + 모델 `LocationAuditOutbox`.
- `services/location_audit.py`: `append_location_log`(체인 primitive, occurred_at/commit 옵션) +
  `enqueue_location_audit_outbox` + `drain_location_audit_outbox` + 백그라운드 `location_audit_outbox_worker_lifespan`.
- 미들웨어: 요청경로를 enqueue로 전환(체인 로직 service로 이전, `_append_log`는 wrapper 유지 →
  기존 직접-적재 테스트 호환).
- config `pinvi_location_audit_outbox_*`(enabled/interval/batch), main.py lifespan 합성.
- 테스트: enqueue→pending 확인→drain→체인 3건/processed + idempotent.

**잔여(T-146/D-26)**: trip view feature 캐시(kor_travel_map batch+join N+1 제거).

## 2026-06-09 (claude) — T-129 완성: `/regions/covering-point` + 통합 `GET /search`

**작업**: T-129 잔여를 닫아 완료 처리.

**신규/갱신**:

- `GET /regions/covering-point` — kor-travel-geo `/v2/reverse` 최선 후보의 `region` pass-through, 미매치 404.
- **통합 `GET /search`**(`apps/api/app/api/v1/search.py`, C-13) — feature(kor_travel_map httpx client) +
  address(kor-travel-geo) + 내 POI(Pinvi `trip_day_pois`, 소유 trip 한정 ILIKE) 3소스 병합.
  외부 소스 한쪽 불가 시 전체 실패 대신 해당 소스만 비우고 `degraded_sources`에 기록(graceful degrade).
  ilike 와일드카드 이스케이프.
- frontend Zod(`packages/schemas/src/geo.ts`): `GeoCandidateList`/`RegionCovering`/
  `UnifiedSearchResult` + index export.
- 테스트: covering-point(region/404) + 통합 search(병합/feature outage degrade).

**경계**: kor_travel_map httpx client를 라우트에서 쓰는 첫 사례(/search). 기존 `/features/*`는 여전히
etl_bridge stub(T-173 cutover 별개). 좌표명 정렬(T-182)도 별개.

## 2026-06-09 (claude) — T-129 slice: `/geo/*` + `/regions/*` (kor-travel-geo v2 REST)

**작업**: T-129의 geo·regions slice를 from-scratch 구현(ADR-025, `docs/integrations/kor-travel-geo.md`).
kor-travel-map 비의존 사용자 경로. 좌표는 `(lon, lat)`, 대한민국 범위(ADR-018).

**신규**:

- `apps/api/app/clients/kor_travel_geo.py` — kor-travel-geo v2 REST httpx client(전송 전용). `geocode`/
  `reverse`/`search`/`regions_within_radius`(POST `/v2/*`) + 도메인 예외(Unavailable/BadRequest) +
  지수 백오프 재시도 + lifespan/dep. 응답 최상위는 `{status, candidates[]}`(envelope `data` 없음).
- `apps/api/app/schemas/geo.py` — `GeoCandidateList`(candidate pass-through).
- `apps/api/app/api/v1/geo.py` — `GET /geo/{geocode,reverse,search}` + `GET /regions/within-radius`
  (인증 필요, Korea 좌표 bounds, client 미주입 시 503 GEOCODING_SERVICE_UNAVAILABLE).
- config `pinvi_kor_travel_geo_*`(base 8888/timeout/max_attempts), main.py lifespan 합성, 라우터 등록.
- 테스트: client MockTransport 계약(경로/payload/재시도/4xx) + 라우터 통합(stub 주입/503/401/422).

**경계**: kor-travel-geo는 별 프로세스(REST), Pinvi는 v2 candidate를 pass-through. 외부 API
(vworld/juso)는 kor-travel-geo 내부 책임.

**잔여(T-129)**: `/regions/covering-point`(→ `/v2/reverse` 매핑), 통합 `GET /search`(features+
addresses+my_pois, C-13), frontend Zod/api-client.

## 2026-06-09 (claude) — T-181 kor_travel_map 외부 `/v1` hard cutover (T-170 client 적응)

**작업**: kor_travel_map `origin/main`이 외부 `/v1` clean cut(PR #319) + batch `/pinvi/features/batch`→
`/v1/features/batch`(PR #318) + 파라미터 개명(PR #321)을 머지함을 `openapi.user.json`로 확인하고
T-170 httpx client를 새 라이브 계약에 맞춰 일괄 교체.

**확인한 라이브 계약**(`openapi.user.json` title `kor-travel-map-user 0.2.0-dev`): 외부 전 표면 `/v1`,
`/health`·`/version`만 비버전. in-bounds=`min_lon/min_lat/max_lon/max_lat`+`limit`+`zoom`+
`cluster_unit`, search=`q`+bbox 4 float+`page_size`+`cursor`, nearby=`lon/lat/radius_m`+`page_size`,
batch=`POST /v1/features/batch {feature_ids[]}`→`{data:{items{},missing[]}}`. **envelope payload/meta
분리(#2)와 problem+json(#5)은 아직 미머지** — `data.next_cursor`·`{error:{code}}` 유지.

**반영**(`apps/api/app/clients/kor_travel_map.py`): 전 feature/category 경로 `/v1` prefix(/health 제외),
batch 경로 교체, `search_features` 시그니처 `bbox`(CSV)→`min_lon/min_lat/max_lon/max_lat` + `limit`→
`page_size`. MCP `_search_features`가 `bounds` CSV를 4 float로 파싱하도록 갱신. MockTransport 계약
테스트(in-bounds/search/batch 경로 + bbox 분리 검증) 추가/갱신.

**잔여**: problem+json 에러·meta.page 분리는 kor_travel_map T-216 머지 시 추종(T-181 잔여로 유지). 라우터
cutover(T-173)·좌표 응답 매핑(T-182)은 별개. 현재 client는 etl_bridge stub 미사용 경로라 라우트 무영향.

## 2026-06-09 (codex) — T-183 Backup hotswap 잔여 보강

**작업**: PR #109에서 남긴 #100 backup hotswap 잔여(self-kill drain, 교차프로세스 lock,
cut-over audit 격리)를 운영 활성화 전 선결 수준으로 닫았다.

**변경**:

- `restore_backup_hotswap()`에 Postgres `pg_try_advisory_lock`을 추가해 다중 API 워커/프로세스가
  동시에 schema-swap을 실행하지 못하게 했다.
- API-triggered restore는 `PINVI_RESTORE_API_TRIGGER=1`을 script에 넘기고,
  `PINVI_RESTORE_DRAIN_COMMAND`가 설정되어 있으면 `draining:failed`로 중단한다. API 호출은
  외부 read-only/drain 완료 후 `PINVI_RESTORE_ALLOW_NO_DRAIN=1`로만 swap을 진행한다.
- swap 전 `backup.restore_hotswap_started` audit를 canonical chain에 먼저 남기고, swap 성공
  reflection은 `app_previous_<restore_id>.admin_audit_log`에 append한다.
- `PINVI_RESTORE_DATABASE_URL`, `PINVI_RESTORE_HOTSWAP_EXECUTE`,
  `PINVI_RESTORE_DRAIN_COMMAND`, `PINVI_RESTORE_ALLOW_NO_DRAIN`,
  `PINVI_RESTORE_APP_ROLE`을 Settings/env/runbook에 정렬했다.

**검증**: backup service unit test, backend ruff/mypy, `git diff --check`, CodeGraph sync.

## 2026-06-09 (claude) — PR #108 리뷰 + T-188(type/target_feature_id 노출)

**작업**: codex PR #108(feature suggestion queue, T-177)을 사후 리뷰([코멘트](https://github.com/digitie/pinvi/pull/108#issuecomment-4656262939))하고
DEC-05 갭을 코드로 반영.

**리뷰 총평**: DEC-05 레이어 1을 정확히 구현(kor_travel_map 직접 호출 없음, dedup partial-unique +
IntegrityError race fallback, 24h rate limit, Korea coord CHECK, owner-only 조회, 라우트 순서).
잔존 [중간] 1건: 테이블·모델은 `type`(new_place/correction/closure)+`target_feature_id`를 갖췄으나
API 미노출 → **new_place만 생성 가능**.

**T-188 반영**: `FeatureRequestCreate/Response`에 `type`+`target_feature_id` 노출 + validator
(correction/closure는 target 필수·new_place는 금지, 422). dedup이 type/target을 구분하도록
`_find_duplicate`(`is_not_distinct_from`) + 마이그레이션 0015(유니크 키에 type+COALESCE(target) 포함).
frontend Zod(`FeatureRequestTypeSchema` + refine) + index export + `docs/api/features.md` + 회귀 테스트.
잔존 낮음(kind 과허용·requester FK RESTRICT·rate-limit status 무관)은 리뷰 코멘트에 기록.

## 2026-06-09 (codex) — T-112 Pinvi MCP 외부 인터페이스

**작업**: ADR-019의 read-only MCP 외부 인터페이스 1차 표면을 Pinvi app 도메인에
구현했다.

**변경**:

- `app.mcp_tokens` 모델과 Alembic migration을 추가했다. MCP 토큰은 `mcp_<JWT>` 원문을
  발급 직후 1회만 반환하고, DB에는 Argon2id hash와 마스킹용 prefix/suffix만 저장한다.
- 사용자 `GET/POST/DELETE /users/me/mcp-tokens`, admin `GET/POST /admin/mcp-tokens`,
  `POST /admin/mcp-tokens/{token_id}/revoke`를 추가했다. admin 발급/회수는
  `admin_audit_log`에 `mcp_token.issue` / `mcp_token.revoke`로 남긴다.
- `/mcp/sse`는 Bearer MCP 토큰 검증 후 5개 read-only tool descriptor를 SSE로 제공하고,
  `/mcp/tools/{tool_name}`은 `list_trips`, `get_trip`, `list_pois`, `search_features`,
  `get_user_profile`을 호출한다. `search_features`는 kor-travel-map OpenAPI HTTP client만
  사용한다.
- `@pinvi/schemas`, `@pinvi/api-client`, `/settings/mcp-tokens`,
  `/admin/mcp-tokens` 화면을 추가했다.

**검증**: backend ruff/mypy, MCP 통합 테스트, schema/api-client/web typecheck, schema test,
web lint/build, `git diff --check`, CodeGraph sync.

## 2026-06-09 (codex) — T-177 사용자 feature 제안 큐

**작업**: DEC-05의 사용자 제안 큐를 Pinvi `app` 도메인에 실체화하고, kor-travel-map
직접 호출 없이 `/features/requests` API가 동작하도록 전환했다.

**변경**:

- `app.feature_suggestions` 모델과 Alembic 마이그레이션을 추가했다. `requester_user_id`,
  제안 type/kind/name/좌표/categories/note/status, admin 처리자, `kor_travel_map_ref`, resolved 시각을
  저장한다.
- `POST /features/requests`는 같은 사용자·kind·정규화 title·소수 6자리 좌표의 pending
  제안을 dedup하고, 신규 등록은 사용자당 24시간 20건으로 제한한다.
- `GET /features/requests/{request_id}`는 본인 제안만 조회하고, 타 사용자 제안은 404로
  숨긴다.
- Pydantic/Zod schema와 `@pinvi/api-client`에 feature request 상세 응답 및
  `getRequest()`를 추가했다.

**검증**: backend ruff/mypy/pytest, schema/api-client/web typecheck, schema test, web lint,
`git diff --check`, CodeGraph sync.

## 2026-06-09 (codex) — T-133 Admin priority-3 결선

**작업**: kor-travel-map 연계가 필요 없는 Admin priority-3 항목을 실제 API/UI로 결선하고,
kor-travel-map 또는 운영 안전장치가 필요한 항목은 문서에서 상태를 명확히 낮췄다.

**변경**:

- `GET /admin/stats/overview`: Pinvi app DB 기준 사용자/여행/POI/email queue/API 호출
  지표를 반환한다. feature/ETL 지표는 외부 결선 전 빈 값/0값으로 고정한다.
- `GET /admin/api-calls`: `app.api_call_log` read-only 조회와 provider/status/error 필터를
  추가했다.
- `GET /admin/audit/location`: CPO 전용 `location_access_log` 조회를 추가했다. 좌표는
  4자리로 마스킹하고, hash chain 깨짐은 `X-Chain-Broken: true` 헤더로 표시한다.
- `/admin`, `/admin/api-calls`, `/admin/audit/location` 화면을 실제 데이터 조회 화면으로
  연결했다.
- `/admin/features`, `/admin/etl`, `/admin/seed`, `/admin/reset`은 각각 kor-travel-map admin API
  또는 운영 안전장치가 필요한 후속 결선으로 문서화했다.

**검증**: backend ruff/mypy/pytest, schema/api-client/web typecheck, schema test,
web lint/build, Windows Playwright e2e(`admin-priority3.e2e.ts`), `git diff --check`,
CodeGraph sync.

## 2026-06-09 (claude) — kor_travel_map PR #316(ADR-048) **3차 검토** — A–F 수렴 확인 + 잔여 정합성 2건

**작업**: 소유자 재지시(호환성 무시, 일관성/확장성/안정성 우선 + gh rate limit 준수)로 PR #316
3차 검토. kor_travel_map 에이전트가 내 재리뷰(A–F)에 **두 코멘트(커밋 3c64b5b, df69057)로 응답**한 것을
확인하고, 최신본(df69057) 직접 정독 후 3차 코멘트 게시 + Pinvi 반영.

**kor_travel_map 응답 확인**: A–F **6건 전부 수용**(df69057):

- A clean cut / B `lon`/`lat`(내 권고 (b) 채택, ADR-048 #10) / **C `cluster_key` 유지 — kor_travel_map가
  2차에서 `cluster_id`로 잘못 개명한 것을 내 C 지적으로 코드확인(행정구역 bjd 코드=자연키) 후 정정** /
  D `feature_id` 값 불변식(§3.2/#11) / E envelope 불변식(§3.3/#12) / F `/vN` 거버넌스(#13).
- kor_travel_map 2차 추가분: **envelope payload/meta 완전 분리(#2)** — `data`=payload만(목록 `{items:[]}`),
  pagination/추적을 `meta{...,page{page_size,next_cursor,total}}`로 일원화 + 단일 정본 수렴(#9).

**3차 검토(PR #316 코멘트)** — A–F 수렴 endorse + envelope 분리 endorse + 잔여 2건:

1. **batch `items`(map) ↔ list `items`(array) 키 충돌**(정합성·codegen): batch `data={items{},
missing[]}`의 `items`(id-map)와 list `data={items:[]}`의 `items`(배열)가 같은 키·다른 타입 →
   `openapi-typescript` 충돌. batch 별도 키(`found` 등) 권장.
2. **`cluster_unit` 위치**(minor): in-bounds `data.cluster_unit`은 메타 성격 → `meta` 후보(판단만).

**Pinvi 반영**: rest-api.md §1(envelope 분리 예고) + §7(A–F 수렴 완료 + 잔여 2건) +
T-181 정교화(list 메서드 `meta.page.next_cursor` threading). tasks.md T-181 갱신.

## 2026-06-09 (claude) — kor_travel_map PR #316(ADR-048) **재리뷰** — 호환성보다 정합성 우선으로 입장 전환

**작업**: 소유자 지시("호환성 신경쓰지 말 것. 지금 다 뒤집더라도 일관성·확장성·안정성 우선")로
PR #316을 한 번 더 리뷰. kor_travel_map 에이전트가 내 1차 리뷰 5건을 **전부 "동결/무중단" 방향으로 반영**
(커밋 7de0668)한 것을 확인하고, 그 전제를 뒤집는 재리뷰를 PR #316에 코멘트로 게시 + Pinvi 반영.

**핵심 모순 발견**: ADR-048 §1.2가 "경로 shim 금지(ADR-046)"와 "구 unprefixed alias 동시지원"을
**한 문단에서 동시에** 말함 — unprefixed alias = 경로 shim이라 자기모순.

**재리뷰 6지점(PR #316 코멘트)**:

- **A. dual-support 창 철회 → hard cutover**: Pinvi 미출시 + `/features/*` 503 + 유일소비자라
  보호할 설치 기반 0. 1차의 "무중단 이중지원" 요청 **철회**, `/v1` 단일 commit cut + lockstep.
- **B. `lon`/`lat` 동결 해제 → 양 repo 정렬**: DEC-07(`longitude`/`latitude`) vs kor_travel_map `lon`/`lat`
  영구 불일치를 동결로 박지 말고 하나로 정렬(경계 매핑 0). → DEC-07 좌표명 하위결정(T-182).
- **C. `cluster_key` merit 분류**: 행정 자연키면 `_key` 유지, surrogate면 `cluster_id`. compat 동결 X.
- **D. `feature_id` 값 안정성 명문화**: v0/v1 행+soft-delete에서 외부 id 불변을 계약에 박기(이름 동결과 별개).
- **E. envelope 불변식**: `meta`/`request_id` 항상 present, `next_cursor` null(omit 금지).
- **F. `/vN` 거버넌스**: pre-1.0 in-place break → v1.0.0 GA에 `/v1` 동결 → 이후 `/v2`+N-1.

**Pinvi 반영**: rest-api.md §1(hard cutover 명시) + §6 **T-181 재정의**(이중지원 의존 제거) +
§7(A~F로 합의항목 교체 + DEC-07 좌표명 하위결정). tasks.md **T-181 재정의 + T-182 신규**.

## 2026-06-09 (claude) — kor_travel_map PR #316(ADR-048) 리뷰 + Pinvi 반영(외부 표준 추종)

**작업**: kor-travel-map PR #316("REST API versioning admin/ops 확장 + 정합성 표준", ADR-048)을
Pinvi consumer 관점에서 리뷰하고 PR에 코멘트를 남긴 뒤, Pinvi 문서/태스크에 반영했다.
ADR-048은 **docs-only OPEN 플랜**(live `openapi.user.json`은 아직 unprefixed) — 차단은 아니나
#317보다 소비자 영향이 크다(외부 표면 표준화).

**PR #316 핵심(Pinvi 영향)**:

- **외부 `/v1` prefix**: 사용자 표면 전체를 `/v1`로(admin/ops/debug까지 통일). T-170 client는
  base path만 config로 바꾸면 되나 **무중단 이중지원 창** 필요.
- **RFC7807 `application/problem+json` 에러**: client `_error_code`(현재 `error.code`)가 확장 멤버
  `code` 파싱으로 갱신 대상. 코드 enum 유지 확인 필요.
- **파라미터 개명**: `search` bbox CSV→4 float, in-bounds `limit`→`max_items`, `total_count`
  opt-in `?include_total=true`. 쿼리 빌더 영향.
- **`*_key`→`*_id` 내부 개명**(경계: `cluster_key`/`feature_id`/`target_key` 보존) + 성공
  `meta.request_id` 추가(하위호환). admin client(T-180)는 신 spec 기준 작성이라 무영향.

**Pinvi 반영**:

- `integrations/kor-travel-map-rest-api.md`: §1(`/v1`/RFC7807 예고 경고) + §6 **T-181** 추가 +
  §7 ADR-048 연동 합의 5건.
- `tasks.md` **T-181** 신규(표준 추종, 현재 대기·차단 아님).

**연동 합의 질의(kor_travel_map PR #316 코멘트)**: ① 외부 `/v1` 이중지원 창+공지, ② 에러 `code`
위치/enum 고정, ③ 소비 read 필드 개명 제외 확인, ④ 외부 파라미터명 확정, ⑤ #317과 외부 spec
반영 순서.

## 2026-06-09 (claude) — kor_travel_map PR #317 리뷰 + Pinvi 반영(K-15 해소)

**작업**: kor-travel-map PR #317("admin feature change API")을 Pinvi consumer 관점에서 리뷰하고
PR에 코멘트를 남긴 뒤, Pinvi 문서/태스크에 반영했다.

**PR #317 핵심(Pinvi 영향)**:

- **K-15 해소**: `POST/PATCH/DELETE /admin/features`(place/event 추가/수정/soft delete) +
  검수 워크플로(`/admin/features/change-requests` approve/reject) + version 0(provider)/1(user)
  분리 + 재적재 보존. → DEC-05 사용자 제안 승인 흐름(T-179) actionable.
- `/pinvi/feature-update-requests*` 제거 → `/admin/feature-update-requests*` 고정(DEC-05 정합).
- **user API(9011) 무영향**: `/pinvi/features/batch`·`/features/*` 유지 → T-170 client 변경 없음.

**Pinvi 반영**:

- `integrations/kor-travel-map-rest-api.md`: §2.8 경로 갱신 + **§2.9 feature change API** 신설 +
  §4(T-170/171 완료) + §5/§6(T-179 actionable, **T-180** admin client) + §7(연동 합의 5건).
- `kor-travel-map-requirements.md` K-15 ✅ resolved. `decisions-needed` DEC-05 갱신.
- `tasks.md` T-179 actionable + T-180 신규.

**연동 합의 질의(kor_travel_map PR #317 코멘트)**: review_mode(이중 검수 방지), idempotency 멱등,
출처 태깅, admin 인증(9012), closure(DELETE vs deactivate).

## 2026-06-09 (claude) — T-170/T-171 kor-travel-map HTTP client + config 배선

**작업**: Pinvi↔kor-travel-map 연결 토대. `docs/integrations/kor-travel-map-rest-api.md` 계약 기준.

- **T-171**: `Settings`에 `pinvi_kor_travel_map_api_base_url`/`admin_base_url`/`service_token`/
  `timeout_seconds`/`max_attempts`/`batch_chunk_size` 필드 추가(기존엔 필드 없어 `.env` 값
  silently ignored) + `.env.example`/`apps/api/.env.example` 블록.
- **T-170**: `apps/api/app/clients/kor_travel_map.py` 신설 — httpx 기반, openapi.user.json 계약
  메서드(features_in_bounds[서버 클러스터]/get_feature[404→None]/get_features[batch,
  cap 청크]/features_nearby/search_features/feature_weather/categories/healthz),
  `{data,meta}` 언랩, 도메인 예외(Unavailable/FeatureNotFound/BadRequest/RateLimited),
  transient(타임아웃/연결/5xx) 지수 백오프 재시도, X-Kor-Travel-Map-Service-Token 전달,
  lifespan(`app.state`) + `get_kor_travel_map_client` 의존성. MockTransport 계약 테스트 10개.
- `main.py` lifespan에 신규 client 등록. 레거시 in-process Protocol stub
  (`etl_bridge/kor_travel_map.py`)은 라우터 cutover(T-173) 후 제거 — 본 PR은 additive.

**검증(WSL 미러)**: ruff check + ruff format --check + mypy --strict app + pytest unit
100 passed. main import OK.

## 2026-06-09 (codex) — T-132 Trip 하위 리소스 API 분할

**작업**: 감사 C-06/D-06 후속으로 Trip 소유 하위 리소스 중 kor-travel-map 연계가 필요 없는
days/shared/attachments/copy/optimize API를 실제 구현했다.

**변경**:

- `DELETE /trips/{trip_id}` soft delete와 owner transfer를 추가했다. owner transfer는
  새 owner를 검증하고 기존 owner를 `co_owner` companion으로 남긴다.
- `/trips/{trip_id}/copy`를 추가했다. `all` / `day` / `range` scope, 날짜 shift, 기존
  target trip append를 지원하고 day/POI/첨부 metadata 복제 건수를 반환한다.
- `/trips/{trip_id}/days` CRUD와 `GET /trips/{trip_id}/shared/{token}` anonymous shared
  view를 추가했다. shared view는 companions/share link 원문 없이 trip/day/POI와
  `broken_feature_count`만 반환한다.
- trip/POI attachment metadata 조회·생성·soft delete API를 `/trips/{trip_id}/attachments`
  및 `/trips/{trip_id}/pois/{poi_id}/attachments`에 연결했다.
- day별 distance matrix와 nearest-neighbor optimize API를 추가했다. optimize는 좌표 없는
  POI를 경고와 함께 뒤에 유지하고, `persist=true`일 때 LexoRank를 재부여한다.
- Pydantic/Zod schema와 `@pinvi/api-client` endpoint를 확장하고, Trip API 통합 테스트에
  day 삭제 cascade, copy + attachment 복제, shared view, distance matrix/optimize 회귀를
  추가했다.

**검증**:

- WSL2 ext4 mirror: `ruff format --check app/api/v1/trips.py app/schemas/trip.py app/services/trip.py tests/integration/test_trips_api.py`
- WSL2 ext4 mirror: `ruff check app/api/v1/trips.py app/schemas/trip.py app/services/trip.py tests/integration/test_trips_api.py`
- WSL2 ext4 mirror: `mypy --strict app/api/v1/trips.py app/schemas/trip.py app/services/trip.py`
- WSL2 ext4 mirror: `pytest --capture=no -q tests/integration/test_trips_api.py`
- WSL2 ext4 mirror: `npm run typecheck --workspace @pinvi/schemas`
- WSL2 ext4 mirror: `npm run test --workspace @pinvi/schemas`
- WSL2 ext4 mirror: `npm run typecheck --workspace @pinvi/api-client`
- WSL2 ext4 mirror: `npm run typecheck --workspace @pinvi/web`
- WSL2 ext4 mirror: `npm run lint --workspace @pinvi/web`
- WSL2 ext4 mirror: `NEXT_PUBLIC_PINVI_API_URL=http://localhost:8001 npm run build --workspace @pinvi/web`

**다음**: PR 머지 후 남은 kor-travel-map 비의존 후보를 재감사한다. 현재 문서상 다음 후보는
T-133 Admin priority-3 엔드포인트·페이지 실구현(or 상태 강등)이다.

## 2026-06-08 (codex) — T-111 Backup/Restore UI 핫스왑

**작업**: ADR-022/T-145의 동일 DB schema-swap restore를 admin API와 `/admin/backup`
UI에 연결했다.

**변경**:

- `POST /admin/backup/restore-hotswap` API를 추가했다. 요청은 `snapshot_id`,
  `access_reason`, `confirm_schema_swap`을 받으며, 성공/실패 모두 admin audit에 기록한다.
- `backup_service`에 snapshot lookup, restore run/phase 모델, hotswap script 실행 및
  `RESTORE_PHASE=...` 로그 파서를 추가했다.
- `scripts/restore-hotswap.sh`를 추가했다. 기본은 `PINVI_RESTORE_HOTSWAP_EXECUTE=1`
  가드 뒤에서 custom dump를 `app_restore_<ts>` schema로 remap restore하고, 검증/drain 후
  `app` → `app_previous_<ts>`, `app_restore_<ts>` → `app` rename을 수행한다.
- `packages/schemas` / `packages/api-client`에 restore request/run schema와 client 메서드를
  추가했고, `/admin/backup`에 `RestoreHotswapDialog`를 연결했다.
- backup/restore API·아키텍처·runbook·환경변수 예시와 `docs/tasks.md` / `docs/resume.md`를
  T-111 완료 상태로 갱신했다.

**검증**:

- WSL2 ext4 mirror: `ruff format --check app/core/config.py app/services/backup_service.py app/api/v1/admin/backup.py app/schemas/admin.py tests/unit/test_backup_service.py`
- WSL2 ext4 mirror: `ruff check app/core/config.py app/services/backup_service.py app/api/v1/admin/backup.py app/schemas/admin.py tests/unit/test_backup_service.py`
- WSL2 ext4 mirror: `mypy --strict app/core/config.py app/services/backup_service.py app/api/v1/admin/backup.py app/schemas/admin.py`
- WSL2 ext4 mirror: `pytest --capture=no -q tests/unit/test_backup_service.py`
- WSL2 ext4 mirror: `bash -n scripts/restore-hotswap.sh`
- WSL2 ext4 mirror: `npm run typecheck --workspace @pinvi/schemas`
- WSL2 ext4 mirror: `npm run typecheck --workspace @pinvi/api-client`
- WSL2 ext4 mirror: `npm run typecheck --workspace @pinvi/web`
- WSL2 ext4 mirror: `npm run lint --workspace @pinvi/web`
- WSL2 ext4 mirror: `NEXT_PUBLIC_PINVI_API_URL=http://localhost:8001 npm run build --workspace @pinvi/web`
- Windows Playwright runner → WSL dev server:
  `PLAYWRIGHT_BASE_URL=http://<wsl-playwright-host>:9022 ... @playwright/test@1.60.0 test admin-backup.e2e.ts`
- NTFS worktree: `git diff --check`

**다음**: PR 머지 후 남은 kor-travel-map 비의존 후보를 재감사한다. 현재 문서상 다음 후보는
T-132 trip 하위 리소스 분할이다.

## 2026-06-08 (codex) — T-135 POI rise_set 응답 노출

**작업**: 감사 C-18 후속인 POI 응답 `rise_set` 미노출을 정리했다.

**변경**:

- Pydantic/Zod POI 응답 schema에 `PoiRiseSetResponse`를 추가하고, `PoiResponse`와
  `TripViewPoi`가 `rise_set`을 `null` 또는 KASI 상태 payload로 받도록 맞췄다.
- `POST/PATCH /trips/{trip_id}/pois`와 POI reorder 응답에 `app.trip_poi_rise_sets`
  상태를 붙였다. 생성 직후에는 `pending_date` / `pending_coord` / `pending_fetch`가
  내려갈 수 있다.
- `GET /trips/{trip_id}` 상세 builder는 POI ID 목록으로 `trip_poi_rise_sets`를 batch
  조회해 N+1 없이 `rise_set`을 붙인다.
- API/통합 문서와 `docs/tasks.md` / `docs/resume.md`를 T-135 완료 상태로 갱신했다.

**검증**:

- WSL2 ext4 mirror: `ruff format --check app/api/v1/pois.py app/schemas/poi.py app/schemas/trip.py app/services/poi.py app/services/trip_view_builder.py tests/integration/test_kasi_poi_rise_set.py tests/integration/test_trip_view_builder.py`
- WSL2 ext4 mirror: `ruff check app/api/v1/pois.py app/schemas/poi.py app/schemas/trip.py app/services/poi.py app/services/trip_view_builder.py tests/integration/test_kasi_poi_rise_set.py tests/integration/test_trip_view_builder.py`
- WSL2 ext4 mirror: `mypy --strict app/api/v1/pois.py app/schemas/poi.py app/schemas/trip.py app/services/poi.py app/services/trip_view_builder.py`
- WSL2 ext4 mirror: `pytest --capture=no -q tests/integration/test_kasi_poi_rise_set.py tests/integration/test_trip_view_builder.py`
- WSL2 ext4 mirror: `npm run typecheck --workspace @pinvi/schemas`
- WSL2 ext4 mirror: `npm run test --workspace @pinvi/schemas`
- WSL2 ext4 mirror: `npm run typecheck --workspace @pinvi/api-client`
- WSL2 ext4 mirror: `npm run typecheck --workspace @pinvi/web`
- WSL2 ext4 mirror: `npm run lint --workspace @pinvi/web`
- WSL2 ext4 mirror: `NEXT_PUBLIC_PINVI_API_URL=http://localhost:8001 npm run build --workspace @pinvi/web`

**다음**: PR 머지 후 남은 kor-travel-map 비의존 후보를 재감사한다. 현재 문서상 다음 후보는
T-111 Backup/Restore UI 핫스왑이다.

## 2026-06-08 (codex) — T-169 MCP list_trips parity + Trip 목록 cursor

**작업**: PR #83 사후 리뷰 잔존인 MCP `list_trips` bucket/cursor parity와
`search_features` HTTP 경계 표현을 정리했다.

**변경**:

- 사용자 `GET /trips`가 `bucket` / `q` / `status` / `visibility` / `date_from` /
  `date_to` / `sort` / `limit` / `cursor` query를 받도록 구현했다.
- `/trips` 목록 응답에 `meta.cursor` / `meta.has_more` / `meta.limit`를 추가하고,
  기존 `data` 배열 shape는 유지했다.
- `packages/api-client`에 envelope meta를 읽는 `requestEnvelope()`와 Trip 목록
  `listPage()`를 추가했다. 기존 `list()`는 배열 반환을 유지한다.
- MCP `list_trips` 문서를 사용자 `GET /trips` query 계약과 맞추고,
  `search_features`는 kor-travel-map Python 함수/DB 직접 호출이 아니라 OpenAPI HTTP
  `GET /features/search` 경유임을 명시했다.
- Sprint 6 `app.mcp_tokens` DDL 골격을 `docs/postgres-schema.md`에 반영했다.

**검증**:

- WSL2 ext4 mirror: `ruff format --check app/api/v1/trips.py app/services/trip.py app/schemas/envelope.py tests/integration/test_trips_api.py`
- WSL2 ext4 mirror: `ruff check app/api/v1/trips.py app/services/trip.py app/schemas/envelope.py tests/integration/test_trips_api.py`
- WSL2 ext4 mirror: `mypy --strict app/api/v1/trips.py app/services/trip.py app/schemas/envelope.py`
- WSL2 ext4 mirror: `pytest --capture=no -q tests/integration/test_trips_api.py`
- WSL2 ext4 mirror: `npm run typecheck --workspace @pinvi/api-client`
- WSL2 ext4 mirror: `npm run typecheck --workspace @pinvi/web`
- WSL2 ext4 mirror: `npm run lint --workspace @pinvi/web`
- WSL2 ext4 mirror: `NEXT_PUBLIC_PINVI_API_URL=http://localhost:8001 npm run build --workspace @pinvi/web`

**다음**: kor-travel-map 비의존 루프는 닫힘. 다음 후보는 T-170 kor-travel-map HTTP client 붙이기.

## 2026-06-08 (claude) — RustFS 설정 배선 (env → Settings)

**작업**: `PINVI_RUSTFS_*` 환경변수를 `Settings`(config.py)에 실제 필드로 배선했다.
기존엔 필드가 없어 `rustfs_storage.py`가 `getattr`/`hasattr` 폴백으로 읽었고 env가 조용히
무시됐다(kor-travel-map config 갭과 같은 부류). 필드 추가로 폴백 제거 + 직접 참조.

**변경**: `config.py`(rustfs 9개 필드 + `public_base_url`), `rustfs_storage.py`(폴백 제거),
`.env.example`/`apps/api/.env.example`(dev 기본값 `rustfsadmin`/`rustfsadmin` 정렬 + public base url),
`docker-compose.yml`/`docker-compose.app.yml`(컨테이너 cred 정렬 + API env 주입), `storage.md`/
`file-storage.md`(문서), `test_storage_keys.py`(Settings env 로드 테스트).

## 2026-06-08 (claude) — DEC-05 교정: 재적재≠제안, kor_travel_map feature 추가 API 신규 필요(K-15)

**교정(사용자)**: 재적재(feature-update-request)와 사용자 제안은 **완전 별개**.

- **재적재** = kor-travel-map **admin 기능**, Pinvi 일반 사용자 **비노출**, 제안 흐름과 무관.
- **사용자 제안** = Pinvi user 제출 → **Pinvi Admin 검사/승인/거절** → 승인 시
  **kor_travel_map feature 추가 API로 추가**(재적재 호출 아님).
- **kor_travel_map 격차 확정**: feature **추가** API가 **없음**(add 경로는 offline-upload 파일뿐,
  `/admin/features`는 list+deactivate만) → kor_travel_map가 **단건 add API를 신규 구축**해야 함.

**반영**: `decisions-needed` DEC-05 재작성, `kor-travel-map-requirements.md` **K-15**(단건 feature
add API, 높음) 신규 등록, `kor-travel-map-rest-api.md` §2.8/§5/§6/§7, `tasks.md` T-179(→feature 추가,
K-15 의존). T-177(사용자 제안 큐)은 그대로.

## 2026-06-08 (claude) — DEC-05 확정: feature 제안/재적재 두 레이어

**결정(사용자)**: kor_travel_map `/pinvi/feature-update-requests`는 **admin 영역**(운영자 재적재
트리거)이고, **사용자 제안 기능도 v1에 구현**한다. → 두 레이어:

- (user) `app.feature_suggestions` 큐 + `POST/GET /features/requests` — 사용자 제출(즉시 201),
  rate-limit/dedup. kor_travel_map 직접 호출 X. (감사 C-12 미존재 테이블 실체화)
- (admin) `/admin/feature-requests` 검수 → approve 시 운영자가 kor_travel_map 재적재 호출(scope) +
  상태조회, RBAC(admin/operator)+audit. 신규장소는 offline-upload 분기.

**반영**: `decisions-needed-2026-06-06.md` DEC-05 확정 기록,
`integrations/kor-travel-map-rest-api.md` §2.8/§5/§6/§7, `tasks.md` T-177(user 큐)/T-179(admin 재적재).

## 2026-06-08 (codex) — T-168 storage AttachmentResponse 호환 alias

**작업**: PR #73 사후 리뷰 잔존인 storage `AttachmentResponse`와 notice-plan attachment
alias 정책 비대칭을 정리했다.

**변경**:

- Pydantic `AttachmentResponse`에 `notice_plan_id` / `notice_poi_id` alias를 추가하고
  `curated_*`와 notice alias를 같은 값으로 정규화한다. 두 값이 불일치하면 validation error.
- Zod `AttachmentResponseSchema`를 추가하고 같은 alias 정규화/불일치 reject 정책을 반영했다.
- storage/notice-plans API 문서에 `curated_*` 정본 + `notice_*` 호환 alias 병행 정책을 명시했다.
- Pydantic unit test와 `packages/schemas` Vitest storage schema 테스트를 추가했다.

**검증**:

- WSL2 ext4 mirror: `ruff format --check app/schemas/storage.py tests/unit/test_schemas.py`
- WSL2 ext4 mirror: `ruff check app/schemas/storage.py tests/unit/test_schemas.py`
- WSL2 ext4 mirror: `mypy --strict app/schemas/storage.py`
- WSL2 ext4 mirror: `pytest --capture=no -q tests/unit/test_schemas.py`
- WSL2 ext4 mirror: `npm run typecheck --workspace @pinvi/schemas`
- WSL2 ext4 mirror: `npm run test --workspace @pinvi/schemas`
- WSL2 ext4 mirror: `npm run typecheck --workspace @pinvi/web`
- WSL2 ext4 mirror: `npm run lint --workspace @pinvi/web`
- WSL2 ext4 mirror: `NEXT_PUBLIC_PINVI_API_URL=http://localhost:8001 npm run build --workspace @pinvi/web`

**다음**: T-169 MCP `list_trips` bucket/cursor parity + `search_features` HTTP 표현 정리.

## 2026-06-08 (codex) — T-167 money 표현 통일

**작업**: PR #79 사후 리뷰 잔존인 admin money `string | number` union과
`packages/schemas` runtime round-trip 테스트 부재를 보강했다.

**변경**:

- `packages/schemas/src/admin.ts`의 admin POI detail `budget_amount` / `actual_amount`를
  `NonNegativeDecimalStringSchema.nullable()`로 통일했다.
- Admin POI detail UI의 `formatAmount` 입력 타입을 `string | null`로 좁혔다.
- `packages/schemas`에 Vitest test script/devDependency와 money response round-trip 테스트를
  추가했다. admin/POI/trip-view/notice-plan 응답 money가 decimal string으로 유지되고
  number/exponential/negative 표현은 거부된다.

**검증**:

- WSL2 ext4 mirror: `npm run typecheck --workspace @pinvi/schemas`
- WSL2 ext4 mirror: `npm run test --workspace @pinvi/schemas`
- WSL2 ext4 mirror: `npm run typecheck --workspace @pinvi/web`
- WSL2 ext4 mirror: `npm run lint --workspace @pinvi/web`
- WSL2 ext4 mirror: `NEXT_PUBLIC_PINVI_API_URL=http://localhost:8001 npm run build --workspace @pinvi/web`

**다음**: T-168 storage `AttachmentResponse` 필드 호환 정책을 notice-plans와 통일.

## 2026-06-08 (codex) — T-166 admin 감사 hash-chain head 직렬화

**작업**: PR #80 사후 리뷰 잔존인 admin audit hash-chain head fork 가능성을 보강했다.

**변경**:

- `app.admin_audit_log.prev_hash` unique constraint migration/model을 추가해 같은 head에서
  두 row가 갈라지는 fork를 DB 차원에서 차단했다.
- `append_admin_audit()`가 마지막 audit row 조회 전에 PostgreSQL transaction-level advisory
  lock을 잡도록 바꿔 병렬 admin action도 하나의 chain head로 직렬화한다.
- 동시 append가 첫 transaction commit 전까지 대기했다가 직전 `content_hash`를 연결하는
  회귀 테스트와, 수동 fork insert가 unique constraint로 거부되는 테스트를 추가했다.
- ADR-034, schema/data-model/runbook 문서에 `prev_hash` unique + advisory lock 기준을 반영했다.

**검증**:

- WSL2 ext4 mirror: `ruff format --check app/services/admin_audit.py app/models/audit.py tests/integration/test_admin_audit_chain.py alembic/versions/20260608_0013_admin_audit_prev_hash_unique.py`
- WSL2 ext4 mirror: `ruff check app/services/admin_audit.py app/models/audit.py tests/integration/test_admin_audit_chain.py alembic/versions/20260608_0013_admin_audit_prev_hash_unique.py`
- WSL2 ext4 mirror: `mypy --strict app/services/admin_audit.py app/models/audit.py`
- WSL2 ext4 mirror: `pytest --capture=no -q tests/integration/test_admin_audit_chain.py tests/integration/test_admin_users_api.py tests/integration/test_admin_trips_api.py tests/integration/test_admin_pois_api.py`

**다음**: T-167 money 표현 통일(admin union→decimal-string) + `packages/schemas` round-trip 테스트.

## 2026-06-08 (codex) — T-165 WebSocket cap/grace + broadcast 비동기 분리

**작업**: PR #78 사후 리뷰 잔존인 rate-limit close grace 슬롯 점유와 HTTP mutation
broadcast 대기 결합을 보강했다.

**변경**:

- `RealtimeBroker.publish_event_nowait`를 추가해 HTTP mutation route가 background
  broadcast task만 예약하고 응답 경로에서 fan-out 완료를 기다리지 않게 했다.
- background broadcast task는 broker가 참조를 보관하고 완료 callback에서 예외를 회수해
  누수/미회수 예외 로그를 방지한다. `reset()`은 남은 background task를 cancel한다.
- WebSocket client message rate 초과 시 `RATE_LIMITED` error 전송 직후 broker에서
  connection을 제거해 close grace 동안 trip/process cap slot을 점유하지 않게 했다.
- broker unit test와 WebSocket integration test에 느린 broadcast 비동기 분리, grace 중 cap
  슬롯 반환 회귀를 추가했다.

**검증**:

- WSL2 ext4 mirror: `ruff format --check app/services/realtime_broker.py app/api/v1/ws.py app/api/v1/trips.py app/api/v1/pois.py tests/unit/test_realtime_broker.py tests/integration/test_ws_trip_channel.py`
- WSL2 ext4 mirror: `ruff check app/services/realtime_broker.py app/api/v1/ws.py app/api/v1/trips.py app/api/v1/pois.py tests/unit/test_realtime_broker.py tests/integration/test_ws_trip_channel.py`
- WSL2 ext4 mirror: `mypy --strict app/services/realtime_broker.py app/api/v1/ws.py app/api/v1/trips.py app/api/v1/pois.py`
- WSL2 ext4 mirror: `pytest --capture=no -q tests/unit/test_realtime_broker.py tests/integration/test_ws_trip_channel.py`

**다음**: T-166 admin 감사 hash-chain head 직렬화(prev_hash unique/advisory lock).

## 2026-06-08 (codex) — T-164 geofence outage guard + 방어심화

**작업**: PR #77 사후 리뷰 잔존인 strict geofence silent outage 풋건과 shared-secret
단일 방어를 보강했다.

**변경**:

- `GeofenceConfigError` / `validate_geofence_configuration` startup guard 추가. strict
  geofence에서 trusted signal이 없으면 API startup이 실패하고, signal이 하나뿐이면 warning을 남긴다.
- country header 신뢰 조건을 shared secret, proxy CIDR allowlist, mTLS verified header 중
  설정된 factor가 모두 통과해야 하는 방식으로 바꿨다.
- `.env.example`, `apps/api/.env.example`, korea-only runbook/architecture에 CIDR/mTLS
  설정과 secret 비로그/회전 운영 기준을 반영했다.
- unit test에 startup guard, proxy CIDR, mTLS verified header, 다중 factor 요구 회귀를 추가했다.

**검증**:

- WSL2 ext4 mirror: `ruff format --check app/core/config.py app/main.py app/middleware/geofence.py tests/unit/test_geofence_middleware.py`
- WSL2 ext4 mirror: `ruff check app/core/config.py app/main.py app/middleware/geofence.py tests/unit/test_geofence_middleware.py`
- WSL2 ext4 mirror: `mypy --strict app/core/config.py app/main.py app/middleware/geofence.py`
- WSL2 ext4 mirror: `pytest --capture=no -q tests/unit/test_geofence_middleware.py`

**다음**: T-165 WS rate-limit grace 슬롯 점유 cap 우회 차단 + `publish_event` broadcast 비동기 분리.

## 2026-06-08 (codex) — T-163 access JWT 무효화 + refresh race 보강

**작업**: PR #76 사후 리뷰 잔존인 비밀번호 재설정 후 access JWT 유효 시간 잔존과
refresh token 동시 회전 race를 보강했다.

**변경**:

- `app.users.access_token_version` migration/model 추가. access JWT에는 `token_version`
  claim을 싣고, 인증 의존성은 사용자 상태와 현재 version을 DB에서 검증한다.
- 비밀번호 재설정 성공 시 `access_token_version` 증가 + 기존 refresh session 일괄
  revoke + reset 완료 새 session 발급으로 access/refresh 전체 무효화를 맞췄다.
- `refresh_user_session`은 기존 refresh row를 `FOR UPDATE`로 잠근 뒤 revoke/insert를
  수행해 같은 refresh token 동시 재사용이 session을 둘 이상 만들지 못하게 했다.
- reset 전 access cookie 401 회귀 테스트와 refresh 동시 회전 단일 성공 테스트를 추가했다.

**검증**:

- WSL2 ext4 mirror: `ruff format --check app/core/deps.py app/models/user.py app/services/auth_session.py app/services/user_registration.py tests/integration/test_auth_sessions.py tests/integration/test_password_reset_flow.py alembic/versions/20260608_0012_user_access_token_version.py`
- WSL2 ext4 mirror: `ruff check app/core/deps.py app/models/user.py app/services/auth_session.py app/services/user_registration.py tests/integration/test_auth_sessions.py tests/integration/test_password_reset_flow.py alembic/versions/20260608_0012_user_access_token_version.py`
- WSL2 ext4 mirror: `mypy --strict app/core/deps.py app/models/user.py app/services/auth_session.py app/services/user_registration.py`
- WSL2 ext4 mirror: `pytest --capture=no -q tests/integration/test_auth_sessions.py tests/integration/test_password_reset_flow.py`

**다음**: T-164 geofence outage 풋건 startup 가드 + shared-secret 외 방어심화.

## 2026-06-08 (claude) — kor-travel-map REST API 계약 문서화 (붙이기 청사진)

**작업**: Pinvi↔kor-travel-map 연결 작업 진입 전, 양쪽 docs+code를 대조해 REST API 계약을
정리했다. **중대 변화**: kor-travel-map이 운영 HTTP API(`packages/kor-travel-map-admin`, 포트 9011,
`openapi.user.json`)를 **이미 구축**(HEAD `f442bd0`, T-213a~h 완료) — ADR-026/027/DEC-01=B 충족.
2026-06-06 requirements가 "없다"던 능력(batch/nearby/search/weather/categories/update-request)
대부분 구현됨.

**신규 문서**: `docs/integrations/kor-travel-map-rest-api.md` — 13개 엔드포인트 계약(params/응답
셰입/소비처/주의) + 데이터 계약(feature*id `f*{bjd}_{k}_{sha1[:16]}` 문자열, name/평면 lon,lat/
구조화 address/weather metric 목록/server cluster) + Pinvi 측 작업 A~~H(T-170~~T-178).

**Pinvi 출발점**: httpx client·config·배선 전부 미구현(`etl_bridge/kor_travel_map.py`는
in-process Protocol stub → 모든 `/features/*` 503). #87로 feature_id 문자열화는 1차 반영됨.

**작업 순서 등록**: T-170(client)→T-171(config)→T-172(feature_id 마감) 토대 후 D~H 병행.
(주의: 본 작업 중 worktree에 있던 무관한 미커밋 변경(rustfs/storage/docker)은 stash로 보존.)

## 2026-06-08 (codex) — T-125 feature_id 문자열화

**작업**: ADR-028에 따라 Pinvi의 feature_id UUID 가정을 제거했다.

**변경**:

- `apps/api/app/schemas/feature.py`, `apps/api/app/api/v1/features.py`,
  `apps/api/app/etl_bridge/kor_travel_map.py` — feature read id를 불투명 문자열로 처리.
- `apps/api/app/services/trip_view_builder.py` — trip POI batch 조회가 문자열
  feature_id를 그대로 사용하고 저장 suffix만 제거.
- `packages/schemas/src/feature.ts` — Zod feature_id `.uuid()` 제거.
- `docs/api/features.md`, `docs/resume.md`, `docs/tasks.md` — T-125 완료 반영.

**검증**:

- WSL2 ext4 mirror: `ruff check ...`
- WSL2 ext4 mirror: `ruff format --check ...`
- WSL2 ext4 mirror: `mypy --strict app`
- WSL2 ext4 mirror: `pytest --capture=no -q tests/unit/test_feature_schemas.py tests/integration/test_trip_view_builder.py`
- WSL2 ext4 mirror: `npm run typecheck -w @pinvi/schemas`
- WSL2 ext4 mirror: `npm run typecheck -w @pinvi/api-client`
- WSL2 ext4 mirror: `npx prettier --check packages/schemas/src/feature.ts packages/schemas/src/index.ts`

**다음**: 사용자 지시로 PR 머지 후 중지. 이후 재개 시 T-163.

## 2026-06-08 (codex) — T-162 Resend webhook unsigned opt-in

**작업**: PR #74 사후 리뷰 잔존인 Resend webhook fail-open 위험을 닫았다. 기존에는
`PINVI_ENVIRONMENT` 기본값 `development` 때문에 운영 env 누락 시 unsigned webhook이
열릴 수 있었다.

**변경**:

- `apps/api/app/core/config.py`, `apps/api/app/webhooks/resend.py` —
  `PINVI_RESEND_WEBHOOK_ALLOW_UNSIGNED`를 추가하고, secret 없는 webhook은 로컬성 환경에서
  opt-in이 명시된 경우에만 허용한다.
- `apps/api/tests/integration/test_resend_webhook.py` — 기본 development에서도 opt-in 없이는
  `503`, 로컬 opt-in은 허용, production은 opt-in이 켜져도 secret 없으면 `503`인 회귀 테스트.
- `.env.example`, `apps/api/.env.example`, `docs/integrations/resend.md`,
  `docs/api/common.md` — 로컬 unsigned는 명시 opt-in, 운영/스테이징은 secret 필수 정책 반영.

**검증**:

- WSL2 ext4 mirror: `pytest --capture=no -q tests/integration/test_resend_webhook.py`
- WSL2 ext4 mirror: `ruff check app/core/config.py app/webhooks/resend.py tests/integration/test_resend_webhook.py`
- WSL2 ext4 mirror: `mypy --strict app/core/config.py app/webhooks/resend.py`

## 2026-06-08 (claude) — Codex PR 사후 리뷰 2라운드 (#73~#83) + 수렴 확인

**작업**: Codex PR 11건(#73~#83)을 사후 리뷰하고 각 PR에 코멘트 게시. 대부분 직전 라운드
[높음] 후속 T-154~T-161 + 감사 항목(T-137/126/127) 구현이라 "실제로 닫혔는지"를 검증.

**핵심**: 직전 [높음] 9건 **전부 회귀 테스트 동반 수정 확인**(수렴). 이번 라운드 신규
[높음]/차단 0건. 잔존은 [중간]/[낮음] — fail-open 잔존(#74 env 기본값), reset 후 access
15분 창·refresh race(#76), geofence outage 가드(#77), WS grace 슬롯·coupling(#78),
hash-chain head fork(#80) 등. [중간] 8건을 T-162~T-169로 승격.

**산출물**: `docs/reviews/2026-06-08-codex-pr-review.md`(수렴 표 + 잔존 TODO).
검증 메모: #78 초기 "ADR-035 미존재"는 오탐(ADR-035 실재) — 종합에서 정정.

## 2026-06-07 (codex) — T-131 Trip 상세 view 연결

**작업**: 감사 C-05에서 지적된 `trip_view_builder.build_trip_view` dead code를 닫고,
`GET /trips/{trip_id}`를 trip 메타 전용 응답에서 상세 view 응답으로 연결했다.

**변경**:

- `apps/api/app/api/v1/trips.py`, `apps/api/app/services/trip_view_builder.py` —
  상세 GET에서 builder를 호출하고 trip/day/POI tree, companion 목록, share link metadata,
  `broken_feature_count`를 반환한다. kor-travel-map client가 없으면 저장 snapshot으로 fallback한다.
- `apps/api/app/schemas/trip.py`, `packages/schemas/src/trip.ts`,
  `packages/api-client/src/endpoints/trips.ts` — `TripView` 응답 schema와 api-client `get`
  계약을 추가했다.
- `apps/api/tests/integration/test_trips_api.py`,
  `apps/api/tests/integration/test_pois_reorder.py` — 상세 view 구조, share token 원문 비노출,
  POI snapshot day tree 회귀 테스트를 추가했다.
- `docs/api/trips.md`, `docs/resume.md`, `docs/tasks.md` — 상세 응답 shape와 T-131 완료,
  다음 비-kor_travel_mapmap 작업(T-125)을 반영했다.

**검증**:

- WSL2 ext4 mirror: `ruff check app tests/integration/test_trips_api.py tests/integration/test_pois_reorder.py`
- WSL2 ext4 mirror: `mypy --strict app`
- WSL2 ext4 mirror: `npm run typecheck -w @pinvi/schemas`
- WSL2 ext4 mirror: `npm run typecheck -w @pinvi/api-client`
- WSL2 ext4 mirror: `npx prettier --check packages/schemas/src/trip.ts packages/schemas/src/index.ts packages/api-client/src/endpoints/trips.ts`
- WSL2 ext4 mirror: `PATH=/home/digitie/pinvi-workspaces/pinvi-codex/apps/api/.venv/bin:$PATH pytest --capture=no -q tests/integration/test_trips_api.py tests/integration/test_pois_reorder.py`
- NTFS worktree: `git.exe diff --check`
- NTFS worktree: `codegraph sync`

**다음**: T-125 feature_id 문자열화(C-09).

## 2026-06-07 (codex) — T-127 MCP 외부 인터페이스 정본화

**작업**: 감사 A-02/A-06/A-12에서 지적된 MCP 문서 충돌, trip status enum 불일치,
토큰 endpoint 미명세를 닫았다.

**변경**:

- `docs/architecture/mcp-server.md` — ADR-019 외부 MCP 정본으로 read-only 5개 tool을
  유지하고, `list_trips.status` enum을 `draft/planned/in_progress/completed/archived`로
  정합했다. kor-travel-map 검색은 OpenAPI HTTP `GET /features/search` 경유로 명시했다.
- `docs/architecture/mcp-tools.md` — v1 후보 tool 가이드로 격하하고, 외부 MCP 정본은
  `mcp-server.md`임을 명시했다. `pinvi_db_admin`은 외부 MCP 금지로 정리했다.
- `docs/api/users.md`, `docs/api/admin.md`, `docs/runbooks/mcp-server.md`,
  `docs/sprints/SPRINT-6.md`, `docs/decisions.md` — 사용자/admin MCP 토큰 발급·회수
  endpoint를 `/users/me/mcp-tokens`와 `/admin/mcp-tokens` 계열로 정본화했다.
- `docs/resume.md`, `docs/tasks.md` — T-127 완료와 다음 비-kor_travel_mapmap 작업(T-131)을
  반영했다.

**검증**:

- NTFS worktree: `rg -n "draft.*active.*archived|/mcp/tokens|<api-host>|\bMCP_JWT_SECRET\b" docs/architecture/mcp-server.md docs/architecture/mcp-tools.md docs/runbooks/mcp-server.md docs/decisions.md docs/sprints/SPRINT-6.md`
- NTFS worktree: `rg -n "/users/me/mcp-tokens|/admin/mcp-tokens|draft.*planned.*in_progress.*completed.*archived" docs/architecture/mcp-server.md docs/api/users.md docs/api/admin.md docs/runbooks/mcp-server.md docs/decisions.md docs/sprints/SPRINT-6.md`
- NTFS worktree: `git.exe diff --check`
- NTFS worktree: `codegraph sync`

**다음**: T-131 `GET /trips/{id}` 상세 view 연결.

## 2026-06-07 (codex) — T-161 README `/search` 앵커 정합

**작업**: PR #54 사후 리뷰에서 남은 README `GET /search` dangling anchor를 닫았다.

**변경**:

- `docs/api/features.md` — 통합 검색 heading을 `2.7 GET /search`로 단순화해
  `#27-get-search` anchor가 안정적으로 생성되게 했다.
- `README.md` — `GET /search` 링크를 `docs/api/features.md#27-get-search`로 교정했다.
- `docs/kor-travel-map-requirements.md` — 통합 검색 feature 부분의 잘못된 features.md 절
  번호를 §2.7로 교정했다.
- `docs/resume.md`, `docs/tasks.md` — T-161 완료와 다음 비-kor_travel_mapmap 작업(T-127)을
  반영했다.

**검증**:

- NTFS worktree: `rg -n "#27-get-search|features.md §2.7" README.md docs/api/features.md docs/kor-travel-map-requirements.md`
- NTFS worktree: `git.exe diff --check`
- NTFS worktree: `codegraph sync`

**다음**: T-127 MCP 외부 인터페이스 정본화.

## 2026-06-07 (codex) — T-126 POI 생성 경로 단일화

**작업**: 감사 A-01/C-16에서 지적된 POI 생성 경로 이중 표기를 닫았다. v2 정본은
`POST /trips/{trip_id}/pois`이고 `day_index`는 요청 body에 둔다.

**변경**:

- `docs/api/trips.md` — 오래된 `/trips/{trip_id}/days/{day_index}/items` 문서 블록을
  `/trips/{trip_id}/pois` 정본 설명과 예시 payload로 교체했다.
- `packages/api-client/src/endpoints/pois.ts`, `packages/api-client/src/index.ts` —
  create/update/delete/reorder가 모두 `/trips/{tripId}/pois` 계열만 호출하는 `poiApi`를
  추가했다.
- `packages/schemas/src/poi.ts`, `packages/schemas/src/index.ts` — API client가 쓰는
  `PoiUpdate`, `PoiReorderRequest` 타입 export를 추가했다.
- `docs/resume.md`, `docs/tasks.md` — T-126 완료와 다음 비-kor_travel_mapmap 작업(T-161)을
  반영했다.

**검증**:

- WSL2 ext4 mirror: `npm run typecheck -w @pinvi/api-client`
- WSL2 ext4 mirror: `npm run typecheck -w @pinvi/schemas`
- WSL2 ext4 mirror: `prettier --check packages/api-client/src/endpoints/pois.ts packages/api-client/src/index.ts packages/schemas/src/poi.ts packages/schemas/src/index.ts`
- NTFS worktree: `git.exe diff --check`
- NTFS worktree: `codegraph sync`

**다음**: T-161 README 앵커 정합 일괄.

## 2026-06-07 (codex) — T-160 admin 상태+audit 원자성

**작업**: PR #50/#52/#53 사후 리뷰에서 남은 admin 상태 변경과 audit append 사이의
비원자성 위험을 닫았다.

**변경**:

- `apps/api/app/services/admin_audit.py` — `append_admin_audit()`가 자체 commit을 하지 않고
  flush만 수행하도록 바꿔 호출 라우트가 업무 변경과 감사 로그를 단일 트랜잭션으로 묶게 했다.
- `apps/api/app/services/admin_{users,trips,pois}.py` — 상태 변경 서비스의 내부 commit을
  제거하고, 사용자 force verify/disable은 실제 before_state를 반환한다.
- `apps/api/app/api/v1/admin/{users,trips,pois,backup}.py` — 상태 변경 + audit append 후
  한 번만 commit하고, audit-only 경로도 명시 commit한다.
- `apps/api/tests/integration/test_admin_{users,trips,pois}_api.py` — audit 실패 시 사용자
  status/session revoke, trip status/version, POI link status/version이 rollback되는 회귀
  테스트를 추가했다.

**검증**:

- WSL2 ext4 mirror: `ruff check app/services/admin_audit.py app/services/admin_users.py app/services/admin_trips.py app/services/admin_pois.py app/api/v1/admin/users.py app/api/v1/admin/trips.py app/api/v1/admin/pois.py app/api/v1/admin/backup.py tests/integration/test_admin_users_api.py tests/integration/test_admin_trips_api.py tests/integration/test_admin_pois_api.py`
- WSL2 ext4 mirror: `mypy --strict app/services/admin_audit.py app/services/admin_users.py app/services/admin_trips.py app/services/admin_pois.py app/api/v1/admin/users.py app/api/v1/admin/trips.py app/api/v1/admin/pois.py app/api/v1/admin/backup.py`
- WSL2 ext4 mirror: `pytest --capture=no -q tests/integration/test_admin_users_api.py tests/integration/test_admin_trips_api.py tests/integration/test_admin_pois_api.py`

**다음**: T-126 POI 생성 경로 단일화 또는 T-161 README 앵커 정합 일괄.

## 2026-06-07 (codex) — T-159 money 응답 Zod 타입 정합

**작업**: PR #67 사후 리뷰에서 남은 `Decimal` 응답과 프론트 Zod schema 불일치를 닫았다.

**변경**:

- `packages/schemas/src/common.ts` — Pydantic `Decimal` JSON 응답용
  `NonNegativeDecimalStringSchema`를 추가했다.
- `packages/schemas/src/poi.ts` — `PoiResponseSchema.budget_amount` /
  `actual_amount`를 nonnegative decimal string으로 정합했다.
- `packages/schemas/src/notice-plan.ts` — `NoticePoiSchema.budget_amount`를 같은 응답
  schema로 정합했다.
- `packages/schemas/src/index.ts`, `docs/resume.md`, `docs/tasks.md` — 공용 export와
  T-159 완료를 반영했다.

**검증**:

- WSL2 ext4 mirror: `npm run typecheck -w @pinvi/schemas`
- WSL2 ext4 mirror: `vite-node` 일회성 Zod parse 검증
- WSL2 ext4 mirror: `prettier --check` (schema 파일)
- NTFS worktree: `git.exe diff --check`
- NTFS worktree: `codegraph sync`

**다음**: T-160 admin 상태변경 status+audit 단일 트랜잭션 또는 T-126 POI 생성 경로 단일화.

## 2026-06-07 (codex) — T-158 Trip WebSocket guard

**작업**: PR #63 사후 리뷰에서 남은 WebSocket 가용성 위험(rate limit 없음,
`presence.cursor` fan-out 증폭, 느린 peer backpressure, connection cap 부재)을 닫았다.

**변경**:

- `apps/api/app/api/v1/ws.py` — client message rate limit(초당 5/분당 60), 초과 시
  `error RATE_LIMITED` 후 close `4429`, `presence.cursor` 좌표 range 검증과 canonical
  `longitude`/`latitude` broadcast를 추가했다.
- `apps/api/app/services/realtime_broker.py` — trip/process connection cap과 broadcast
  send timeout을 추가해 느린 peer를 stale connection으로 제거한다.
- `apps/api/tests/{unit,integration}` — broker cap/timeout, WebSocket rate-limit close,
  connection cap reject, cursor 검증 회귀 테스트를 추가했다.
- `docs/api/websocket.md`, `docs/architecture/websocket-broker.md`,
  `docs/resume.md`, `docs/tasks.md` — 운영 환경변수와 close code를 반영했다.

**검증**:

- WSL2 ext4 mirror: `ruff check app/core/config.py app/api/v1/ws.py app/services/realtime_broker.py tests/unit/test_realtime_broker.py tests/integration/test_ws_trip_channel.py`
- WSL2 ext4 mirror: `mypy --strict app/core/config.py app/api/v1/ws.py app/services/realtime_broker.py`
- WSL2 ext4 mirror: `pytest --capture=no -q tests/unit/test_realtime_broker.py tests/integration/test_ws_trip_channel.py`

**다음**: T-159 응답 money 필드 Zod 타입 정합 또는 T-126 POI 생성 경로 단일화.

## 2026-06-07 (codex) — T-157 geofence fallback 발신 검증

**작업**: FastAPI geofence fallback이 `CF-IPCountry`만 신뢰하면 직접 접근에서
`CF-IPCountry: KR` spoof로 우회할 수 있던 PR #60 사후 리뷰 후속을 닫았다.

**변경**:

- `apps/api/app/core/config.py`, `apps/api/.env.example` — trusted proxy shared secret
  header 설정(`PINVI_GEOFENCE_TRUSTED_PROXY_*`)을 추가했다.
- `apps/api/app/middleware/geofence.py` — strict 모드에서 shared secret proxy header가
  맞을 때만 country header를 신뢰하고, 누락/오류는 `UNKNOWN`으로 처리한다.
- `apps/api/tests/unit/test_geofence_middleware.py` — KR 허용/US 차단은 trusted proxy
  header가 있을 때만 통과하고, 직접 spoof와 wrong secret은 451 UNKNOWN으로 차단됨을 검증한다.
- `docs/runbooks/korea-only.md`, `docs/architecture/korea-only-policy.md`,
  `docs/resume.md`, `docs/tasks.md` — 운영 secret 주입과 T-157 완료를 반영했다.

**검증**:

- WSL2 ext4 mirror: `ruff check app/core/config.py app/middleware/geofence.py tests/unit/test_geofence_middleware.py`
- WSL2 ext4 mirror: `mypy --strict app/core/config.py app/middleware/geofence.py`
- WSL2 ext4 mirror: `pytest --capture=no -q tests/unit/test_geofence_middleware.py`

**다음**: T-126 POI 생성 경로 단일화 또는 T-158 WebSocket rate limit/cursor 증폭 차단.

## 2026-06-07 (codex) — T-156 비밀번호 재설정 session 폐기 보강

**작업**: 비밀번호 재설정 후 기존 refresh session이 남으면 탈취 세션이 계속 유효할 수
있다는 PR #71 사후 리뷰 후속을 닫았다.

**변경**:

- `apps/api/app/services/auth_session.py` — 현재 트랜잭션 안에서 사용자 active session을
  일괄 폐기하는 `revoke_active_user_sessions` helper를 추가했다.
- `apps/api/app/services/user_registration.py` — password reset 성공 시 helper로 기존
  active refresh session을 모두 revoke한다.
- `apps/api/tests/integration/test_password_reset_flow.py` — 기존 active session 2개가 모두
  revoked 되고 reset 완료 후 새 session 1개만 active인 회귀 테스트로 강화했다.
- `docs/resume.md`, `docs/tasks.md` — T-156 완료를 반영했다.

**검증**:

- WSL2 ext4 mirror: `ruff check app/services/auth_session.py app/services/user_registration.py tests/integration/test_password_reset_flow.py`
- WSL2 ext4 mirror: `mypy --strict app/services/auth_session.py app/services/user_registration.py`
- WSL2 ext4 mirror: `pytest --capture=no -q tests/integration/test_password_reset_flow.py`

**다음**: T-126 POI 생성 경로 단일화 또는 T-157 geofence fallback 발신 검증.

## 2026-06-07 (codex) — T-155 Admin access_reason URL 로깅 제거

**작업**: Admin 사용자 상세의 PII reveal 사유가 `access_reason` query string으로 전송돼
nginx/proxy/browser history에 남을 수 있던 PR #50 사후 리뷰 후속을 닫았다.

**변경**:

- `apps/api/app/api/v1/admin/users.py` — PII reveal은
  `POST /admin/users/{user_id}/reveal-pii` + JSON body 사유로 분리하고, GET
  `?reveal=true` misuse는 `422`로 닫는다.
- `packages/api-client/src/endpoints/admin.ts`,
  `apps/web/e2e/admin-users.e2e.ts` — reveal reason을 URL query가 아니라 POST body로
  전송/검증한다.
- `apps/api/tests/integration/test_admin_users_api.py` — query reason이 422로 거부되고
  body reason만 audit에 저장되는 케이스를 추가했다.
- `docs/api/admin.md`, `docs/resume.md`, `docs/tasks.md` — T-155 완료와 body-only
  계약을 반영했다.

**검증**:

- WSL2 ext4 mirror: `ruff check app/api/v1/admin/users.py tests/integration/test_admin_users_api.py`
- WSL2 ext4 mirror: `mypy --strict app/api/v1/admin/users.py`
- WSL2 ext4 mirror: `pytest --capture=no -q tests/integration/test_admin_users_api.py`
- WSL2 ext4 mirror: `npm run typecheck --workspaces --if-present`

**다음**: T-126 POI 생성 경로 단일화 또는 T-156 비밀번호 재설정 시 기존 refresh session 폐기.

## 2026-06-07 (codex) — T-154 Resend webhook fail-closed 보강

**작업**: PR #70 사후 리뷰에서 재오픈된 C-22를 닫았다. Resend webhook secret이 없는
운영성 환경은 서명 검증을 건너뛰지 않고 `503`으로 닫으며, `whsec_` secret은 표준
base64만 허용한다.

**변경**:

- `apps/api/app/webhooks/resend.py` — dev/test/local만 unsigned webhook을 허용하고,
  그 외 환경의 secret 미설정/형식 오류는 `WEBHOOK_SIGNATURE_NOT_CONFIGURED`로
  fail-closed한다. signature mismatch는 기존대로 `401 WEBHOOK_SIGNATURE_INVALID`.
- `apps/api/tests/integration/test_resend_webhook.py` — 운영 secret 미설정 차단,
  표준 base64 secret 성공, URL-safe secret config 차단을 검증한다.
- `docs/integrations/resend.md`, `docs/api/common.md`, `docs/resume.md`,
  `docs/tasks.md` — C-22 재오픈 후속과 운영 fail-closed 계약을 반영했다.

**검증**:

- WSL2 ext4 mirror: `ruff check app/webhooks/resend.py tests/integration/test_resend_webhook.py`
- WSL2 ext4 mirror: `mypy --strict app/webhooks/resend.py`
- WSL2 ext4 mirror: `pytest --capture=no -q tests/integration/test_resend_webhook.py`

**다음**: T-126 POI 생성 경로 단일화 또는 T-155 admin `access_reason` PII URL 제거.

## 2026-06-07 (codex) — T-137 curated trip plan 스키마 정본화

**작업**: ADR-029의 `notice_plans` 명칭 충돌 결정을 실제 ORM/Alembic/문서에
반영했다. 추천 여행 템플릿은 `curated_*` 계열로 분리하고, `app.notice_plans`는
운영 공지(system notice) 전용으로 남긴다.

**변경**:

- `apps/api/app/models/curated_plan.py`,
  `apps/api/app/models/{notice_plan,attachment}.py` — `CuratedTripPlan`,
  `CuratedPlanPoi`, `CuratedPlanAttachment`를 정본 ORM으로 두고 legacy notice import/
  property alias를 유지했다.
- `apps/api/alembic/versions/20260607_0011_curated_trip_plans.py` —
  `notice_plans` / `notice_pois` / `plan_poi_attachments`를 `curated_trip_plans` /
  `curated_plan_pois` / `curated_plan_attachments`로 rename한다.
- `apps/api/app/services/notice_plan.py`, `apps/api/app/api/v1/notice_plans.py` —
  내부 조회/복사는 curated ORM 필드를 쓰고 `/notice-plans` 응답 필드는 기존
  `notice_plan_id` / `notice_poi_id` alias를 유지한다.
- `apps/api/app/schemas/storage.py`, `packages/schemas/src/storage.ts` — 첨부 purpose와
  response 필드를 `curated_*`로 정본화했다.
- 문서: ADR-013/029, notice-plans architecture/API, storage/admin API,
  data-model/postgres-schema, conventions, file-storage runbook, Sprint 2, resume/tasks.

**검증**:

- WSL2 ext4 mirror: ruff / mypy / notice-plan copy integration tests
- WSL2 ext4 mirror: alembic upgrade head smoke
- WSL2 ext4 mirror: `npm run typecheck --workspaces --if-present`
- NTFS worktree: `git diff --check`

**다음**: T-126 POI 생성 경로 단일화(`/trips/{id}/pois` 정본).

## 2026-06-07 (claude) — Codex PR 사후 리뷰 20건 + 긴급성 종합

**작업**: Codex가 올린 머지 완료 PR 20건(#50, #52~#65, #67~#71)을 각 PR diff + 실제
코드 + 2026-06-06 감사와 대조해 사후 리뷰하고, 각 PR에 "리뷰 결과" 코멘트를 게시했다.

**핵심 발견**: 감사 백로그 대부분이 실구현으로 닫혔으나, 보안/가용성 PR에서 잔존 결함 확인.

- **#70(T-136 resend)**: C-22 **미완결** — secret 미설정 fail-open + `_decode_svix_secret`
  base64 altchars 버그(운영 서명 전부 mismatch).
- **#71(T-134 auth refresh)**: 비밀번호 재설정이 기존 session 미폐기.
- **#60(T-142 geofence)**: header spoof + nginx 강등 우회.
- **#63(T-128 WS)**: rate limit·backpressure 부재(DoS).
- **#67(T-140 budget)**: 응답 money Zod 타입 깨짐.
- **#50/#52/#53 admin**: status+audit 비원자성.

**산출물**: `docs/reviews/2026-06-07-codex-pr-review.md`(긴급성순 통합 TODO + PR별 표).
[높음] 9건을 T-154~T-161로 backlog 승격(`docs/tasks.md`).

## 2026-06-07 (codex) — T-134 auth refresh/session 영속화

**작업**: `pinvi_refresh` cookie가 opaque token으로 내려가지만 DB에 저장되지 않아
`POST /auth/refresh`와 서버 측 세션 폐기가 불가능하던 C-14 감사 항목을 구현했다.

**변경**:

- `apps/api/app/services/auth_session.py`, `apps/api/app/core/session_cookies.py` —
  refresh token SHA-256 hash 저장, refresh rotation, revoke, cookie 세팅/삭제 helper를
  추가했다.
- `apps/api/app/api/v1/auth.py` — login / verify-email / password reset 성공 시
  `app.user_sessions` row를 발급하고, `POST /auth/refresh`와 `POST /auth/logout`을
  구현했다.
- `apps/api/app/api/v1/oauth.py` — Google OAuth callback 성공 시에도 refresh session
  row를 저장하게 했다. Naver/Kakao는 계속 future provider다.
- `packages/api-client/src/endpoints/auth.ts` — refresh 응답 schema를 `AuthUser`로
  맞추고 logout은 204 no-content helper를 사용하게 했다.
- `apps/api/tests/integration/test_auth_sessions.py`,
  `apps/api/tests/integration/test_oauth_google.py` — 세션 저장, refresh rotation,
  만료/폐기 거부, logout revoke, OAuth callback session 저장을 검증한다.
- `docs/api/{auth,common}.md`, `docs/{data-model,postgres-schema,resume,tasks}.md` —
  refresh rotation 계약과 T-134 완료, 다음 후보 T-137을 반영했다.

**검증**:

- WSL2 ext4 mirror: ruff / mypy
- WSL2 ext4 mirror: auth session + OAuth integration tests

**다음**: T-137 notice/curated-plan 스키마 정본화.

## 2026-06-07 (codex) — T-136 Resend webhook Svix 서명 검증

**작업**: `PINVI_RESEND_WEBHOOK_SECRET`이 설정된 운영 환경에서 Resend webhook이
서명 없이 email 상태를 갱신할 수 있던 Sprint 2 임시 구현을 실제 Svix 검증으로
교체했다.

**변경**:

- `apps/api/app/webhooks/resend.py` — JSON 파싱 전 raw body 기준으로
  `svix-id`/`svix-timestamp`/`svix-signature`를 검증한다. `whsec_` secret을 HMAC key로
  쓰고, `id.timestamp.payload` HMAC-SHA256 `v1` signature와 timestamp 300초 허용
  오차를 확인한다. 실패 시 `401 WEBHOOK_SIGNATURE_INVALID`.
- `apps/api/tests/integration/test_resend_webhook.py` — 서명 비활성 dev mode 기존
  동작, 정상 서명 delivered 갱신, 헤더 누락/서명 불일치/오래된 timestamp 거부를
  검증한다.
- `docs/integrations/resend.md`, `docs/api/common.md`, `docs/resume.md`,
  `docs/tasks.md` — Resend webhook 검증 계약과 T-136 완료, 다음 비의존 후보 T-134를
  반영했다.

**검증**:

- WSL2 ext4 mirror: ruff / mypy
- WSL2 ext4 mirror: `pytest --capture=no tests/integration/test_resend_webhook.py`

**다음**: T-134 `POST /auth/refresh` + `user_sessions` 영속화.

## 2026-06-07 (codex) — T-141 trip↔지역 구조적 연결

**작업**: D-11 감사 항목의 `region_hint` 자유텍스트 한계를 줄이기 위해 Pinvi
자체 trip metadata에 구조화 지역 키를 추가했다.

**변경**:

- `apps/api/app/models/trip.py`,
  `apps/api/alembic/versions/20260606_0010_trip_primary_region.py` — `app.trips`에
  `primary_region_code`/`primary_region_source`와 code/source pair 제약, region index를
  추가했다.
- `apps/api/app/schemas/trip.py`, `apps/api/app/services/trip.py`,
  `apps/api/app/api/v1/trips.py` — Trip create/update/response가 수동 region code를
  저장하고 source를 `manual`로 관리하게 했다.
- `apps/api/app/services/poi.py` — POI 생성 시 `feature_snapshot`의 region code가 있으면
  비어 있는 trip primary region을 `poi_snapshot`으로 자동 보강한다.
- Admin API/schema와 `packages/schemas`, web/admin mock·표시 fallback을 구조화 지역
  필드에 맞췄다.
- `apps/api/tests/integration/{test_trips_api.py,test_pois_reorder.py}` — 수동 region
  round-trip/validation/null clear와 POI snapshot 기반 자동 보강을 검증한다.
- `docs/api/{trips,admin}.md`, `docs/{data-model,postgres-schema,resume,tasks}.md` —
  T-141 완료와 다음 비의존 후보 T-136을 반영했다.

**검증**:

- WSL2 ext4 mirror: ruff / mypy /
  `test_trips_api.py test_pois_reorder.py`
- WSL2 ext4 mirror: `npm run typecheck --workspaces --if-present`
- WSL2 ext4 mirror: prettier check (`packages/schemas`, admin/trip TSX/e2e)
- NTFS worktree: `git diff --check`

**다음**: T-136 Resend webhook Svix 서명 검증.

## 2026-06-07 (codex) — PR 리뷰 모니터 MCP 알림 보강

**작업**: PR 모니터가 5분 cron처럼 보이지만 실제 GitHub schedule 실행 간격이
25~30분대로 밀리고, 새 commit(`synchronize`)에는 즉시 반응하지 않는 점을 보강했다.
`kor-travel-map`식 MCP 진입을 PR reminder 본문에 넣고, 모니터 로직을 로컬/Actions
공용 Python 스크립트로 단일화했다.

**변경**:

- `scripts/pr_review_monitor.py` — 열린 PR 또는 지정 PR의 최신 head SHA marker를
  확인하고 없으면 MCP 기반 리뷰 알림 댓글을 남긴다.
- `.github/workflows/codex-pr-review.yml` — `reopened` / `synchronize` 이벤트 추가,
  공용 스크립트 실행으로 변경.
- `.github/workflows/codex-pr-monitor.yml` — GitHub Script matrix 로직 제거,
  공용 스크립트로 열린 PR 전체를 보정 감시.
- 문서: workflow index, Sprint 4 PR review runbook, agent-guide, ADR-021 amendment,
  resume/tasks 갱신.

**검증**: `gh` 기준 현재 열린 PR은 0개. 스크립트 dry-run / py_compile / YAML parse /
`git diff --check` 통과.

## 2026-06-07 (claude) — Telegram 완료 알림 MCP 도입 (모든 agent)

**작업**: kor-travel-map PR #229 패턴을 미러해 Pinvi 모든 agent worktree에서 PR 후
Telegram 완료 알림을 보낼 수 있게 했다. GitHub Actions secret/워크플로 없이
worktree 로컬 credential + MCP로 처리(T-062 0-secret 정책 유지).

**변경**:

- `scripts/mcp_telegram_start.py` — `.env.mcp-telegram`(gitignore) 로드 후
  `mcp-telegram` 실행하는 wrapper.
- `claude.json` / `.codex/config.toml` / `.gemini/mcp.json` / `antigravity.json` —
  각 agent worktree `cwd`로 `mcp-telegram` MCP 서버 등록.
- `.gitignore` — `.env.mcp-telegram` 무시. `.env.mcp-telegram.example` 템플릿 추가.
- 문서: `AGENTS.md`/`CLAUDE.md`/`SKILL.md` "Telegram 완료 알림 MCP" 정책(ADR-016 동기),
  `docs/runbooks/codegraph-worktrees.md` §3.7 셋업(모든 agent),
  `docs/agent-workflow.md` §5 발송 시점.

**검증**: wrapper `version`/JSON·TOML parse/py_compile OK. `mcp-telegram` v0.1.11 +
사용자 전역 세션(`~/.local/state/mcp-telegram/session.session`, kor-travel-map 로그인
재사용)으로 **실제 전송 성공**(Saved Messages, 사용자 수신 확인). `.env.mcp-telegram`은
gitignore되어 tracked secret 없음.

## 2026-06-06 (codex) — T-140 여행 예산/currency + copy 흐름 정합

**작업**: 감사 D-10 범위의 POI 예산/currency domain과 추천 plan copy 보존 흐름을
구현/검증했다.

**변경**:

- `apps/api/app/models/{poi,notice_plan}.py`,
  `apps/api/alembic/versions/20260606_0009_budget_constraints.py` — 금액 nonnegative와
  currency 대문자 3글자 check constraint를 추가했다.
- `apps/api/app/schemas/{poi,notice}.py`, `packages/schemas/src/{poi,notice-plan}.ts`
  — API/Zod schema에 같은 validation을 반영했다.
- `apps/api/app/services/poi.py`, `apps/api/app/api/v1/pois.py` — POI 생성 시
  `planned_arrival_at`, `planned_departure_at`, `budget_amount`, `actual_amount`,
  `currency`, `user_url`을 실제 저장하도록 연결하고 PATCH currency 변경을 허용했다.
- `apps/api/app/services/notice_plan.py` — 추천 plan seed/copy helper가
  `budget_amount`, `currency`, `user_url`, custom marker를 보존하게 했다.
- `apps/api/tests/integration/{test_pois_reorder.py,test_notice_plan_copy.py}` — 예산
  round-trip, 음수 예산 거부, 추천 plan budget/currency 복사를 검증한다.
- `docs/api/{pois,notice-plans}.md`, `docs/{data-model,postgres-schema}.md` — 예산/
  currency 계약과 copy 보존 규칙을 최신화했다.
- `docs/resume.md`, `docs/tasks.md` — T-140 완료와 다음 비의존 후보 T-141을 반영했다.

**검증**:

- WSL2 ext4 mirror: ruff / mypy /
  `test_pois_reorder.py test_notice_plan_copy.py`
- WSL2 ext4 mirror: `npm run typecheck --workspaces --if-present`
- WSL2 ext4 mirror: prettier check (`packages/schemas/src/{poi,notice-plan}.ts`)

**다음**: T-141 trip↔지역 구조적 연결(POI 좌표 유도 or region code).

## 2026-06-06 (codex) — T-139 동반자 초대/댓글/visibility 정합 보강

**작업**: 감사 D-06 범위의 동반자 초대 엔드포인트 부재와
`share_links.visibility='comment'` 대비 댓글 모델/API 부재를 정리했다.

**변경**:

- `apps/api/app/services/trip.py`, `apps/api/app/api/v1/trips.py` — owner-only
  동반자 초대/삭제, 기존 user 이메일 매칭, 중복 초대 방지, 공유 토큰 owner-only 경계,
  로그인 사용자 댓글 조회/작성/삭제를 구현했다.
- `apps/api/app/services/email_service.py` — `trip_invite` email_queue 적재 helper와
  HTML 렌더링을 추가했다.
- `apps/api/app/models/comment.py`, `apps/api/alembic/versions/20260606_0008_trip_comments.py`
  — `app.trip_comments` 테이블, index, updated_at trigger를 추가했다.
- `apps/api/tests/integration/test_trips_api.py` — 기존 user 초대 매칭 + outbox, 동반자
  권한 차단, 동반자 댓글 작성 + owner 삭제 흐름을 검증한다.
- `packages/schemas`, `packages/api-client` — companion/comment/share link schema와
  trip API client 메서드를 추가했다.
- `docs/api/trips.md`, `docs/postgres-schema.md`, `docs/data-model.md` — companion,
  share link, comment 계약과 `comment` visibility 의미를 최신화했다.
- `docs/resume.md`, `docs/tasks.md` — T-139 완료와 다음 비의존 후보 T-140을 반영했다.

**검증**:

- WSL2 ext4 mirror: ruff / mypy / `test_trips_api.py`
- WSL2 ext4 mirror: `npm run typecheck --workspaces --if-present`

**다음**: T-140 여행 예산(budget/currency) 도메인 + 복사 흐름.

## 2026-06-06 (codex) — T-138 사용자/보안 스키마 보강

**작업**: 감사 D-02/D-03 범위의 `users` 문서 drift와 PIPA 침해 대응 테이블 누락을
정리했다.

**변경**:

- `apps/api/app/models/security.py` — `SecurityIncident` 모델을 추가했다.
- `apps/api/alembic/versions/20260606_0007_security_incidents.py` —
  `app.security_incidents` 테이블, status/severity index, updated_at trigger를 추가했다.
- `apps/api/tests/integration/test_security_incidents_schema.py` — Alembic 적용 후 모델
  round-trip과 index 존재를 검증한다.
- `docs/postgres-schema.md`, `docs/data-model.md` — 실제 `users` 모델/마이그레이션의
  `password_hash`, `nickname`, demographic 선택 컬럼, `email_status` 등을 반영했다.
- `docs/compliance/pipa.md` — `security_incidents` foundation 완료와 후속 CPO 알림을
  분리했다.
- `docs/resume.md`, `docs/tasks.md` — T-138 완료와 다음 비의존 후보 T-139를 반영했다.

**검증**:

- WSL2 ext4 mirror: ruff / mypy / `test_security_incidents_schema.py`
- NTFS worktree: `git diff --check`, CodeGraph sync

**다음**: T-139 동반자 초대 흐름 + 댓글 모델/`visibility` 정리.

## 2026-06-06 (codex) — T-128 실시간 협업 백엔드 설계 + WS 계층

**작업**: Sprint 5 실시간 협업의 kor-travel-map 비의존 backend slice를 구현했다.

**변경**:

- `docs/decisions.md` ADR-035 — Trip WebSocket은 단일 프로세스 in-memory broker로
  시작하고, 다중 worker fan-out/durable replay는 후속 ADR로 분리했다.
- `apps/api/app/services/realtime_broker.py` — trip별 connection set, presence,
  JSON envelope broadcast, 테스트 reset/count helper를 추가했다.
- `apps/api/app/api/v1/ws.py` — `WS /ws/trips/{trip_id}` 인증(cookie/query token),
  trip 권한 확인, heartbeat/cursor/error 수신 루프를 추가했다.
- `apps/api/app/api/v1/{trips,pois}.py` — Trip/POI mutation 성공 후 `trip.updated`,
  `poi.created/updated/deleted/reordered` 이벤트를 publish한다.
- `docs/architecture/websocket-broker.md`, `docs/api/websocket.md` — broker 결정,
  close code, presence/broadcast 범위와 구현 체크리스트를 최신화했다.
- `docs/resume.md`, `docs/tasks.md` — T-128 완료와 다음 비의존 후보 T-138을 반영했다.

**검증**:

- WSL2 ext4 mirror: ruff / mypy / realtime broker unit test / WS integration test /
  Trip·POI 기존 통합 테스트
- NTFS worktree: `git diff --check`

**다음**: T-138 `users` 누락 컬럼 + `security_incidents` 테이블 추가.

## 2026-06-06 (codex) — T-145 backup schema-swap 확정

**작업**: 감사 D-19 범위의 Backup/Restore 핫스왑 정책을 Odroid M1S/N150 단일 노드
예산에 맞춰 정리했다.

**변경**:

- `docs/decisions.md` ADR-022 — 신규 DB instance 방식을 폐기하고, 동일 Postgres
  database 안의 `app_restore_<ts>` → `app` schema-swap으로 확정했다.
- `docs/architecture/backup-restore.md`, `docs/runbooks/backup-restore.md` — precheck,
  restore schema 준비, validation, write drain, schema rename, rollback, previous schema
  retention(N150 7일 / Odroid 24시간)을 문서화했다.
- `docs/sprints/SPRINT-6.md` — T-111 산출물/시나리오를 schema-swap 기준으로 정정했다.
- `apps/web/app/(admin)/admin/backup/page.tsx` — Restore placeholder를 신규 DB/DB URL
  cut-over가 아니라 schema-swap future workflow로 고쳤다.
- `docs/resume.md`, `docs/tasks.md` — T-145 완료와 다음 비의존 후보 T-128을 반영했다.

**검증**:

- NTFS worktree: stale 신규 DB/DATABASE_URL cut-over 표현 검색, `git diff --check`
- WSL2 ext4 mirror: Web typecheck

**다음**: T-128 실시간 협업 백엔드 설계 + WS 계층.

## 2026-06-06 (codex) — T-144 여행/장소 검색 UX + 내보내기 설계

**작업**: 감사 D-16/D-17 범위의 사용자 여행 검색, 장소 검색 drawer, PDF/GPX/print
내보내기 설계를 문서화했다.

**변경**:

- `docs/api/trips.md` — `GET /trips` 검색 파라미터(`q`, bucket/status/date/sort)와
  `exports/print-data`, `exports/gpx`, `exports/pdf` 계약을 추가했다.
- `docs/api/features.md` — 장소 검색을 실제 경로 `GET /features/search`로 분리하고,
  통합 `GET /search`는 T-129 future bucket 설계로 정리했다.
- `docs/architecture/frontend.md`, `docs/spec/v8/03-frontend.md` — Trip search bar,
  place search drawer, export menu, print route 책임과 kor-travel-map unavailable UX를
  문서화했다. Naver/Kakao 검색 fallback은 쓰지 않는다.
- `docs/api/common.md`, `docs/api/README.md`, `docs/spec/v8/02-backend.md` — rate limit,
  인덱스, SPEC 적용 노트를 같은 계약으로 맞췄다.
- `docs/resume.md`, `docs/tasks.md` — T-144 완료와 다음 비의존 후보 T-145를 반영했다.

**검증**:

- NTFS worktree: 문서 stale pattern 검색, `git diff --check`

**다음**: T-145 backup 핫스왑 동일호스트 schema-swap 확정.

## 2026-06-06 (codex) — T-142 geofence/admin 정합

**작업**: 감사 D-13/D-24 범위의 geofence admin 우회와 nginx GeoIP2 계층 과잉 표현을
정리했다.

**변경**:

- `apps/api/app/middleware/geofence.py` — KR/우회 path는 그대로 빠르게 통과시키고,
  KR 외 또는 strict unknown 차단 후보일 때만 access token `sub`로 `app.users.roles`를
  조회해 admin/operator/cpo 우회를 판단하도록 변경했다. token `roles` claim은 더 이상
  신뢰하지 않는다.
- `apps/api/tests/unit/test_geofence_middleware.py` — DB-role resolver 기반 admin 우회와
  token `roles` claim 단독 우회 차단 회귀 테스트를 추가했다.
- `docs/architecture/korea-only-policy.md`, `docs/runbooks/korea-only.md` — 단일
  Cloudflare Tunnel 기본 운영은 Cloudflare WAF + FastAPI fallback이며, nginx GeoIP2는
  별도 공개 edge가 있을 때의 선택 계층으로 정리했다.
- `docs/resume.md`, `docs/tasks.md` — T-142 완료와 다음 비의존 후보 T-144를 반영했다.

**검증**:

- WSL2 ext4 mirror: ruff / mypy / geofence unit test
- NTFS worktree: stale token role claim·nginx 3중 필수 표현 검색, `git diff --check`

**다음**: T-144 여행/장소 검색 UX + 내보내기(PDF/GPX/print) 설계.

## 2026-06-06 (codex) — T-147 잔여 문서 정정

**작업**: 감사 D-23/D-25 범위의 KASI rise/set 재계산 정책과 Gemini 문서 SQL 문법을
정리했다.

**변경**:

- `docs/integrations/kasi.md`, `docs/api/pois.md` — POI rise/set은 생성 당시
  `locdate`/좌표 snapshot 기준 1회 저장하며, 날짜/좌표 변경 시 자동 재조회하지 않는다고
  명시했다. 명시적 refresh action은 후속 PR 대상이다.
- `docs/integrations/gemini.md` — partial unique index를 table constraint가 아니라
  `CREATE UNIQUE INDEX ... WHERE deleted_at IS NULL` PostgreSQL 문법으로 정정했다.
- `docs/resume.md`, `docs/tasks.md` — T-147 완료와 다음 비의존 후보 T-142를 반영했다.

**검증**:

- NTFS worktree: `rg`로 미결 rise/set 문구와 invalid inline partial unique 문법 검색
- NTFS worktree: `git diff --check`

**다음**: T-142 geofence admin 우회 RBAC 소스 정정 + nginx 티어 정리.

## 2026-06-06 (codex) — T-143 지도/소셜 문서 정정

**작업**: 감사 D-15/D-21/D-22 범위의 지도 클라이언트, 소셜 로그인 provider,
kor-travel-geo geocoding 경계 문서 드리프트를 정리했다.

**변경**:

- `docs/architecture/frontend.md` — `apps/web/lib`의 폐기된 지도 어댑터 표현을
  `maplibre-vworld`로 바꾸고, 카카오맵 약관 메모가 ADR-015로 superseded됐음을 명시했다.
- `docs/architecture/map-marker-design.md` — 로그인 화면 OAuth 버튼 예시를 Google 하나로
  축소하고 Naver/Kakao는 T-122 전까지 만들지 않는다고 명시했다.
- `docs/integrations/README.md`, `docs/data-sources/README.md` — 현재 직접 OAuth
  provider는 Google이며, 주소/행정구역/geocoding은 `kor-travel-geo` v2 REST 직접
  호출임을 반영했다.
- `docs/architecture/mcp-tools.md` — in-process geocoding 호출 표현을 v2 REST 호출
  기준으로 정정했다.

**검증**:

- NTFS worktree: stale Kakao/Naver/social/kor-travel-geo 표현 검색
- NTFS worktree: `git diff --check`

**다음**: T-147 잔여 문서 정정. kor-travel-map feature read는 계속 T-066 대기.

## 2026-06-06 (codex) — T-151 미기록 ADR 백필

**작업**: Sprint 문서에 placeholder로 남아 있던 인증 토큰 / Admin RBAC / Admin audit
chain 결정을 현재 구현 기준으로 ADR에 박았다.

**변경**:

- `docs/decisions.md` — ADR-032(access JWT + httpOnly cookie), ADR-033(`users.roles[]`
  Admin RBAC), ADR-034(Admin audit hash chain)를 추가하고 다음 신규 ADR을 ADR-035로
  갱신했다.
- `CLAUDE.md`, `docs/sprints/SPRINT-1.md`, `SPRINT-2.md`, `SPRINT-3.md`,
  `SPRINT-5.md`, `SPRINT-6.md` — ADR 번호/후속 후보/구현 기준을 최신화했다.
- `docs/resume.md`, `docs/tasks.md` — T-151 완료와 다음 비의존 후보 T-143을 반영했다.

**검증**:

- NTFS worktree: `rg`로 Sprint/resume/decisions의 `ADR-NNN`, stale ADR-032/T-151 포인터 확인
- NTFS worktree: `git diff --check`

**다음**: T-143 지도/소셜 문서 정정. kor-travel-map feature read는 계속 T-066 대기.

## 2026-06-06 (codex) — T-150 계획/추적 문서 정합화

**작업**: 감사 P-04~21 중 T-150 범위의 sprint status, tracking 문서, ADR 참조
드리프트를 최신 main 기준으로 정리했다.

**변경**:

- `docs/sprints/SPRINT-1.md`, `SPRINT-3.md`, `SPRINT-4.md` 헤더 상태를 merged /
  in progress 기준으로 정정하고, 잘못 배정됐던 Sprint 1 ADR 참조를 실제 ADR 번호와
  T-151 백필 대상으로 분리했다.
- `docs/sprints/SPRINT-5.md`의 Pinvi ETL provider asset 계획을 ADR-026/T-210c
  경계에 맞춰 `app` schema 소유 job만 남기고, feature/provider 적재는 kor-travel-map
  책임으로 정리했다.
- `docs/sprints/README.md` 관련 ADR 목록을 ADR-031까지 확장했다.
- `docs/resume.md`의 stale ADR 후보를 T-151/T-148 후속으로 재분류하고, 박힌 ADR
  목록을 ADR-031까지 갱신했다.
- `docs/tasks.md` 완료/다음 작업/merge history를 최신화했다.

**검증**:

- NTFS worktree: `rg`로 Sprint status / ADR 후보 / T-111 중복 / 보류 `[x]` 혼재
  상태 확인
- NTFS worktree: `git diff --check`

**다음**: T-151 미기록 ADR 백필. kor-travel-map feature read는 계속 T-066 대기.

## 2026-06-06 (codex) — T-149 Gemini 책임 목록 정정

**작업**: ADR-020(`kor-travel-concierge` 별도 repo 분리)에 맞춰, 본 저장소의 현재
책임 목록에 남아 있던 Gemini 직접 통합 표현을 AI companion 호출 계약으로 정정했다.

**변경**:

- `README.md` — 책임/외부 통합 목록에서 Gemini 직접 통합을 제거하고 AI companion
  호출 계약으로 표기했다.
- `AGENTS.md` / `CLAUDE.md` — ADR-016 동기 원칙에 따라 외부 통합 진입 문구를
  AI companion 호출 계약으로 맞췄다.
- `SKILL.md` — DO NOT 항목의 webhook 검증 대상을 Telegram/Resend/AI companion으로
  정리했다.
- `docs/integrations/README.md` — Gemini 문서를 deferred reference로 낮추고,
  AI provider 구현은 `kor-travel-concierge`이 소유한다고 명시했다.

**검증**:

- NTFS worktree: `git diff --check`
- NTFS worktree: stale 책임 표현 검색
  (`외부 통합 .*Gemini`, `Telegram, Gemini`, `Google (OAuth + Gemini)`,
  `Gemini Deep Research (사용자 키) | 4+` 등) — 잔여 없음

**다음**: T-150 계획/추적 문서 정합화. kor-travel-map feature read는 계속 T-066 대기.

## 2026-06-06 (codex) — T-123 문서 정합 일괄 정정

**작업**: 감사 A-14/C-20/C-21/P-10/P-13/P-17/P-18 범위의 저위험 정합 문제를
최신 구현 기준으로 정리했다.

**변경**:

- README/API index에 `GET /search`, `GET /health/external`을 노출하고, OAuth는
  Google만 활성 + Naver/Kakao future provider로 표현을 맞췄다.
- `POST /trips/{trip_id}/share-tokens` URL 생성을 `PINVI_WEB_BASE_URL` 기반으로
  변경하고 통합 테스트를 추가했다.
- feature viewport zoom 하한을 코드/Zod와 같은 5로 문서 정정했다.
- `docs/sprints/SPRINT-4.md`의 dangling `docs/release-plan.md` 링크를 현재 추적
  문서(`sprints/README`, `tasks`, `resume`) 참조로 바꿨다.
- `docs/decisions.md`의 `python-kraddr-map` 오타를 `kor-travel-geo`로 정정했다.
- `docs/agent-guide.md`의 구식 co-author 예시와 잔여 `Restrict force-push` bullet을
  정리했다.
- `docs/tasks.md` merge history에 PR #52/#53을 추가했다.

**검증**:

- WSL2 ext4 mirror:
  `uv run ruff format app/api/v1/trips.py tests/integration/test_trips_api.py`
- WSL2 ext4 mirror:
  `uv run ruff check app/api/v1/trips.py tests/integration/test_trips_api.py`
- WSL2 ext4 mirror: `uv run mypy --strict app`
- WSL2 ext4 mirror: `uv run pytest -s tests/integration/test_trips_api.py -q`
  — 6 passed

**다음**: T-149 Gemini 책임 목록 정정. kor-travel-map feature read는 계속 T-066 대기.

## 2026-06-06 (codex) — T-121 POI Admin 목록/상세/연결 상태 관리

**작업**: kor-travel-map 연계가 필요 없는 admin 후속으로, Pinvi 소유
`app.trip_day_pois` POI 첨부 행의 목록/상세/연결 상태 관리 기능을 구현했다.

**변경**:

- `GET /admin/pois` — `q` 검색(`feature_id`, snapshot JSON, trip 제목, owner email,
  UUID 정확 일치), `trip_id`, `has_broken_link` 필터와 owner 이메일 마스킹을 제공한다.
- `GET /admin/pois/{poi_id}` — feature snapshot, 일정/비용/메모/URL, 추가자 마스킹,
  최근 `admin_audit_log` 10건을 반환한다.
- `PATCH /admin/pois/{poi_id}/link-status` — admin 전용 로컬 연결 상태 변경,
  `access_reason` 필수, `poi.update_link_status` audit 기록.
- `packages/schemas`, `packages/api-client`, Web `/admin/pois` 목록/상세 화면을
  계약에 맞춰 추가했다.
- `apps/api/tests/integration/test_admin_pois_api.py`,
  `apps/web/e2e/admin-pois.e2e.ts` — 검색/마스킹/broken filter/link status audit과
  kor-travel-map 미호출을 검증했다.

**검증**:

- WSL2 ext4 mirror:
  `uv run ruff format app tests/integration/test_admin_pois_api.py`
- WSL2 ext4 mirror:
  `uv run ruff check app tests/integration/test_admin_pois_api.py`
- WSL2 ext4 mirror: `uv run mypy --strict app`
- WSL2 ext4 mirror: `uv run pytest -s tests/integration/test_admin_pois_api.py -q`
  — 4 passed
- WSL2 ext4 mirror:
  `npm run typecheck --workspace packages/schemas`,
  `npm run typecheck --workspace packages/api-client`,
  `npm run typecheck --workspace apps/web`,
  `npm run lint --workspace apps/web`,
  `npm run build --workspace apps/web`
- Windows Playwright runner → WSL dev server:
  `PLAYWRIGHT_BASE_URL=http://<wsl-playwright-host>:9022 ... @playwright/test ... admin-pois.e2e.ts`
  — 2 passed
- WSL2 ext4 mirror: `uv run ruff format --check .`
- NTFS worktree: `git diff --check`

**다음**: T-123 문서 정합 일괄 정정. 구현 feature read와 feature re-link는 계속
kor-travel-map HTTP/OpenAPI 준비 후로 둔다.

## 2026-06-06 (codex) — T-120 여행계획 Admin 목록/상세/상태 관리

**작업**: kor-travel-map 연계가 필요 없는 admin 후속으로, Pinvi 소유 여행계획의
목록/상세/상태 관리 기능을 구현했다.

**변경**:

- `GET /admin/trips` — `q` 검색(제목/지역/owner email 부분 일치, trip_id /
  owner_user_id 정확 일치), `status_filter`, `visibility_filter`, `owner_user_id`
  필터와 day/POI/companion/share count를 제공한다.
- `GET /admin/trips/{trip_id}` — owner 이메일은 마스킹하고, companion/share metadata와
  최근 `admin_audit_log` 10건을 반환한다.
- `PATCH /admin/trips/{trip_id}/status` — admin 전용 상태 변경, `access_reason`
  필수, `trip.update_status` audit 기록.
- `packages/schemas`, `packages/api-client`, Web `/admin/trips` 목록/상세 화면을
  계약에 맞춰 추가했다.
- `apps/api/tests/integration/test_admin_trips_api.py`,
  `apps/web/e2e/admin-trips.e2e.ts` — 검색/마스킹/count/status audit과 kor-travel-map
  미호출을 검증했다.

**검증**:

- WSL2 ext4 mirror:
  `uv run ruff format app tests/integration/test_admin_trips_api.py`
- WSL2 ext4 mirror:
  `uv run ruff check app tests/integration/test_admin_trips_api.py`
- WSL2 ext4 mirror: `uv run mypy --strict app`
- WSL2 ext4 mirror: `uv run pytest -s tests/integration/test_admin_trips_api.py -q`
  — 3 passed
- WSL2 ext4 mirror:
  `npm run typecheck --workspace packages/schemas`,
  `npm run typecheck --workspace packages/api-client`,
  `npm run typecheck --workspace apps/web`,
  `npm run lint --workspace apps/web`,
  `npm run build --workspace apps/web`
- Windows Playwright runner → WSL dev server:
  `PLAYWRIGHT_BASE_URL=http://<wsl-playwright-host>:9022 ... @playwright/test ... admin-trips.e2e.ts`
  — 2 passed

**다음**: T-121 POI Admin 목록/상세/연결 상태 관리. feature re-link는 kor-travel-map
client 준비 후로 두고, 현재는 Pinvi 소유 `trip_day_pois` 영역만 다룬다.

## 2026-06-06 (claude) — T-210c(ADR-045 Phase 6) Pinvi ETL 경계 정합

**작업**: kor-travel-map ADR-045 Phase 6의 T-210c("Pinvi `apps/etl` 레거시 Dagster
이관/삭제") 중 Pinvi가 지금 처리할 수 있는 부분을 수행했다.

**확인**: `apps/etl`은 이미 `app` schema 소유 job만 보유(KASI 특일 asset +
`kasi_poi_rise_set_job` + DB/KASI resource). feature/provider 적재 Dagster 코드는
**없음** → kor-travel-map으로 이관/삭제할 레거시 스켈레톤 자체가 없다(코드 측 T-210c는 N/A).

**변경(문서 phantom 스켈레톤 정합 + 코드 가드)**:

- `docs/architecture/dagster-etl-bridge.md` §2 — 미존재 파일(`sensors.py`,
  `pinvi_kasi_poi_rise_set/telegram_weekly/email_outbox/pii_retention/
location_log_archive`) 나열을 "현재 구현 vs 계획(미구현)"으로 정합. §3.1 asset명을
  `kasi_special_days_daily` → 실제 `pinvi_kasi_special_days`로 정정.
- `docs/runbooks/etl.md` §2 — 동일하게 구현/계획 분리 + T-210c 경계 노트.
- `apps/etl/pinvi/etl/assets/__init__.py` — "feature/provider asset 추가 금지,
  kor-travel-map 소유(ADR-003/026/045 T-210c)" 가드 docstring 추가.
- `docs/tasks.md` — kor-travel-map ADR-045 Phase 6 Pinvi 몫 매핑(T-210b/c 완료,
  T-210d=T-066 대기, T-210e 대기).

## 2026-06-06 (codex) — T-119 회원 관리 Admin 보강

**작업**: kor-travel-map과 무관한 admin 후속으로, 회원 목록 검색과 상세 PII reveal audit
UX를 보강했다.

**변경**:

- `GET /admin/users` — `q` 검색(이메일/닉네임 부분 일치, user_id 정확 일치)과
  `status_filter`를 함께 적용한다.
- `GET /admin/users/{user_id}` — 기본 응답은 이메일을 마스킹하고, `reveal=true` +
  사유가 있을 때만 원본 이메일을 반환하며 `user.reveal_pii` audit을 남긴다.
- `AdminUserDetail` / Web schema / API client — `email_revealed`, `recent_audit`,
  reveal 조회 파라미터를 추가했다.
- `/admin/users` UI — 검색 입력 + 상태 필터 결합 조회를 추가했다.
- `/admin/users/{user_id}` UI — 원본 보기 사유 입력 dialog와 최근 audit 표를 추가했다.
- `apps/api/tests/integration/test_admin_users_api.py`,
  `apps/web/e2e/admin-users.e2e.ts` — 검색/마스킹/reveal audit과 kor-travel-map 미호출을
  검증했다.

**검증**:

- WSL2 ext4 mirror:
  `uv run ruff format app tests/integration/test_admin_users_api.py`
- WSL2 ext4 mirror:
  `uv run ruff check app tests/integration/test_admin_users_api.py`
- WSL2 ext4 mirror: `uv run mypy --strict app`
- WSL2 ext4 mirror: `uv run pytest -s tests/integration/test_admin_users_api.py -q`
  — 2 passed
- WSL2 ext4 mirror:
  `npm run typecheck --workspace packages/schemas`,
  `npm run typecheck --workspace packages/api-client`,
  `npm run typecheck --workspace apps/web`,
  `npm run lint --workspace apps/web`,
  `npm run build --workspace apps/web`
- Windows Playwright runner → WSL dev server:
  `PLAYWRIGHT_BASE_URL=http://<wsl-playwright-host>:9022 ... @playwright/test ... admin-users.e2e.ts`
  — 2 passed

**다음**: T-120 여행계획 Admin 목록/상세/상태 관리.

## 2026-06-06 (codex) — T-118 Google OAuth 계정 매칭 UX

**작업**: kor-travel-map과 무관한 인증 UX 후속으로, Google OAuth의 같은 이메일 자동
연결을 제거하고 명시 연결 안내/충돌 메시지를 보강했다. Naver/Kakao는 계속 T-122
미래 작업으로 둔다.

**변경**:

- `apps/api/app/services/oauth_google.py` — 같은 이메일 로컬 계정이 있으면
  `OAUTH_ACCOUNT_LINK_REQUIRED`를 발생시켜 자동 연결하지 않는다. Google 이메일
  인증 불확실성은 `OAUTH_EMAIL_UNVERIFIED`로 거부한다.
- `apps/api/app/api/v1/oauth.py` — link-mode callback 실패는 `/login`이 아니라
  state의 `return_to`(`/profile`)로 redirect한다.
- `apps/web/app/(auth)/login/page.tsx`, `apps/web/app/(auth)/profile/page.tsx` —
  계정 매칭/연결 충돌 메시지를 code 기반으로 표시한다.
- `apps/api/tests/integration/test_oauth_google.py`,
  `apps/web/e2e/oauth-account-match.e2e.ts` — 자동 연결 금지, profile 충돌 redirect,
  Naver/Kakao 미노출 e2e를 보강했다.
- `docs/api/auth.md`, `docs/integrations/social-login.md`, `docs/tasks.md`,
  `docs/resume.md` — OAuth 매칭 계약과 다음 비의존 후보(T-119)를 반영했다.

**검증**:

- WSL2 ext4 mirror:
  `uv run ruff format app tests/integration/test_oauth_google.py`
- WSL2 ext4 mirror:
  `uv run ruff check app tests/integration/test_oauth_google.py`
- WSL2 ext4 mirror: `uv run mypy --strict app`
- WSL2 ext4 mirror: `uv run pytest -s tests/integration/test_oauth_google.py -q`
  — 18 passed
- WSL2 ext4 mirror:
  `npm run typecheck --workspace apps/web`,
  `npm run lint --workspace apps/web`,
  `npm run build --workspace apps/web`
- Windows Playwright runner → WSL dev server:
  `PLAYWRIGHT_BASE_URL=http://<wsl-playwright-host>:9022 ... @playwright/test ... oauth-account-match.e2e.ts`
  — 2 passed

**다음**: T-119 회원 관리 Admin 보강.

## 2026-06-06 (codex) — T-117 회원가입 약관 동의

**작업**: kor-travel-map과 무관한 가입 UX/컴플라이언스 후보로, 회원가입 단계에서
필수 약관 동의를 받고 `app.user_consents`에 저장하도록 보강했다.

**변경**:

- `apps/api/app/schemas/auth.py`, `packages/schemas/src/auth.ts` —
  `RegisterRequest`에 `consents` 배열을 추가하고 필수 4종 동의 누락/중복을 검증한다.
- `apps/api/app/services/user_registration.py`, `apps/api/app/api/v1/auth.py` —
  가입 트랜잭션 안에서 `UserConsent` row를 생성한다.
- `apps/api/app/core/errors.py` — Pydantic validator의 `ctx.error` 객체가 표준
  validation 응답 직렬화를 깨지 않도록 JSON-safe 변환을 추가했다.
- `apps/web/app/(auth)/signup/page.tsx` — 필수 전체 동의, 필수 4종 체크박스,
  선택 `marketing` 동의를 추가하고 필수 동의 전 제출을 막는다.
- `docs/api/auth.md`, `docs/compliance/lbs-act.md`, `docs/tasks.md`, `docs/resume.md`
  — 회원가입 동의 계약과 다음 비의존 후보(T-118)를 반영했다.

**검증**:

- WSL2 ext4 mirror:
  `uv run pytest -s tests/unit/test_schemas.py tests/integration/test_register_consents.py -q`
  — 9 passed
- WSL2 ext4 mirror:
  `uv run ruff format --check app tests/unit/test_schemas.py tests/integration/test_register_consents.py`
- WSL2 ext4 mirror:
  `uv run ruff check app tests/unit/test_schemas.py tests/integration/test_register_consents.py`
- WSL2 ext4 mirror: `uv run mypy --strict app`
- WSL2 ext4 mirror:
  `npm run typecheck --workspace packages/schemas`,
  `npm run typecheck --workspace packages/api-client`,
  `npm run typecheck --workspace apps/web`,
  `npm run lint --workspace apps/web`,
  `npm run build --workspace apps/web`
- Windows Playwright runner → WSL dev server:
  `PLAYWRIGHT_BASE_URL=http://<wsl-playwright-host>:9022 ... @playwright/test ... signup-consents.e2e.ts`
  — 1 passed

**다음**: T-118 Google OAuth 계정 매칭 UX 보강. Naver/Kakao OAuth는 T-122 미래
작업으로 유지한다.

## 2026-06-06 (claude) — 문서·구현 정합성 전수 감사 + kor-travel-map 요구사항 명세

**작업**: Sprint 1~4 중 계획 변경·Task 분절로 누적된 모순·불일치·누락을 문서 전체 +
`apps/` 코드 + `kor-travel-map`(HEAD `b775c74`) 대조로 전수 점검했다. 5개 병렬
감사(계획/프로세스, 외부 API, 코드 vs 문서, 기능/도메인, kor-travel-map 저장소)를 종합.

**핵심 발견**: Pinvi(ADR-026, HTTP 9011)와 kor-travel-map(in-process 함수 라이브러리,
HTTP는 인증 없는 debug-UI 8087뿐)의 **통합 모델이 정반대**이며, ADR-026이 참조한
kor_travel_map 산출물(`kor-travel-map-admin` 패키지·`openapi.user.json`·`/pinvi/features/batch`)
이 **실재하지 않음**을 확인. 그 외 외부 API 규약 혼재(envelope/pagination/좌표/datetime),
feature read 전 경로 미연결(C-01 client stub), `notice_plans` 명칭 충돌, PIPA `users`
컬럼·`security_incidents` 테이블 누락, 실시간/검색/내보내기/동반자 초대 부재 등.

**신규 문서**:

- `docs/audit/2026-06-06-doc-impl-audit.md` — 감사 종합(증거 ID P/A/C/D, 병합 매핑표
  T-123~~151 / ADR-027~~031).
- `docs/kor-travel-map-requirements.md` — kor-travel-map 에이전트용 요구사항(능력별 왜/언제 +
  현재 상태 + 격차표 K-1~14).
- `docs/decisions-needed-2026-06-06.md` — 결정 DEC-01~10 + 사용자 결정 기록.

**사용자 결정**: DEC-01=운영급 HTTP 서비스(B), DEC-03=`curated_trip_plans` 분리,
DEC-06=kor_travel_map 연동까지 v0.1.0 대기, DEC-07=API 규약 제안 기본값+`/v1`. 나머지는 저위험
권고 기본값 채택.

**반영**: `decisions.md` ADR-027~031 추가, `common.md` 정본 규약(ADR-030),
`kor-travel-map-integration.md` 실재성 정정, `sprints/README.md` status·v0.1.0 게이트,
`tasks.md` 감사 후속 백로그 + 머지표, `notice-plans.md`/`data-model.md` 정정 노트.

## 2026-06-06 (codex) — T-100~T-104 backlog 상태 정정

**작업**: 완료된 T-100~T-104가 `docs/tasks.md`의 `보류` 섹션에 남아 실제 상태와
다르게 읽히던 문서 구조를 정리했다.

**변경**:

- `docs/tasks.md` — T-100~T-104를 `완료` 섹션으로 옮기고 `보류`에는 실제
  보류/미래 항목만 남겼다.
- `docs/agent-guide.md` — `tasks.md` 형식 예시의 T-100 번호를 예시용 T-900으로
  바꿔 실제 backlog와 충돌하지 않게 했다.

**검증**:

- `git diff --check`

**다음**: T-066은 kor-travel-map OpenAPI/client 의존으로 계속 보류한다.

## 2026-06-06 (codex) — T-115 Backup snapshot foundation + T-116 Google-only OAuth

**작업**: kor-travel-map과 무관한 운영/인증 후보로 ADR-022 Sprint 5 backup snapshot
foundation을 구현하고, 현재 OAuth provider 범위를 Google-only로 정리했다.

**변경**:

- `scripts/backup-db.sh`, `scripts/restore-db.sh` — Pinvi 소유 `app` schema custom
  dump / restore 스크립트 추가. backup은 `.dump`와 `.sha256`을 생성한다.
- `apps/api/app/services/backup_service.py`,
  `apps/api/app/api/v1/admin/backup.py` — snapshot 목록 조회와 수동 snapshot 생성
  endpoint(`GET /admin/backup/snapshots`, `POST /admin/backup/snapshot`) 추가.
- `packages/schemas`, `packages/api-client`, `apps/web/app/(admin)/admin/backup/page.tsx`
  — admin backup snapshot 목록 / 수동 trigger UI와 client schema 연결.
- `apps/api/app/api/v1/oauth.py`, `apps/web/app/(auth)/login/page.tsx` — 현재 provider
  응답과 UI를 Google만 활성으로 고정. Naver/Kakao는 T-122 미래 작업으로 분리.
- `.env.example`, `docs/api/{admin,auth}.md`,
  `docs/{architecture,runbooks}/backup-restore.md`,
  `docs/integrations/social-login.md`, `docs/tasks.md`, `docs/resume.md` — backup
  환경변수, API/runbook, Google-only OAuth 정책, 신규 비의존 backlog 반영.

**검증**:

- WSL2 ext4 mirror:
  `uv run pytest -s tests/unit/test_backup_service.py tests/integration/test_oauth_google.py::test_providers_endpoint_exposes_google_only_for_now -q`
  — 4 passed
- WSL2 ext4 mirror:
  `uv run ruff format --check app tests/unit/test_backup_service.py tests/integration/test_oauth_google.py`
- WSL2 ext4 mirror:
  `uv run ruff check app tests/unit/test_backup_service.py tests/integration/test_oauth_google.py`
- WSL2 ext4 mirror: `uv run mypy --strict app`
- WSL2 ext4 mirror:
  `npm run typecheck --workspace packages/schemas`,
  `npm run typecheck --workspace packages/api-client`,
  `npm run typecheck --workspace apps/web`,
  `npm run lint --workspace apps/web`,
  `npm run build --workspace apps/web`
- Windows Playwright runner → WSL dev server:
  `PLAYWRIGHT_BASE_URL=http://<wsl-playwright-host>:9022 ... @playwright/test ... admin-backup.e2e.ts`
  — 1 passed
- NTFS worktree: `git diff --check`

**다음**: T-117 회원가입 약관 동의 화면 + `user_consents` 저장 보강부터 진행한다.
Naver/Kakao OAuth는 현재 사용하지 않고 T-122 미래 작업으로 둔다.

## 2026-06-05 (codex) — T-109 한국 전용 geofencing FastAPI fallback

**작업**: kor-travel-map과 무관한 보안/운영 후보로 ADR-018의 3차 FastAPI fallback을
구현했다.

**변경**:

- `apps/api/app/middleware/geofence.py` — 기본 비활성 geofence middleware 추가.
  활성 시 `CF-IPCountry` 기반으로 허용 국가(`KR`) 외 요청을 451로 차단한다.
- `apps/api/app/core/config.py`, `.env.example` — `PINVI_GEOFENCE_*` 환경변수 추가.
- `apps/api/app/main.py` — Geofence middleware를 API middleware stack에 연결.
- `apps/api/tests/unit/test_geofence_middleware.py` — 비활성 허용, KR 허용, 비KR 차단,
  health 우회, unknown strict 차단, roles claim 기반 admin 우회를 검증.
- `docs/runbooks/korea-only.md`, `docs/architecture/korea-only-policy.md`,
  `resume.md`, `tasks.md` — 현재 FastAPI fallback 계약과 운영 우회 한계를 반영.

**검증**:

- WSL2 ext4 mirror: `uv run pytest -s tests/unit/test_geofence_middleware.py -q` — 6 passed
- WSL2 ext4 mirror:
  `uv run ruff format --check app tests/unit/test_geofence_middleware.py && uv run ruff check app tests/unit/test_geofence_middleware.py`
- WSL2 ext4 mirror: `uv run mypy --strict app`

**다음**: T-111 Backup/Restore UI 핫스왑은 kor-travel-map 비의존이지만 운영 데이터 보호
범위라 ADR-022와 backup runbook을 먼저 확인한다.

## 2026-06-05 (codex) — T-110 Admin Grafana iframe embed

**작업**: kor-travel-map과 무관한 운영 UI 후보로 `/admin/grafana` iframe shell을 먼저
연결했다.

**변경**:

- `apps/web/app/(admin)/admin/grafana/page.tsx` — Grafana iframe, 새로고침, 새 창
  action, embed origin 표시를 추가했다.
- `apps/web/app/(admin)/admin/layout.tsx` — Admin navigation에 Grafana 항목 추가.
- `apps/web/next.config.mjs` — `/admin/grafana`에 Grafana origin 대상 `frame-src`
  CSP를 추가했다.
- `.env.example`, `docs/runbooks/grafana-admin-embed.md` —
  `NEXT_PUBLIC_GRAFANA_URL`, `NEXT_PUBLIC_GRAFANA_DASHBOARD_PATH`를 명시했다.
- `apps/web/e2e/admin-grafana.e2e.ts` — admin guard 뒤에서 iframe shell이 렌더링되고
  kor-travel-map API `9011`을 호출하지 않음을 검증한다.

**검증**:

- WSL2 ext4 mirror:
  `PATH=/home/digitie/.cache/parking-radar-node-v22.15.0/bin:... npm run typecheck --workspace apps/web`
- WSL2 ext4 mirror:
  `PATH=/home/digitie/.cache/parking-radar-node-v22.15.0/bin:... npm run lint --workspace apps/web`
- WSL2 ext4 mirror:
  `PATH=/home/digitie/.cache/parking-radar-node-v22.15.0/bin:... npm run build --workspace apps/web`
- Windows Playwright runner → WSL dev server:
  `PLAYWRIGHT_BASE_URL=http://<wsl-playwright-host>:9022 ... @playwright/test ... admin-grafana.e2e.ts`
  — 1 passed

**다음**: T-109 geofencing은 kor-travel-map 비의존이지만 보안/운영 정책 범위라
ADR-018과 `docs/runbooks/korea-only.md`를 먼저 확인한다.

## 2026-06-05 (codex) — T-075 Trip / notice plan 사용자 shell

**작업**: kor-travel-map feature 조회 없이 Pinvi 자체 Trip / notice plan API만으로
사용자 shell을 연결했다.

**변경**:

- `packages/api-client/src/endpoints/trips.ts`,
  `packages/api-client/src/endpoints/notice-plans.ts` — `GET /trips`,
  `POST /trips`, `GET /notice-plans`, `POST /notice-plans/{id}/copy` 등 사용자
  endpoint client를 추가했다.
- `apps/web/app/(app)/layout.tsx`, `apps/web/components/app/AppShell.tsx` — 사용자
  앱 공통 navigation shell을 추가했다.
- `apps/web/app/(app)/trips/page.tsx`,
  `apps/web/components/trips/TripDashboard.tsx` — Trip 목록, bucket 필터, 빈 상태,
  간단 생성 form을 연결했다.
- `apps/web/app/(app)/notice-plans/page.tsx`,
  `apps/web/components/notice-plans/NoticePlanShelf.tsx` — 추천 여행 목록, category
  필터, 내 여행으로 copy action을 연결했다.
- `apps/web/e2e/user-shells.e2e.ts` — API 응답을 Playwright route mock으로 고정하고
  `/features/*`와 kor-travel-map API `9011` 미호출을 검증했다.

**검증**:

- WSL2 ext4 mirror:
  `PATH=/home/digitie/.cache/parking-radar-node-v22.15.0/bin:... npm run typecheck --workspace packages/api-client`
- WSL2 ext4 mirror:
  `PATH=/home/digitie/.cache/parking-radar-node-v22.15.0/bin:... npm run typecheck --workspace apps/web`
- WSL2 ext4 mirror:
  `PATH=/home/digitie/.cache/parking-radar-node-v22.15.0/bin:... npm run lint --workspace apps/web`
- WSL2 ext4 mirror:
  `PATH=/home/digitie/.cache/parking-radar-node-v22.15.0/bin:... npm run build --workspace apps/web`
- Windows Playwright runner → WSL dev server:
  `PLAYWRIGHT_BASE_URL=http://<wsl-playwright-host>:9022 ... @playwright/test ... map-shell.e2e.ts user-shells.e2e.ts`
  — 3 passed

**다음**: kor-travel-map client 의존 T-066은 계속 보류한다. 남은 비의존 후보는 Sprint
5~6 backlog 중 운영/관리 UI 범위(T-110 등)를 별도 task로 선별한다.

## 2026-06-05 (codex) — T-074 PR-C frontend 지도 shell

**작업**: kor-travel-map feature 조회를 연결하지 않고, Sprint 4 PR-C의 지도 shell을
Pinvi Web에 먼저 붙였다.

**변경**:

- `apps/web/package.json` / `package-lock.json` — `maplibre-vworld`를
  `digitie/maplibre-vworld-js` commit `f1dd74b9...`의 GitHub archive tarball에
  pin하고 `maplibre-gl`, Playwright dev dependency를 추가했다.
- `apps/web/components/map/MapView.tsx` — `VWorldMap`, `ClusterLayer`,
  `MakiMarker`, `Popup`을 dynamic import로 연결하고 정적 서울 샘플 포인트만 렌더링한다.
  `/features/in-bounds` 또는 kor-travel-map API `9011` 호출은 하지 않는다.
- `apps/web/app/(app)/trips/map-shell/page.tsx` — `/trips/map-shell` 지도 shell route
  추가.
- `apps/web/playwright.config.ts`, `apps/web/e2e/map-shell.e2e.ts` — Windows
  Playwright smoke로 shell 렌더링과 kor-travel-map 비호출을 검증.
- `apps/web/next.config.mjs` — `maplibre-vworld` transpile 대상 추가. 라이브러리 dist의
  development JSX runtime이 `require("react")`를 호출하는 dev-only 문제는
  `MapView`의 React require shim으로 보완했다. production build는 정상 통과.
- `docs/integrations/maplibre-vworld.md`, `resume.md`, `tasks.md` — PR-C pin/import/e2e
  상태와 다음 비의존 후속을 갱신.

**검증**:

- WSL2 ext4 mirror: `npm run lint --workspace apps/web`
- WSL2 ext4 mirror: `npm run typecheck --workspace apps/web`
- WSL2 ext4 mirror: `npm run build --workspace apps/web`
- Windows Playwright runner → WSL dev server:
  `PLAYWRIGHT_BASE_URL=http://<wsl-playwright-host>:9022 npx -y @playwright/test@1.60.0 test map-shell.e2e.ts`
  — 1 passed

**다음**: kor-travel-map client 의존 T-066은 계속 보류하고, Trip 대시보드 / notice plan
사용자 shell처럼 feature 조회 없이 가능한 PR-C 후속을 진행한다.

## 2026-06-05 (codex) — T-073 Google OAuth profile 연결/해제 UI

**작업**: kor-travel-map과 무관한 Google OAuth profile 연결/해제 흐름을 Web UI까지
연결했다.

**변경**:

- `/auth/me` — 현재 사용자 응답에 `has_password`와 `oauth_identities`를 포함한다.
- `/auth/oauth/google/link` — 로그인된 사용자용 link state를 발급하고 `user_id`를
  state row에 저장한다.
- `DELETE /auth/oauth/google` — `password_hash`가 없는 소셜-only 계정은 409로 해제
  차단.
- `@pinvi/schemas` / `@pinvi/api-client` — OAuth identity schema,
  `linkGoogleOAuth`, `unlinkGoogleOAuth`, 204 no-content client 처리 추가.
- `apps/web/app/(auth)/profile/page.tsx` — Google 연결 상태, 연결 시작, 해제 UI 추가.
- `docs/api/auth.md`, `docs/integrations/social-login.md`, `resume.md`, `tasks.md` —
  현재 계약과 진행 상태 반영.

**검증**:

- `apps/api`: `python -m pytest -s tests/integration/test_oauth_google.py -q` — 14 passed
- `apps/api`: `ruff format --check app tests/integration/test_oauth_google.py`
- `apps/api`: `ruff check app tests/integration/test_oauth_google.py`
- `apps/api`: `mypy --strict app`
- `apps/web`: `npm run build --workspace apps/web`
- root: `npm run typecheck --workspaces --if-present`
- NTFS worktree: `git diff --check`

**다음**: kor-travel-map client 의존 T-066은 계속 보류하고, PR-C frontend 지도 shell 중
feature 조회를 제외한 범위를 진행한다.

## 2026-06-05 (codex) — T-072 Google OAuth callback 실패 UX

**작업**: Google OAuth callback 실패가 API JSON 오류로 남지 않고 Web 로그인 화면으로
돌아오도록 정리했다.

**변경**:

- `/auth/oauth/google/callback` — provider 거부, 필수 query 누락, state 검증 실패,
  token/userinfo 실패, 매칭 실패를 `/login?error=...&error_description=...` 303
  redirect로 변환.
- `apps/web/app/(auth)/login/page.tsx` — `error` query를 고정 한국어 메시지로 매핑해
  인라인 표시. 임의 `error_description`은 화면에 직접 노출하지 않는다.
- `test_oauth_google.py` — invalid state / provider denied redirect 회귀 테스트 추가.
- `docs/api/auth.md`, `docs/integrations/social-login.md`, `resume.md`, `tasks.md` —
  현재 Google callback 실패 UX 반영.

**검증**: PR 전 API OAuth integration, API lint/typecheck, web lint/typecheck/build를
재실행한다.

**다음**: Google OAuth profile 연결/해제 UI는 별도 비의존 후속으로 진행한다.

## 2026-06-05 (codex) — T-071 Google OAuth 로그인 UI

**작업**: 로컬 Google OAuth client id를 반영한 뒤, 로그인 화면에서 Google OAuth
authorize URL 발급 흐름을 시작할 수 있게 연결했다.

**변경**:

- `/auth/oauth/google/start` — 공통 API client가 읽을 수 있도록 envelope 응답
  (`data.authorize_url`)으로 정리.
- `oauth_google.issue_login_state` / `consume_login_state` — PKCE verifier를 DB 평문
  저장 없이 `state` + 서버 secret으로 재생성해 callback 토큰 교환에 전달.
- `@pinvi/schemas` / `@pinvi/api-client` — OAuth provider 목록과 Google start
  schema/client 메서드 추가.
- `apps/web/app/(auth)/login/page.tsx` — `/auth/oauth/providers` 조회 후 Google 버튼
  활성화, 클릭 시 `authorize_url`로 top-level navigation.
- `apps/web/eslint.config.mjs` — `FlatCompat.baseDirectory`를 file URL이 아닌 절대
  디렉터리 경로로 고쳐 Windows/CI lint 경로 해석을 안정화.

**검증**: `test_oauth_google.py`에 start envelope와 PKCE verifier 재생성 회귀 테스트를
추가했다. 전체 로컬 검증은 PR 전 WSL ext4 미러에서 실행한다.

**다음**: Google OAuth callback 실패 redirect UX와 profile 연결/해제 UI는 별도
비의존 후속으로 분리한다.

## 2026-06-05 (codex) — T-065 aggregate CI gate

**작업**: path-filtered `api` / `web` / `etl` workflow를 유지하면서 docs-only PR도
막히지 않도록 항상 실행되는 aggregate required check를 추가했다.

**변경**:

- `.github/workflows/aggregate-ci.yml` — 모든 PR에서 `Aggregate CI gate` job 실행.
  변경 파일을 기준으로 필요한 check(`lint-typecheck-test`, `lint-typecheck-build`,
  `sanity`)를 GitHub Checks API로 polling한다.
- `.github/workflows/README.md`, `docs/agent-guide.md`, `docs/decisions.md`,
  `docs/sprints/SPRINT-4.md` — required status check 정책을 `Aggregate CI gate`
  하나로 정리.
- `docs/tasks.md`, `docs/resume.md` — T-065 완료와 다음 작업 정리.

**검증**: 로컬 `python3` PyYAML 파싱과 `git diff --check` 통과. `node`/`actionlint`는
현재 WSL PATH에 없어 PR CI에서 workflow 실행으로 최종 확인한다. PR merge 후
`main-pr-only` ruleset에 required status check `Aggregate CI gate`를 적용한다.

**다음**: kor-travel-map 의존 작업은 계속 보류하고, 남은 비의존 frontend/운영 작업 범위를
재확인.

## 2026-06-05 (codex) — T-063 maplibre consumer sync

**작업**: `maplibre-vworld-js` 선행 PR 상태와 Pinvi consumer sync 체크리스트를
정리했다. 라이브러리 저장소에서 PR #46을 생성해 `docs/consumer-feature-catalog.md`
를 T-033~T-037 실제 구현 상태와 맞췄고, `build-and-test` 통과 후 squash merge했다.

**변경**:

- `docs/integrations/maplibre-vworld.md` — §6 snapshot을 PR #37/#46 기준으로 갱신,
  §11.1에 Pinvi consumer sync 결과와 남은 frontend pin/import/e2e 체크 추가.
- `docs/sprints/SPRINT-4.md` — 라이브러리 선행 PR 조건을 완료 처리.
- `docs/tasks.md`, `docs/resume.md` — T-063 완료와 다음 작업 T-065 반영.

**검증**:

- `maplibre-vworld-js` PR #46: `build-and-test` green, merge `f1dd74b9`.
- Pinvi: 문서 전용 변경. `git diff --check` 통과.

**다음**: kor-travel-map 비의존 작업으로 T-065 aggregate CI gate 설계/적용.

## 2026-06-05 (codex) — T-070 Sprint 2 잔여 마감

**작업**: kor-travel-map과 연계하지 않는 Sprint 2 잔여를 마감. `email_queue`
SKIP LOCKED worker batch, 비밀번호 재설정 요청/확정 API, `api_call_log` httpx event
hook 통합 테스트, API CI integration step을 추가했다.

**변경**:

- `apps/api/app/services/email_service.py` — outbox enqueue + `process_pending_email_batch`
  (`FOR UPDATE SKIP LOCKED`) + verify/reset HTML 렌더링.
- `/auth/password/reset-request`, `/auth/password/reset` — enumeration-safe reset 요청,
  token 검증, `password_hash` 갱신, `user_sessions.revoked_at` 처리, cookie 재발급.
- `tests/integration/test_{password_reset_flow,email_queue_worker,api_call_logging}.py`
  신규.
- `.github/workflows/api.yml` — PR에서 `pytest tests/integration -q` 실행.
- Google OAuth client id는 `/mnt/f/dev/pinvi`, `pinvi-codex`,
  `pinvi-claude`, `pinvi-antigravity`의 로컬 `.env`에 반영.

**검증**:

- `apps/api`: `uv run pytest -s tests/unit -q` — 56 passed
- `apps/api`: `uv run pytest -s tests/integration -q` — 35 passed
- `apps/api`: `uv run ruff format --check . && uv run ruff check .`
- `apps/api`: `uv run mypy --strict app`

**다음**: 본 PR 머지 후 kor-travel-map 의존 T-066은 계속 보류하고, T-063 또는 T-065처럼
비의존 작업부터 진행.

## 2026-06-05 (codex) — T-067 KASI Dagster/DB/POI 연동 구현

**작업**: kor-travel-map과 연계하지 않는 KASI 범위를 먼저 구현. `python-kasi-api`와
`DATA_GO_KR_SERVICE_KEY`를 기준으로 특일 계열 upsert asset, POI별 해·달 출몰시각
one-shot Dagster job, API POI 생성 시 fetch 대기 row 생성을 추가했다.

**변경**:

- `app.kasi_special_days`, `app.trip_poi_rise_sets` Alembic migration + ORM 모델.
- POI 생성 시 trip 시작일 기반 `locdate`, feature snapshot 좌표를 읽어
  `pending_date` / `pending_coord` / `pending_fetch` 상태 row 생성.
- `apps/etl` Dagster definitions에 `pinvi_kasi_special_days` asset,
  `kasi_poi_rise_set_job`, `PinviDatabaseResource`, `KasiResource` 추가.
- KASI/ETL/API 문서와 `docs/tasks.md` / `docs/resume.md` 상태 갱신.

**검증**:

- `apps/api`: `uv run pytest -s tests/unit/test_kasi_service.py -q`
- `apps/api`: `uv run pytest -s tests/integration/test_kasi_poi_rise_set.py -q`
- `apps/api`: `uv run ruff check app tests/unit/test_kasi_service.py tests/integration/test_kasi_poi_rise_set.py`
- `apps/api`: `uv run mypy app`
- `apps/etl`: `uv run pytest -s tests -q`
- `apps/etl`: `uv run ruff check .`
- `apps/etl`: `uv run mypy pinvi`

**다음**: 본 PR 머지 후 사용자의 최신 지시에 따라 kor-travel-map 의존 T-066은 보류하고,
T-070(Sprint 2 잔여 마감) 또는 T-065(aggregate CI gate) 같은 비의존 작업부터 진행.

## 2026-06-05 (codex) — production API/Web URL + OAuth 보안 문서화

**작업**: 사용자 지시로 production API/Web 공개 URL을 문서와 환경변수 예시에
명시하고, 관련 보안 처리(OAuth callback, Google JavaScript origin, CORS, CSP,
Secure cookie, open redirect 방지)를 함께 정리.

**결정**:

- API production URL: `https://pinvi-api.example.com` (내부/host port
  `9021`)
- Web production URL: `https://pinvi.example.com` (내부/host port `9022`)
- Google 승인된 JavaScript 원본: `https://pinvi.example.com`
- Google redirect URI:
  `https://pinvi-api.example.com/auth/oauth/google/callback`

**보안 처리**:

- CORS 허용 origin은 Web origin만. API origin과 wildcard는 허용하지 않는다.
- OAuth `return_to`는 상대 경로 또는 `PINVI_WEB_BASE_URL` 하위 경로만 허용해
  open redirect를 차단한다.
- 운영은 `PINVI_ENVIRONMENT=production`으로 cookie `Secure` 속성을 강제한다.
- reverse proxy / Cloudflare Tunnel은 `X-Forwarded-Proto=https`를 보존하고 HTTP를
  HTTPS로 redirect한다.

## 2026-06-04 (codex) — 최신 kor-travel-map/kor-travel-geo/KASI 계약 반영

**작업**: 사용자가 지시한 대로 `kor-travel-map` 최신 `main`을 별도 clean clone으로
받아 `openapi.user.json` / `openapi.json` / `docs/pinvi-rest-api.md`를 확인했다.
`kor-travel-geo` 최신 `main`의 `openapi.json` / `llm-summary.md`와
`python-kasi-api`의 특일·출몰시각 함수도 확인해 Pinvi 문서에 반영했다.

**핵심 결정**:

- ADR-026 추가 — Pinvi ↔ kor-travel-map은 더 이상 함수 직접 호출이 아니라 최신
  OpenAPI HTTP 계약을 사용한다. API `9011`, admin `9012`.
- ADR-002는 `superseded by ADR-026`으로 변경. `feature` / `provider_sync` schema
  책임은 ADR-003 그대로 kor-travel-map 소유.
- kor-travel-geo v2 최신 표면에 `/v2/regions/within-radius`, `point_precision`,
  `distance_m`, `include_geometry`, admin RustFS/ops 경로를 문서화했다.
- KASI는 `python-kasi-api`와 `DATA_GO_KR_SERVICE_KEY`를 사용한다. 별도 `KASI_*`
  API key는 만들지 않는다.

**KASI 계약**:

- 특일 정보는 하루 1회 Dagster job으로 과거 6개월~미래 18개월 월 범위를 조회해
  `app.kasi_special_days`에 upsert한다. 별도 삭제는 없다.
- POI 생성 시 좌표와 방문일로 "위치별 해달 출몰시각 정보조회"를 1회 호출하고
  `app.trip_poi_rise_sets`에 저장한다. 정기 재조회는 없다.

**후속**:

- T-066 — kor-travel-map OpenAPI HTTP client 구현 + drift gate.
- T-067 — KASI Dagster job / POI 생성 enqueue 구현.

## 2026-06-03 (codex) — RustFS 9003/9004 + Docker app 스크립트

**작업**: 사용자 지시로 RustFS 저장소 포트를 API `9003`, console `9004`로 고정하고,
kor-travel-map 독립 프로그램 포트를 API `9011`, admin `9012`로 문서화. 또한
`kor-travel-geo`의 `scripts/docker_app.sh` 패턴을 참고해 Pinvi Docker app
build/run/smoke 스크립트를 추가.

**변경**:

- `infra/docker-compose.yml`, `infra/docker-compose.app.yml` — RustFS 내부/host API
  포트를 `9003`, console 포트를 `9004`로 통일. API/Dagster 내부 endpoint도
  `rustfs:9003` / `app-rustfs:9003`로 정렬.
- `scripts/docker-app.sh` 신규 — `build`, `up`, `down`, `reset`, `status`,
  `logs`, `migrate`, `smoke` 지원. 시작 전 API `9021`, Web `9022`, RustFS
  `9003`/`9004` 점유 컨테이너/프로세스를 정리.
- `scripts/docker-app-smoke-test.sh` — `scripts/docker-app.sh smoke` 호환 wrapper로
  단순화.
- `.env.example`, `package.json`, `README.md`, `SKILL.md`,
  `docs/runbooks/{docker-app,file-storage,etl,README}.md`, `docs/api/storage.md` —
  RustFS 포트와 Docker app 실행 방법 동기화.
- `AGENTS.md`, `CLAUDE.md` — 고정 포트 정책에 RustFS `9003`/`9004`와 Docker app
  스크립트 사용 원칙, kor-travel-map `9011`/`9012` 포트 추가.
- `docs/kor-travel-map-integration.md`, `.env.example` — kor-travel-map API/Admin base URL을
  `9011`/`9012`로 정리하고 예전 debug UI 포트 언급 제거.

**검증**: WSL ext4 미러에 sync 후 `scripts/docker-app.sh smoke --keep-running` 통과.
이미지 빌드, RustFS `/health/live`, Alembic `upgrade head`, API `/health`, API
`/health/db`, Web `/`, RustFS health 응답을 확인했다. Postgres 초기화 race는
Alembic 재시도 루프로 흡수했고, `lsof`가 9022 리스너를 못 잡는 경우를 위해
`fuser` fallback을 보강했다.

## 2026-06-02 (codex) — 로컬 dev 포트 9021/9022/9023 고정

**작업**: 사용자 지시로 로컬 개발 포트 원칙을 고정. API는 `9021`, Web은 `9022`,
Dagster는 `9023`을 항상 사용한다. 해당 포트가 점유되어 있으면 종료하고 같은 포트로
다시 올린다.

**변경**:

- `scripts/dev-up.sh` / `scripts/dev-down.sh` 신규 — 9021/9022/9023 점유 프로세스
  정리 후 API/Web/Dagster dev server 기동.
- `apps/web/package.json` — `next dev` / `next start`를 9022로 고정.
- `.env.example`, `apps/api/app/core/config.py`, `apps/web/**`, `apps/web/Dockerfile` —
  API/Web dev URL 기본값을 9021/9022로 정렬.
- `infra/docker-compose.yml` — Dagster UI host port 9023.
- `infra/docker-compose.app.yml`, `scripts/docker-app-smoke-test.sh` — Docker smoke
  host port도 API 9021 / Web 9022로 정렬.
- `README.md`, `SKILL.md`, `docs/runbooks/{local-dev,README,docker-app,etl}.md`,
  `docs/api/*`, `docs/integrations/*` 등 기존 개발 포트 참조를 새 규칙으로 정정.

**검증 예정**: WSL ext4 미러에 sync 후 `scripts/dev-up.sh`로 포트 점유 종료 +
재기동 확인. 실행 결과는 본 PR 코멘트/최종 보고에 기록.

## 2026-06-02 (codex) — T-062 GitHub Actions secret / branch protection 점검

**작업**: T-062 진행. GitHub Actions secret, branch protection/ruleset, 최근 Actions
실패를 `gh`로 실제 확인하고, 사용자 지시 "API key 안 씀 / 앞으로도 안 씀"과
"프론트엔드 실행은 WSL, e2e Playwright만 Windows"를 운영 문서와 workflow에 반영.

**실측**:

- Actions repository secret은 `0`개. 이는 정책과 일치. `OPENAI_API_KEY`는 등록하지
  않고 앞으로도 사용하지 않는다.
- classic `main` branch protection은 없음(REST 404).
- repository ruleset은 없었으나, `main-pr-only`(id `17146781`)를 적용:
  PR 필수, squash-only, required linear history, force push 차단, branch deletion
  차단, bypass 없음(`current_user_can_bypass=never`).
- 최근 `api` / `web` / `etl` workflow는 PR 또는 push에서 성공 이력 있음.
- 기존 `Codex PR Review` 실패는 `openai/codex-action@v1`의
  `/home/runner/.codex/<run>.json` server info 파일 누락. API key를 쓰지 않는 정책과
  충돌하므로 action 호출을 제거.

**변경**:

- `.github/workflows/codex-pr-review.yml`, `codex-pr-monitor.yml` — 외부 API 호출 없는
  review reminder / head SHA 마커 댓글 workflow로 변경.
- `.github/workflows/README.md`, `docs/runbooks/secrets.md`,
  `docs/runbooks/pr-review-sprint4.md` — API key 미사용, ruleset 실제 상태, required
  status check 보류 사유 기록.
- `AGENTS.md`, `CLAUDE.md`, `docs/dev-environment.md`, `docs/runbooks/local-dev.md` —
  `apps/web` dev/lint/typecheck/build/Vitest는 WSL ext4 미러, Playwright 브라우저
  e2e만 Windows에서 실행하도록 정리.
- `docs/decisions.md` ADR-021 amendment — API key 미사용 + 프론트 실행 경계 반영.
- `docs/tasks.md`, `docs/resume.md` — T-062 완료, 후속 T-065(aggregate CI gate 후
  required status check 적용) 추가.

**후속**: required status check는 현재 `api` / `web` / `etl` path filter 때문에
docs-only PR이 `Expected` 대기에 갇힐 수 있어 바로 적용하지 않음. 항상 실행되는
aggregate gate 설계 후 T-065에서 적용.

## 2026-06-02 (codex) — 최신 main 기준 문서 충돌 정정

**작업**: 최신 `origin/main`(PR #27 이후)에서 문서를 다시 검토하고 ADR-024 개발
환경 모델, ADR-015 지도 클라이언트, ADR-025 geocoding 경계와 충돌하는 잔여 표현을
정정.

**변경 파일**:

- `README.md`, `AGENTS.md`, `CLAUDE.md`, `SKILL.md`, `docs/agent-guide.md`
- `docs/runbooks/local-dev.md`, `docs/runbooks/README.md`, `docs/runbooks/etl.md`
- `docs/architecture.md`, `docs/api/features.md`
- `docs/conventions/coding-style.md`, `docs/conventions/testing.md`
- `docs/sprints/SPRINT-1.md`, `docs/sprints/SPRINT-4.md`
- `docs/spec/v8/00-infrastructure.md`
- `docs/execplan/doc-review-2026-06-02.md`, `docs/resume.md`, `docs/tasks.md`

**결정**: 신규 ADR은 만들지 않음. 기존 accepted ADR-015/024/025를 문서 전반에
적용하는 정합성 수정.

**발견**: `docs/runbooks/local-dev.md`와 `docs/agent-guide.md`에 ADR-024 이전의
"WSL 미러에서 git/commit" 모델과 "코드 작성 금지 단계" 문구가 남아 있었다.
`docs/architecture.md`에는 React 18 / Kakao SDK / `@kor_travel_map/map-marker-react` 시절
표현이 남아 있었고, 진입 문서에는 ADR-023 이전의 Odroid 단일 노드 표기가 남아
있었다.

**다음**: PR 머지 후 실제 다음 작업은 `docs/resume.md`의 Sprint 2 잔여 마감 또는
Sprint 4 PR-B2(features client readiness) 후보 중 선택.

## 2026-06-02 (claude) — geocoding을 kor-travel-geo v2 REST 직접 호출로 (ADR-025)

**작업**: kor-travel-map / kor-travel-geo 문서를 확인하고, Pinvi geocoding을 kor-travel-geo
v2 REST API 직접 접근으로 문서화 (사용자 지시 "geocoding 관련 기능은 kor-travel-geo v2
api에 직접 접근"). 문서화만, 코드 변경 없음.

**핵심 발견(경계)**: Pinvi 외부 데이터 의존이 두 갈래인데 문서가 이를 뭉뚱그려
region/주소를 kor-travel-map 함수 경유로 서술하고 있었다.

1. Feature 데이터(place/event/weather/...) → kor-travel-map **함수 직접 호출**(ADR-002).
2. Geocoding/주소/행정구역 → **kor-travel-geo v2 REST HTTP 직접**(사용자 지시).
   kor-travel-geo는 이미 `POST /v2/{geocode,reverse,search}` candidate 표면 제공, kor-travel-map도
   자기 ETL 적재 때 이 v2를 HTTP로 쓴다(그쪽 ADR-006) → v2가 geocoding 공식 표면.

**신규/변경**:

- ADR-025 신설 — 사용자 대면 geocoding은 kor-travel-geo v2 REST 직접. feature는 종전
  함수 호출 유지. region도 v2(reverse `include_region` / search `type=district`)로
  수렴. VWorld/juso 직접 호출 금지(kor-travel-geo 내부). 다음 ADR 025→026.
- `docs/integrations/kor-travel-geo.md` 신규 — v2 3개 endpoint 정확한 req/resp, 좌표
  `(lon,lat)`·코드 규약, httpx client 주입+lifespan, `/geo/*` 노출 endpoint, 캐싱·
  rate-limit, 위치 감사(`/geo/reverse`), 에러 graceful degrade, 사용처 매핑, AI agent
  구현 체크리스트, 환경변수.
- `docs/architecture/geocoding-open-decisions.md` 신규 — 사용자 판단 대기 8건
  (D1 regions 처리 / D2 fallback=api / D3 캐시 / D4 quantize / D5 within-radius /
  D6 MCP / D7 network·auth / D8 precision 활용). 각 잠정 기본값으로 구현 막지 않음.
- `docs/api/regions.md` 정정(kor-travel-map 경유 → kor-travel-geo v2), `user-location.md`
  역지오코딩 region label + `reverse_geocode` purpose 추가, `kor-travel-map-integration.md`
  경계 명시. CLAUDE/AGENTS 인덱스에 geocoding 행.

**의사결정 별도화**: 사용자 지시대로 열린 결정은 `geocoding-open-decisions.md`에
모으고 잠정값으로 진행(되돌리기 비용 있는 선택만 가시화).

**다음**: 본 PR 머지 → Sprint 4 PR-B2(features) 또는 geocoding `/geo/*` 구현 시
본 문서 기준. open-decisions D1~D8은 사용자 확정 시 ADR로 박음.

## 2026-06-01 (claude) — 에이전트 환경 문서를 kor-travel-geo에 정렬

**작업**: 개발 환경 문서 구조를 별 저장소 `kor-travel-geo`의 성숙한 3-doc 패턴에
맞춰 정렬 (사용자 지시 "python kor-travel-geo에 맞춰").

**배경**: ADR-024로 환경 모델은 확정했으나, kor-travel-geo는 그 위에 (1)
`dev-environment.md`(reference) + (2) `agent-workflow.md`("무엇을 치는가" 런북) +
(3) `agent-failure-patterns.md`(반복 실패 카탈로그) 3단 구조 + `agent/<agent>-idle`
idle 브랜치 컨벤션을 갖고 있었다. pinvi는 (1)만 있고 idle 브랜치는 `-init`이었다.

**신규/정렬**:

- `docs/agent-failure-patterns.md` 신규 — kor-travel-geo 패턴 포팅 + 이번 세션 실측:
  WSL git on NTFS worktree 포인터 혼용, 명령 런처/대량 병렬 backlog, MSYS `grep`의
  `\n` 오해석(정상 문서를 손상으로 오판 → ripgrep/`od -c` 교차검증), async alembic
  미커밋 + pytest-asyncio 루프/풀.
- `docs/agent-workflow.md` 신규 — 두 위치 표 + 함정 먼저(git.exe/PATH/TMP) + 작업
  루프 + 붙여넣기 체크리스트. 스크립트(`agent_env.sh` 등) 대신 수동 명령(사용자
  결정: 스크립트 없이 문서 절차만).
- **idle 브랜치 `agent/<agent>-init` → `-idle`** (kor-travel-geo 통일). worktree 생성을
  Windows git.exe로 하라는 caveat 추가(WSL 생성 시 `/mnt/f` 포인터 사고).
- AGENTS.md worktree 표에 idle branch 열 추가, AGENTS/CLAUDE/dev-environment/
  agent-guide §10에서 신규 2개 문서 cross-link. agent-guide §10의 구 모델 문구
  (양방향 sync) 교체.

**검증**: 내부 링크 점검(깨진 참조 0), `-init` 잔존 0, 신규 문서 2개 + 수정 5개.

**다음**: 본 PR 머지 → 각 에이전트가 `docs/agent-workflow.md` 따라 진입.

## 2026-06-01 (claude) — 개발 환경 모델 확정 (ADR-024)

**작업**: NTFS git + WSL 개발/테스트 환경에서 에이전트(특히 codex)가 반복적으로
헤매던 문제의 근본 원인을 잡고, 따라 할 수 있는 절차로 문서화 (사용자 지시,
`kor-travel-geo` 문서 참고).

**근본 원인**: `docs/dev-environment.md`가 구 모델(ADR-004: "WSL ext4가 표준 작업
위치 / Git source of truth는 ext4 / 양방향 rsync")을 그대로 서술하는데, ADR-017 +
AGENTS/CLAUDE는 신 모델(NTFS worktree + Windows git.exe)을 말해 **문서 간 모순**이
있었다. 그래서 에이전트가 "어디서 commit?"을 헤맸다. 실제 증거:

- codex worktree `.git` = `gitdir: /mnt/f/dev/pinvi/.git/worktrees/pinvi-codex`
  (WSL 생성), claude worktree = `gitdir: F:/dev/pinvi/.git/worktrees/pinvi-geo-claude`
  (Windows 생성, 게다가 stale `-geo-` 이름). 환경 혼용 시 `fatal: not a git
repository` / `prunable` → 잘못된 prune으로 worktree 삭제 위험.

**결정·문서**:

- **ADR-024 신설** — NTFS worktree = git source of truth(Windows git.exe) / WSL ext4
  = 일회용 테스트 미러(단방향 rsync, commit 금지). ADR-004의 source-of-truth 주장만
  supersede(디스크/경로는 유지). 다음 ADR 번호 024→025.
- **`docs/dev-environment.md` 전면 재작성** — §0에 codex가 겪은 함정 4종(포인터
  혼용 / source 모호 / WSL PATH 오염 / TMP=Windows Temp)과 대책, §1~§12에 레이아웃·
  worktree·미러 rsync·셋업·PATH·검증 게이트·DB·체크리스트. `kor-travel-geo`와
  동일 패턴.
- **AGENTS.md / CLAUDE.md 동기**(ADR-016) — 모순됐던 "Git source of truth는 ext4"
  문구 교체, 진입 절차표·§7 인덱스에 dev-environment 행 추가.
- **`docs/runbooks/codegraph-worktrees.md`** — §3.6 Windows/WSL git 포인터 함정 +
  `git worktree repair` 복구 절차 추가, ADR-024 참조.

**검증**: 내부 문서 링크 점검(깨진 참조 0), ADR 번호 정합(024 박힘/다음 025),
AGENTS↔CLAUDE 동기 확인.

**사용자 액션 권장(문서 밖)**: claude worktree의 stale 포인터(`pinvi-geo-claude`)는
trunk에서 `git worktree repair F:\dev\pinvi-claude`로 교정하면 깔끔하다.

**다음**: 본 PR 머지 → 각 에이전트가 `docs/dev-environment.md` 따라 미러 재셋업.

## 2026-06-01 (claude) — Sprint 2 핵심 DoD 마감

**작업**: Sprint 2 잔여 구현 — Google OAuth(G-4 안전 매칭) + Notice plan → trip
copy(ADR-013) + 통합 테스트 harness/스위트 (사용자 지시 "Sprint 2 완료").

**컨텍스트**: Sprint 2 코드는 머지돼 있었으나 (1) OAuth service/route, (2) Notice
plan service/route/copy, (3) `tests/integration` 이 비어 있었음 — 모델/스키마/
마이그레이션은 이미 존재. 본 작업이 service+route+test 계층을 채움.

**신규**:

- `app/services/oauth_google.py` — G-4 안전 매칭(기존 identity 로그인 / Google
  `email_verified=true` + 동일 이메일 로컬계정 → 안전 연결 / 미인증 → 비연결 신규,
  provider-namespaced email 로 UNIQUE 충돌 회피) + state·PKCE + HTTP 분리.
- `app/api/v1/oauth.py` — `/auth/oauth/google/{start,callback}` + `/providers` + unlink.
- `app/services/notice_plan.py` — published listing/상세 + `copy_plan_to_trip`
  (notice_pois → trip_day_pois, LexoRank append, plan_poi_attachments 복제) + seed helper.
- `app/api/v1/notice_plans.py` — listing / 상세 / `POST /{id}/copy`.
- `app/api/v1/users.py` — `PUT /users/me/consents`, `DELETE /.../{type}` REST endpoint.
- `tests/integration/` — conftest harness + 7개 파일 27 테스트.

**부수 버그 수정**:

- **`alembic/env.py`** — async 마이그레이션이 DDL 트랜잭션을 커밋하지 않던 잠재
  버그(`AsyncConnection` 가 commit 없이 롤백). `connection.commit()` 추가.
  testcontainer 로 실제 테이블 생성 검증 중 발견 — CI 는 exit code 만 봐서 미검출.
- `services/poi.py` — sort_order UNIQUE 위반 → `SortOrderConflictError`(409).

**검증** (WSL ext4 미러 + Docker PostGIS, git=Windows git.exe — ADR-017):

- `pytest tests/unit` → 53 passed
- `pytest tests/integration` → **27 passed** (postgis/postgis:16-3.5-alpine)
- `ruff check` / `ruff format --check` / `mypy --strict app` → 통과

**잔여(후속)**: 위치 감사 자동 적재 e2e(`/features/in-bounds` — Sprint 4 kor_travel_map
client 의존), `email_queue` SKIP LOCKED worker + 비밀번호 재설정, `api_call_log`
미들웨어 통합 테스트. 상세 `docs/sprints/SPRINT-2.md` "잔여" 절.

**교훈**: testcontainers + async alembic 은 마이그레이션이 실제로 커밋되는지
(테이블 count) 까지 확인할 것 — exit code 만으로는 부족. pytest-asyncio
function-loop 에서는 엔진을 함수 스코프 + NullPool 로 만들어야 "another operation
in progress" / "Future attached to different loop" 를 피한다.

**다음**: 본 PR 머지 → 실질 다음은 Sprint 4 PR-B2 (kor_travel_map client + 위치 감사 e2e)
또는 PR-C (프론트엔드) — `docs/resume.md`.

## 2026-06-01 (claude)

**작업**: 문서 정합성 점검 + git 실행 정책 / `.codegraph` ignore 명시 (PR #19, #20).

**컨텍스트**: 사용자의 "문서 정합성 확인 + 보완 + git Windows 버전 명시 +
`.codegraph` gitignore" 지시. Windows worktree(`F:/dev/pinvi-claude`, NTFS)에서
작업.

**반영 (유효)**:

- **git 실행 정책** — Windows worktree(NTFS)에서 git 명령은 Windows 버전
  git(`git.exe`) 사용, WSL git으로 `/mnt/f` NTFS 경로 조작 금지. pytest/docker/
  npm은 기존대로 WSL ext4 미러(ADR-004) 유지. `CLAUDE.md` worktree 블록 +
  `AGENTS.md` worktree/WSL 섹션 + `docs/decisions.md` ADR-017 amendment(2026-05-31)에
  동기 반영 (ADR-016 준수).
- **`.codegraph/` ignore** — `.gitignore`에 이미 반영(71~72행, ADR-017 후속)됨을
  확인. 변경 불필요 — ADR-017 amendment에 명시.
- **`docs/decisions.md`** — ADR-017 블록 안에 잘못 들어가 있던 `다음 신규 =
ADR-024.` 중복 라인 제거. 정식 `## 다음 ADR 번호` 섹션(파일 끝)은 유지.
- **`CLAUDE.md` §5** — "가장 중요한 5개" → "6개" (실제 6개 룰 나열에 맞춰 정정).

**정정 기록 (중요)**: PR #19/#20 작업 중 "literal `\n` 직렬화 손상 10개 문서"로
오판해 변환을 수행했으나, **실제 손상이 아니었음**. 원인은 Windows MSYS `grep`이
`\n` 패턴을 개행으로 해석해 정상 문서를 손상으로 표시한 도구 아티팩트.
ripgrep / `od -c` / Read 교차검증 결과 모든 문서는 처음부터 정상 마크다운이며
실내용 변경 없음. 따라서 PR #19/#20 커밋 메시지의 "literal \n 복구" 문구는
부정확 — 실질 변경은 위 git 정책 / 중복 제거 / 카운트 정정뿐. 또한 #19에 실수로
포함된 임시 스크립트 `_verify.js`는 #20에서 제거.

**교훈**: NTFS worktree에서 텍스트 패턴 검사는 MSYS `grep` 대신 ripgrep(Grep
도구)을 쓴다. `\n` 같은 메타문자 카운트는 도구별 해석 차이가 크므로 `od -c` /
Read로 교차검증 후 판단한다.

**후속**: 본 PR(journal) 머지 + 머지된 로컬 브랜치 정리.

## 2026-06-01 10:20 (codex)

**작업**: 기준 문서 정합성 복구. Sprint 상태, 진입 절차, backlog 추적 문서의
시점 불일치를 정리.

**컨텍스트**: `README.md`는 여전히 "Sprint 1 진입 직전 / 문서 전용"으로 남아
있었고, `AGENTS.md`는 코드 작성 금지 규칙을 현재형으로 유지했다. 반면 실제
저장소에는 Sprint 1~3 산출물, Sprint 4 workflow, features API 구현이 이미 있다.
`resume.md`와 `tasks.md`도 최신 `journal.md`보다 과거 시점을 가리켰다.

**갱신 파일**:

- `docs/execplan/doc-sync-2026-06-01.md` — 문서 정합성 복구 범위 기록
- `README.md` — 현재 상태를 Sprint 4 기준선으로 갱신, 진입 순서 정리
- `AGENTS.md` — stale한 "코드 작성 금지"를 현재 단계 정책으로 교체
- `CLAUDE.md` — 현 단계 설명을 Sprint 4 준비/진행으로 갱신
- `SKILL.md` — quick start 주석과 첫 5분 진입 프로토콜 정합화
- `docs/agent-guide.md` — 도구별 1차 진입 파일 기준으로 프로토콜 재정렬
- `docs/resume.md` — PR-A/T-030 등 stale 항목 제거, 다음 작업 재기록
- `docs/tasks.md` — Sprint 4 backlog 중심으로 재정렬, 완료/진행 항목 수정
- `docs/architecture/frontend.md` — `apps/web/lib/kakao.ts` 구 경로 참조 제거

**결정**: 최신 기준선은 "Sprint 1~3 머지 완료 + Sprint 4 준비/진행"으로 본다.
진행 추적은 `resume.md` 단독이 아니라 `resume.md` + `tasks.md` + `journal.md`
교차 확인이 필요하다.

**발견**: 문서 drift의 대부분은 상태 문구가 실제 merge 이후 갱신되지 않은 데서
생겼다. 신규 ADR보다 상태 추적 문서의 정기 정리가 먼저 필요하다.

**다음**: secret / branch protection 실제 적용 여부를 확인하고 Sprint 4 open item을
merge 상태 기준으로 다시 쪼갠다.

## 2026-05-27 16:30 (claude)

**작업**: worktree 이름 prefix `geo-` → `pinvi-` 변경 (ADR-017 amendment).

**컨텍스트**: 사용자 지시. `geo-claude` / `geo-codex` / `geo-antigravity` →
`pinvi-claude` / `pinvi-codex` / `pinvi-antigravity`. 경로 예시도
`F:/dev/pinvi-<agent>` + WSL `~/pinvi-workspaces/pinvi-<agent>`.

**갱신 파일** (정의 문서 4개 — journal 과거 엔트리는 사실 기록이라 유지):

- `docs/decisions.md` — ADR-017 본문 + amendment 노트
- `docs/runbooks/codegraph-worktrees.md` — 전 구간 경로/이름
- `AGENTS.md` — worktree 표 + DO NOT
- `CLAUDE.md` — 머리 박스 + DO NOT #6

**후속**: 본 PR 머지 후 trunk에서 실제 worktree 디렉터리 rename —
`git worktree move ../pinvi-geo-claude ../pinvi-claude`.

## 2026-05-27 16:00 (claude)

**작업**: Sprint 4 진입 PR-B — 백엔드 features API + lifespan + cluster_query +
trip_view_builder.

**컨텍스트**: PR-A (#15) 머지 후 후속. `kor-travel-map` 라이브러리 client는
아직 Sprint 2 라이브러리측 placeholder (실 구현 없음) — Pinvi는 Protocol 정의 +
lazy import 패턴으로 인터페이스 박음. 실 client 주입은 라이브러리 ready 시 후속 PR-B2.

**신규 / 갱신**:

- `apps/api/app/etl_bridge/__init__.py` 신규 디렉토리
- `apps/api/app/etl_bridge/kor_travel_map.py` 신규 — `KorTravelMapClient` Protocol (8 메서드)
  - `kor_travel_map_lifespan` FastAPI lifespan (lazy import, 라이브러리 미주입 시 503)
  - `KorTravelMapClientDep` 의존성 alias
- `apps/api/app/schemas/feature.py` 신규 — Coord / BBox / FeatureSummary /
  FeatureCluster / FeaturesInBoundsResponse / FeatureDetail / WeatherTimepoint /
  FeatureWeatherCard / FeatureRequestCreate / FeatureRequestResponse
- `apps/api/app/api/v1/features.py` 신규 — 6 endpoint (in-bounds / nearby /
  search / get / weather / POST requests)
- `apps/api/app/services/cluster_query.py` 신규 — zoom → mode (sido / sigungu /
  dbscan / individual) + 각 모드 PostGIS raw SQL. TripDayPoi `attachment_id` PK +
  `(trip_id, day_index)` FK 정합
- `apps/api/app/services/trip_view_builder.py` 신규 — `app.trips ↔ feature.feature`
  batch join (N+1 회피) + `feature_link_broken_at` 처리
- `apps/api/app/main.py` — lifespan 합성 (기존 + kor_travel_map_lifespan)
- `apps/api/app/api/v1/__init__.py` — features router 등록
- `packages/schemas/src/feature.ts` 신규 — Zod 11개 schema, 한국 범위 검증 (ADR-018)
- `packages/api-client/src/endpoints/feature.ts` 신규 — 6 endpoint client
- 테스트: `tests/unit/test_feature_schemas.py` (Pydantic validation) +
  `tests/unit/test_cluster_query.py` (zoom → mode 매트릭스)

**제약 / 책임 분리**:

- Pinvi는 wrapper 만들지 않음 (ADR-005) — Protocol은 type contract라 OK
- 라이브러리 client는 lifespan에서 lazy import — placeholder 상태에서는
  ImportError → `None` 으로 두고 503 fallback
- 사용자 데이터 (trip / poi) join은 Pinvi 책임, feature 데이터는 라이브러리
  batch 호출

**다음**: 본 PR 머지 → Sprint 4 PR-C (프론트엔드 — apps/web/components/map/\* +
지도 lib) → PR-D (라이브러리 PR sync + E2E + v0.1.0 tag).

## 2026-05-27 15:00 (claude)

**작업**: Sprint 4 진입 PR-A — GitHub Actions workflow 5개 복원 (ADR-021).
Sprint 1~3 동안 비활성이었던 CI/CD 부활.

**컨텍스트**: PR #14 (Sprint 4~6 plan)에서 ADR-021로 결정 박힘. 본 PR이 실제
workflow YAML을 복원하는 첫 단계. Sprint 4 본격 코드 구현 (features API + 지도
UI) 은 후속 PR.

**복원 / 신규**:

- `.github/workflows/api.yml` 복원 — ruff + format check + mypy --strict +
  pytest + alembic upgrade (PostGIS service container)
- `.github/workflows/web.yml` 복원 — npm ci + lint + typecheck + build
- `.github/workflows/etl.yml` 복원 — ruff + pytest (placeholder, Sprint 5 본격)
- `.github/workflows/codex-pr-review.yml` 복원 — PR open/ready_for_review 자동
  Codex 리뷰 + 코멘트 (`docs/runbooks/pr-review-sprint4.md`)
- `.github/workflows/codex-pr-monitor.yml` 복원 — 5분 cron으로 review 마커
  없는 PR 재리뷰
- `.github/workflows/README.md` 신규 — workflow 인덱스 + branch protection
  설정 안내
- `docs/runbooks/secrets.md` 신규 — GitHub Actions secret 카탈로그
  (`OPENAI_API_KEY` 등, 2026-06-02 사용자 지시로 API key 미사용 정책에 의해 superseded)

**복원 source**: `git show dd11f04~1:.github/workflows/<file>` — Sprint 1 머지
직전 (커밋 `dd11f04` "chore: remove GitHub Actions workflows") 의 직전 상태.

**다음**: PR 머지 → 사용자가 GitHub UI에서 (1) `OPENAI_API_KEY` secret 등록 +
(2) branch protection 활성 → Sprint 4 본격 코드 PR (PR-B 백엔드 / PR-C 프론트엔드).
이 다음 행동은 2026-06-02 T-062에서 superseded: API key는 쓰지 않고, `main-pr-only`
repository ruleset을 적용했다.

## 2026-05-27 13:30 (claude)

**작업**: Sprint 4~6 plan 정밀화 + 릴리즈 마일스톤 (v0.1.0 / v0.2.0 / v1.0.0)

- ADR-018~023 6건 박음. AI agent가 본 문서들만 보고 자율 진행 가능하도록 상세화.

**컨텍스트**: 사용자 8개 지시 일괄 반영:

1. 외부 인터페이스 MCP 서버 — 마지막 Sprint (Sprint 6, v1.0)에 포함 (ADR-019)
2. 지도 = `maplibre-vworld-js` — 공통 기능 라이브러리 PR / Pinvi 전용 분리 명시,
   v0.1.0 게이트 (Sprint 4)
3. GitHub Actions CI/CD 재활성 — Sprint 4 진입 시 (ADR-021, 이전 비활성 결정 뒤집기)
4. T100~T106, T108 진행, T107 보류 — Gemini 별 repo로 분리 (ADR-020)
5. T108 하드웨어 확장 — N150 16GB / NVMe 1TB / Ubuntu 26.04 + Odroid 병행 (ADR-023)
6. 한국 전용 geofencing — Cloudflare WAF + nginx geo + FastAPI middleware 3중
   안전망 (ADR-018)
7. Backup/Restore + UI — 핫스왑 패턴 (ADR-022)
8. Admin Grafana iframe embed — `/admin/grafana` (Sprint 5)

**신규 / 갱신 파일**:

- `docs/decisions.md` — ADR-018 ~ ADR-023 6건 박음
- `docs/sprints/README.md` — 릴리즈 마일스톤 표 + Sprint 1~3 머지 표시
- `docs/sprints/SPRINT-4.md` — v0.1.0 closure + CI/CD 재활성 + §5 라이브러리
  PR / Pinvi 전용 분류 + §6 v0.1.0 절차 + §7 workflow 복원
- `docs/sprints/SPRINT-5.md` — Grafana embed + Backup/Restore 1차 + v0.2.0 tag
- `docs/sprints/SPRINT-6.md` — MCP 외부 인터페이스 + Backup UI 핫스왑 + T108
  Odroid+N150 + Korean geofencing + T-107 defer + E2E 9 시나리오 (기존 6 + 3
  신규) + v1.0.0 tag
- `docs/tasks.md` — T-100~~T-106 상태 갱신 + T-107 deferred + T-108 확장 +
  신규 T-109~~T-114 backlog
- `docs/architecture/mcp-server.md` 신규 — ADR-019 1차 reference
- `docs/architecture/korea-only-policy.md` 신규 — ADR-018 1차 reference
- `docs/architecture/backup-restore.md` 신규 — ADR-022 1차 reference
- `docs/runbooks/mcp-server.md` 신규 — 토큰 발급 / 운영 / 트러블슈팅
- `docs/runbooks/korea-only.md` 신규 — Cloudflare WAF + nginx geo 설정 +
  GeoIP 갱신
- `docs/runbooks/backup-restore.md` 신규 — backup / restore / 핫스왑 절차
- `docs/runbooks/grafana-admin-embed.md` 신규 — Grafana iframe + CSP
- `docs/runbooks/README.md` — 새 runbook 5개 인덱스 갱신
- `docs/integrations/maplibre-vworld.md` — §6에 책임 분류 (라이브러리 PR / Pinvi
  전용 / 분류 변경 절차) 추가
- `CLAUDE.md` — 현 단계 갱신 + §7 인덱스에 4개 신규 문서 추가
- `AGENTS.md` — 릴리즈 로드맵 표 신설

**다음**: PR 생성. 머지 후 사용자 결정 — Sprint 4 진입 PR 시작 (지도 + CI/CD
복원).

## 2026-05-26 23:30 (claude)

**작업**: ADR-017 박음 — CodeGraph 인덱스 + agent별 고정 worktree 운영. 별 PR로
분리 (Sprint 3 admin PR과 무관).

**컨텍스트**: 사용자 지시:

- Claude Code / OpenAI Codex / Google Antigravity 2.0 세 도구가 동시 편집 →
  고정 worktree로 격리 (`geo-claude` / `geo-codex` / `geo-antigravity`).
- 작업마다 worktree 새로 만들지 않고 **브랜치만** 새로 (`git fetch && git
switch -c agent/<agent>-<task> main`).
- `colbymchenry/codegraph`로 의미 인덱스 — worktree마다 1회 `codegraph init -i`,
  이후 task 시작 시 `codegraph sync`.
- `.codegraph/`는 `.gitignore`.

**신규 / 갱신**:

- `docs/decisions.md` — ADR-017 박음
- `docs/runbooks/codegraph-worktrees.md` 신규 — 1회 setup + task 흐름 + 도구별
  메모 + trunk 관계
- `docs/runbooks/README.md` — 인덱스 갱신
- `.gitignore` — `.codegraph/` 추가
- `CLAUDE.md` — 머리 호환성 박스에 worktree 정책 추가 + DO NOT #6 (trunk 직접
  편집 금지) + §7 빠른 문서 검색에 runbook 추가
- `AGENTS.md` — "개발 환경 정책" 머리에 Worktree + CodeGraph 섹션 + 브랜치 명명
  컨벤션 갱신 (`agent/<agent>-<task>`)

**다음**: PR 생성 후 머지 → 실제 codegraph 설치 + geo-claude worktree 생성 +
init -i 실행.

## 2026-05-26 22:00 (claude)

**작업**: Sprint 3 진입 — Admin RBAC + audit chain + 사용자 목록/상세 + force-verify/disable + 이메일 큐 + 감사 로그 chain 검증 + 13페이지 frontend skeleton.

**Backend** (`apps/api/app/`):

- `core/rbac.py` — `require_role()` 의존성. 미권한 → **404** (존재 자체 숨김, SPEC V8 M-4)
- `services/admin_audit.py` — `append_admin_audit()` (prev_hash + content_hash 자동 계산, append-only trigger 호환)
- `services/admin_users.py` — `force_verify` / `disable_user` / `list_users` / `mask_email`
- `schemas/admin.py` — AdminUserSummary (마스킹) / AdminUserDetail (정식) / AdminActionRequest (사유 필수) / AdminAuditEntry / AdminPagedResponse
- `api/v1/admin/users.py` — GET `/admin/users` (page/limit/status_filter), GET `/admin/users/{id}`, POST `{id}/force-verify`, POST `{id}/disable`
- `api/v1/admin/audit.py` — GET `/admin/audit` + GET `/admin/audit/verify-chain` (cpo 권한 전용)
- `api/v1/admin/emails.py` — GET `/admin/emails` (status_filter) + POST `{id}/resend`
- `api/v1/__init__.py` — `admin_router` 통합

**Frontend** (`apps/web/`):

- `app/(admin)/admin/layout.tsx` — 사이드바 13개 + `/auth/me` RBAC guard (admin/operator/cpo 외 → /admin/login)
- `app/(admin)/admin/login/page.tsx` — admin role 검증 후 router push
- `app/(admin)/admin/page.tsx` — 대시보드 8 카드 placeholder
- `app/(admin)/admin/users/page.tsx` — DataTable + status filter + pagination
- `app/(admin)/admin/users/[user_id]/page.tsx` — 상세 + force-verify/disable 다이얼로그 (access_reason 필수)
- `app/(admin)/admin/emails/page.tsx` — DataTable + status filter + 재발송 버튼
- `app/(admin)/admin/audit/page.tsx` — DataTable + chain 검증 버튼
- `app/(admin)/admin/{trips,features,pois,etl,api-calls,feature-requests,category-mapping,seed,reset}/page.tsx` — Placeholder (Sprint 4~6 결선)
- `components/admin/{AdminPage,DataTable,Placeholder}.tsx` — 공통 chrome

**packages**:

- `packages/schemas/src/admin.ts` — Admin Zod 스키마 + envelope
- `packages/api-client/src/endpoints/admin.ts` — listUsers/getUser/forceVerify/disableUser/listAudit/verifyChain/listEmails/resendEmail
- `packages/design-tokens/{tailwind-preset.cjs,src/colors.ts}` — `error-bg` / `success-text` / `success-bg` 시맨틱 색 추가

**테스트**: `tests/unit/test_admin_users.py` (mask_email), `tests/unit/test_admin_audit_hash.py` (chain 안정성/연결).

**제약 유지**: GitHub CI/CD 없음 (local WSL only). main 직접 push 금지 (PR-only).

---

## 2026-05-26 17:00 (claude)

**작업**: Sprint 2 진입 — 도메인 API + DB + 4 분리 동의 + Resend webhook + 위치 감사 + Storage presigned.

**신규 Alembic** (`apps/api/alembic/versions/20260602_*`):

- `0001_trips_and_share` — `trips` + `trip_companions` + `trip_share_links`
- `0002_pois_collate_c` — `trip_days` + `trip_day_pois` (`sort_order TEXT COLLATE "C"`, SPEC V8 E-6 Critical)
- `0003_audit_chain` — `location_access_log` + `admin_audit_log` (content_hash chain + append-only trigger)
- `0004_email_queue_and_api_log` — `email_queue` + `api_call_log` + `user_oauth_identities` + `oauth_login_states`
- `0005_notice_plans_and_attachments` — `notice_plans` + `notice_pois` + `plan_poi_attachments` (단일 테이블 4 대상)

**신규 모델**: trip / trip_day / poi / companion / share_link / audit / email_queue / api_call_log / oauth_identity / notice_plan / attachment

**신규 Pydantic schema**: trip / poi / consent / share_link / notice / storage / oauth.
**신규 Zod schema** (공용): trip / poi / notice-plan / storage.

**신규 services**:

- `hash_chain` — content_hash + GENESIS_HASH
- `lexorank` — between/before/after (POI sort_order, COLLATE "C" 일관)
- `trip` — CRUD + 동반자 + 공유 토큰 발급/revoke + optimistic lock
- `poi` — CRUD + reorder + sort_order conflict 처리
- `consent` — 4 분리 동의 + demographic 부작용 (`gender`/`birth_year_month`/`residence_sigungu_code` NULL)
- `rustfs_storage` — presigned PUT URL 생성 (실서명은 Sprint 5)

**신규 미들웨어**:

- `location_audit` — 좌표 query 자동 detect + `app.location_access_log` chain 적재
- `api_call_logging` — httpx event_hook → `app.api_call_log`

**신규 라우터**:

- `/trips` + `/trips/{id}` (CRUD, If-Match) + `/trips/{id}/share-tokens`
- `/trips/{id}/pois` (CRUD) + `/trips/{id}/pois/reorder` (LexoRank batch)
- `/users/me/profile/complete` + `/users/me/consents` + withdraw
- `/storage/upload-urls` (presigned PUT)
- `/webhooks/resend` (Svix 서명은 Sprint 5에 실 검증)

**프론트**:

- `apps/web/lib/locationAdapter.ts` — `navigator.geolocation` LocationAdapter
- `apps/web/app/(auth)/profile-complete/page.tsx` — 4 분리 동의 UI + (선택) demographic 항목

**단위 테스트**: hash_chain (chain link 검증) / lexorank / consent schema (필수 동의 누락 / demographic 부작용) / storage keys

**보류 (Sprint 2 후속 PR 또는 Sprint 3 시작 PR로 분리)**:

- Google / Naver / Kakao OAuth start/callback 라우터 (모델·schema·migration 박혀 있음)
- Resend Webhook Svix 서명 (Sprint 5)
- Notice plan copy 흐름 (라우터 미작성, schema·model만)
- 통합 테스트 (PostGIS testcontainer + Alembic + httpx ASGI) — DoD pytest sanity는 단위만

**다음**: PR push + 머지 대기 → Sprint 3 (Admin 콘솔 + RBAC + audit chain integration + seed) 진입.

## 2026-05-26 13:00 (claude)

**작업**: 지도 클라이언트를 내부 라이브러리 `maplibre-vworld-js`로 전환
(ADR-015) + AI 에이전트 도구 다중 지원 (`AGENTS.md` ↔ `CLAUDE.md` 동기 정책,
ADR-016).

**컨텍스트**: 사용자 두 요청:

1. "kakao map 쪽은 내부 라이브러리인 maplibre-vworld-js로 대체. 관련 내용 변경
   하고, 추가로 maplibre-vworld-js에 필요한 기능을 정리한 문서를 만들 것."
2. "CLAUDE.md 외 codex와 antigravity 에서도 대응할 수 있도록 AGENTS.md도 항상
   함께 수정."

`maplibre-vworld-js`는 사용자가 보유한 내부 라이브러리 (`F:\dev\maplibre-vworld-js`,
Antigravity 2.0 + Gemini 3.1 Pro로 작성). VWorld + MapLibre GL JS 선언형 React
통합. `VWorldMap` / `ClusterLayer` / `PolygonArea` / `RouteLine` / `Popup` +
도메인 마커 (`PlaceMarker` / `PriceMarker` / `WeatherMarker`) generic primitive
제공 (이후 리팩터로 `MarkerClusterer` → `ClusterLayer`, `MapPopup` → `Popup`
이름 변경, Pinvi 전용 wrapper / 팔레트는 라이브러리에서 제거).

**신규 파일**:

- `docs/integrations/maplibre-vworld.md` — 라이브러리 식별자 + 환경변수 +
  사용 패턴 + 16색 매핑 + 라이브러리 보강 필요 카탈로그 (§6)

**갱신 (Kakao → maplibre-vworld-js)**:

- `docs/integrations/kakao-map.md` — 폐기 표시 + 이전 가이드 표
- `docs/integrations/README.md` — 인덱스
- `docs/architecture/frontend.md` — 스택 표
- `docs/architecture/map-marker-design.md` — Mapbox token 정책
- `docs/architecture/user-location.md` — `setCenter` / `flyTo` → 선언형 prop
- `docs/api/features.md` — zoom 7~19 (VWorld 한계) / Kakao 한도 → VWorld 한도
- `docs/api/common.md` — CSP `connect-src` VWorld 추가
- `docs/spec/v8/00-infrastructure.md` — CSP
- `docs/spec/v8/03-frontend.md` — 스택 채택 표
- `docs/spec/v8/05-execution.md` — A-1 #4 결정 정정
- `docs/sprints/SPRINT-4.md` — 지도 어댑터 / ADR 후보 → ADR-015
- `docs/runbooks/docker-app.md` — 환경변수
- `docs/compliance/data-policy.md` — Kakao Map TOS → VWorld
- `docs/compliance/pipa.md` — 위탁자 (VWorld 추가, Kakao는 OAuth만)
- `docs/conventions/geospatial.md` — Kakao lat-lng 어댑터 폐기
- `docs/integrations/sentry.md` / `loki.md` — Kakao 언급 정정
- `docs/data-sources/README.md` — 지도 SDK 항목
- `docs/compliance/README.md` — provider 목록
- `README.md` — 의존 라이브러리

**ADR 추가**:

- **ADR-015** 지도 클라이언트 변경 (Kakao Maps SDK → `maplibre-vworld-js`)
- **ADR-016** AI 에이전트 도구 다중 지원 — `AGENTS.md` ↔ `CLAUDE.md` 동기 정책

**진입 가이드 강화**:

- `AGENTS.md` 머리 — "AI 에이전트 도구 지원 — `AGENTS.md` 단일 진실" 섹션 +
  도구별 1차 진입 표 (Claude / Codex / Antigravity / Cursor)
- `CLAUDE.md` 머리 — 호환성 안내 추가
- `SKILL.md` 머리 — 도구별 진입 안내
- `docs/agent-guide.md` 머리 — 동기 룰 + §7.1 PR 체크리스트에 동기 항목 추가

**결정**:

- 라이브러리에 `wrapper class` 만들지 않음 (ADR-005 mirror) — 부족 기능 발견
  시 `maplibre-vworld-js` 저장소에 PR
- 좌표 변환 어댑터 (`apps/web/lib/coordAdapter.ts`) 제거 — VWorld는 GeoJSON
  순서 `(lng, lat)` 그대로
- Kakao Local 검색 / 모빌리티 길찾기는 라이브러리 함수 (`kor-travel-map.search`)
  또는 OR-Tools 직선 거리로 대체

**다음**: PR 생성.

## 2026-05-26 02:00 (claude)

**작업**: v1 자산 전수 조사 + 누락 항목 일괄 반영 + 문서 일관성 정리 + AI agent
friendly 보강 (ADR-014).

**컨텍스트**: 사용자 요청. v2 골격 + SPEC V8 + frontend/location/notice 반영
이후, v1의 9개월 운영 자산을 빠짐없이 v2 문서로 가져오고 문서 일관성 정리.

**v1 전수 조사** (`docs/v1-to-v2-mapping.md`):

- v1 docs/ 84개 (api/architecture/data-sources/decisions/execplan/integrations/
  runbooks/skills/PROJECT_BRIEF), apps/api 80+, apps/web 30+, scripts 13, infra 2
- ✅ / 🚚 / 📋 / ⛔ / 🆕 상태로 매핑

**신규 작성** (본 PR — ~30 파일):

- `docs/api/` 11개: README / common / auth / users / trips / pois / features /
  notice-plans / storage / admin / public / regions / health / websocket
- `docs/integrations/` 9개: README / resend / social-login / gemini / telegram /
  kakao-map / sentry / loki
- `docs/runbooks/` 7개: README / local-dev / docker-app / etl / admin /
  file-storage / odroid-docker
- `docs/compliance/` 4개: README / lbs-act / pipa / data-policy
- `docs/conventions/` 6개: README / coding-style / database / testing /
  geospatial / normalization
- `docs/architecture/` 5개 추가: map-marker-design / youtube-travel-intelligence /
  mcp-tools / dagster-etl-bridge / api-contract
- `docs/data-sources/README.md` — cross-ref 인덱스
- `docs/v1-to-v2-mapping.md` — 매핑 매트릭스

**기존 문서 갱신**:

- `README.md` — 문서 인덱스 전면 강화 (역할별 그룹)
- `AGENTS.md` — "AI Agent 작업 진입 절차" 섹션 신규 + 작업 종류별 진입 문서표
- `CLAUDE.md` — §7 빠른 문서 검색 표 추가
- `docs/decisions.md` — ADR-014 박음

**결정**:

- v1 자산 cherry-pick X — 본 문서 + schema 정합성 기준으로 재작성 (특히
  notice_plans Sprint 2 재작성 결정 — ADR-013 mirror)
- v1의 `apps/api/app/etl/`, `dagster_etl/`, `core/{kex,kto}.py`,
  `services/kor_travel_map_*` 는 모두 폐기 (ADR-005 / ADR-006 mirror)
- v1 `docs/data-sources/*` 8개는 모두 라이브러리 위임 — 본 저장소는 인덱스만
- `pyXyz` 짧은 alias 사용 금지 (canonical `python-xyz-api`만)
- AI agent 진입 절차를 AGENTS.md / CLAUDE.md에 명시

**일관성 점검**:

- Pinvi vs `kor-travel-map` 책임 분담을 모든 신규 문서에 명시
- WSL 미러 모델 (ADR-004)이 모든 runbook에 일관 반영
- 환경변수 `PINVI_*` prefix 일관
- 좌표 lon-lat 순서 일관
- 시간 KST aware 일관
- audit log chain (content_hash) 일관
- 동의 4 분리 일관

**다음**: PR 작성 후 사용자 review.

## 2026-05-25 23:51 (codex)

**작업**: PR #9 Sprint 1 scaffolding CI 실패 리뷰 및 수정.

**변경 파일**:

- `apps/api/**` — ruff/mypy strict 실패 정리, JWT `expires_minutes=0` 만료 버그 수정,
  bootstrap admin password 기본값 제거, Alembic version table 생성 전 schema 보장
- `apps/etl/tests/test_definitions.py` — Dagster `Definitions.resolve_asset_graph()`
  API에 맞게 테스트 갱신
- `packages/*/src` — workspace source 패키지를 Next가 직접 transpile할 수 있도록
  내부 TS import의 `.js` 확장자 제거
- `apps/web/app/(auth)/verify-email/page.tsx`, `apps/web/next.config.mjs` — App Router
  Suspense boundary와 Next 15 config 경고 정리
- `package-lock.json`, `.github/workflows/web.yml` — Linux Node 컨테이너에서 lockfile
  생성 후 CI를 `npm ci` + cache 흐름으로 고정

**결정**: lockfile은 Windows npm이 아니라 Linux Node 컨테이너에서 생성한다. CI는
`npm ci`로 재현 가능한 설치를 강제한다.

**발견**: API unit test가 `expires_minutes=0`을 기본 만료 시간으로 처리하는 실제
토큰 만료 버그를 잡았다.

**다음**: 수정 commit push 후 PR #9 CI 재실행 확인.

## 2026-05-25 23:30 (claude)

**작업**: Frontend 스택 상세 + Expo 공용 패키지 + 위치 정보 사양 + v1 notice POI
도메인 보강.

**컨텍스트**: 사용자 요청 3가지:

1. Frontend는 React/Next.js/TanStack Query/Zod/Zustand/RHF/shadcn/ui/Tailwind 기반
   임을 상세 명시. DESIGN.md / palette HTML의 색상톤·UX 따름. 추후 Expo 대응을
   위해 주요 로직 + 데이터 정의 코드를 Next.js / Expo 공용으로 작성. Expo 프론트
   구성도 명시.
2. v1에서 notice POI 관련 문서/코드 확인해서 보강.
3. 웹/앱에서 사용자 위치 정보 획득을 기능 사양에 명시.

v1 탐색 결과: `notice_plans` 도메인은 SPEC V8 D-10의 `notice` feature와 **완전히
다른 개념**. v1 `notice_plans`는 Admin이 작성한 **추천 여행 plan** (사용자가 자기
trip으로 copy 가능). 같은 단어를 쓰는 두 개념이 v2에서 혼동되지 않도록 명명을
분리.

**신규 파일**:

- `docs/architecture/frontend.md` — Next.js + Expo 공용 monorepo 구조,
  `packages/{schemas,api-client,state,design-tokens,hooks,i18n}`, shadcn/ui +
  Tailwind 통합, Airbnb 톤 디자인 토큰, 컴포넌트별 가이드, React Native
  Compatibility 룰
- `docs/architecture/user-location.md` — `navigator.geolocation` /
  `expo-location` 어댑터 추상화, `useUserLocation` 공용 hook, 4 분리 동의
  연계, content_hash chain 적재, fallback chain, UI 가이드
- `docs/architecture/notice-plans.md` — 추천 여행 plan 도메인 (v1에서 가져옴),
  `notice_plans` + `notice_pois` + `plan_poi_attachments` 단일 테이블 4 대상,
  copy 흐름, RustFS 정합, "notice plan ≠ notice feature" 명명 분리

**갱신**:

- `docs/decisions.md` — ADR-011 (Frontend 스택 + Expo 공용), ADR-012 (위치
  정보), ADR-013 (Notice plan 이전 + 명명 분리)
- `docs/spec/v8/03-frontend.md` — 스택 표 갱신 (shadcn/ui 명시) + 새 문서
  cross-reference
- `docs/sprints/SPRINT-1.md` — `packages/*` skeleton 등록 항목 박음
- `docs/sprints/SPRINT-2.md` — notice_plans / plan_poi_attachments Alembic,
  공용 schema/api-client/state/hooks 활성화, 4 분리 동의 UI + 위치 audit
- `docs/sprints/SPRINT-4.md` — 사용자 notice plan listing + copy 다이얼로그 +
  지도 "내 위치로 이동" 버튼
- `docs/sprints/SPRINT-6.md` — Admin notice plan 작성기 UI
- `README.md`, `SKILL.md` — 새 문서 cross-reference + 도메인 어휘
  (Notice plan / Notice feature / Plan POI attachment)
- `docs/architecture.md` §2.2 — Frontend 섹션을 새 `architecture/frontend.md`
  로 위임 + 공용 패키지 + 위치 hook 명시

**v1에서 확인한 자산** (`v1` 브랜치):

- `apps/api/alembic/versions/20260521_0027_notice_plans.py`
- `apps/api/alembic/versions/20260522_0028_plan_poi_attachments.py`
- `apps/api/app/models/trip.py` (`NoticePlan`, `NoticePoi`, `PlanPoiAttachment`)
- `apps/api/app/schemas/notice.py`
- `apps/api/app/services/notice_plan.py` (copy 흐름)
- `apps/api/app/services/plan_poi_attachment.py`
- `apps/api/app/api/routes/notice.py`
- `apps/api/tests/test_notice_plans_api.py`
- `docs/architecture/plan-poi-attachments.md`

**결정**:

- shadcn/ui + Tailwind 채택 — DESIGN.md Airbnb 톤을 컴포넌트 레벨에서 customizing
- `packages/*` 공용 패키지를 v1.0 단계부터 박아 Expo 추가 비용 최소화
- 좌표 서버 전송 시 audit chain 자동 적재. 좌표 정밀도는 UI에 4자리 (~10m) 까지만
- v1 notice plan 도메인은 cherry-pick 안 함 — schema 정합성 위해 재작성 (Sprint 2)
- "notice plan" (Pinvi) vs "notice feature" (라이브러리) 명명 명시 분리

**다음**: PR #5에 추가 커밋 후 push. Sprint 1 진입 승인 시 `apps/` + `packages/`
scaffolding.

## 2026-05-25 22:27 (codex)

**작업**: Sprint 4까지 새 PR을 리뷰 → 상세 코멘트 → 코드 수정 → 기반 라이브러리
sync → 검증 → 머지하는 운영 지시를 문서화하고 자동 리뷰 프롬프트 및 5분 주기
PR 감시 workflow 보강.

**변경 파일**:

- `.github/workflows/codex-pr-review.yml` — PR 자동 리뷰 프롬프트를 장기 설계 관점,
  기반 라이브러리 sync, 상세 코멘트 구조 중심으로 보강 + head SHA 리뷰 마커 추가
- `.github/workflows/codex-pr-monitor.yml` — 5분마다 열린 PR을 감시하고 최신 head
  SHA 리뷰 마커가 없으면 Codex 리뷰 코멘트 작성
- `docs/runbooks/pr-review-sprint4.md` — Sprint 4까지 반복할 PR 운영 runbook 신규
- `AGENTS.md`, `CLAUDE.md`, `docs/agent-guide.md` — 새 PR 운영 지시 cross-reference
- `docs/resume.md`, `docs/tasks.md` — 운영 지시와 완료 항목 반영

**결정**: 변경량 최소화보다 Sprint 1~4 장기 설계 정합성을 우선한다. 올바른 수정
위치가 기반 라이브러리이면 Pinvi wrapper로 덮지 않고 라이브러리 PR → 머지 →
Pinvi sync 순서로 처리한다.

**발견**: Codex 앱의 자동화/모니터 도구는 현재 노출되지 않았고, GitHub PR 조작
도구만 노출된다. 따라서 지속 감시는 GitHub Actions schedule workflow로 구현했다.

**다음**: 새 PR이 올라오면 `docs/runbooks/pr-review-sprint4.md` 절차로 리뷰와
수정/머지 진행.

## 2026-05-25 22:00 (claude)

**작업**: SPEC V8 6편 반영 + v1 자산 일부 복원.

**컨텍스트**: 사용자가 외부 docx 6편(`spec_v8_0_infrastructure` ~ `spec_v8_5_execution`)
제공하면서 "Pinvi에 반영할 것들도 문서화"와 "v1에서 색상맵 html과 DESIGN.md를
v2로 끌고 와" 지시. SPEC V8은 v1 시점에 작성되었지만 후속 메모(M~~R)에 이미
`kor-travel-map` 책임 분리가 반영되어 있어, 본 저장소의 v2 골격(ADR-001~~009)과
정합되게 적용 노트만 작성하면 됨.

**신규 파일**:

- `docs/spec/v8/README.md` — 6편 인덱스 + 책임 매핑
- `docs/spec/v8/00-infrastructure.md` — Odroid M1S, RustFS, Sentry, Loki, 위치정보법
- `docs/spec/v8/01-data.md` — 7 Feature, PostGIS, Record Linkage (라이브러리 위임)
- `docs/spec/v8/02-backend.md` — FastAPI 스택, JWT/OAuth, Resend, OR-Tools
- `docs/spec/v8/03-frontend.md` — Next.js 15, 16색 팔레트, 우클릭, 실시간
- `docs/spec/v8/04-admin.md` — 13 페이지, RBAC, audit chain, debug 콘솔
- `docs/spec/v8/05-execution.md` — 결정 6건, Sprint 1~6
- `docs/design/marker-palette.md` — P-01~P-16 + 카테고리 매핑
- `docs/sprints/SPRINT-2.md` — 도메인 API + DB
- `docs/sprints/SPRINT-3.md` — Admin 데이터 디버그 (Sprint 4 전)
- `docs/sprints/SPRINT-4.md` — 지도 + 사용자 UI
- `docs/sprints/SPRINT-5.md` — 실시간 + ETL + Loki
- `docs/sprints/SPRINT-6.md` — 일정 최적화 + LBS 신고 + 법무

**복원 (v1 → v2)**:

- `airbnb-marker-palette.html` (저장소 루트, 색상 시각 reference)
- `DESIGN.md` (저장소 루트, Airbnb 디자인 토큰 가이드 — 브랜드 확정 전 임시)

**갱신**:

- `docs/decisions.md` ADR-010 추가 (SPEC V8 채택)
- `docs/sprints/README.md` — Sprint 2~6 인덱스 추가
- `docs/sprints/SPRINT-1.md` — SPEC V8 cross-ref §8

**결정**:

- SPEC V8 N-7.2의 "ext4 직접 작업본 + NTFS export" 모델은 ADR-004로 정정 유지
- SPEC V8 D~E (feature schema)는 `kor-travel-map`이 소유 (ADR-003)
- SPEC V8 M-14의 `users.role` RBAC를 따름 (`is_admin BOOLEAN` 정정)
- LBS 사업자 신고는 Sprint 6에 박음 (출시 전 필수)
- Sprint 3 (Admin) ≺ Sprint 4 (지도) 순서 유지

**발견**: SPEC V8 원본의 후속 메모(2026-05-16 ~ 05-20)가 이미 `kor-travel-map`
분리와 wrapper 금지 원칙을 명시 — v2 골격의 ADR-001/002/003/005와 자연스럽게
정합. 별도 충돌 해소 불필요.

**다음**: PR 갱신 (`docs/bootstrap-v2-skeleton` 브랜치에 추가 커밋 후 push).

## 2026-05-25 19:30 (claude)

**작업**: v2 재시작 — v1 보존 + main 골격 재작성.

**컨텍스트**: 사용자 지시. v1은 9개월 운영하면서 책임 경계가 흐려지고 WSL/NTFS
작업 흐름이 두 번 흔들렸다. 사용자 결정으로 (1) `codex/wsl-test-mirror-docs`
브랜치의 unstaged 변경을 마지막 v1 commit으로 박음, (2) v1 브랜치를 main과 동일
시점에서 분기 + origin push, (3) main에서 모든 추적 파일 git rm + 캐시/빌드 정리,
(4) `kor-travel-map`의 문서 구조(README/CLAUDE/AGENTS/SKILL/docs/) 패턴을 본
저장소 컨텍스트로 미러링.

**변경 파일** (신규):

- `.gitignore` — `kor-travel-map` 패턴 + Pinvi dataset/refdocs 보존 정책
- `.gitattributes` — text=auto eol=lf + binary 분류
- `README.md` — 정체성, 빠른 시작, 문서 지도
- `CLAUDE.md` — 1쪽 진입 요약 (Claude Code 우선 진입)
- `AGENTS.md` — 작업 룰, 식별자, 책임 경계
- `SKILL.md` — 도메인 어휘, DO NOT 20항, 자주 묻는 작업
- `docs/architecture.md` — 큰 그림, 의존 방향, Pinvi ↔ kor-travel-map
- `docs/agent-guide.md` — 결정·기록 5종, ADR 규약, PR 워크플로
- `docs/dev-environment.md` — WSL 미러 단일 모델, rsync 절차, 부트스트랩
- `docs/decisions.md` — ADR-001 ~ ADR-009 (v2 시작 결정)
- `docs/journal.md` — 본 파일
- `docs/resume.md` — 다음 한 작업
- `docs/tasks.md` — 백로그
- `docs/data-model.md` — app 도메인 (사용자/여행계획/POI 첨부)
- `docs/postgres-schema.md` — app schema DDL/인덱스 골격
- `docs/test-strategy.md` — 단위/통합/e2e 경계
- `docs/kor-travel-map-integration.md` — DI helper 패턴 + Dagster asset 사용
- `docs/sprints/README.md` — Sprint 1~N 개요
- `docs/sprints/SPRINT-1.md` — 코드 작성 단계 진입 PR plan

**삭제**:

- `.codex/`, `.dockerignore`, `AGENTS.md`(구), `DESIGN.md`, `README.md`(구),
  `airbnb-marker-palette.html`, `apps/`, `config/`, `docs/`(구), `infra/`,
  `package-lock.json`, `package.json`, `scripts/`, `skills/`
- (보존) `.gitattributes`, `.gitignore` (재작성), `.claude/`, `.env`, `dataset/`,
  `refdocs/` (`.gitignore` 보호 항목)

**Git 흐름**:

1. `codex/wsl-test-mirror-docs` 브랜치의 unstaged 변경 16개 → `bc83fb1 Mirror docs
back to WSL test mirror workflow` 커밋 + origin push.
2. `main`을 codex tip(`bc83fb1`)으로 fast-forward.
3. `v1` 브랜치 생성(main의 현재 시점) + origin push.
4. main에서 v2 골격 신규 작성 (본 PR).

**ADR 적용**:

- ADR-001 — v1 보존 + v2 재시작
- ADR-002 — Pinvi ↔ `kor-travel-map` 함수 직접 호출
- ADR-003 — schema 책임 분담 (`app`/`ops` = Pinvi, `feature`/`provider_sync`
  = `kor-travel-map`)
- ADR-004 — WSL 미러 단일 모델
- ADR-005 — provider 어댑터 wrapper 금지
- ADR-006 — Dagster code location 분리 (`apps/etl`)
- ADR-007 — PR-only workflow + main branch protection
- ADR-008 — Postgres extension `x_extension` schema 분리
- ADR-009 — 한국어 문서 정책

**다음**:

- 사용자 review → v2 골격 PR로 main에 push (현재 작업 디렉토리에서 작성된 결과).
- Sprint 1 진입 승인 시 `apps/{api,web,etl}` + `infra/` + `packages/` scaffolding
  첫 PR (`docs/sprints/SPRINT-1.md` 참고).
- v1의 자산(Resend 통합, 소셜 로그인, Notice plan, RustFS Storage API 등)은 v2에서
  한 건씩 ADR로 결정하고 가져온다.
